from rest_framework import status
from rest_framework.test import APITestCase
from django.urls import reverse
from django.contrib.auth.models import User
from unittest.mock import patch
from django.test import SimpleTestCase

from .serializers import ChatMessageSerializer


class ChatRuntimeContractTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='pass1234')
        self.client.force_authenticate(user=self.user)
        self.session_list_url = reverse('chat-session-list')
        self.runtime_config_url = reverse('chat-runtime-config')

    @patch('apps.fabrix_chat.views.get_chat_runtime_config')
    def test_runtime_config_view_proxies_fastapi_contract(self, mocked_contract):
        mocked_contract.return_value = {
            'mode': 'test',
            'requires_model_selection': False,
            'allow_empty_model_id': True,
        }

        response = self.client.get(self.runtime_config_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.json(),
            {
                'mode': 'test',
                'requires_model_selection': False,
                'allow_empty_model_id': True,
            },
        )

    @patch('apps.fabrix_chat.serializers.get_chat_runtime_config')
    def test_session_create_allows_missing_model_id_in_test_mode(self, mocked_contract):
        mocked_contract.return_value = {
            'mode': 'test',
            'requires_model_selection': False,
            'allow_empty_model_id': True,
        }

        response = self.client.post(
            self.session_list_url,
            {'title': 'Test Mode Session'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(response.data['model_id'])

    @patch('apps.fabrix_chat.serializers.get_chat_runtime_config')
    def test_session_create_requires_model_id_in_normal_mode(self, mocked_contract):
        mocked_contract.return_value = {
            'mode': 'normal',
            'requires_model_selection': True,
            'allow_empty_model_id': False,
        }

        response = self.client.post(
            self.session_list_url,
            {'title': 'Normal Mode Session'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['model_id'][0], 'model_id is required in normal mode')

    @patch('apps.fabrix_chat.views.get_chat_runtime_config')
    def test_session_create_returns_503_when_runtime_contract_lookup_fails(self, mocked_contract):
        mocked_contract.side_effect = RuntimeError('config unavailable')

        response = self.client.post(
            self.session_list_url,
            {'title': 'Unavailable runtime contract'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)


class ChatMessageMetadataContractTests(SimpleTestCase):
    def test_system_message_metadata_accepts_current_runtime_contract_shape(self):
        serializer = ChatMessageSerializer(
            data={
                'role': 'system',
                'content': 'Provider connection established.',
                'metadata': {
                    'kind': 'system_log',
                    'level': 'info',
                    'channel': 'mcp_test',
                    'title': 'Provider connect end',
                    'phase': 'provider_connect',
                    'provider': 'internal_docs',
                    'providerId': 'internal_docs',
                    'providerDisplayName': 'Internal Docs',
                    'tool': None,
                    'selectionReason': 'keyword rule matched',
                    'selectionRank': 1,
                    'candidateSummary': ['internal_docs.search_docs_rag'],
                    'partialFailure': None,
                    'requestId': 'turn-20260408-000000-000001',
                    'fingerprint': 'abc123',
                    'timestamp': '2026-04-08T09:43:00Z',
                    'persist': True,
                    'repeatCount': 1,
                    'suppressedCount': 0,
                    'rawSuppressed': False,
                    'rawSuppressedCount': 0,
                    'raw': {'tools': ['search_docs_rag']},
                },
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_system_message_metadata_rejects_unknown_keys(self):
        serializer = ChatMessageSerializer(
            data={
                'role': 'system',
                'content': 'Provider connection established.',
                'metadata': {
                    'kind': 'system_log',
                    'level': 'info',
                    'channel': 'mcp_test',
                    'phase': 'provider_connect',
                    'persist': True,
                    'unexpectedField': 'internal_docs',
                },
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn('unknown system metadata keys', str(serializer.errors))