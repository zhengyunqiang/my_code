"""
MCP System Exception Handling
自定义异常类和错误处理框架
"""

from typing import Any, Dict, Optional, List
from enum import Enum
from dataclasses import dataclass, field


class ErrorCode(int, Enum):
    """错误码枚举"""

    # 通用错误 (1000-1999)
    UNKNOWN_ERROR = 1000
    INTERNAL_ERROR = 1001
    NOT_IMPLEMENTED = 1002

    # 协议错误 (2000-2999)
    INVALID_REQUEST = 2000
    METHOD_NOT_FOUND = 2001
    INVALID_PARAMS = 2002
    PARSE_ERROR = 2003

    # 认证授权错误 (3000-3999)
    UNAUTHORIZED = 3000
    FORBIDDEN = 3001
    INVALID_TOKEN = 3002
    TOKEN_EXPIRED = 3003
    INVALID_API_KEY = 3004
    API_KEY_EXPIRED = 3005

    # 安全错误 (4000-4999)
    RATE_LIMIT_EXCEEDED = 4000
    QUOTA_EXCEEDED = 4001
    SUSPICIOUS_INPUT = 4002
    PROMPT_INJECTION_DETECTED = 4003
    MALICIOUS_INPUT = 4004

    # 业务逻辑错误 (5000-5999)
    TOOL_NOT_FOUND = 5000
    TOOL_EXECUTION_FAILED = 5001
    TOOL_TIMEOUT = 5002
    TOOL_INVALID_ARGUMENTS = 5003
    RESOURCE_NOT_FOUND = 5004
    RESOURCE_ACCESS_DENIED = 5005
    PROMPT_NOT_FOUND = 5006
    PROMPT_RENDER_FAILED = 5007

    # 数据错误 (6000-6999)
    DATABASE_ERROR = 6000
    CACHE_ERROR = 6001
    STORAGE_ERROR = 6002
    EXTERNAL_API_ERROR = 6003

    # 验证错误 (7000-7999)
    VALIDATION_ERROR = 7000
    SCHEMA_MISMATCH = 7001
    TYPE_ERROR = 7002


@dataclass
class ErrorDetail:
    """错误详情"""

    code: ErrorCode
    message: str
    details: Optional[Dict[str, Any]] = None
    suggestion: Optional[str] = None
    stack_trace: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = {
            "code": self.code.value,
            "message": self.message,
        }
        if self.details:
            result["details"] = self.details
        if self.suggestion:
            result["suggestion"] = self.suggestion
        return result


class MCPError(Exception):
    """
    MCP 系统基础异常类
    所有自定义异常的父类
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        suggestion: Optional[str] = None,
    ):
        self.code = code
        self.message = message
        self.details = details
        self.suggestion = suggestion
        super().__init__(self.message)

    def to_error_detail(self, include_stack: bool = False) -> ErrorDetail:
        """转换为错误详情"""
        import traceback

        stack_trace = traceback.format_exc() if include_stack else None
        return ErrorDetail(
            code=self.code,
            message=self.message,
            details=self.details,
            suggestion=self.suggestion,
            stack_trace=stack_trace,
        )


# ========================================
# 协议层异常
# ========================================

class ProtocolError(MCPError):
    """协议层异常基类"""
    pass


class InvalidRequestError(ProtocolError):
    """无效请求错误"""

    def __init__(
        self,
        message: str = "Invalid request",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            code=ErrorCode.INVALID_REQUEST,
            message=message,
            details=details,
            suggestion="Please check your request format and parameters",
        )


class MethodNotFoundError(ProtocolError):
    """方法未找到错误"""

    def __init__(self, method: str):
        super().__init__(
            code=ErrorCode.METHOD_NOT_FOUND,
            message=f"Method '{method}' not found",
            details={"method": method},
            suggestion=f"Available methods: initialize, list_tools, call_tool, list_resources, read_resource",
        )


class InvalidParamsError(ProtocolError):
    """无效参数错误"""

    def __init__(
        self,
        message: str = "Invalid parameters",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            code=ErrorCode.INVALID_PARAMS,
            message=message,
            details=details,
            suggestion="Please check the parameter types and values",
        )


# ========================================
# 认证授权异常
# ========================================

class AuthError(MCPError):
    """认证授权异常基类"""
    pass


class UnauthorizedError(AuthError):
    """未授权错误"""

    def __init__(
        self,
        message: str = "Unauthorized",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            code=ErrorCode.UNAUTHORIZED,
            message=message,
            details=details,
            suggestion="Please provide valid authentication credentials",
        )


class ForbiddenError(AuthError):
    """禁止访问错误"""

    def __init__(
        self,
        message: str = "Forbidden",
        required_permission: Optional[str] = None,
    ):
        details = {"required_permission": required_permission} if required_permission else None
        super().__init__(
            code=ErrorCode.FORBIDDEN,
            message=message,
            details=details,
            suggestion="You don't have permission to perform this action",
        )


class InvalidTokenError(AuthError):
    """无效令牌错误"""

    def __init__(self, message: str = "Invalid token"):
        super().__init__(
            code=ErrorCode.INVALID_TOKEN,
            message=message,
            suggestion="Please provide a valid JWT token",
        )


class TokenExpiredError(AuthError):
    """令牌过期错误"""

    def __init__(self):
        super().__init__(
            code=ErrorCode.TOKEN_EXPIRED,
            message="Token has expired",
            suggestion="Please refresh your token",
        )


class InvalidAPIKey(AuthError):
    """无效 API 密钥错误"""

    def __init__(
        self,
        message: str = "Invalid API key",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            code=ErrorCode.INVALID_API_KEY,
            message=message,
            details=details,
            suggestion="Please provide a valid API key",
        )


class APIKeyExpiredError(AuthError):
    """API 密钥过期错误"""

    def __init__(self):
        super().__init__(
            code=ErrorCode.API_KEY_EXPIRED,
            message="API key has expired",
            suggestion="Please generate a new API key",
        )


# ========================================
# 安全层异常
# ========================================

class SecurityError(MCPError):
    """安全层异常基类"""
    pass


class RateLimitError(SecurityError):
    """速率限制错误"""

    def __init__(
        self,
        limit: int,
        window: int,
        retry_after: Optional[int] = None,
    ):
        super().__init__(
            code=ErrorCode.RATE_LIMIT_EXCEEDED,
            message=f"Rate limit exceeded: {limit} requests per {window} seconds",
            details={"limit": limit, "window": window, "retry_after": retry_after},
            suggestion=f"Please wait {retry_after or window} seconds before making another request",
        )


class QuotaExceededError(SecurityError):
    """配额超限错误"""

    def __init__(
        self,
        quota_type: str,
        current: int,
        limit: int,
        reset_time: Optional[str] = None,
    ):
        super().__init__(
            code=ErrorCode.QUOTA_EXCEEDED,
            message=f"{quota_type} quota exceeded: {current}/{limit}",
            details={
                "quota_type": quota_type,
                "current": current,
                "limit": limit,
                "reset_time": reset_time,
            },
            suggestion=f"Your quota will reset at {reset_time or 'the next billing period'}",
        )


class PromptInjectionError(SecurityError):
    """Prompt 注入检测错误"""

    def __init__(
        self,
        detected_patterns: List[str],
        input_source: str = "user_input",
    ):
        super().__init__(
            code=ErrorCode.PROMPT_INJECTION_DETECTED,
            message="Potential prompt injection detected",
            details={
                "detected_patterns": detected_patterns,
                "input_source": input_source,
            },
            suggestion="Please remove any instructions that attempt to override system behavior",
        )


# ========================================
# 业务逻辑层异常
# ========================================

class BusinessError(MCPError):
    """业务逻辑层异常基类"""
    pass


class ToolNotFoundError(BusinessError):
    """工具未找到错误"""

    def __init__(self, tool_name: str):
        super().__init__(
            code=ErrorCode.TOOL_NOT_FOUND,
            message=f"Tool '{tool_name}' not found",
            details={"tool_name": tool_name},
            suggestion=f"Please check the tool name using list_tools",
        )


class ToolExecutionError(BusinessError):
    """工具执行错误"""

    def __init__(
        self,
        tool_name: str,
        reason: str,
        original_error: Optional[str] = None,
    ):
        super().__init__(
            code=ErrorCode.TOOL_EXECUTION_FAILED,
            message=f"Tool '{tool_name}' execution failed: {reason}",
            details={
                "tool_name": tool_name,
                "reason": reason,
                "original_error": original_error,
            },
            suggestion="Please check the tool parameters and try again",
        )


class ToolTimeoutError(BusinessError):
    """工具超时错误"""

    def __init__(self, tool_name: str, timeout: int):
        super().__init__(
            code=ErrorCode.TOOL_TIMEOUT,
            message=f"Tool '{tool_name}' execution timed out after {timeout} seconds",
            details={"tool_name": tool_name, "timeout": timeout},
            suggestion="The operation may take longer than expected. Please try again later or contact support",
        )


class ResourceNotFoundError(BusinessError):
    """资源未找到错误"""

    def __init__(self, resource_uri: str):
        super().__init__(
            code=ErrorCode.RESOURCE_NOT_FOUND,
            message=f"Resource '{resource_uri}' not found",
            details={"resource_uri": resource_uri},
            suggestion="Please check the resource URI using list_resources",
        )


class ResourceAccessDeniedError(BusinessError):
    """资源访问拒绝错误"""

    def __init__(
        self,
        resource_uri: str,
        required_permission: str,
    ):
        super().__init__(
            code=ErrorCode.RESOURCE_ACCESS_DENIED,
            message=f"Access denied to resource '{resource_uri}'",
            details={
                "resource_uri": resource_uri,
                "required_permission": required_permission,
            },
            suggestion="You don't have permission to access this resource",
        )


# ========================================
# 验证层异常
# ========================================

class ValidationError(MCPError):
    """验证层异常基类"""
    pass


class SchemaValidationError(ValidationError):
    """Schema 验证错误"""

    def __init__(
        self,
        message: str,
        field_errors: Optional[Dict[str, str]] = None,
    ):
        super().__init__(
            code=ErrorCode.VALIDATION_ERROR,
            message=message,
            details={"field_errors": field_errors} if field_errors else None,
            suggestion="Please check the data format and required fields",
        )


class TypeValidationError(ValidationError):
    """类型验证错误"""

    def __init__(
        self,
        field: str,
        expected_type: str,
        actual_type: str,
    ):
        super().__init__(
            code=ErrorCode.TYPE_ERROR,
            message=f"Type validation failed for field '{field}'",
            details={
                "field": field,
                "expected_type": expected_type,
                "actual_type": actual_type,
            },
            suggestion=f"Field '{field}' should be of type {expected_type}",
        )


# ========================================
# 错误处理工具函数
# ========================================

def create_error_response(
    error: MCPError,
    include_stack: bool = False,
) -> Dict[str, Any]:
    """
    创建错误响应

    Args:
        error: MCP 异常
        include_stack: 是否包含堆栈信息

    Returns:
        错误响应字典
    """
    error_detail = error.to_error_detail(include_stack=include_stack)
    return {
        "success": False,
        "error": error_detail.to_dict(),
    }


def handle_exception(
    exc: Exception,
    logger,
    include_stack: bool = False,
) -> Dict[str, Any]:
    """
    处理异常并返回错误响应

    Args:
        exc: 异常对象
        logger: 日志记录器
        include_stack: 是否包含堆栈信息

    Returns:
        错误响应字典
    """
    if isinstance(exc, MCPError):
        logger.error(f"{exc.__class__.__name__}: {exc.message}", extra=exc.details or {})
        return create_error_response(exc, include_stack=include_stack)
    else:
        # 处理未知异常
        import traceback

        logger.exception(f"Unhandled exception: {str(exc)}")
        error = MCPError(
            code=ErrorCode.INTERNAL_ERROR,
            message="An internal error occurred",
            details={"original_error": str(exc)},
        )
        return create_error_response(error, include_stack=include_stack)
