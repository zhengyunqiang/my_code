"""
Schema Mapper Module
Schema 映射器 - 参数映射和类型转换
"""

import json
from typing import Dict, Any, Optional, List, Type, get_type_hints
from dataclasses import is_dataclass, asdict
from enum import Enum
from datetime import datetime
import inspect

from backend.core.logging import get_logger
from backend.core.exceptions import SchemaValidationError, TypeValidationError

logger = get_logger(__name__)


class SchemaMapper:
    """
    Schema 映射器

    将 AI 模型理解的描述性参数映射为后端函数所需的强类型参数
    """

    def __init__(self):
        self._type_converters = {
            "string": self._convert_to_string,
            "integer": self._convert_to_int,
            "number": self._convert_to_float,
            "boolean": self._convert_to_bool,
            "array": self._convert_to_list,
            "object": self._convert_to_dict,
        }

    def map_parameters(
        self,
        input_schema: Dict[str, Any],
        input_values: Dict[str, Any],
        target_schema: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        映射参数

        Args:
            input_schema: 输入 JSON Schema
            input_values: 输入值字典
            target_schema: 目标 Schema（可选）

        Returns:
            映射后的参数字典
        """
        result = {}

        # 遍历输入 Schema 的属性
        properties = input_schema.get("properties", {})
        required = set(input_schema.get("required", []))

        for prop_name, prop_def in properties.items():
            # 检查是否提供了值
            if prop_name not in input_values:
                if prop_name in required:
                    raise SchemaValidationError(
                        message=f"Missing required parameter: {prop_name}",
                        field_errors={prop_name: "Required field is missing"},
                    )
                continue

            value = input_values[prop_name]
            prop_type = prop_def.get("type", "string")

            # 转换类型
            try:
                converted = self._convert_type(value, prop_type, prop_def)
                result[prop_name] = converted
            except Exception as e:
                raise TypeValidationError(
                    field=prop_name,
                    expected_type=prop_type,
                    actual_type=type(value).__name__,
                )

        # 应用目标 Schema 映射
        if target_schema:
            result = self._apply_target_mapping(result, target_schema)

        return result

    def _convert_type(
        self,
        value: Any,
        target_type: str,
        type_def: Dict[str, Any],
    ) -> Any:
        """
        转换类型

        Args:
            value: 原始值
            target_type: 目标类型
            type_def: 类型定义

        Returns:
            转换后的值
        """
        converter = self._type_converters.get(target_type)
        if converter:
            return converter(value, type_def)

        # 未知类型，返回原值
        return value

    def _convert_to_string(self, value: Any, type_def: Dict[str, Any]) -> str:
        """转换为字符串"""
        if isinstance(value, str):
            return value
        return str(value)

    def _convert_to_int(self, value: Any, type_def: Dict[str, Any]) -> int:
        """转换为整数"""
        if isinstance(value, int):
            return value

        if isinstance(value, float):
            return int(value)

        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                pass

        # 处理枚举
        if "enum" in type_def:
            enum_values = type_def["enum"]
            if value in enum_values:
                return enum_values.index(value)

        raise TypeValidationError(
            field="unknown",
            expected_type="integer",
            actual_type=type(value).__name__,
        )

    def _convert_to_float(self, value: Any, type_def: Dict[str, Any]) -> float:
        """转换为浮点数"""
        if isinstance(value, float):
            return value

        if isinstance(value, int):
            return float(value)

        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                pass

        raise TypeValidationError(
            field="unknown",
            expected_type="number",
            actual_type=type(value).__name__,
        )

    def _convert_to_bool(self, value: Any, type_def: Dict[str, Any]) -> bool:
        """转换为布尔值"""
        if isinstance(value, bool):
            return value

        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes", "on")

        if isinstance(value, (int, float)):
            return value != 0

        return bool(value)

    def _convert_to_list(self, value: Any, type_def: Dict[str, Any]) -> list:
        """转换为列表"""
        if isinstance(value, list):
            return value

        if isinstance(value, str):
            try:
                # 尝试解析 JSON 数组
                return json.loads(value)
            except json.JSONDecodeError:
                # 返回单元素列表
                return [value]

        return [value]

    def _convert_to_dict(self, value: Any, type_def: Dict[str, Any]) -> dict:
        """转换为字典"""
        if isinstance(value, dict):
            return value

        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                pass

        return {"value": value}

    def _apply_target_mapping(
        self,
        values: Dict[str, Any],
        target_schema: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        应用目标 Schema 映射

        Args:
            values: 原始值字典
            target_schema: 目标 Schema

        Returns:
            映射后的字典
        """
        result = {}

        # 处理字段映射
        field_mapping = target_schema.get("fieldMapping", {})
        for target_field, source_field in field_mapping.items():
            if source_field in values:
                result[target_field] = values[source_field]

        # 处理默认值
        defaults = target_schema.get("defaults", {})
        for field, default_value in defaults.items():
            if field not in result and field not in values:
                result[field] = default_value

        # 添加未映射的字段
        for field, value in values.items():
            if field not in result:
                result[field] = value

        return result

    def validate_schema(
        self,
        schema: Dict[str, Any],
    ) -> List[str]:
        """
        验证 Schema

        Args:
            schema: JSON Schema

        Returns:
            验证错误列表
        """
        errors = []

        # 检查必需字段
        if "type" not in schema:
            errors.append("Missing 'type' field")

        if schema.get("type") == "object":
            if "properties" not in schema:
                errors.append("Object type must have 'properties'")

        # 检查类型值
        valid_types = {"string", "integer", "number", "boolean", "array", "object"}
        if "type" in schema and schema["type"] not in valid_types:
            errors.append(f"Invalid type: {schema['type']}")

        return errors

    def merge_schemas(
        self,
        base_schema: Dict[str, Any],
        override_schema: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        合并 Schema

        Args:
            base_schema: 基础 Schema
            override_schema: 覆盖 Schema

        Returns:
            合并后的 Schema
        """
        result = base_schema.copy()

        for key, value in override_schema.items():
            if key == "properties" and "properties" in result:
                result["properties"] = {**result["properties"], **value}
            elif key == "required" and "required" in result:
                result["required"] = list(set(result["required"] + value))
            else:
                result[key] = value

        return result


class FunctionSchemaGenerator:
    """
    函数 Schema 生成器

    从 Python 函数生成 JSON Schema
    """

    def __init__(self, mapper: Optional[SchemaMapper] = None):
        """
        初始化

        Args:
            mapper: Schema 映射器
        """
        self.mapper = mapper or SchemaMapper()

    def generate_schema(
        self,
        func: callable,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        生成函数的 JSON Schema

        Args:
            func: 函数对象
            description: 函数描述

        Returns:
            JSON Schema
        """
        # 获取函数签名
        sig = inspect.signature(func)
        type_hints = get_type_hints(func)

        # 生成属性定义
        properties = {}
        required = []

        for param_name, param in sig.parameters.items():
            # 跳过 self 和上下文参数
            if param_name in ["self", "cls", "context", "ctx"]:
                continue

            param_type = type_hints.get(param_name, str)

            # 生成属性定义
            prop_def = self._type_to_schema(param_type)
            properties[param_name] = prop_def

            # 检查是否必需
            if param.default == inspect.Parameter.empty:
                required.append(param_name)

        return {
            "type": "object",
            "properties": properties,
            "required": required,
            "description": description or func.__doc__ or "",
        }

    def _type_to_schema(self, type_hint: Type) -> Dict[str, Any]:
        """
        将类型提示转换为 Schema 定义

        Args:
            type_hint: 类型提示

        Returns:
            Schema 定义
        """
        origin = getattr(type_hint, "__origin__", None)

        # 处理泛型
        if origin is list or origin is List:
            return {"type": "array"}

        if origin is dict or origin is Dict:
            return {"type": "object"}

        if origin is Optional:
            # 可选类型
            inner_type = type_hint.__args__[0]
            return self._type_to_schema(inner_type)

        # 基本类型
        if type_hint is str:
            return {"type": "string"}

        if type_hint is int:
            return {"type": "integer"}

        if type_hint is float:
            return {"type": "number"}

        if type_hint is bool:
            return {"type": "boolean"}

        # 枚举
        if isinstance(type_hint, type) and issubclass(type_hint, Enum):
            return {
                "type": "string",
                "enum": [e.value for e in type_hint],
            }

        # 默认为字符串
        return {"type": "string"}


# 全局实例
schema_mapper = SchemaMapper()
schema_generator = FunctionSchemaGenerator()


__all__ = [
    "SchemaMapper",
    "FunctionSchemaGenerator",
    "schema_mapper",
    "schema_generator",
]
