from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from contextlib import asynccontextmanager
from typing import Dict
import uvicorn
import asyncio
from pathlib import Path

from config import settings
from database import init_db, close_db
from redis_client import redis_manager
from websocket_manager import manager
from websocket_handlers import WebSocketHandlers
from api import router as api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    print("🚀 Starting WebSocket Realtime Platform...")

    # 初始化数据库
    try:
        await init_db()
        print("✅ Database initialized")
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")

    # 连接 Redis
    try:
        await redis_manager.connect()
        if await redis_manager.ping():
            print("✅ Redis connected")
        else:
            print("⚠️  Redis connection failed")
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")

    # 启动清理任务
    cleanup_task = asyncio.create_task(cleanup_inactive_connections())

    yield

    # 关闭时
    print("🛑 Shutting down...")

    # 取消清理任务
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass

    # 关闭 Redis 连接
    await redis_manager.disconnect()
    print("✅ Redis disconnected")

    # 关闭数据库连接
    await close_db()
    print("✅ Database closed")

    print("👋 Shutdown complete")


# 创建 FastAPI 应用
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件服务（客户端）
client_path = Path(__file__).parent.parent / "client"
if client_path.exists():
    app.mount("/static", StaticFiles(directory=str(client_path)), name="static")

# API 路由
app.include_router(api_router, prefix="/api", tags=["API"])


# 根路径 - 返回客户端页面
@app.get("/", response_class=HTMLResponse)
async def root():
    """返回客户端页面"""
    index_path = client_path / "index.html"
    if index_path.exists():
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>WebSocket Realtime Platform</h1><p>Client not found. Please check the client directory.</p>")


# WebSocket 端点
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 连接端点"""
    # 接受连接
    client_id = await manager.connect(websocket)

    # 发送连接成功消息
    await manager.send_personal_message({
        "type": "system",
        "action": "connected",
        "data": {
            "clientId": client_id,
            "timestamp": __import__('datetime').datetime.utcnow().isoformat(),
            "message": "Connected to WebSocket Realtime Platform"
        }
    }, client_id)

    print(f"📥 New connection: {client_id}")

    # 创建消息处理器
    handlers = WebSocketHandlers(websocket, client_id)

    try:
        while True:
            # 接收消息
            data = await websocket.receive_text()

            try:
                # 解析 JSON
                import json
                message = json.loads(data)

                # 处理消息
                await handlers.handle_message(message)

            except json.JSONDecodeError:
                # 如果不是 JSON，作为文本消息处理
                await handlers.handle_message({
                    "type": "chat",
                    "action": "message",
                    "data": {"content": data}
                })

    except WebSocketDisconnect:
        print(f"📤 Client disconnected: {client_id}")
        await manager.disconnect(client_id)

    except Exception as e:
        print(f"❌ WebSocket error for {client_id}: {e}")
        await manager.disconnect(client_id)


# API 端点

@app.get("/health")
async def health_check():
    """健康检查"""
    redis_ok = await redis_manager.ping() if redis_manager.redis else False

    return JSONResponse({
        "status": "healthy" if redis_ok else "degraded",
        "redis": "connected" if redis_ok else "disconnected",
        "connections": len(manager.active_connections)
    })


@app.get("/api/stats")
async def get_stats():
    """获取服务器统计信息"""
    stats = manager.get_stats()
    online_count = await manager.online_manager.get_online_count()

    return {
        "server": stats,
        "online_users": online_count,
        "redis": "connected" if await redis_manager.ping() else "disconnected"
    }


# 后台任务：清理不活跃连接
async def cleanup_inactive_connections():
    """定期清理不活跃的连接"""
    while True:
        try:
            await asyncio.sleep(60)  # 每分钟清理一次
            await manager.cleanup_inactive_connections(timeout_seconds=300)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"Cleanup task error: {e}")


# 开发服务器启动
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info"
    )
