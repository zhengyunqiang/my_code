"""
Input Sanitization Module
输入清洗模块 - 防范 Prompt 注入和恶意输入
"""

import re
import html
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass

from backend.core.logging import get_logger
from backend.core.exceptions import PromptInjectionError
from backend.config import settings

logger = get_logger(__name__)


@dataclass
class SanitizationResult:
    """清洗结果"""
    is_clean: bool
    original: str
    sanitized: str
    detected_issues: List[str]
    severity: str  # low, medium, high, critical


class InputSanitizer:
    """
    输入清洗器

    检测和清洗恶意输入，包括：
    - Prompt 注入检测
    - 特殊字符过滤
    - 控制字符处理
    - 输入长度验证
    """

    def __init__(self):
        # Prompt 注入模式（可配置）
        self.injection_patterns = set(settings.PROMPT_INJECTION_PATTERNS)

        # 扩展的注入模式
        self._extended_patterns = {
            # 越狱尝试
            r"ignore\s+(all\s+)?(previous|above|the)\s+instructions?",
            r"disregard\s+(everything|all|the\s+above)",
            r"forget\s+(everything|all|previous)",
            r"override\s+(the\s+)?(system|default)",
            r"bypass\s+(security|restrictions|filters)",
            # 角色切换
            r"you\s+are\s+(now\s+)?(no\s+longer|not)",
            r"act\s+as\s+(if\s+you\s+were|a\s+different)",
            r"pretend\s+(to\s+be|you\s+are)",
            r"roleplay\s+as",
            # 指令泄露
            r"show\s+(me\s+)?your\s+(instructions|prompt|system)",
            r"print\s+(your\s+)?(instructions|prompt)",
            r"tell\s+me\s+(how\s+you\s+work|your\s+rules)",
            r"repeat\s+(everything|the\s+above|back\s+to\s+me)",
            # 编码尝试
            r"(base64|rot13|hex|ascii)\s+(decode|encode)",
            r"translate\s+to\s+(base64|rot13|hex)",
        }

        # 控制字符（除了常见的换行、制表符）
        self.control_chars = {
            c for c in range(0x00, 0x20)
            if c not in (0x09, 0x0A, 0x0D)  # Tab, LF, CR
        }

        # 危险字符（在某些上下文中）
        self.dangerous_chars = {
            '\x00',  # Null 字节
            '\x1B',  # Escape
        }

        # 最大输入长度
        self.max_input_length = settings.MAX_INPUT_LENGTH

    def add_injection_pattern(self, pattern: str) -> None:
        """
        添加注入模式

        Args:
            pattern: 模式字符串
        """
        self.injection_patterns.add(pattern.lower())
        logger.debug(f"Added injection pattern: {pattern}")

    def remove_injection_pattern(self, pattern: str) -> None:
        """
        移除注入模式

        Args:
            pattern: 模式字符串
        """
        self.injection_patterns.discard(pattern.lower())
        logger.debug(f"Removed injection pattern: {pattern}")

    def sanitize(
        self,
        input_text: str,
        check_injection: bool = True,
        check_length: bool = True,
        check_control_chars: bool = True,
    ) -> SanitizationResult:
        """
        清洗输入

        Args:
            input_text: 输入文本
            check_injection: 是否检查注入
            check_length: 是否检查长度
            check_control_chars: 是否检查控制字符

        Returns:
            SanitizationResult
        """
        original = input_text
        sanitized = input_text
        detected_issues = []
        severity = "low"

        # 检查长度
        if check_length and len(sanitized) > self.max_input_length:
            detected_issues.append(
                f"Input too long: {len(sanitized)} > {self.max_input_length}"
            )
            sanitized = sanitized[: self.max_input_length]
            severity = "medium"

        # 检查控制字符
        if check_control_chars:
            has_control_chars = any(ord(c) in self.control_chars for c in sanitized)
            if has_control_chars:
                detected_issues.append("Contains control characters")
                # 移除控制字符
                sanitized = "".join(
                    c for c in sanitized
                    if ord(c) not in self.control_chars
                )
                severity = "medium"

        # 检查注入
        if check_injection and settings.PROMPT_INJECTION_ENABLED:
            injection_result = self._check_injection(sanitized)
            if injection_result:
                detected_issues.extend(injection_result["issues"])
                severity = injection_result["severity"]
                # 不修改输入内容，仅记录问题

        is_clean = len(detected_issues) == 0

        return SanitizationResult(
            is_clean=is_clean,
            original=original,
            sanitized=sanitized,
            detected_issues=detected_issues,
            severity=severity,
        )

    def _check_injection(self, input_text: str) -> Optional[Dict[str, Any]]:
        """
        检查 Prompt 注入

        Args:
            input_text: 输入文本

        Returns:
            检测结果字典，无注入返回 None
        """
        input_lower = input_text.lower()
        detected_patterns = []
        severity = "low"

        # 检查配置的模式
        for pattern in self.injection_patterns:
            if pattern in input_lower:
                detected_patterns.append(pattern)
                severity = "high"

        # 检查扩展模式
        for pattern in self._extended_patterns:
            if re.search(pattern, input_lower):
                detected_patterns.append(f"regex: {pattern}")
                severity = "critical"

        if detected_patterns:
            return {
                "issues": [f"Prompt injection detected: {p}" for p in detected_patterns],
                "severity": severity,
                "patterns": detected_patterns,
            }

        return None

    def escape_html(self, text: str) -> str:
        """
        转义 HTML 特殊字符

        Args:
            text: 输入文本

        Returns:
            转义后的文本
        """
        return html.escape(text)

    def escape_shell(self, text: str) -> str:
        """
        转义 Shell 特殊字符

        Args:
            text: 输入文本

        Returns:
            转义后的文本
        """
        # 简单的 shell 转义
        return "'" + text.replace("'", "'\"'\"'") + "'"

    def escape_sql(self, text: str) -> str:
        """
        转义 SQL 特殊字符

        Args:
            text: 输入文本

        Returns:
            转义后的文本
        """
        # 简单的 SQL 转义
        return text.replace("'", "''").replace("\\", "\\\\")

    def sanitize_dict(
        self,
        data: Dict[str, Any],
        **kwargs,
    ) -> Dict[str, Any]:
        """
        清洗字典中的所有字符串值

        Args:
            data: 输入字典
            **kwargs: 传递给 sanitize 的额外参数

        Returns:
            清洗后的字典
        """
        result = {}
        for key, value in data.items():
            if isinstance(value, str):
                sanitization_result = self.sanitize(value, **kwargs)
                result[key] = sanitization_result.sanitized
            elif isinstance(value, dict):
                result[key] = self.sanitize_dict(value, **kwargs)
            elif isinstance(value, list):
                result[key] = self.sanitize_list(value, **kwargs)
            else:
                result[key] = value
        return result

    def sanitize_list(
        self,
        data: List[Any],
        **kwargs,
    ) -> List[Any]:
        """
        清洗列表中的所有字符串值

        Args:
            data: 输入列表
            **kwargs: 传递给 sanitize 的额外参数

        Returns:
            清洗后的列表
        """
        result = []
        for item in data:
            if isinstance(item, str):
                sanitization_result = self.sanitize(item, **kwargs)
                result.append(sanitization_result.sanitized)
            elif isinstance(item, dict):
                result.append(self.sanitize_dict(item, **kwargs))
            elif isinstance(item, list):
                result.append(self.sanitize_list(item, **kwargs))
            else:
                result.append(item)
        return result

    def validate_and_sanitize(
        self,
        input_text: str,
        raise_on_injection: bool = True,
        **kwargs,
    ) -> str:
        """
        验证并清洗输入

        Args:
            input_text: 输入文本
            raise_on_injection: 检测到注入时是否抛出异常
            **kwargs: 传递给 sanitize 的额外参数

        Returns:
            清洗后的文本

        Raises:
            PromptInjectionError: 检测到注入且 raise_on_injection=True
        """
        result = self.sanitize(input_text, **kwargs)

        if not result.is_clean:
            # 检查是否有注入问题
            injection_issues = [
                issue for issue in result.detected_issues
                if "injection" in issue.lower()
            ]

            if injection_issues and raise_on_injection:
                raise PromptInjectionError(
                    detected_patterns=injection_issues,
                    input_source="user_input",
                )

        return result.sanitized


# 全局实例
input_sanitizer = InputSanitizer()


__all__ = [
    "SanitizationResult",
    "InputSanitizer",
    "input_sanitizer",
]
