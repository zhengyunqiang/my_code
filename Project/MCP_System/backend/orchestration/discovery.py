"""
Tool Discovery Service Module
工具发现服务 - 基于上下文动态发现可用工具
"""

import re
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime

from backend.core.logging import get_logger
from backend.services.tools import ToolRegistry, tool_registry, ToolStatus

logger = get_logger(__name__)


@dataclass
class DiscoveryContext:
    """发现上下文"""
    user_id: Optional[int] = None
    session_id: Optional[str] = None
    current_file: Optional[str] = None
    current_directory: Optional[str] = None
    language: Optional[str] = None
    framework: Optional[str] = None
    capabilities: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def has_capability(self, capability: str) -> bool:
        """检查是否有特定能力"""
        return capability in self.capabilities

    def add_capability(self, capability: str) -> None:
        """添加能力"""
        self.capabilities.add(capability)


@dataclass
class ToolMatch:
    """工具匹配结果"""
    tool_name: str
    score: float
    reason: str
    category: str


class ToolDiscoveryService:
    """
    工具发现服务

    根据当前上下文动态发现和推荐可用工具
    """

    def __init__(self, registry: Optional[ToolRegistry] = None):
        """
        初始化工具发现服务

        Args:
            registry: 工具注册表（默认使用全局注册表）
        """
        self.registry = registry or tool_registry

        # 语言-工具映射
        self._language_tools: Dict[str, List[str]] = {
            "python": [
                "run_python_script",
                "python_lint",
                "python_format",
                "python_test",
            ],
            "javascript": [
                "run_javascript",
                "npm_install",
                "javascript_lint",
            ],
            "typescript": [
                "compile_typescript",
                "typescript_lint",
            ],
            "java": [
                "compile_java",
                "java_test",
            ],
            "go": [
                "run_go",
                "go_test",
            ],
            "rust": [
                "cargo_build",
                "cargo_test",
            ],
        }

        # 文件扩展名-语言映射
        self._extension_language: Dict[str, str] = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".java": "java",
            ".go": "go",
            ".rs": "rust",
            ".c": "c",
            ".cpp": "cpp",
            ".h": "c",
            ".hpp": "cpp",
            ".cs": "csharp",
            ".php": "php",
            ".rb": "ruby",
            ".swift": "swift",
            ".kt": "kotlin",
            ".scala": "scala",
        }

        # 框架-工具映射
        self._framework_tools: Dict[str, List[str]] = {
            "fastapi": [
                "start_fastapi_server",
                "fastapi_route_test",
            ],
            "django": [
                "django_migrate",
                "django_collectstatic",
            ],
            "flask": [
                "flask_run",
            ],
            "react": [
                "npm_start",
                "npm_build",
            ],
            "vue": [
                "npm_dev",
            ],
            "next": [
                "next_dev",
                "next_build",
            ],
        }

    def discover(
        self,
        context: DiscoveryContext,
        query: Optional[str] = None,
        limit: int = 10,
    ) -> List[ToolMatch]:
        """
        发现可用工具

        Args:
            context: 发现上下文
            query: 搜索查询（可选）
            limit: 返回结果限制

        Returns:
            工具匹配列表（按分数排序）
        """
        matches: Dict[str, ToolMatch] = {}

        # 1. 基于语言发现工具
        if context.language:
            language_tools = self._language_tools.get(context.language, [])
            for tool_name in language_tools:
                if self.registry.is_enabled(tool_name):
                    matches[tool_name] = ToolMatch(
                        tool_name=tool_name,
                        score=0.8,
                        reason=f"Language: {context.language}",
                        category=self._get_tool_category(tool_name),
                    )

        # 2. 基于框架发现工具
        if context.framework:
            framework_tools = self._framework_tools.get(context.framework, [])
            for tool_name in framework_tools:
                score = 0.9 if tool_name in matches else 0.7
                if self.registry.is_enabled(tool_name):
                    matches[tool_name] = ToolMatch(
                        tool_name=tool_name,
                        score=score,
                        reason=f"Framework: {context.framework}",
                        category=self._get_tool_category(tool_name),
                    )

        # 3. 基于文件类型发现工具
        if context.current_file:
            language = self._detect_language_from_file(context.current_file)
            if language:
                language_tools = self._language_tools.get(language, [])
                for tool_name in language_tools:
                    if tool_name not in matches and self.registry.is_enabled(tool_name):
                        matches[tool_name] = ToolMatch(
                            tool_name=tool_name,
                            score=0.6,
                            reason=f"File type: {language}",
                            category=self._get_tool_category(tool_name),
                        )

        # 4. 基于能力发现工具
        for capability in context.capabilities:
            capability_tools = self._get_tools_for_capability(capability)
            for tool_name in capability_tools:
                if tool_name not in matches and self.registry.is_enabled(tool_name):
                    matches[tool_name] = ToolMatch(
                        tool_name=tool_name,
                        score=0.5,
                        reason=f"Capability: {capability}",
                        category=self._get_tool_category(tool_name),
                    )

        # 5. 基于查询文本匹配
        if query:
            query_matches = self._search_by_query(query)
            for tool_name, score in query_matches.items():
                if tool_name not in matches and self.registry.is_enabled(tool_name):
                    matches[tool_name] = ToolMatch(
                        tool_name=tool_name,
                        score=score * 0.4,  # 降低文本匹配的权重
                        reason=f"Query match: {query}",
                        category=self._get_tool_category(tool_name),
                    )

        # 排序并限制结果
        sorted_matches = sorted(
            matches.values(),
            key=lambda m: m.score,
            reverse=True,
        )[:limit]

        logger.debug(
            f"Tool discovery: found {len(sorted_matches)} tools for context",
            extra={"context": str(context)},
        )

        return sorted_matches

    def _detect_language_from_file(self, file_path: str) -> Optional[str]:
        """
        从文件路径检测语言

        Args:
            file_path: 文件路径

        Returns:
            语言名称或 None
        """
        # 检查文件扩展名
        for ext, lang in self._extension_language.items():
            if file_path.endswith(ext):
                return lang

        return None

    def _get_tool_category(self, tool_name: str) -> str:
        """
        获取工具分类

        Args:
            tool_name: 工具名称

        Returns:
            分类名称
        """
        tool_def = self.registry.get(tool_name)
        if tool_def:
            return tool_def.category
        return "general"

    def _get_tools_for_capability(self, capability: str) -> List[str]:
        """
        获取支持特定能力的工具

        Args:
            capability: 能力名称

        Returns:
            工具名称列表
        """
        # 简化实现：基于工具名称模式匹配
        capability_map = {
            "file_operations": ["read_file", "write_file", "list_files", "delete_file"],
            "code_execution": ["run_python", "run_javascript", "execute_command"],
            "testing": ["python_test", "go_test", "cargo_test"],
            "linting": ["python_lint", "javascript_lint", "typescript_lint"],
            "formatting": ["python_format", "javascript_format"],
            "build": ["cargo_build", "compile_java", "compile_typescript"],
            "database": ["query_database", "migrate_database"],
            "api": ["call_api", "test_endpoint"],
        }

        return capability_map.get(capability, [])

    def _search_by_query(self, query: str) -> Dict[str, float]:
        """
        基于查询文本搜索工具

        Args:
            query: 查询字符串

        Returns:
            工具名称-分数字典
        """
        query_lower = query.lower()
        matches = {}

        for tool_def in self.registry.list_tools():
            # 搜索工具名称
            name_score = self._fuzzy_match(query_lower, tool_def.name.lower())

            # 搜索描述
            desc_score = self._fuzzy_match(query_lower, tool_def.description.lower())

            # 搜索标签
            tag_score = 0
            for tag in tool_def.tags:
                tag_score = max(tag_score, self._fuzzy_match(query_lower, tag.lower()))

            # 综合分数
            score = max(name_score, desc_score, tag_score)

            if score > 0.3:  # 阈值
                matches[tool_def.name] = score

        return matches

    def _fuzzy_match(self, query: str, text: str) -> float:
        """
        模糊匹配

        Args:
            query: 查询字符串
            text: 目标文本

        Returns:
            匹配分数 (0-1)
        """
        # 精确匹配
        if query == text:
            return 1.0

        # 包含匹配
        if query in text:
            return 0.8

        # 单词匹配
        query_words = set(query.split())
        text_words = set(text.split())

        if query_words & text_words:  # 有交集
            intersection = query_words & text_words
            return len(intersection) / len(query_words)

        return 0.0

    def get_recommended_tools(
        self,
        context: DiscoveryContext,
    ) -> List[str]:
        """
        获取推荐工具列表（简化版）

        Args:
            context: 发现上下文

        Returns:
            工具名称列表
        """
        matches = self.discover(context, limit=5)
        return [m.tool_name for m in matches]


# 全局工具发现服务
tool_discovery = ToolDiscoveryService()


__all__ = [
    "DiscoveryContext",
    "ToolMatch",
    "ToolDiscoveryService",
    "tool_discovery",
]
