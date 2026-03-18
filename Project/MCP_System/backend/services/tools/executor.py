"""
Tools Executor Module
工具执行器 - 执行工具并处理结果
"""

import asyncio
import time
import uuid
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor

from backend.core.logging import get_logger
from backend.core.exceptions import ToolNotFoundError, ToolExecutionError, ToolTimeoutError
from backend.services.tools.registry import ToolRegistry, tool_registry
from backend.config import settings

logger = get_logger(__name__)


@dataclass
class ExecutionContext:
    """执行上下文"""
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: Optional[int] = None
    session_id: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionResult:
    """执行结果"""
    success: bool
    content: List[Dict[str, Any]]
    error: Optional[str] = None
    error_code: Optional[str] = None
    duration_ms: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionMetrics:
    """执行指标"""
    total_executions: int = 0
    successful_executions: int = 0
    failed_executions: int = 0
    timeout_executions: int = 0
    total_duration_ms: int = 0

    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.total_executions == 0:
            return 0.0
        return (self.successful_executions / self.total_executions) * 100

    @property
    def average_duration_ms(self) -> float:
        """平均执行时间（毫秒）"""
        if self.total_executions == 0:
            return 0.0
        return self.total_duration_ms / self.total_executions


class ToolExecutor:
    """
    工具执行器

    负责安全、高效地执行工具
    """

    def __init__(self, registry: Optional[ToolRegistry] = None):
        """
        初始化工具执行器

        Args:
            registry: 工具注册表（默认使用全局注册表）
        """
        self.registry = registry or tool_registry
        self.metrics = ExecutionMetrics()

        # 线程池（用于同步工具）
        self._thread_pool = ThreadPoolExecutor(max_workers=settings.TOOL_MAX_CONCURRENT)

        # 幂等性缓存
        self._idempotency_cache: Dict[str, ExecutionResult] = {}

    async def execute(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        context: Optional[ExecutionContext] = None,
    ) -> ExecutionResult:
        """
        执行工具

        Args:
            tool_name: 工具名称
            arguments: 工具参数
            context: 执行上下文

        Returns:
            ExecutionResult

        Raises:
            ToolNotFoundError: 工具不存在
            ToolExecutionError: 工具执行失败
            ToolTimeoutError: 工具执行超时
        """
        context = context or ExecutionContext()

        # 检查工具是否存在
        tool_def = self.registry.get(tool_name)
        if tool_def is None:
            raise ToolNotFoundError(tool_name)

        # 检查工具是否启用
        if not self.registry.is_enabled(tool_name):
            raise ToolExecutionError(
                tool_name=tool_name,
                reason="Tool is disabled",
            )

        # 检查幂等性缓存
        if settings.TOOL_IDEMPOTENCY_ENABLED and tool_def.is_idempotent:
            cache_key = self._generate_idempotency_key(tool_name, arguments)
            if cache_key in self._idempotency_cache:
                logger.debug(f"Returning cached result for {tool_name}")
                return self._idempotency_cache[cache_key]

        # 记录开始时间
        start_time = time.time()

        try:
            # 执行工具
            result = await self._execute_tool(tool_def, arguments, context)

            # 记录成功指标
            duration_ms = int((time.time() - start_time) * 1000)
            self.metrics.total_executions += 1
            self.metrics.successful_executions += 1
            self.metrics.total_duration_ms += duration_ms

            result.duration_ms = duration_ms

            # 缓存结果（如果是幂等的）
            if settings.TOOL_IDEMPOTENCY_ENABLED and tool_def.is_idempotent:
                cache_key = self._generate_idempotency_key(tool_name, arguments)
                self._idempotency_cache[cache_key] = result

            logger.info(
                f"Tool {tool_name} executed successfully in {duration_ms}ms",
                extra={"request_id": context.request_id},
            )

            return result

        except asyncio.TimeoutError:
            # 超时
            self.metrics.total_executions += 1
            self.metrics.timeout_executions += 1

            raise ToolTimeoutError(
                tool_name=tool_name,
                timeout=tool_def.timeout,
            )

        except Exception as e:
            # 执行失败
            self.metrics.total_executions += 1
            self.metrics.failed_executions += 1

            logger.error(
                f"Tool {tool_name} execution failed: {e}",
                extra={"request_id": context.request_id},
            )

            raise ToolExecutionError(
                tool_name=tool_name,
                reason=str(e),
                original_error=type(e).__name__,
            )

    async def _execute_tool(
        self,
        tool_def,
        arguments: Dict[str, Any],
        context: ExecutionContext,
    ) -> ExecutionResult:
        """
        执行工具内部实现

        Args:
            tool_def: 工具定义
            arguments: 参数
            context: 上下文

        Returns:
            ExecutionResult
        """
        # 验证参数
        self._validate_arguments(tool_def, arguments)

        # 执行工具
        if tool_def.is_async:
            # 异步工具
            result_data = await self._execute_async(
                tool_def,
                arguments,
                context,
            )
        else:
            # 同步工具
            result_data = await self._execute_sync(
                tool_def,
                arguments,
                context,
            )

        # 格式化结果
        return self._format_result(result_data)

    async def _execute_async(
        self,
        tool_def,
        arguments: Dict[str, Any],
        context: ExecutionContext,
    ) -> Any:
        """执行异步工具"""
        try:
            # 带超时执行
            result = await asyncio.wait_for(
                tool_def.handler(arguments, context),
                timeout=tool_def.timeout,
            )
            return result
        except asyncio.TimeoutError:
            logger.warning(f"Async tool {tool_def.name} timed out")
            raise

    async def _execute_sync(
        self,
        tool_def,
        arguments: Dict[str, Any],
        context: ExecutionContext,
    ) -> Any:
        """执行同步工具"""
        loop = asyncio.get_event_loop()

        try:
            # 在线程池中执行
            result = await asyncio.wait_for(
                loop.run_in_executor(
                    self._thread_pool,
                    tool_def.handler,
                    arguments,
                    context,
                ),
                timeout=tool_def.timeout,
            )
            return result
        except asyncio.TimeoutError:
            logger.warning(f"Sync tool {tool_def.name} timed out")
            raise

    def _validate_arguments(
        self,
        tool_def,
        arguments: Dict[str, Any],
    ) -> None:
        """
        验证参数

        Args:
            tool_def: 工具定义
            arguments: 参数

        Raises:
            ToolExecutionError: 参数验证失败
        """
        schema = tool_def.input_schema

        # 检查必需参数
        required = schema.get("required", [])
        for param in required:
            if param not in arguments:
                raise ToolExecutionError(
                    tool_name=tool_def.name,
                    reason=f"Missing required parameter: {param}",
                )

        # 检查额外参数（可选）
        # if "additionalProperties" not in schema or not schema["additionalProperties"]:
        #     allowed = set(schema.get("properties", {}).keys())
        #     for param in arguments:
        #         if param not in allowed:
        #             raise ToolExecutionError(
        #                 tool_name=tool_def.name,
        #                 reason=f"Unknown parameter: {param}",
        #             )

    def _format_result(self, result_data: Any) -> ExecutionResult:
        """
        格式化结果

        Args:
            result_data: 原始结果数据

        Returns:
            ExecutionResult
        """
        # 如果结果是 ExecutionResult，直接返回
        if isinstance(result_data, ExecutionResult):
            return result_data

        # 如果是字典，检查格式
        if isinstance(result_data, dict):
            if "content" in result_data:
                # 已有 content 字段
                return ExecutionResult(
                    success=not result_data.get("isError", False),
                    content=result_data["content"],
                    error=result_data.get("error"),
                    error_code=result_data.get("errorCode"),
                )
            else:
                # 转换为 content
                return ExecutionResult(
                    success=True,
                    content=[{"type": "text", "text": str(result_data)}],
                )

        # 其他类型，转换为文本
        return ExecutionResult(
            success=True,
            content=[{"type": "text", "text": str(result_data)}],
        )

    def _generate_idempotency_key(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> str:
        """
        生成幂等性键

        Args:
            tool_name: 工具名称
            arguments: 参数

        Returns:
            幂等性键
        """
        import hashlib
        import json

        # 对参数进行排序，确保顺序不影响结果
        normalized_args = json.dumps(arguments, sort_keys=True)
        key_data = f"{tool_name}:{normalized_args}"
        return hashlib.sha256(key_data.encode()).hexdigest()

    def clear_idempotency_cache(self) -> None:
        """清空幂等性缓存"""
        self._idempotency_cache.clear()
        logger.debug("Idempotency cache cleared")

    def get_metrics(self) -> Dict[str, Any]:
        """
        获取执行指标

        Returns:
            指标字典
        """
        return {
            "total_executions": self.metrics.total_executions,
            "successful_executions": self.metrics.successful_executions,
            "failed_executions": self.metrics.failed_executions,
            "timeout_executions": self.metrics.timeout_executions,
            "success_rate": self.metrics.success_rate,
            "average_duration_ms": self.metrics.average_duration_ms,
        }

    async def execute_batch(
        self,
        requests: List[Dict[str, Any]],
        context: Optional[ExecutionContext] = None,
    ) -> List[ExecutionResult]:
        """
        批量执行工具

        Args:
            requests: 请求列表，每个请求包含 tool_name 和 arguments
            context: 执行上下文

        Returns:
            执行结果列表
        """
        context = context or ExecutionContext()

        # 创建任务
        tasks = [
            self.execute(
                req["tool_name"],
                req.get("arguments", {}),
                context,
            )
            for req in requests
        ]

        # 并发执行
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理结果
        formatted_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                formatted_results.append(
                    ExecutionResult(
                        success=False,
                        content=[],
                        error=str(result),
                        error_code=type(result).__name__,
                    )
                )
            else:
                formatted_results.append(result)

        return formatted_results


# 全局工具执行器
tool_executor = ToolExecutor()


__all__ = [
    "ExecutionContext",
    "ExecutionResult",
    "ExecutionMetrics",
    "ToolExecutor",
    "tool_executor",
]
