"""
Result Aggregator Module
结果聚合器 - 多工具调用结果合并
"""

from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
import asyncio

from backend.core.logging import get_logger
from backend.services.tools import ExecutionResult, ExecutionContext

logger = get_logger(__name__)


@dataclass
class AggregatedResult:
    """聚合结果"""
    success: bool
    results: List[ExecutionResult] = field(default_factory=list)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    duration_ms: Optional[int] = None

    def get_content(self) -> List[Dict[str, Any]]:
        """获取所有内容"""
        content = []
        for result in self.results:
            if result.success:
                content.extend(result.content or [])
        return content

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "success": self.success,
            "results": [r.__dict__ for r in self.results],
            "errors": self.errors,
            "metadata": self.metadata,
            "duration_ms": self.duration_ms,
        }


class ResultAggregator:
    """
    结果聚合器

    合并多个工具调用的结果
    """

    def __init__(self):
        self._aggregation_strategies = {
            "sequential": self._aggregate_sequential,
            "parallel": self._aggregate_parallel,
            "merge": self._aggregate_merge,
            "first_success": self._aggregate_first_success,
            "majority": self._aggregate_majority,
        }

    async def aggregate(
        self,
        results: List[ExecutionResult],
        strategy: str = "merge",
    ) -> AggregatedResult:
        """
        聚合结果

        Args:
            results: 执行结果列表
            strategy: 聚合策略

        Returns:
            AggregatedResult
        """
        aggregator = self._aggregation_strategies.get(
            strategy,
            self._aggregate_merge,
        )
        return await aggregator(results)

    async def _aggregate_sequential(
        self,
        results: List[ExecutionResult],
    ) -> AggregatedResult:
        """
        顺序聚合（保持顺序）

        Args:
            results: 执行结果列表

        Returns:
            AggregatedResult
        """
        success = all(r.success for r in results)
        errors = [
            {"tool": "unknown", "error": r.error}
            for r in results
            if not r.success and r.error
        ]

        return AggregatedResult(
            success=success,
            results=results,
            errors=errors,
            metadata={"strategy": "sequential"},
        )

    async def _aggregate_parallel(
        self,
        results: List[ExecutionResult],
    ) -> AggregatedResult:
        """
        并行聚合（无序）

        Args:
            results: 执行结果列表

        Returns:
            AggregatedResult
        """
        success = all(r.success for r in results)
        errors = [
            {"tool": "unknown", "error": r.error}
            for r in results
            if not r.success and r.error
        ]

        return AggregatedResult(
            success=success,
            results=results,
            errors=errors,
            metadata={"strategy": "parallel"},
        )

    async def _aggregate_merge(
        self,
        results: List[ExecutionResult],
    ) -> AggregatedResult:
        """
        合并聚合（合并所有内容）

        Args:
            results: 执行结果列表

        Returns:
            AggregatedResult
        """
        success = all(r.success for r in results)
        errors = [
            {"tool": "unknown", "error": r.error}
            for r in results
            if not r.success and r.error
        ]

        return AggregatedResult(
            success=success,
            results=results,
            errors=errors,
            metadata={"strategy": "merge"},
        )

    async def _aggregate_first_success(
        self,
        results: List[ExecutionResult],
    ) -> AggregatedResult:
        """
        首个成功聚合

        Args:
            results: 执行结果列表

        Returns:
            AggregatedResult
        """
        for result in results:
            if result.success:
                return AggregatedResult(
                    success=True,
                    results=[result],
                    metadata={"strategy": "first_success"},
                )

        # 全部失败
        return AggregatedResult(
            success=False,
            results=results,
            errors=[
                {"tool": "unknown", "error": r.error}
                for r in results
                if r.error
            ],
            metadata={"strategy": "first_success"},
        )

    async def _aggregate_majority(
        self,
        results: List[ExecutionResult],
    ) -> AggregatedResult:
        """
        多数聚合（多数结果决定）

        Args:
            results: 执行结果列表

        Returns:
            AggregatedResult
        """
        success_count = sum(1 for r in results if r.success)
        total_count = len(results)
        success = success_count > total_count / 2

        errors = [
            {"tool": "unknown", "error": r.error}
            for r in results
            if not r.success and r.error
        ]

        return AggregatedResult(
            success=success,
            results=results,
            errors=errors,
            metadata={
                "strategy": "majority",
                "success_count": success_count,
                "total_count": total_count,
            },
        )

    def format_result(
        self,
        aggregated: AggregatedResult,
        format_type: str = "text",
    ) -> str:
        """
        格式化聚合结果

        Args:
            aggregated: 聚合结果
            format_type: 格式类型 (text, json, markdown)

        Returns:
            格式化字符串
        """
        if format_type == "json":
            import json
            return json.dumps(aggregated.to_dict())

        elif format_type == "markdown":
            lines = []
            lines.append(f"## Result Summary")
            lines.append(f"**Success**: {aggregated.success}")
            lines.append(f"**Duration**: {aggregated.duration_ms}ms" if aggregated.duration_ms else "")
            lines.append("")

            if aggregated.results:
                lines.append("### Individual Results")
                for i, result in enumerate(aggregated.results, 1):
                    lines.append(f"#### Result {i}")
                    lines.append(f"- **Success**: {result.success}")
                    if result.content:
                        lines.append(f"- **Content**: {len(result.content)} items")
                    if result.error:
                        lines.append(f"- **Error**: {result.error}")
                    lines.append("")

            if aggregated.errors:
                lines.append("### Errors")
                for error in aggregated.errors:
                    lines.append(f"- {error}")

            return "\n".join(lines)

        else:  # text
            lines = []
            lines.append(f"Result Summary:")
            lines.append(f"  Success: {aggregated.success}")
            if aggregated.duration_ms:
                lines.append(f"  Duration: {aggregated.duration_ms}ms")
            lines.append(f"  Results: {len(aggregated.results)}")

            if aggregated.errors:
                lines.append(f"  Errors: {len(aggregated.errors)}")

            return "\n".join(lines)


# 全局结果聚合器
result_aggregator = ResultAggregator()


__all__ = [
    "AggregatedResult",
    "ResultAggregator",
    "result_aggregator",
]
