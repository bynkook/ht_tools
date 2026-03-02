from django.conf import settings
from django.contrib.auth.models import User
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase


@override_settings(ADMIN_SIGNUP_KEY='test-signup-key')
class SignUpViewTests(APITestCase):
    # 회원가입 API 엔드포인트
    signup_url = '/api/auth/signup/'

    def _payload(self, **overrides):
        # 기본적으로 정책을 만족하는 정상 요청 페이로드
        payload = {
            'username': 'tester1',
            'password': 'pass1234!',
            'email': 'tester1@samsung.com',
            'auth_key': settings.ADMIN_SIGNUP_KEY,
            'recovery_pin': '123456',
        }
        payload.update(overrides)
        return payload

    def test_signup_allows_samsung_domain_email(self):
        # @samsung.com 도메인은 가입 허용(201)되어야 함
        response = self.client.post(self.signup_url, self._payload(), format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(username='tester1').exists())

    def test_signup_rejects_non_samsung_domain_email(self):
        # 타 도메인 이메일은 가입 거부(400)되어야 함
        response = self.client.post(
            self.signup_url,
            self._payload(email='tester1@gmail.com'),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data.get('error'), 'Only @samsung.com email addresses are allowed.')
        self.assertFalse(User.objects.filter(username='tester1').exists())

    def test_signup_normalizes_email_and_allows_case_insensitive_domain(self):
        # 공백/대소문자가 섞여도 normalize 후 samsung.com이면 허용되어야 함
        response = self.client.post(
            self.signup_url,
            self._payload(email='  Tester1@SAMSUNG.COM  '),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created_user = User.objects.get(username='tester1')
        self.assertEqual(created_user.email, 'tester1@samsung.com')
