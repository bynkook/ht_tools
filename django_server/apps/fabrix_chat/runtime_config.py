import logging
import os

import httpx
from django.conf import settings
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import APIException

logger = logging.getLogger(__name__)

DEFAULT_AI_GATEWAY_BASE_URL = 'http://127.0.0.1:8001'
RUNTIME_CONFIG_PATH = '/chat-messages/runtime-config'
RUNTIME_CONFIG_TIMEOUT_SECONDS = 5.0
RUNTIME_CONFIG_REQUIRED_KEYS = {
    'mode',
    'requires_model_selection',
    'supports_external_llm',
}


class ChatRuntimeContractUnavailable(APIException):
    status_code = 503
    default_detail = 'FabriX Chat runtime contract is unavailable.'
    default_code = 'chat_runtime_contract_unavailable'


def _get_runtime_contract_url():
    base_url = os.getenv(
        'FABRIX_AI_GATEWAY_BASE_URL',
        DEFAULT_AI_GATEWAY_BASE_URL,
    ).rstrip('/')
    return f'{base_url}{RUNTIME_CONFIG_PATH}'


def _build_authorization_header(request):
    if request is None:
        raise ChatRuntimeContractUnavailable('Runtime contract lookup requires request context.')

    authorization = request.headers.get('Authorization', '').strip()
    if authorization:
        return {'Authorization': authorization}

    if getattr(request.user, 'is_authenticated', False):
        token = Token.objects.filter(user=request.user).values_list('key', flat=True).first()
        if token:
            return {'Authorization': f'Token {token}'}

    raise ChatRuntimeContractUnavailable('Runtime contract lookup requires token-authenticated request.')


def _request_runtime_contract(headers):
    url = _get_runtime_contract_url()
    client = getattr(settings, 'SHARED_HTTP_CLIENT', None)

    try:
        if client is None:
            with httpx.Client(timeout=RUNTIME_CONFIG_TIMEOUT_SECONDS) as new_client:
                response = new_client.get(url, headers=headers)
        else:
            response = client.get(
                url,
                headers=headers,
                timeout=RUNTIME_CONFIG_TIMEOUT_SECONDS,
            )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.warning(
            'Runtime contract request failed with status %s: %s',
            exc.response.status_code,
            url,
        )
        raise ChatRuntimeContractUnavailable('FabriX Chat runtime contract request failed.') from exc
    except httpx.HTTPError as exc:
        logger.warning('Runtime contract request failed: %s', exc)
        raise ChatRuntimeContractUnavailable('FabriX Chat runtime contract request failed.') from exc

    try:
        payload = response.json()
    except ValueError as exc:
        logger.warning('Runtime contract response is not valid JSON: %s', url)
        raise ChatRuntimeContractUnavailable('FabriX Chat runtime contract response is invalid.') from exc

    if not isinstance(payload, dict) or not RUNTIME_CONFIG_REQUIRED_KEYS.issubset(payload.keys()):
        logger.warning('Runtime contract response is invalid: %s', payload)
        raise ChatRuntimeContractUnavailable('FabriX Chat runtime contract response is invalid.')

    return payload


def get_chat_runtime_config(*, request):
    headers = _build_authorization_header(request)
    return _request_runtime_contract(headers)
