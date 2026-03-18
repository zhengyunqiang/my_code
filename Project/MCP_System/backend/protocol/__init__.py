"""
Protocol Layer Package
协议层 - JSON-RPC 处理和传输协议实现
"""

from backend.protocol.json_rpc import (
    JSONRPCErrorCode,
    JSONRPCRequest,
    JSONRPCResponse,
    JSONRPCParser,
    JSONRPCHandler,
)
from backend.protocol.transports import StdioTransport, HTTPSseTransport
from backend.protocol.handlers import MCPProtocolHandler, create_default_handler
from backend.protocol.lifecycle import (
    ConnectionState,
    ClientInfo,
    ClientCapabilities,
    ConnectionMetrics,
    MCPLifecycleManager,
)

__all__ = [
    # JSON-RPC
    "JSONRPCErrorCode",
    "JSONRPCRequest",
    "JSONRPCResponse",
    "JSONRPCParser",
    "JSONRPCHandler",
    # Transports
    "StdioTransport",
    "HTTPSseTransport",
    # Handlers
    "MCPProtocolHandler",
    "create_default_handler",
    # Lifecycle
    "ConnectionState",
    "ClientInfo",
    "ClientCapabilities",
    "ConnectionMetrics",
    "MCPLifecycleManager",
]
