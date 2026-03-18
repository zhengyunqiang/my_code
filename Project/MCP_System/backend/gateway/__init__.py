"""
Gateway Layer Package
网关层 - 安全、认证、授权、流控
"""

from backend.gateway.auth import (
    AuthManager,
    APIKeyManager,
    AuthContext,
    auth_manager,
    api_key_manager,
)
from backend.gateway.authorization import (
    ResourceType,
    Action,
    Permission,
    Role,
    SystemRoles,
    RBACManager,
    rbac_manager,
)
from backend.gateway.sanitization import (
    SanitizationResult,
    InputSanitizer,
    input_sanitizer,
)
from backend.gateway.rate_limit import (
    RateLimiter,
    QuotaManager,
    rate_limiter,
    quota_manager,
    init_rate_limiting,
)
from backend.gateway.middleware import (
    extract_auth_context,
    require_auth,
    require_permission,
    check_rate_limit,
    check_quota,
    sanitize_input,
    SecurityMiddleware,
    require_authentication,
    require_permission as require_permission_decorator,
    sanitize_request,
)

__all__ = [
    # Auth
    "AuthManager",
    "APIKeyManager",
    "AuthContext",
    "auth_manager",
    "api_key_manager",
    # Authorization
    "ResourceType",
    "Action",
    "Permission",
    "Role",
    "SystemRoles",
    "RBACManager",
    "rbac_manager",
    # Sanitization
    "SanitizationResult",
    "InputSanitizer",
    "input_sanitizer",
    # Rate Limit
    "RateLimiter",
    "QuotaManager",
    "rate_limiter",
    "quota_manager",
    "init_rate_limiting",
    # Middleware
    "extract_auth_context",
    "require_auth",
    "require_permission",
    "check_rate_limit",
    "check_quota",
    "sanitize_input",
    "SecurityMiddleware",
    "require_authentication",
    "require_permission_decorator",
    "sanitize_request",
]
