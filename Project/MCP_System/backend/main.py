"""
MCP System Main Entry Point
主应用入口 - 支持多种传输协议
"""

import asyncio
import sys
from pathlib import Path
from typing import Optional

import uvicorn

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.config import settings
from backend.core.logging import get_logger, setup_logging
from backend.adapters.database import init_db, close_db

logger = get_logger(__name__)


class MCPApplication:
    """
    MCP 应用主类

    管理所有组件的初始化和生命周期
    """

    def __init__(self):
        self._redis_client = None
        self._http_client = None
        self._kafka_producer = None

    async def startup(self):
        """应用启动初始化"""
        logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
        logger.info(f"Environment: {settings.ENVIRONMENT}")

        # Initialize database
        try:
            await init_db()
            logger.info("✓ Database connection established")
        except Exception as e:
            logger.error(f"✗ Failed to connect to database: {e}")
            raise

        # Initialize Redis
        try:
            import redis.asyncio as redis
            self._redis_client = await redis.from_url(
                settings.REDIS_URL,
                decode_responses=settings.REDIS_DECODE_RESPONSES,
            )
            await self._redis_client.ping()
            logger.info("✓ Redis connection established")

            # Initialize cache and rate limiting
            from backend.adapters.cache import init_cache
            from backend.gateway.rate_limit import init_rate_limiting

            await init_cache(self._redis_client)
            await init_rate_limiting(self._redis_client)
            logger.info("✓ Cache and rate limiting initialized")

        except Exception as e:
            logger.warning(f"⚠ Redis not available: {e}")
            logger.info("Running without cache and rate limiting")

        # Initialize HTTP client
        try:
            from backend.adapters.external import init_http_client
            self._http_client = await init_http_client()
            logger.info("✓ HTTP client initialized")
        except Exception as e:
            logger.warning(f"⚠ HTTP client initialization failed: {e}")

        # Initialize Kafka (optional)
        if settings.KAFKA_ENABLED:
            try:
                from backend.adapters.messaging import init_kafka_producer
                self._kafka_producer = await init_kafka_producer()
                logger.info("✓ Kafka producer initialized")
            except Exception as e:
                logger.warning(f"⚠ Kafka initialization failed: {e}")

        # Initialize context manager
        try:
            from backend.orchestration.context_manager import context_manager
            await context_manager.start()
            logger.info("✓ Context manager started")
        except Exception as e:
            logger.warning(f"⚠ Context manager initialization failed: {e}")

        # Initialize tools
        try:
            from backend.services.tools.init_tools import init_default_tools
            await init_default_tools()
            logger.info("✓ Default tools initialized")
        except Exception as e:
            logger.warning(f"⚠ Tools initialization failed: {e}")

        logger.info("=" * 50)
        logger.info("MCP System startup complete!")
        logger.info("=" * 50)

    async def shutdown(self):
        """应用关闭清理"""
        logger.info("Shutting down MCP System...")

        # Stop Kafka producer
        if self._kafka_producer:
            try:
                await self._kafka_producer.stop()
                logger.info("✓ Kafka producer stopped")
            except Exception as e:
                logger.error(f"✗ Error stopping Kafka producer: {e}")

        # Stop HTTP client
        if self._http_client:
            try:
                await self._http_client.stop()
                logger.info("✓ HTTP client stopped")
            except Exception as e:
                logger.error(f"✗ Error stopping HTTP client: {e}")

        # Stop context manager
        try:
            from backend.orchestration.context_manager import context_manager
            await context_manager.stop()
            logger.info("✓ Context manager stopped")
        except Exception as e:
            logger.error(f"✗ Error stopping context manager: {e}")

        # Close database connection
        try:
            await close_db()
            logger.info("✓ Database connection closed")
        except Exception as e:
            logger.error(f"✗ Error closing database: {e}")

        # Close Redis connection
        if self._redis_client:
            try:
                await self._redis_client.close()
                logger.info("✓ Redis connection closed")
            except Exception as e:
                logger.error(f"✗ Error closing Redis: {e}")

        logger.info("MCP System shutdown complete")


# Global application instance
app = MCPApplication()


def create_app():
    """创建 FastAPI 应用"""
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    fastapi_app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Production-grade MCP System with 5-layer architecture",
        debug=settings.DEBUG,
    )

    # CORS middleware
    fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=settings.CORS_ALLOW_METHODS,
        allow_headers=settings.CORS_ALLOW_HEADERS,
    )

    # Startup and shutdown events
    @fastapi_app.on_event("startup")
    async def on_startup():
        await app.startup()

    @fastapi_app.on_event("shutdown")
    async def on_shutdown():
        await app.shutdown()

    # Health check endpoint
    @fastapi_app.get("/health")
    async def health_check():
        return {
            "status": "healthy",
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT,
        }

    # Root endpoint
    @fastapi_app.get("/")
    async def root():
        return {
            "name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "status": "running",
            "transport": settings.TRANSPORT_TYPE,
        }

    # Metrics endpoint (for Prometheus)
    if settings.METRICS_ENABLED:
        from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
        from starlette.responses import Response

        @fastapi_app.get("/metrics")
        async def metrics():
            from prometheus_client import REGISTRY
            return Response(
                content=generate_latest(REGISTRY),
                media_type=CONTENT_TYPE_LATEST,
            )

    # MCP Protocol endpoint (for HTTP-based MCP requests)
    @fastapi_app.post("/mcp")
    async def mcp_endpoint(request: dict):
        """MCP 协议端点 - 处理 JSON-RPC 2.0 请求"""
        from backend.protocol.handlers import create_default_handler
    
        handler = create_default_handler()
        method = request.get("method")
        params = request.get("params", {})
        request_id = request.get("id")
    
        logger.info(f"Received MCP request: {method}")
    
        try:
            if method == "initialize":
                result = await handler.initialize(params)
            elif method == "tools/list":
                result = await handler.list_tools(params)
            elif method == "tools/call":
                result = await handler.call_tool(params)
            elif method == "resources/list":
                result = await handler.list_resources(params)
            elif method == "resources/read":
                result = await handler.read_resource(params)
            elif method == "prompts/list":
                result = await handler.list_prompts(params)
            elif method == "prompts/get":
                result = await handler.get_prompt(params)
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method}"
                    }
                }
    
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": result
            }
    
        except Exception as e:
            logger.error(f"Error processing MCP request: {e}")
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32603,
                    "message": str(e)
                }
            }
    
    # Tool list endpoint (convenience)
    @fastapi_app.get("/tools")
    async def list_tools():
        """列出所有可用工具"""
        from backend.protocol.handlers import create_default_handler
    
        handler = create_default_handler()
        result = await handler.list_tools({})
        return result

    return fastapi_app


def run_http_server():
    """运行 HTTP 服务器"""
    fastapi_app = create_app()

    logger.info(f"Starting HTTP server on {settings.HOST}:{settings.PORT}")

    uvicorn.run(
        fastapi_app,
        host=settings.HOST,
        port=settings.PORT,
        log_level=settings.LOG_LEVEL.lower(),
        access_log=True,
    )


async def run_stdio_server():
    """运行 stdio 服务器（用于 Claude Desktop 集成）"""
    logger.info("Starting stdio server for Claude Desktop integration")

    from backend.protocol.transports.stdio import StdioTransport
    from backend.protocol.handlers import MCPProtocolHandler

    # Create transport and handler
    transport = StdioTransport()
    handler = MCPProtocolHandler()

    # Run server
    try:
        await app.startup()
        await transport.run(handler)
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    finally:
        await app.shutdown()


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="MCP System Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http", "both"],
        default=settings.TRANSPORT_TYPE,
        help="Transport protocol to use",
    )
    parser.add_argument(
        "--host",
        default=settings.HOST,
        help="Host to bind to (HTTP mode)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=settings.PORT,
        help="Port to bind to (HTTP mode)",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=settings.LOG_LEVEL,
        help="Log level",
    )

    args = parser.parse_args()

    # Update settings from command line
    settings.HOST = args.host
    settings.PORT = args.port
    settings.LOG_LEVEL = args.log_level

    # Setup logging
    setup_logging()

    # Run appropriate transport
    if args.transport == "stdio":
        asyncio.run(run_stdio_server())
    elif args.transport == "http":
        run_http_server()
    else:  # both
        logger.error("Running both transports simultaneously is not supported yet")
        logger.info("Please choose either 'stdio' or 'http' transport")
        sys.exit(1)


if __name__ == "__main__":
    main()
