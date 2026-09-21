"""JSON Schema 校验封装，把 jsonschema 的英文报错映射为中文提示。"""

from dataclasses import dataclass
from typing import Any, Mapping

from jsonschema import Draft7Validator, FormatChecker
from jsonschema.exceptions import SchemaError

from app.server.process.src.constants import MAX_CONFIG_ISSUES_PER_NODE


# JSON Schema 类型名到中文的映射。
JSON_TYPE_NAMES: dict[str, str] = {
    "string": "字符串",
    "integer": "整数",
    "number": "数字",
    "boolean": "布尔值",
    "object": "对象",
    "array": "数组",
    "null": "空值",
}


@dataclass(frozen=True)
class JsonSchemaIssue:
    """一条配置结构错误。"""

    path: str
    message: str


def resolve_json_type(value: Any) -> str:
    """返回一个 JSON 值对应的 JSON Schema 类型名。

    bool 是 int 的子类，必须先判断布尔值，否则 True 会被判断成整数。
    返回值用于和 Schema 中声明的 type 直接比较。
    """

    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, Mapping):
        return "object"
    if isinstance(value, (list, tuple)):
        return "array"
    return type(value).__name__


def describe_json_type(value: Any) -> str:
    """返回一个 JSON 值的中文类型名，用于拼装错误提示。"""

    return JSON_TYPE_NAMES.get(resolve_json_type(value), resolve_json_type(value))


def check_schema(schema: Mapping[str, Any], *, label: str = "配置") -> str | None:
    """校验 JSON Schema 本身是否合法，非法时返回中文提示。

    节点定义保存的 config_schema_json 和流程保存的表单 Schema 都会在后续被反复
    使用，因此写入前必须先确认它本身合法，否则之后每次校验都会失败。
    """

    try:
        Draft7Validator.check_schema(schema)
    except SchemaError as exc:
        return f"{label} Schema 非法：{exc.message}"
    return None


def validate_object_schema(
    schema: dict[str, Any],
    *,
    label: str = "配置",
) -> dict[str, Any]:
    """校验 Schema 合法且根类型为对象，校验通过时原样返回。

    节点配置和审批表单都描述一个对象，因此根类型必须是 object；根类型缺省时按
    JSON Schema 规则同样表示允许任意类型，这里一并拒绝。
    """

    if not schema:
        return schema

    schema_error = check_schema(schema, label=label)
    if schema_error:
        raise ValueError(schema_error)

    declared_type = schema.get("type")
    if declared_type != "object":
        raise ValueError(f"{label} Schema 的根类型必须是 object")

    return schema


def validate_instance(
    instance: Any,
    schema: Mapping[str, Any],
    *,
    root_path: str = "config",
    max_issues: int = MAX_CONFIG_ISSUES_PER_NODE,
) -> list[JsonSchemaIssue]:
    """按 JSON Schema 校验一个实例，返回中文错误列表。

    只返回问题列表而不抛异常，让流程校验引擎能够一次汇总全部错误。
    """

    validator = Draft7Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(instance), key=_build_sort_key)

    if not errors:
        return []

    issues: list[JsonSchemaIssue] = []
    for error in errors[:max_issues]:
        issues.append(
            JsonSchemaIssue(
                path=_format_path(root_path, error.absolute_path),
                message=_translate_error(error),
            )
        )

    omitted_count = len(errors) - max_issues
    if omitted_count > 0:
        issues.append(
            JsonSchemaIssue(
                path=root_path,
                message=f"其余 {omitted_count} 个配置问题已省略",
            )
        )

    return issues


def _build_sort_key(error: Any) -> tuple[list[Any], str]:
    """构造稳定排序键，保证同一份配置每次返回的问题顺序一致。"""

    normalized_path: list[Any] = []
    for path_part in error.absolute_path:
        normalized_path.append(0 if isinstance(path_part, int) else 1)
        normalized_path.append(str(path_part))

    return normalized_path, error.validator or ""


def _format_path(root_path: str, absolute_path: Any) -> str:
    """把 JSON Schema 的路径元组拼成便于前端定位的路径文本。"""

    path_text = root_path
    for path_part in absolute_path:
        if isinstance(path_part, int):
            path_text += f"[{path_part}]"
        else:
            path_text += f".{path_part}"
    return path_text


def _translate_error(error: Any) -> str:
    """把单条 jsonschema 错误翻译成中文。

    对无法识别的关键字保留英文原文，避免丢失排查信息。
    """

    validator = error.validator
    validator_value = error.validator_value

    if validator == "required":
        missing_fields = [
            field_name
            for field_name in validator_value
            if field_name not in error.instance
        ]
        if missing_fields:
            return f"缺少必填配置项 {'、'.join(missing_fields)}"
        return "缺少必填配置项"

    if validator == "type":
        expected_types = _iter_strings(validator_value)
        translated = "、".join(
            JSON_TYPE_NAMES.get(item, item) for item in expected_types
        )
        return f"类型应为 {translated}，实际为 {describe_json_type(error.instance)}"

    if validator == "enum":
        choices = "、".join(_display_value(item) for item in validator_value)
        return f"取值必须是 {choices} 之一"

    if validator == "const":
        return f"取值必须为 {_display_value(validator_value)}"

    if validator in {
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
    }:
        return f"数值不满足范围要求（限制值 {validator_value}）"

    if validator in {"minLength", "maxLength", "minItems", "maxItems"}:
        return f"长度或数量不符合要求（限制值 {validator_value}）"

    if validator == "minProperties" or validator == "maxProperties":
        return f"配置项数量不符合要求（限制值 {validator_value}）"

    if validator == "uniqueItems":
        return "数组元素不能重复"

    if validator == "pattern":
        return f"取值不符合格式要求（{validator_value}）"

    if validator == "format":
        return f"取值不是合法的 {validator_value} 格式"

    if validator == "additionalProperties":
        unexpected_fields = _collect_unexpected_fields(error)
        if unexpected_fields:
            return f"存在不支持的配置字段 {'、'.join(unexpected_fields)}"
        return "存在不支持的配置字段"

    if validator in {"anyOf", "oneOf", "allOf", "not"}:
        return "取值不满足组合校验规则"

    return f"配置不满足校验规则（{validator}）：{error.message}"


def _collect_unexpected_fields(error: Any) -> list[str]:
    """计算 additionalProperties 拒绝的字段名。"""

    if not isinstance(error.instance, Mapping):
        return []

    unexpected_fields: list[str] = []
    for field_name in error.instance:
        if error.validator_value is False and error.schema.get("properties"):
            if field_name not in error.schema["properties"]:
                unexpected_fields.append(str(field_name))
        elif isinstance(error.validator_value, Mapping):
            if field_name not in error.validator_value:
                unexpected_fields.append(str(field_name))
    return sorted(unexpected_fields)


def _iter_strings(value: Any) -> list[str]:
    """把 JSON Schema 里的字符串或字符串数组统一成列表。"""

    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    return [str(value)]


def _display_value(value: Any) -> str:
    """把配置取值渲染成适合放进中文提示的文本。"""

    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, str):
        return value
    return str(value)
