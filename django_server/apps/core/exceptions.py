import math

from rest_framework.exceptions import Throttled
from rest_framework.views import exception_handler as drf_exception_handler


def custom_exception_handler(exc, context):
    """DRF 기본 예외 처리 후 Throttled 예외에 Retry-After 헤더를 명시적으로 추가."""
    response = drf_exception_handler(exc, context)
    if response is not None and isinstance(exc, Throttled):
        wait = getattr(exc, 'wait', None)
        if wait is not None:
            response['Retry-After'] = str(math.ceil(wait))
    return response
