"""
External API Adapters Package
外部 API 适配器 - HTTP 客户端
"""

from backend.adapters.external.http_client import (
    HTTPMethod,
    HTTPRequest,
    HTTPResponse,
    APIEndpoint,
    HTTPClientAdapter,
    http_client,
    init_http_client,
)

__all__ = [
    "HTTPMethod",
    "HTTPRequest",
    "HTTPResponse",
    "APIEndpoint",
    "HTTPClientAdapter",
    "http_client",
    "init_http_client",
]
