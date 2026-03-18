"""
Utility Functions Module
工具函数模块
"""

import asyncio
import hashlib
import secrets
import string
from typing import Any, Dict, List, Optional, TypeVar, Generic
from datetime import datetime, timezone
import json

from backend.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


# ========================================
# 字符串工具
# ========================================

def generate_random_string(length: int = 32) -> str:
    """
    生成随机字符串

    Args:
        length: 字符串长度

    Returns:
        随机字符串
    """
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_api_key() -> str:
    """
    生成 API 密钥

    Returns:
        API 密钥字符串
    """
    return f"mcp_{generate_random_string(40)}"


def hash_string(content: str, algorithm: str = "sha256") -> str:
    """
    哈希字符串

    Args:
        content: 待哈希内容
        algorithm: 哈希算法

    Returns:
        哈希值
    """
    hash_func = hashlib.new(algorithm)
    hash_func.update(content.encode("utf-8"))
    return hash_func.hexdigest()


def truncate_string(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    截断字符串

    Args:
        text: 原始字符串
        max_length: 最大长度
        suffix: 截断后缀

    Returns:
        截断后的字符串
    """
    if len(text) <= max_length:
        return text
    return text[: max_length - len(suffix)] + suffix


# ========================================
# 时间工具
# ========================================

def get_utc_now() -> datetime:
    """
    获取当前 UTC 时间

    Returns:
        UTC 时间
    """
    return datetime.now(timezone.utc)


def format_datetime(dt: datetime, format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    格式化日期时间

    Args:
        dt: 日期时间对象
        format_str: 格式字符串

    Returns:
        格式化后的字符串
    """
    return dt.strftime(format_str)


# ========================================
# JSON 工具
# ========================================

def json_dumps(obj: Any, **kwargs) -> str:
    """
    JSON 序列化（支持 datetime）

    Args:
        obj: 待序列化对象
        **kwargs: 额外参数

    Returns:
        JSON 字符串
    """
    def default(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    return json.dumps(obj, default=default, **kwargs)


def json_loads(text: str, **kwargs) -> Any:
    """
    JSON 反序列化

    Args:
        text: JSON 字符串
        **kwargs: 额外参数

    Returns:
        反序列化后的对象
    """
    return json.loads(text, **kwargs)


def merge_dicts(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """
    深度合并字典

    Args:
        base: 基础字典
        override: 覆盖字典

    Returns:
        合并后的字典
    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_dicts(result[key], value)
        else:
            result[key] = value
    return result


# ========================================
# 验证工具
# ========================================

def validate_email(email: str) -> bool:
    """
    验证邮箱格式

    Args:
        email: 邮箱地址

    Returns:
        是否有效
    """
    import re
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(pattern, email) is not None


def validate_url(url: str) -> bool:
    """
    验证 URL 格式

    Args:
        url: URL 地址

    Returns:
        是否有效
    """
    import re
    pattern = r"^https?://[^\s/$.?#].[^\s]*$"
    return re.match(pattern, url) is not None


def sanitize_filename(filename: str) -> str:
    """
    清理文件名

    Args:
        filename: 原始文件名

    Returns:
        清理后的文件名
    """
    import re
    # 移除危险字符
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    # 限制长度
    return truncate_string(filename, 255, "")


# ========================================
# 异步工具
# ========================================

async def run_sync(func, *args, **kwargs) -> Any:
    """
    在异步上下文中运行同步函数

    Args:
        func: 同步函数
        *args: 位置参数
        **kwargs: 关键字参数

    Returns:
        函数返回值
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, func, *args, **kwargs)


async def gather_with_exceptions(*coros, return_exceptions: bool = False) -> List[Any]:
    """
    并发执行协程（保留异常）

    Args:
        *coros: 协程列表
        return_exceptions: 是否返回异常

    Returns:
        结果列表
    """
    return await asyncio.gather(*coros, return_exceptions=return_exceptions)


# ========================================
# 幂等性工具
# ========================================

class IdempotencyKey:
    """幂等性键生成器"""

    @staticmethod
    def from_request(method: str, path: str, body: Optional[Dict[str, Any]] = None) -> str:
        """
        从请求生成幂等性键

        Args:
            method: HTTP 方法
            path: 请求路径
            body: 请求体

        Returns:
            幂等性键
        """
        key_parts = [method.upper(), path]
        if body:
            key_parts.append(json_dumps(body, sort_keys=True))
        key_string = ":".join(key_parts)
        return hash_string(key_string)


# ========================================
# 类型和模式工具
# ========================================

def is_empty(value: Any) -> bool:
    """
    检查值是否为空

    Args:
        value: 待检查值

    Returns:
        是否为空
    """
    if value is None:
        return True
    if isinstance(value, (str, list, dict, set, tuple)) and len(value) == 0:
        return True
    return False


def to_bool(value: Any) -> bool:
    """
    转换为布尔值

    Args:
        value: 待转换值

    Returns:
        布尔值
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes", "on")
    if isinstance(value, (int, float)):
        return value != 0
    return bool(value)


# ========================================
# 输出美化工具
# ========================================

def format_size(size_bytes: int) -> str:
    """
    格式化文件大小

    Args:
        size_bytes: 字节数

    Returns:
        格式化后的字符串
    """
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


def format_duration(seconds: float) -> str:
    """
    格式化时间间隔

    Args:
        seconds: 秒数

    Returns:
        格式化后的字符串
    """
    if seconds < 1:
        return f"{seconds * 1000:.2f}ms"
    if seconds < 60:
        return f"{seconds:.2f}s"
    minutes = seconds / 60
    if minutes < 60:
        return f"{minutes:.2f}m"
    hours = minutes / 60
    return f"{hours:.2f}h"


__all__ = [
    # String utilities
    "generate_random_string",
    "generate_api_key",
    "hash_string",
    "truncate_string",
    # Time utilities
    "get_utc_now",
    "format_datetime",
    # JSON utilities
    "json_dumps",
    "json_loads",
    "merge_dicts",
    # Validation utilities
    "validate_email",
    "validate_url",
    "sanitize_filename",
    # Async utilities
    "run_sync",
    "gather_with_exceptions",
    # Idempotency
    "IdempotencyKey",
    # Type utilities
    "is_empty",
    "to_bool",
    # Formatting
    "format_size",
    "format_duration",
]
