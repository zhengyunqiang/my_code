#!/bin/bash

# WebSocket 实时协作平台启动脚本

set -e

echo "🚀 WebSocket Realtime Platform Launcher"
echo "=========================================="
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 函数：打印彩色消息
print_message() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

# 函数：检查 Docker 是否安装
check_docker() {
    if ! command -v docker &> /dev/null; then
        print_message "$RED" "❌ Docker is not installed. Please install Docker first."
        exit 1
    fi

    if ! command -v docker-compose &> /dev/null; then
        print_message "$RED" "❌ Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi

    print_message "$GREEN" "✅ Docker and Docker Compose are installed"
}

# 函数：启动服务
start_services() {
    print_message "$BLUE" "📦 Starting services with Docker Compose..."
    docker-compose up -d

    print_message "$GREEN" "✅ Services started"
    print_message "$YELLOW" "⏳ Waiting for services to be ready..."
    sleep 5
}

# 函数：显示服务状态
show_status() {
    print_message "$BLUE" "📊 Service Status:"
    docker-compose ps
}

# 函数：显示日志
show_logs() {
    print_message "$BLUE" "📋 Recent logs:"
    docker-compose logs --tail=20 backend
}

# 函数：显示访问信息
show_access_info() {
    echo ""
    print_message "$GREEN" "🎉 Services are running!"
    echo ""
    print_message "$BLUE" "📍 Access URLs:"
    echo "   • Backend API:     http://localhost:8000"
    echo "   • WebSocket:       ws://localhost:8000/ws"
    echo "   • API Docs:        http://localhost:8000/docs"
    echo "   • PostgreSQL:      localhost:5432"
    echo "   • Redis:           localhost:6379"
    echo ""
    print_message "$BLUE" "👤 Test Accounts:"
    echo "   • Admin:   admin / admin123"
    echo "   • User:    test / test123"
    echo ""
    print_message "$YELLOW" "💡 Commands:"
    echo "   • View logs:       docker-compose logs -f"
    echo "   • Stop services:   docker-compose down"
    echo "   • Restart:         docker-compose restart"
    echo ""
}

# 函数：停止服务
stop_services() {
    print_message "$YELLOW" "🛑 Stopping services..."
    docker-compose down
    print_message "$GREEN" "✅ Services stopped"
}

# 函数：重启服务
restart_services() {
    print_message "$YELLOW" "🔄 Restarting services..."
    docker-compose restart
    print_message "$GREEN" "✅ Services restarted"
}

# 函数：初始化数据库
init_database() {
    print_message "$BLUE" "🗄️  Initializing database..."
    docker-compose exec backend python init_db.py all
}

# 函数：重置数据库
reset_database() {
    print_message "$RED" "⚠️  This will delete all data. Are you sure? (yes/no)"
    read -r confirm
    if [ "$confirm" = "yes" ]; then
        print_message "$BLUE" "🗄️  Resetting database..."
        docker-compose exec backend python init_db.py reset
    else
        print_message "$YELLOW" "❌ Cancelled"
    fi
}

# 主菜单
show_menu() {
    echo ""
    print_message "$BLUE" "📋 What would you like to do?"
    echo "   1) Start services"
    echo "   2) Stop services"
    echo "   3) Restart services"
    echo "   4) Show status"
    echo "   5) Show logs"
    echo "   6) Initialize database"
    echo "   7) Reset database"
    echo "   8) Exit"
    echo ""
    read -p "Select an option [1-8]: " choice

    case $choice in
        1)
            check_docker
            start_services
            show_access_info
            ;;
        2)
            stop_services
            ;;
        3)
            restart_services
            ;;
        4)
            show_status
            ;;
        5)
            show_logs
            ;;
        6)
            init_database
            ;;
        7)
            reset_database
            ;;
        8)
            print_message "$GREEN" "👋 Goodbye!"
            exit 0
            ;;
        *)
            print_message "$RED" "❌ Invalid option"
            ;;
    esac
}

# 主程序
main() {
    # 如果有命令行参数，执行对应命令
    if [ $# -gt 0 ]; then
        case $1 in
            start)
                check_docker
                start_services
                show_access_info
                ;;
            stop)
                stop_services
                ;;
            restart)
                restart_services
                ;;
            status)
                show_status
                ;;
            logs)
                show_logs
                ;;
            init)
                init_database
                ;;
            reset)
                reset_database
                ;;
            *)
                print_message "$RED" "❌ Unknown command: $1"
                echo "Available commands: start, stop, restart, status, logs, init, reset"
                exit 1
                ;;
        esac
    else
        # 交互式菜单
        while true; do
            show_menu
        done
    fi
}

# 运行主程序
main "$@"
