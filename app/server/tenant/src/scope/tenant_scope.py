"""基于分表绑定关系实现统一租户资源作用域。"""

import os
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import exists
from sqlmodel import Session, select

from app.common.scope import GlobalResourceScope, ResourceScope
from app.server.tenant.src.models.tenant_model import (
    BusinessActionBinding,
    PersonBinding,
    ProcessBinding,
    ProcessUsageRecord,
)


RESOURCE_PERSON = "organization.person"
RESOURCE_PROCESS = "process.approval_process"
RESOURCE_BUSINESS_ACTION = "integration.business_action"
RESOURCE_APPROVAL_INSTANCE = "process.approval_instance"


class TenantResourceAccessError(Exception):
    """当前租户无权访问指定业务资源。"""


@dataclass(frozen=True)
class BindingDefinition:
    """描述一种业务资源使用的绑定模型和资源 ID 字段。

    status_field 为空表示这类绑定没有启停状态，记录存在即代表资源可访问，审批使用
    记录属于这一类。required_attribute_fields 列出建立绑定时必须由调用方补充的资源
    特有字段，缺失时不允许写入半成品绑定。
    """

    model: type
    resource_id_field: str
    status_field: str | None = "status"
    required_attribute_fields: tuple[str, ...] = ()


BINDING_DEFINITIONS: dict[str, BindingDefinition] = {
    RESOURCE_PERSON: BindingDefinition(
        model=PersonBinding,
        resource_id_field="person_id",
    ),
    RESOURCE_PROCESS: BindingDefinition(
        model=ProcessBinding,
        resource_id_field="process_id",
    ),
    RESOURCE_BUSINESS_ACTION: BindingDefinition(
        model=BusinessActionBinding,
        resource_id_field="business_action_id",
    ),
    # 使用记录没有启停状态，写入时必须带上流程、版本和业务单据标识。
    RESOURCE_APPROVAL_INSTANCE: BindingDefinition(
        model=ProcessUsageRecord,
        resource_id_field="approval_instance_id",
        status_field=None,
        required_attribute_fields=(
            "process_id",
            "process_version_id",
            "business_key",
        ),
    ),
}


def is_tenancy_enabled() -> bool:
    """读取租户能力开关，默认保持当前多租户模式。"""

    raw_value = os.getenv("TENANCY_ENABLED", "true").strip().lower()
    return raw_value in {"1", "true", "yes", "on"}


class TenantResourceScope(ResourceScope):
    """使用具体 binding 表实现当前租户的资源作用域。"""

    def __init__(self, tenant_id: UUID, resource_type: str):
        """初始化租户、资源类型和对应绑定定义。"""

        binding_definition = BINDING_DEFINITIONS.get(resource_type)
        if not binding_definition:
            raise ValueError(f"尚未注册租户资源类型：{resource_type}")

        self.tenant_id = tenant_id
        self.resource_type = resource_type
        self.binding_definition = binding_definition

    def apply_filter(self, statement: Any, resource_id_column: Any) -> Any:
        """使用 EXISTS 子查询限制为当前租户已启用的资源。"""

        binding_model = self.binding_definition.model
        binding_resource_id = getattr(
            binding_model,
            self.binding_definition.resource_id_field,
        )
        conditions = [
            binding_model.tenant_id == self.tenant_id,
            binding_resource_id == resource_id_column,
        ]

        # 没有启停状态的绑定只要求记录存在，不追加状态条件。
        status_field = self.binding_definition.status_field
        if status_field is not None:
            conditions.append(getattr(binding_model, status_field) == "ENABLED")

        binding_exists = exists(select(binding_model.id).where(*conditions))
        return statement.where(binding_exists)

    def require_access(self, resource_id: UUID, db: Session) -> None:
        """确认当前租户存在可用的资源绑定。"""

        binding = self.get_binding(resource_id, db)
        if not binding:
            raise TenantResourceAccessError("当前租户无权访问该资源")

        status_field = self.binding_definition.status_field
        if status_field is not None and getattr(binding, status_field) != "ENABLED":
            raise TenantResourceAccessError("当前租户无权访问该资源")

    def bind(
        self,
        resource_id: UUID,
        db: Session,
        attributes: dict[str, Any] | None = None,
    ) -> Any:
        """创建或重新启用当前租户的资源绑定。"""

        binding_definition = self.binding_definition
        normalized_attributes = attributes or {}

        missing_fields = [
            field_name
            for field_name in binding_definition.required_attribute_fields
            if normalized_attributes.get(field_name) is None
        ]
        if missing_fields:
            raise ValueError("资源绑定缺少必需字段：" + "、".join(missing_fields))

        existing_binding = self.get_binding(resource_id, db)
        if existing_binding:
            status_field = binding_definition.status_field
            if status_field is None:
                # 使用记录是不可变的历史事实。即使重复绑定时传入了不同属性，也保留
                # 第一次写入的原始数据，避免流程归属和业务单号被意外篡改。
                return existing_binding

            # 普通授权记录允许重新启用，并同步调用方显式传入的扩展属性。
            setattr(existing_binding, status_field, "ENABLED")
            self._apply_supported_attributes(existing_binding, normalized_attributes)
            db.add(existing_binding)
            return existing_binding

        binding_values: dict[str, Any] = {
            "tenant_id": self.tenant_id,
            binding_definition.resource_id_field: resource_id,
        }
        if binding_definition.status_field is not None:
            binding_values[binding_definition.status_field] = "ENABLED"

        supported_fields = binding_definition.model.model_fields
        for field_name, field_value in normalized_attributes.items():
            if field_name in supported_fields:
                binding_values[field_name] = field_value

        binding = binding_definition.model(**binding_values)
        db.add(binding)
        return binding

    def unbind(self, resource_id: UUID, db: Session) -> None:
        """停用当前租户与业务资源的绑定。"""

        binding = self.get_binding(resource_id, db)
        if not binding:
            return

        status_field = self.binding_definition.status_field
        if status_field is None:
            return

        setattr(binding, status_field, "DISABLED")
        db.add(binding)

    def get_binding(self, resource_id: UUID, db: Session) -> Any | None:
        """查询当前租户与指定资源的绑定。"""

        binding_model = self.binding_definition.model
        binding_resource_id = getattr(
            binding_model,
            self.binding_definition.resource_id_field,
        )
        statement = select(binding_model).where(
            binding_model.tenant_id == self.tenant_id,
            binding_resource_id == resource_id,
        )
        return db.exec(statement).first()

    def list_bindings(self, db: Session, enabled_only: bool = False) -> list[Any]:
        """查询当前租户当前资源类型的全部绑定。"""

        binding_model = self.binding_definition.model
        statement = select(binding_model).where(
            binding_model.tenant_id == self.tenant_id
        )

        status_field = self.binding_definition.status_field
        if enabled_only and status_field is not None:
            statement = statement.where(getattr(binding_model, status_field) == "ENABLED")

        statement = statement.order_by(binding_model.created_at.desc())
        return list(db.exec(statement).all())

    @staticmethod
    def _apply_supported_attributes(binding: Any, attributes: dict[str, Any]) -> None:
        """只把绑定模型支持的扩展字段写入对象。"""

        supported_fields = binding.__class__.model_fields
        for field_name, field_value in attributes.items():
            if field_name in supported_fields:
                setattr(binding, field_name, field_value)


def create_resource_scope(
    resource_type: str,
    tenant_id: UUID | None = None,
) -> ResourceScope:
    """根据租户开关创建租户作用域或全局空操作作用域。"""

    if not is_tenancy_enabled():
        return GlobalResourceScope()
    if tenant_id is None:
        raise ValueError("启用租户能力时必须提供 tenant_id")
    return TenantResourceScope(tenant_id=tenant_id, resource_type=resource_type)
