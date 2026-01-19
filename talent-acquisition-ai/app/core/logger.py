"""
Logging configuration for Talent Acquisition AI System.
Uses loguru for advanced logging capabilities.
"""
import sys
from pathlib import Path
from typing import Optional

from loguru import logger

from app.core.config import get_settings

settings = get_settings()


class InterceptHandler:
    """Intercept standard logging and redirect to loguru."""

    def __init__(self, /, level: Optional[int] = None):
        self.level = level

    def emit(self, record):
        """Emit log record through loguru."""
        # Get corresponding loguru level if it exists
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where originated the logged message
        frame, depth = record.sys._getframe(6), 6
        while frame and depth == 6:
            if frame.f_code.co_filename == record.pathname:
                break
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def setup_logging():
    """Configure logging for the application."""
    # Remove default handler
    logger.remove()

    # Add console handler with color
    logger.add(
        sys.stdout,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        level=settings.log_level,
        colorize=True,
        backtrace=True,
        diagnose=True,
    )

    # Add file handler for general logs
    logger.add(
        settings.log_dir / "app_{time:YYYY-MM-DD}.log",
        rotation=settings.log_rotation,
        retention=settings.log_retention,
        compression="zip",
        level=settings.log_level,
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
            "{level: <8} | "
            "{name}:{function}:{line} | "
            "{message}"
        ),
        backtrace=True,
        diagnose=True,
    )

    # Add file handler for error logs
    logger.add(
        settings.log_dir / "error_{time:YYYY-MM-DD}.log",
        rotation=settings.log_rotation,
        retention=settings.log_retention,
        compression="zip",
        level="ERROR",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
            "{level: <8} | "
            "{name}:{function}:{line} | "
            "{message}"
        ),
        backtrace=True,
        diagnose=True,
    )

    # Add file handler for JSON logs (for parsing by monitoring tools)
    logger.add(
        settings.log_dir / "json_{time:YYYY-MM-DD}.log",
        rotation=settings.log_rotation,
        retention=settings.log_retention,
        compression="zip",
        level=settings.log_level,
        serialize=True,
    )

    # Intercept standard logging
    # import logging
    # logging.basicConfig(handlers=[InterceptHandler()], level=0)

    logger.info(f"Logging configured. Level: {settings.log_level}")
    logger.info(f"Log directory: {settings.log_dir}")


def get_logger(name: Optional[str] = None):
    """
    Get a logger instance.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Logger instance
    """
    if name:
        return logger.bind(name=name)
    return logger


# Initialize logging on module import
setup_logging()
