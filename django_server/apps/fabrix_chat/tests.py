from unittest.mock import patch

from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from .runtime_config import ChatRuntimeContractUnavailable


class ChatRuntimeContractTests(APITestCase):
    runtime_config_url = '/api/chat/runtime-config/'
    session_list_url = '/api/chat/sessions/'

    def setUp(self):
        self.user = User.objects.create_user(
            username='chat-runtime-user',
            password='password123',
        )
        token, _ = Token.objects.get_or_create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

    @patch(
        'apps.fabrix_chat.runtime_config._request_runtime_contract',
        return_value={
            'mode': 'mcp_test',
            'requires_model_selection': False,
            'supports_external_llm': False,
        },
    )
    def test_runtime_config_view_proxies_fastapi_contract(self, mock_request_runtime_contract):
        response = self.client.get(self.runtime_config_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data,
            {
                'mode': 'mcp_test',
                'requires_model_selection': False,
                'supports_external_llm': False,
            },
        )
        headers = mock_request_runtime_contract.call_args.args[0]
        self.assertIn('Authorization', headers)
        self.assertTrue(headers['Authorization'].startswith('Token '))

    @patch(
        'apps.fabrix_chat.runtime_config._request_runtime_contract',
        return_value={
            'mode': 'normal',
            'requires_model_selection': True,
            'supports_external_llm': True,
        },
    )
    def test_session_create_requires_model_id_in_normal_mode(self, _mock_request_runtime_contract):
        response = self.client.post(
            self.session_list_url,
            {'title': 'Normal mode session'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['model_id'][0], 'model_id is required in normal mode')

    @patch(
        'apps.fabrix_chat.runtime_config._request_runtime_contract',
        return_value={
            'mode': 'mcp_test',
            'requires_model_selection': False,
            'supports_external_llm': False,
        },
    )
    def test_session_create_allows_missing_model_id_in_test_mode(self, _mock_request_runtime_contract):
        response = self.client.post(
            self.session_list_url,
            {'title': 'Test mode session'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(response.data['model_id'])

    @patch(
        'apps.fabrix_chat.runtime_config._request_runtime_contract',
        side_effect=ChatRuntimeContractUnavailable('runtime contract down'),
    )
    def test_session_create_returns_503_when_runtime_contract_lookup_fails(self, _mock_request_runtime_contract):
        response = self.client.post(
            self.session_list_url,
            {'title': 'Unavailable runtime contract'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
