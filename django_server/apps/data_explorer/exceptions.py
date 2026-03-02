"""
Data Explorer Custom Exceptions
===============================
Structured exception classes for better error handling and user-friendly messages.

Usage:
    from apps.data_explorer.exceptions import QueryTimeoutError, SessionExpiredError

These exceptions are caught in views.py and converted to appropriate HTTP responses.
"""


class DataExplorerBaseError(Exception):
    """Base exception for Data Explorer errors."""
    
    # Default HTTP status code
    status_code = 500
    # Default user-friendly message
    default_message = "데이터 탐색기에서 오류가 발생했습니다."
    
    def __init__(self, message=None, detail=None):
        """
        Args:
            message: User-friendly error message (shown to user)
            detail: Technical detail (logged, shown only in DEBUG mode)
        """
        self.message = message or self.default_message
        self.detail = detail
        super().__init__(self.message)
    
    def to_response_dict(self, include_detail=False):
        """Convert to dictionary for API response."""
        result = {"error": self.message}
        if include_detail and self.detail:
            result["detail"] = self.detail
        return result


class SessionExpiredError(DataExplorerBaseError):
    """Raised when DuckDB session/file is no longer available."""
    
    status_code = 404
    default_message = "세션이 만료되었습니다. 데이터셋을 다시 로드해주세요."


class QueryValidationError(DataExplorerBaseError):
    """Raised when SQL query fails validation (e.g., write operation attempt)."""
    
    status_code = 400
    default_message = "허용되지 않는 쿼리입니다."


class DSLParsingError(DataExplorerBaseError):
    """Raised when gw-dsl-parser fails to transpile payload."""
    
    status_code = 400
    default_message = "쿼리 변환에 실패했습니다. 데이터 형식을 확인해주세요."


class DataLoadError(DataExplorerBaseError):
    """Raised when data loading into DuckDB fails."""
    
    status_code = 500
    default_message = "데이터 로드에 실패했습니다. 파일 형식을 확인해주세요."


class ConcurrencyError(DataExplorerBaseError):
    """Raised when concurrent access causes conflict."""
    
    status_code = 409
    default_message = "다른 작업이 진행 중입니다. 잠시 후 다시 시도해주세요."
