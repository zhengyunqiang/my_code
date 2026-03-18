"""
MCP System - Production-grade Model Context Protocol Service
生产级 MCP 服务系统

5层分层架构：
1. Access & Protocol Layer - 协议接入和传输
2. Security & Gateway Layer - 安全网关和权限控制
3. Orchestration & Routing Layer - 请求编排和路由
4. Business Logic Layer - 业务逻辑和核心功能
5. Data & Integration Layer - 数据访问和外部集成
"""

__version__ = "1.0.0"
__author__ = "Your Name"
__license__ = "MIT"

from backend.config import settings
from backend.core import get_logger, logger

# 导出核心配置
__all__ = [
    "settings",
    "get_logger",
    "logger",
]
