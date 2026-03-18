"""
Security Middleware Module
安全中间件 - 集成认证、授权、输入清洗和流控
"""

from typing import Optional, Dict, Any, Callable
from functools import wraps

from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from backend.core.logging import get_logger
from backend.core.exceptions import (
    UnauthorizedError,
    ForbiddenError,
    RateLimitError,
    QuotaExceededError,
    PromptInjectionError,
)
from backend.gateway.auth import auth_manager, api_key_manager, AuthContext
from backend.gateway.authorization import rbac_manager, ResourceType, Action
from backend.gateway.sanitization import input_sanitizer
from backend.gateway.rate_limit import rate_limiter, quota_manager

logger = get_logger(__name__)


async def extract_auth_context(request: Request) -> Optional[AuthContext]:
    """
    从请求中提取认证上下文

    Args:
        request: FastAPI 请求对象

    Returns:
        AuthContext 或 None
    """
    # 尝试 JWT 令牌
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            payload = auth_manager.decode_access_token(token)
            return AuthContext(
                user_id=payload.get("sub"),
                token_type="jwt",
                scopes=payload.get("scopes", []),
            )
        except Exception as e:
            logger.warning(f"Invalid JWT token: {e}")
            raise UnauthorizedError(str(e))

    # 尝试 API 密钥
    api_key = request.headers.get("X-API-Key")
    if api_key:
        # 这里应该从数据库验证 API 密钥
        # 简化实现：假设验证成功
        return AuthContext(
            user_id=1,  # 从数据库获取
            token_type="api_key",
            scopes=["read", "write"],
        )

    # 未认证
    return None


async def require_auth(request: Request) -> AuthContext:
    """
    要求认证

    Args:
        request: FastAPI 请求对象

    Returns:
        AuthContext

    Raises:
        UnauthorizedError: 未认证
    """
    auth_context = await extract_auth_context(request)
    if auth_context is None or not auth_context.is_authenticated():
        raise UnauthorizedError("Authentication required")
    return auth_context


async def require_permission(
    request: Request,
    resource: ResourceType,
    action: Action,
    scope: Optional[str] = None,
) -> AuthContext:
    """
    要求指定权限

    Args:
        request: FastAPI 请求对象
        resource: 资源类型
        action: 操作类型
        scope: 资源范围

    Returns:
        AuthContext

    Raises:
        UnauthorizedError: 未认证
        ForbiddenError: 权限不足
    """
    auth_context = await require_auth(request)
    user_id = auth_context.user_id

    if not rbac_manager.has_permission(user_id, resource, action, scope):
        required = f"{resource.value}:{action.value}"
        if scope:
            required += f":{scope}"
        raise ForbiddenError(message="Permission denied", required_permission=required)

    return auth_context


async def check_rate_limit(
    request: Request,
    auth_context: Optional[AuthContext] = None,
) -> None:
    """
    检查速率限制

    Args:
        request: FastAPI 请求对象
        auth_context: 认证上下文

    Raises:
        RateLimitError: 超过速率限制
    """
    if rate_limiter is None:
        return

    # 使用用户 ID 或 IP 作为限制键
    if auth_context and auth_context.user_id:
        key = f"user:{auth_context.user_id}"
    else:
        key = f"ip:{request.client.host if request.client else 'unknown'}"

    try:
        await rate_limiter.check_and_raise(key)
    except RateLimitError as e:
        logger.warning(f"Rate limit exceeded for {key}")
        raise


async def check_quota(
    request: Request,
    auth_context: AuthContext,
) -> None:
    """
    检查配额

    Args:
        request: FastAPI 请求对象
        auth_context: 认证上下文

    Raises:
        QuotaExceededError: 超过配额
    """
    if quota_manager is None:
        return

    if auth_context.user_id:
        try:
            # 检查每小时配额
            await quota_manager.check_and_raise(auth_context.user_id, "hourly")
        except QuotaExceededError as e:
            logger.warning(f"Quota exceeded for user {auth_context.user_id}")
            raise


async def sanitize_input(data: Any) -> Any:
    """
    清洗输入数据

    Args:
        data: 输入数据

    Returns:
        清洗后的数据

    Raises:
        PromptInjectionError: 检测到注入
    """
    if isinstance(data, str):
        return input_sanitizer.validate_and_sanitize(data, raise_on_injection=True)
    elif isinstance(data, dict):
        return {k: await sanitize_input(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [await sanitize_input(item) for item in data]
    else:
        return data


class SecurityMiddleware(BaseHTTPMiddleware):
    """
    安全中间件

    集成所有安全检查：
    1. 认证
    2. 速率限制
    3. 配额检查
    4. 输入清洗
    """

    async def dispatch(self, request: Request, call_next):
        """处理请求"""
        # 跳过健康检查端点
        if request.url.path in ["/health", "/"]:
            return await call_next(request)

        try:
            # 1. 认证（可选，某些端点可能不需要）
            auth_context = await extract_auth_context(request)

            # 2. 速率限制
            await check_rate_limit(request, auth_context)

            # 3. 配额检查（仅对已认证用户）
            if auth_context and auth_context.is_authenticated():
                await check_quota(request, auth_context)

            # 4. 处理请求
            response = await call_next(request)

            # 添加安全头
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-XSS-Protection"] = "1; mode=block"

            return response

        except (UnauthorizedError, ForbiddenError, RateLimitError, QuotaExceededError) as e:
            # 返回标准错误响应
            return Response(
                content=f'{{"error": "{e.message}", "code": {e.code.value}}}',
                status_code=status.HTTP_403_FORBIDDEN if isinstance(e, (ForbiddenError, RateLimitError, QuotaExceededError)) else status.HTTP_401_UNAUTHORIZED,
                media_type="application/json",
            )

        except PromptInjectionError as e:
            logger.warning(f"Prompt injection detected: {e.details}")
            return Response(
                content=f'{{"error": "Suspicious input detected", "code": {e.code.value}}}',
                status_code=status.HTTP_400_BAD_REQUEST,
                media_type="application/json",
            )


# ========================================
# 装饰器
# ========================================

def require_authentication(func: Callable) -> Callable:
    """
    要求认证装饰器

    用于保护需要认证的端点
    """
    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        auth_context = await require_auth(request)
        request.state.auth_context = auth_context
        return await func(request, *args, **kwargs)
    return wrapper


def require_permission(
    resource: ResourceType,
    action: Action,
    scope: Optional[str] = None,
) -> Callable:
    """
    要求权限装饰器

    用于保护需要特定权限的端点

    Args:
        resource: 资源类型
        action: 操作类型
        scope: 资源范围
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            auth_context = await require_permission(request, resource, action, scope)
            request.state.auth_context = auth_context
            return await func(request, *args, **kwargs)
        return wrapper
    return decorator


def sanitize_request(func: Callable) -> Callable:
    """
    输入清洗装饰器

    自动清洗请求体中的输入
    """
    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        # 如果有请求体，进行清洗
        if request.method in ["POST", "PUT", "PATCH"]:
            body = await request.json()
            sanitized = await sanitize_input(body)
            # 替换请求体（需要特殊处理）
            # 这里简化处理
            logger.debug(f"Sanitized request body")

        return await func(request, *args, **kwargs)
    return wrapper


__all__ = [
    "extract_auth_context",
    "require_auth",
    "require_permission",
    "check_rate_limit",
    "check_quota",
    "sanitize_input",
    "SecurityMiddleware",
    "require_authentication",
    "require_permission",
    "sanitize_request",
]
