#!/usr/bin/env python3
"""
MCP System 快速启动脚本
"""

import os
import sys
import subprocess
from pathlib import Path

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))


def check_dependencies():
    """检查依赖是否安装"""
    print("🔍 检查依赖...")

    required_packages = [
        ("fastapi", "FastAPI"),
        ("sqlalchemy", "SQLAlchemy"),
        ("openai", "OpenAI SDK"),
        ("pydantic_settings", "Pydantic Settings"),
    ]

    missing = []
    for package, name in required_packages:
        try:
            __import__(package)
            print(f"  ✅ {name}")
        except ImportError:
            print(f"  ❌ {name} - 未安装")
            missing.append(package)

    if missing:
        print(f"\n⚠️  缺少依赖: {', '.join(missing)}")
        print("请运行: pip install -r backend/requirements/base.txt")
        return False

    print("✅ 所有依赖已安装\n")
    return True


def check_config():
    """检查配置文件"""
    print("🔍 检查配置...")

    env_file = PROJECT_ROOT / "backend" / ".env"
    if not env_file.exists():
        print(f"  ❌ 配置文件不存在: {env_file}")
        print("请复制 .env.example 到 .env 并填写配置")
        return False

    print(f"  ✅ 配置文件存在: {env_file}")

    # 检查关键配置
    from backend.config import settings

    configs = [
        ("千问 API Key", hasattr(settings, 'QWEN_API_KEY') and settings.QWEN_API_KEY),
        ("数据库 URL", hasattr(settings, 'DATABASE_URL') and settings.DATABASE_URL),
        ("Redis URL", hasattr(settings, 'REDIS_URL') and settings.REDIS_URL),
    ]

    all_ok = True
    for name, ok in configs:
        if ok:
            print(f"  ✅ {name}")
        else:
            print(f"  ⚠️  {name} - 未配置")
            all_ok = False

    if not all_ok:
        print("\n⚠️  部分配置未完成，服务可能无法正常运行")

    print()
    return True


def start_server(mode="http"):
    """启动服务器"""
    print(f"🚀 启动 MCP System 服务器 ({mode} 模式)\n")

    if mode == "http":
        print("访问地址:")
        print(f"  - API: http://localhost:8000")
        print(f"  - 健康检查: http://localhost:8000/health")
        print(f"  - 指标: http://localhost:8000/metrics")
    elif mode == "stdio":
        print("运行模式: stdio (适用于 Claude Desktop 集成)")

    print("\n按 Ctrl+C 停止服务器\n")
    print("=" * 50)

    # 启动服务
    from backend.main import main
    main()


def show_help():
    """显示帮助信息"""
    print("""
MCP System 启动指南
===================

用法:
  python startup.py [模式]

模式:
  http    HTTP 服务器模式 (默认) - 适用于 Web API 调用
  stdio   stdio 模式 - 适用于 Claude Desktop 集成

示例:
  python startup.py          # 启动 HTTP 服务器
  python startup.py stdio    # 启动 stdio 服务器

环境要求:
  - Python 3.11+
  - PostgreSQL 15+ (可选，用于数据持久化)
  - Redis 7+ (可选，用于缓存)

配置文件:
  backend/.env - 主配置文件

更多信息:
  - README.md
  - docs/nl_database_tool.md
  - docs/prompt_management.md
""")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="MCP System 启动脚本")
    parser.add_argument(
        "mode",
        nargs="?",
        choices=["http", "stdio"],
        default="http",
        help="运行模式"
    )
    parser.add_argument(
        "--skip-check",
        action="store_true",
        help="跳过依赖和配置检查"
    )
    parser.add_argument(
        "--help-config",
        action="store_true",
        help="显示配置帮助"
    )

    args = parser.parse_args()

    if args.help_config:
        show_help()
        sys.exit(0)

    # 检查依赖和配置
    if not args.skip_check:
        if not check_dependencies():
            sys.exit(1)
        if not check_config():
            sys.exit(1)

    # 启动服务器
    try:
        start_server(args.mode)
    except KeyboardInterrupt:
        print("\n\n👋 服务器已停止")
    except Exception as e:
        print(f"\n❌ 启动失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
