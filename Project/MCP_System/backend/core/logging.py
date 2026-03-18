"""
MCP System Logging Configuration
使用 loguru 实现结构化日志
"""

import sys
import logging
from pathlib import Path
from typing import Any, Dict, Optional
from loguru import logger as loguru_logger
from contextvars import ContextVar

from backend.config import settings


# 请求上下文变量
REQUEST_ID_CTX: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
USER_ID_CTX: ContextVar[Optional[int]] = ContextVar("user_id", default=None)


class RequestIdFilter:
    """请求 ID 过滤器"""

    def __init__(self):
        pass

    def __call__(self, record: Dict[str, Any]) -> Dict[str, Any]:
        request_id = REQUEST_ID_CTX.get()
        if request_id:
            record["extra"]["request_id"] = request_id
        user_id = USER_ID_CTX.get()
        if user_id:
            record["extra"]["user_id"] = user_id
        return record


class InterceptHandler(logging.Handler):
    """
    将标准 logging 重定向到 loguru
    用于捕获第三方库的日志
    """

    def emit(self, record: logging.LogRecord) -> None:
        # 获取对应的 loguru level
        try:
            level = loguru_logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # 查找调用者
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        loguru_logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def setup_logging() -> None:
    """
    配置日志系统
    """
    # 移除默认的 handler
    loguru_logger.remove()

    # 日志格式
    if settings.LOG_FORMAT == "json":
        # JSON 格式（生产环境推荐）
        # 使用 serialize=True 自动格式化为 JSON
        log_format = None  # format will be handled by serialize
    else:
        # 文本格式（开发环境）
        log_format = (
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level> | "
            "Request ID: {extra[request_id]} | "
            "User ID: {extra[user_id]}"
        )

    # 控制台输出
    if settings.LOG_OUTPUT in ["stdout", "both"]:
        if settings.LOG_FORMAT == "json":
            loguru_logger.add(
                sys.stdout,
                level=settings.LOG_LEVEL,
                colorize=False,
                backtrace=True,
                diagnose=settings.DEBUG,
                filter=RequestIdFilter(),
                serialize=True,  # 自动序列化为 JSON
            )
        else:
            loguru_logger.add(
                sys.stdout,
                format=log_format,
                level=settings.LOG_LEVEL,
                colorize=True,
                backtrace=True,
                diagnose=settings.DEBUG,
                filter=RequestIdFilter(),
            )

    # 文件输出
    if settings.LOG_OUTPUT in ["file", "both"]:
        log_path = Path(settings.LOG_FILE_PATH)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        serialize = settings.LOG_FORMAT == "json"

        # 主日志文件（带轮转）
        if serialize:
            loguru_logger.add(
                settings.LOG_FILE_PATH,
                level=settings.LOG_LEVEL,
                rotation=settings.LOG_ROTATION,
                retention=settings.LOG_RETENTION,
                compression="zip",
                backtrace=True,
                diagnose=settings.DEBUG,
                filter=RequestIdFilter(),
                serialize=True,
            )
        else:
            loguru_logger.add(
                settings.LOG_FILE_PATH,
                format=log_format,
                level=settings.LOG_LEVEL,
                rotation=settings.LOG_ROTATION,
                retention=settings.LOG_RETENTION,
                compression="zip",
                backtrace=True,
                diagnose=settings.DEBUG,
                filter=RequestIdFilter(),
            )

    # 错误日志文件（单独存储）
        if serialize:
            loguru_logger.add(
                settings.LOG_FILE_PATH.replace(".log", "_error.log"),
                level="ERROR",
                rotation=settings.LOG_ROTATION,
                retention=settings.LOG_RETENTION,
                compression="zip",
                backtrace=True,
                diagnose=True,
                filter=RequestIdFilter(),
                serialize=True,
            )
        else:
            loguru_logger.add(
                settings.LOG_FILE_PATH.replace(".log", "_error.log"),
                format=log_format,
                level="ERROR",
                rotation=settings.LOG_ROTATION,
                retention=settings.LOG_RETENTION,
                compression="zip",
                backtrace=True,
                diagnose=True,
                filter=RequestIdFilter(),
            )

    # 拦截标准 logging
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)


class Logger:
    """
    日志记录器包装类
    提供便捷的日志记录方法
    """

    def __init__(self, name: str):
        self._logger = loguru_logger.bind(logger=name)

    def debug(self, message: str, **kwargs: Any) -> None:
        """记录调试日志"""
        self._logger.debug(message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        """记录信息日志"""
        self._logger.info(message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        """记录警告日志"""
        self._logger.warning(message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        """记录错误日志"""
        self._logger.error(message, **kwargs)

    def critical(self, message: str, **kwargs: Any) -> None:
        """记录严重错误日志"""
        self._logger.critical(message, **kwargs)

    def exception(self, message: str, **kwargs: Any) -> None:
        """记录异常日志（包含堆栈信息）"""
        self._logger.exception(message, **kwargs)

    # 上下文管理方法
    def bind_context(self, **kwargs: Any) -> "Logger":
        """绑定上下文信息"""
        return Logger(self._logger.bind(**kwargs))

    def with_request_id(self, request_id: str) -> "Logger":
        """绑定请求 ID"""
        REQUEST_ID_CTX.set(request_id)
        return self

    def with_user_id(self, user_id: int) -> "Logger":
        """绑定用户 ID"""
        USER_ID_CTX.set(user_id)
        return self


def get_logger(name: str) -> Logger:
    """
    获取日志记录器

    Args:
        name: 日志记录器名称（通常使用 __name__）

    Returns:
        Logger 实例
    """
    return Logger(name)


# 初始化日志系统
setup_logging()

# 导出默认 logger
logger = get_logger(__name__)
