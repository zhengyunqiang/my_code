#!/bin/bash

# Talent Acquisition AI - Development Startup Script

set -e

echo "🚀 Starting Talent Acquisition AI Development Environment..."

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
    echo "✅ Environment variables loaded"
else
    echo "⚠️  No .env file found, using defaults"
fi

# Check Python version
PYTHON_VERSION=$(python --version 2>&1 | awk '{print $2}')
echo "🐍 Python version: $PYTHON_VERSION"

# Install dependencies
if [ "$1" == "--install" ] || [ "$1" == "-i" ]; then
    echo "📦 Installing dependencies..."
    pip install poetry
    poetry install
    echo "✅ Dependencies installed"
fi

# Initialize database
if [ "$1" == "--init-db" ] || [ "$1" == "-d" ]; then
    echo "🗄️  Initializing database..."
    python -m database.migrations.init reset
    echo "✅ Database initialized"
fi

# Start services
echo "🔧 Starting services..."

# Start Redis (if not running)
if ! pgrep -x "redis-server" > /dev/null; then
    echo "📮 Starting Redis..."
    redis-server --daemonize yes
    echo "✅ Redis started"
else
    echo "✅ Redis already running"
fi

# Start PostgreSQL (if using Docker)
if command -v docker &> /dev/null; then
    if ! docker ps | grep -q "postgres"; then
        echo "🐘 Starting PostgreSQL container..."
        docker run -d \
            --name talentai-postgres \
            -e POSTGRES_USER=postgres \
            -e POSTGRES_PASSWORD=postgres \
            -e POSTGRES_DB=talent_ai \
            -p 5432:5432 \
            postgres:15-alpine
        echo "✅ PostgreSQL started"
    else
        echo "✅ PostgreSQL already running"
    fi
fi

# Start API server
echo "🌐 Starting FastAPI server..."
uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --reload \
    --log-level info

echo "✅ All services started!"
echo ""
echo "📖 API Documentation: http://localhost:8000/api/docs"
echo "💚 Health Check: http://localhost:8000/health"
echo "📊 Metrics: http://localhost:8000/metrics"
