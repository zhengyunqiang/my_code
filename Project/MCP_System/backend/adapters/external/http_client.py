"""
External HTTP Client Adapter
外部 HTTP 客户端适配器 - 调用外部 API
"""

import asyncio
import json
from typing import Any, Dict, Optional, List, Union
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

import httpx

from backend.core.logging import get_logger
from backend.core.exceptions import MCPError

logger = get_logger(__name__)


class HTTPMethod(str, Enum):
    """HTTP 方法"""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


@dataclass
class HTTPRequest:
    """HTTP 请求"""
    url: str
    method: HTTPMethod = HTTPMethod.GET
    headers: Dict[str, str] = field(default_factory=dict)
    params: Dict[str, Any] = field(default_factory=dict)
    json_data: Optional[Dict[str, Any]] = None
    data: Optional[Any] = None
    timeout: float = 30.0
    follow_redirects: bool = True


@dataclass
class HTTPResponse:
    """HTTP 响应"""
    status_code: int
    headers: Dict[str, str]
    content: bytes
    text: str
    json_data: Optional[Dict[str, Any]] = None
    elapsed_ms: float = 0
    success: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "status_code": self.status_code,
            "headers": self.headers,
            "content": self.content.decode("utf-8", errors="ignore"),
            "json": self.json_data,
            "elapsed_ms": self.elapsed_ms,
            "success": self.success,
        }


@dataclass
class APIEndpoint:
    """API 端点定义"""
    name: str
    base_url: str
    endpoint: str = ""
    method: HTTPMethod = HTTPMethod.GET
    headers: Dict[str, str] = field(default_factory=dict)
    timeout: float = 30.0
    requires_auth: bool = False
    auth_type: str = "bearer"  # bearer, api_key, basic
    auth_location: str = "header"  # header, query


class HTTPClientAdapter:
    """
    HTTP 客户端适配器

    提供异步 HTTP 请求功能
    """

    def __init__(
        self,
        timeout: float = 30.0,
        max_connections: int = 100,
        max_keepalive_connections: int = 20,
    ):
        """
        初始化 HTTP 客户端

        Args:
            timeout: 默认超时时间
            max_connections: 最大连接数
            max_keepalive_connections: 最大保持连接数
        """
        self._client: Optional[httpx.AsyncClient] = None
        self._timeout = timeout
        self._max_connections = max_connections
        self._max_keepalive_connections = max_keepalive_connections

        # API 端点注册表
        self._endpoints: Dict[str, APIEndpoint] = {}

    async def start(self) -> None:
        """启动 HTTP 客户端"""
        limits = httpx.Limits(
            max_connections=self._max_connections,
            max_keepalive_connections=self._max_keepalive_connections,
        )

        self._client = httpx.AsyncClient(
            timeout=self._timeout,
            limits=limits,
            follow_redirects=True,
        )

        logger.info("HTTP client started")

    async def stop(self) -> None:
        """停止 HTTP 客户端"""
        if self._client:
            await self._client.aclose()
            logger.info("HTTP client stopped")

    def register_endpoint(self, endpoint: APIEndpoint) -> None:
        """
        注册 API 端点

        Args:
            endpoint: API 端点定义
        """
        self._endpoints[endpoint.name] = endpoint
        logger.info(f"Registered API endpoint: {endpoint.name}")

    def get_endpoint(self, name: str) -> Optional[APIEndpoint]:
        """
        获取 API 端点

        Args:
            name: 端点名称

        Returns:
            APIEndpoint 或 None
        """
        return self._endpoints.get(name)

    async def request(
        self,
        request: HTTPRequest,
        auth_token: Optional[str] = None,
    ) -> HTTPResponse:
        """
        发送 HTTP 请求

        Args:
            request: HTTP 请求
            auth_token: 认证令牌

        Returns:
            HTTP 响应
        """
        if self._client is None:
            raise RuntimeError("HTTP client not started")

        start_time = datetime.now(timezone.utc)

        try:
            # 构建请求参数
            request_kwargs = {
                "method": request.method.value,
                "url": request.url,
                "params": request.params,
                "headers": request.headers.copy(),
                "timeout": request.timeout,
                "follow_redirects": request.follow_redirects,
            }

            # 添加请求体
            if request.json_data:
                request_kwargs["json"] = request.json_data
            elif request.data is not None:
                request_kwargs["content"] = request.data

            # 添加认证
            if auth_token:
                request_kwargs["headers"]["Authorization"] = f"Bearer {auth_token}"

            # 发送请求
            response = await self._client.request(**request_kwargs)

            # 计算耗时
            elapsed_ms = (
                datetime.now(timezone.utc) - start_time
            ).total_seconds() * 1000

            # 解析响应
            content = response.content
            text = response.text
            json_data = None

            try:
                json_data = response.json()
            except (json.JSONDecodeError, ValueError):
                pass

            return HTTPResponse(
                status_code=response.status_code,
                headers=dict(response.headers),
                content=content,
                text=text,
                json_data=json_data,
                elapsed_ms=elapsed_ms,
                success=response.status_code < 400,
            )

        except httpx.TimeoutException as e:
            logger.error(f"HTTP request timeout: {request.url}")
            raise MCPError(
                code=5000,
                message=f"Request timeout: {request.url}",
                details={"timeout": request.timeout},
            )
        except httpx.HTTPError as e:
            logger.error(f"HTTP request error: {e}")
            raise MCPError(
                code=6003,
                message=f"HTTP error: {str(e)}",
                details={"url": request.url},
            )

    async def call_endpoint(
        self,
        endpoint_name: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        auth_token: Optional[str] = None,
    ) -> HTTPResponse:
        """
        调用已注册的 API 端点

        Args:
            endpoint_name: 端点名称
            params: 查询参数
            json_data: JSON 数据
            auth_token: 认证令牌

        Returns:
            HTTP 响应
        """
        endpoint = self.get_endpoint(endpoint_name)
        if endpoint is None:
            raise MCPError(
                code=5000,
                message=f"Endpoint not found: {endpoint_name}",
            )

        # 构建完整 URL
        url = f"{endpoint.base_url.rstrip('/')}/{endpoint.endpoint.lstrip('/')}"

        # 构建请求
        request = HTTPRequest(
            url=url,
            method=endpoint.method,
            headers=endpoint.headers.copy(),
            params=params or {},
            json_data=json_data,
            timeout=endpoint.timeout,
        )

        # 添加认证
        if endpoint.requires_auth and auth_token:
            if endpoint.auth_type == "bearer":
                request.headers["Authorization"] = f"Bearer {auth_token}"
            elif endpoint.auth_type == "api_key":
                if endpoint.auth_location == "header":
                    request.headers["X-API-Key"] = auth_token
                else:  # query
                    request.params["api_key"] = auth_token

        return await self.request(request)

    async def get(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> HTTPResponse:
        """发送 GET 请求"""
        request = HTTPRequest(
            url=url,
            method=HTTPMethod.GET,
            params=params or {},
            headers=headers or {},
        )
        return await self.request(request)

    async def post(
        self,
        url: str,
        json_data: Optional[Dict[str, Any]] = None,
        data: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> HTTPResponse:
        """发送 POST 请求"""
        request = HTTPRequest(
            url=url,
            method=HTTPMethod.POST,
            json_data=json_data,
            data=data,
            headers=headers or {},
        )
        return await self.request(request)


# 全局 HTTP 客户端实例
http_client: Optional[HTTPClientAdapter] = None


async def init_http_client(
    timeout: float = 30.0,
    max_connections: int = 100,
) -> HTTPClientAdapter:
    """
    初始化 HTTP 客户端

    Args:
        timeout: 默认超时时间
        max_connections: 最大连接数

    Returns:
        HTTPClientAdapter 实例
    """
    global http_client
    http_client = HTTPClientAdapter(
        timeout=timeout,
        max_connections=max_connections,
    )
    await http_client.start()
    return http_client


__all__ = [
    "HTTPMethod",
    "HTTPRequest",
    "HTTPResponse",
    "APIEndpoint",
    "HTTPClientAdapter",
    "http_client",
    "init_http_client",
]
