"""
Local Storage Adapter
本地存储适配器 - 文件系统操作
"""

import os
import shutil
import hashlib
from pathlib import Path
from typing import Optional, List, Dict, Any, BinaryIO
from datetime import datetime
import mimetypes

from backend.core.logging import get_logger

logger = get_logger(__name__)


class LocalStorageAdapter:
    """
    本地存储适配器

    提供文件系统操作功能
    """

    def __init__(self, base_path: Optional[str] = None):
        """
        初始化本地存储适配器

        Args:
            base_path: 基础路径
        """
        self.base_path = Path(base_path or "./storage")
        self.base_path.mkdir(parents=True, exist_ok=True)

    async def read(
        self,
        file_path: str,
        mode: str = "r",
        encoding: str = "utf-8",
    ) -> Any:
        """
        读取文件

        Args:
            file_path: 文件路径
            mode: 打开模式
            encoding: 编码

        Returns:
            文件内容
        """
        full_path = self._resolve_path(file_path)

        try:
            if "b" in mode:
                # 二进制模式
                with open(full_path, "rb") as f:
                    return f.read()
            else:
                # 文本模式
                with open(full_path, "r", encoding=encoding) as f:
                    return f.read()

        except FileNotFoundError:
            logger.error(f"File not found: {full_path}")
            raise
        except Exception as e:
            logger.error(f"Error reading file {full_path}: {e}")
            raise

    async def write(
        self,
        file_path: str,
        content: Any,
        mode: str = "w",
        encoding: str = "utf-8",
        create_dirs: bool = True,
    ) -> int:
        """
        写入文件

        Args:
            file_path: 文件路径
            content: 文件内容
            mode: 写入模式
            encoding: 编码
            create_dirs: 是否创建目录

        Returns:
            写入字节数
        """
        full_path = self._resolve_path(file_path)

        try:
            if create_dirs:
                full_path.parent.mkdir(parents=True, exist_ok=True)

            if "b" in mode:
                # 二进制模式
                with open(full_path, "wb") as f:
                    if isinstance(content, str):
                        content = content.encode(encoding)
                    f.write(content)
                    return len(content)
            else:
                # 文本模式
                with open(full_path, "w", encoding=encoding) as f:
                    f.write(content)
                    return len(content.encode(encoding))

        except Exception as e:
            logger.error(f"Error writing file {full_path}: {e}")
            raise

    async def delete(
        self,
        file_path: str,
        recursive: bool = False,
    ) -> bool:
        """
        删除文件或目录

        Args:
            file_path: 文件路径
            recursive: 是否递归删除

        Returns:
            是否成功
        """
        full_path = self._resolve_path(file_path)

        try:
            if full_path.is_file():
                full_path.unlink()
            elif full_path.is_dir():
                if recursive:
                    shutil.rmtree(full_path)
                else:
                    full_path.rmdir()
            return True

        except Exception as e:
            logger.error(f"Error deleting {full_path}: {e}")
            return False

    async def exists(self, file_path: str) -> bool:
        """
        检查文件是否存在

        Args:
            file_path: 文件路径

        Returns:
            是否存在
        """
        full_path = self._resolve_path(file_path)
        return full_path.exists()

    async def list_files(
        self,
        directory: str = "",
        pattern: str = "*",
        recursive: bool = False,
    ) -> List[str]:
        """
        列出文件

        Args:
            directory: 目录路径
            pattern: 文件匹配模式
            recursive: 是否递归

        Returns:
            文件路径列表
        """
        full_path = self._resolve_path(directory)

        if recursive:
            files = full_path.rglob(pattern)
        else:
            files = full_path.glob(pattern)

        return [str(f.relative_to(self.base_path)) for f in files if f.is_file()]

    async def get_file_info(
        self,
        file_path: str,
    ) -> Dict[str, Any]:
        """
        获取文件信息

        Args:
            file_path: 文件路径

        Returns:
            文件信息字典
        """
        full_path = self._resolve_path(file_path)

        if not full_path.exists():
            return {}

        stat = full_path.stat()

        return {
            "path": file_path,
            "name": full_path.name,
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
            "is_file": full_path.is_file(),
            "is_dir": full_path.is_dir(),
            "mime_type": mimetypes.guess_type(str(full_path))[0] or "application/octet-stream",
        }

    async def create_directory(
        self,
        dir_path: str,
        parents: bool = True,
    ) -> bool:
        """
        创建目录

        Args:
            dir_path: 目录路径
            parents: 是否创建父目录

        Returns:
            是否成功
        """
        full_path = self._resolve_path(dir_path)

        try:
            full_path.mkdir(parents=parents, exist_ok=True)
            return True
        except Exception as e:
            logger.error(f"Error creating directory {full_path}: {e}")
            return False

    async def copy(
        self,
        src: str,
        dst: str,
    ) -> bool:
        """
        复制文件

        Args:
            src: 源路径
            dst: 目标路径

        Returns:
            是否成功
        """
        src_path = self._resolve_path(src)
        dst_path = self._resolve_path(dst)

        try:
            if src_path.is_file():
                shutil.copy2(src_path, dst_path)
            elif src_path.is_dir():
                shutil.copytree(src_path, dst_path)
            return True
        except Exception as e:
            logger.error(f"Error copying {src} to {dst}: {e}")
            return False

    async def move(
        self,
        src: str,
        dst: str,
    ) -> bool:
        """
        移动文件

        Args:
            src: 源路径
            dst: 目标路径

        Returns:
            是否成功
        """
        src_path = self._resolve_path(src)
        dst_path = self._resolve_path(dst)

        try:
            shutil.move(str(src_path), str(dst_path))
            return True
        except Exception as e:
            logger.error(f"Error moving {src} to {dst}: {e}")
            return False

    async def calculate_hash(
        self,
        file_path: str,
        algorithm: str = "sha256",
    ) -> str:
        """
        计算文件哈希

        Args:
            file_path: 文件路径
            algorithm: 哈希算法

        Returns:
            哈希值
        """
        full_path = self._resolve_path(file_path)

        hash_obj = hashlib.new(algorithm)

        with open(full_path, "rb") as f:
            while chunk := f.read(8192):
                hash_obj.update(chunk)

        return hash_obj.hexdigest()

    def _resolve_path(self, path: str) -> Path:
        """
        解析路径

        Args:
            path: 文件路径

        Returns:
            解析后的完整路径
        """
        # 安全检查：防止路径穿越
        resolved = (self.base_path / path).resolve()

        # 确保解析后的路径在基础路径内
        try:
            resolved.relative_to(self.base_path)
        except ValueError:
            raise ValueError(f"Path traversal detected: {path}")

        return resolved


# 全局本地存储实例
local_storage = LocalStorageAdapter()


__all__ = [
    "LocalStorageAdapter",
    "local_storage",
]
