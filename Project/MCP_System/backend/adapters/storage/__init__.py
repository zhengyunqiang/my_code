"""
Storage Adapters Package
存储适配器 - 本地文件系统
"""

from backend.adapters.storage.local import (
    LocalStorageAdapter,
    local_storage,
)

__all__ = [
    "LocalStorageAdapter",
    "local_storage",
]
