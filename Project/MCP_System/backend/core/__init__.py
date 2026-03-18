"""
MCP System Core Module
核心模块 - 日志、异常、工具函数
"""

from backend.core.logging import get_logger, logger
from backend.core.exceptions import (
    MCPError,
    ErrorCode,
    InvalidRequestError,
    MethodNotFoundError,
    InvalidParamsError,
    UnauthorizedError,
    ForbiddenError,
    InvalidTokenError,
    TokenExpiredError,
    InvalidAPIKey,
    APIKeyExpiredError,
    RateLimitError,
    QuotaExceededError,
    PromptInjectionError,
    ToolNotFoundError,
    ToolExecutionError,
    ToolTimeoutError,
    ResourceNotFoundError,
    ResourceAccessDeniedError,
    SchemaValidationError,
    TypeValidationError,
    create_error_response,
    handle_exception,
)

__all__ = [
    # Logging
    "get_logger",
    "logger",
    # Exceptions
    "MCPError",
    "ErrorCode",
    "InvalidRequestError",
    "MethodNotFoundError",
    "InvalidParamsError",
    "UnauthorizedError",
    "ForbiddenError",
    "InvalidTokenError",
    "TokenExpiredError",
    "InvalidAPIKey",
    "APIKeyExpiredError",
    "RateLimitError",
    "QuotaExceededError",
    "PromptInjectionError",
    "ToolNotFoundError",
    "ToolExecutionError",
    "ToolTimeoutError",
    "ResourceNotFoundError",
    "ResourceAccessDeniedError",
    "SchemaValidationError",
    "TypeValidationError",
    "create_error_response",
    "handle_exception",
]
