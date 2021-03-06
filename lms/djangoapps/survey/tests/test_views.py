"""
Python tests for the Survey views
"""

from __future__ import absolute_import

import json
from collections import OrderedDict

import six
from django.test.client import Client
from django.urls import reverse

from student.tests.factories import UserFactory
from survey.models import SurveyAnswer, SurveyForm
from xmodule.modulestore.tests.django_utils import ModuleStoreTestCase
from xmodule.modulestore.tests.factories import CourseFactory


class SurveyViewsTests(ModuleStoreTestCase):
    """
    All tests for the views.py file
    """

    def setUp(self):
        """
        Set up the test data used in the specific tests
        """
        super(SurveyViewsTests, self).setUp()

        self.client = Client()

        # Create two accounts
        self.password = 'abc'
        self.student = UserFactory.create(username='student', email='student@test.com', password=self.password)

        self.test_survey_name = 'TestSurvey'
        self.test_form = '''
            <input name="field1" /><input name="field2" /><select name="ddl"><option>1</option></select>
            <textarea name="textarea" />
        '''

        self.student_answers = OrderedDict({
            u'field1': u'value1',
            u'field2': u'value2',
            u'ddl': u'1',
            u'textarea': u'textarea'
        })

        self.course = CourseFactory.create(
            display_name='Test Course',
            course_survey_required=True,
            course_survey_name=self.test_survey_name
        )

        self.survey = SurveyForm.create(self.test_survey_name, self.test_form)

        self.view_url = reverse('view_survey', args=[self.test_survey_name])
        self.postback_url = reverse('submit_answers', args=[self.test_survey_name])

        self.client.login(username=self.student.username, password=self.password)

    def test_unauthenticated_survey_view(self):
        """
        Asserts that an unauthenticated user cannot access a survey
        """
        anon_user = Client()

        resp = anon_user.get(self.view_url)
        self.assertEquals(resp.status_code, 302)

    def test_survey_not_found(self):
        """
        Asserts that if we ask for a Survey that does not exist, then we get a 302 redirect
        """
        resp = self.client.get(reverse('view_survey', args=['NonExisting']))
        self.assertEquals(resp.status_code, 302)

    def test_authenticated_survey_view(self):
        """
        Asserts that an authenticated user can see the survey
        """
        resp = self.client.get(self.view_url)
        self.assertEquals(resp.status_code, 200)

        # is the SurveyForm html present in the HTML response?
        self.assertIn(self.test_form, resp.content)

    def test_unauthenticated_survey_postback(self):
        """
        Asserts that an anonymous user cannot answer a survey
        """
        anon_user = Client()
        resp = anon_user.post(
            self.postback_url,
            self.student_answers
        )
        self.assertEquals(resp.status_code, 302)

    def test_survey_postback_to_nonexisting_survey(self):
        """
        Asserts that any attempts to post back to a non existing survey returns a 404
        """
        resp = self.client.post(
            reverse('submit_answers', args=['NonExisting']),
            self.student_answers
        )
        self.assertEquals(resp.status_code, 404)

    def test_survey_postback(self):
        """
        Asserts that a well formed postback of survey answers is properly stored in the
        database
        """
        resp = self.client.post(
            self.postback_url,
            self.student_answers
        )
        self.assertEquals(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertIn('redirect_url', data)

        answers = self.survey.get_answers(self.student)
        self.assertEquals(answers[self.student.id], self.student_answers)

    def test_strip_extra_fields(self):
        """
        Verify that any not expected field name in the post-back is not stored
        in the database
        """
        data = dict.copy(self.student_answers)

        data['csrfmiddlewaretoken'] = 'foo'
        data['_redirect_url'] = 'bar'
        data['course_id'] = six.text_type(self.course.id)

        resp = self.client.post(
            self.postback_url,
            data
        )
        self.assertEquals(resp.status_code, 200)
        answers = self.survey.get_answers(self.student)
        self.assertNotIn('csrfmiddlewaretoken', answers[self.student.id])
        self.assertNotIn('_redirect_url', answers[self.student.id])
        self.assertNotIn('course_id', answers[self.student.id])

        # however we want to make sure we persist the course_id
        answer_objs = SurveyAnswer.objects.filter(
            user=self.student,
            form=self.survey
        )

        for answer_obj in answer_objs:
            self.assertEquals(six.text_type(answer_obj.course_key), data['course_id'])

    def test_encoding_answers(self):
        """
        Verify that if some potentially harmful input data is sent, that is is properly HTML encoded
        """
        data = dict.copy(self.student_answers)

        data['field1'] = '<script type="javascript">alert("Deleting filesystem...")</script>'

        resp = self.client.post(
            self.postback_url,
            data
        )
        self.assertEquals(resp.status_code, 200)
        answers = self.survey.get_answers(self.student)
        self.assertEqual(
            '&lt;script type=&quot;javascript&quot;&gt;alert(&quot;Deleting filesystem...&quot;)&lt;/script&gt;',
            answers[self.student.id]['field1']
        )
