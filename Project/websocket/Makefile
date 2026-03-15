.PHONY: help start stop restart status logs init reset clean install test

# 默认目标
help:
	@echo "🚀 WebSocket Realtime Platform - Makefile Commands"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "Available targets:"
	@echo "  start      - Start all services (docker-compose up -d)"
	@echo "  stop       - Stop all services (docker-compose down)"
	@echo "  restart    - Restart all services"
	@echo "  status     - Show service status"
	@echo "  logs       - Show service logs"
	@echo "  init       - Initialize database"
	@echo "  reset      - Reset database (delete all data)"
	@echo "  clean      - Remove all containers and volumes"
	@echo "  install    - Install Python dependencies"
	@echo "  test       - Run tests"
	@echo "  help       - Show this help message"

# 启动服务
start:
	@echo "📦 Starting services..."
	docker-compose up -d
	@echo "⏳ Waiting for services..."
	@sleep 5
	@echo "✅ Services started"
	@echo ""
	@echo "📍 Access URLs:"
	@echo "   • Backend API:     http://localhost:8000"
	@echo "   • WebSocket:       ws://localhost:8000/ws"
	@echo "   • API Docs:        http://localhost:8000/docs"

# 停止服务
stop:
	@echo "🛑 Stopping services..."
	docker-compose down
	@echo "✅ Services stopped"

# 重启服务
restart:
	@echo "🔄 Restarting services..."
	docker-compose restart
	@echo "✅ Services restarted"

# 显示状态
status:
	@echo "📊 Service Status:"
	@docker-compose ps

# 显示日志
logs:
	@echo "📋 Service Logs:"
	@docker-compose logs -f --tail=50

# 初始化数据库
init:
	@echo "🗄️  Initializing database..."
	docker-compose exec backend python init_db.py all

# 重置数据库
reset:
	@echo "⚠️  This will delete all data."
	@read -p "Are you sure? [y/N] " confirm; \
	if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
		echo "🗄️  Resetting database..."; \
		docker-compose exec backend python init_db.py reset; \
	else \
		echo "❌ Cancelled"; \
	fi

# 清理
clean:
	@echo "🧹 Cleaning up..."
	@read -p "This will remove all containers and volumes. Are you sure? [y/N] " confirm; \
	if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
		docker-compose down -v; \
		echo "✅ Cleanup complete"; \
	else \
		echo "❌ Cancelled"; \
	fi

# 安装依赖
install:
	@echo "📦 Installing Python dependencies..."
	cd server-fastapi && pip install -r requirements.txt
	@echo "✅ Dependencies installed"

# 运行测试
test:
	@echo "🧪 Running tests..."
	cd server-fastapi && python -m pytest tests/ -v
