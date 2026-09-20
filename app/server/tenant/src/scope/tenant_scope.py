"""基于分表绑定关系实现统一租户资源作用域。"""

import os
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import exists
from sqlmodel import Session, select

from app.common.scope import GlobalResourceScope, ResourceScope
from app.server.tenant.src.models.tenant_model import PersonBinding


RESOURCE_PERSON = "organization.person"


class TenantResourceAccessError(Exception):
    """当前租户无权访问指定业务资源。"""


@dataclass(frozen=True)
class BindingDefinition:
    """描述一种业务资源使用的绑定模型和资源 ID 字段。"""

    model: type
    resource_id_field: str


BINDING_DEFINITIONS: dict[str, BindingDefinition] = {
    RESOURCE_PERSON: BindingDefinition(
        model=PersonBinding,
        resource_id_field="person_id",
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
        binding_exists = exists(
            select(binding_model.id).where(
                binding_model.tenant_id == self.tenant_id,
                binding_resource_id == resource_id_column,
                binding_model.status == "ENABLED",
            )
        )
        return statement.where(binding_exists)

    def require_access(self, resource_id: UUID, db: Session) -> None:
        """确认当前租户存在已启用的资源绑定。"""

        binding = self.get_binding(resource_id, db)
        if not binding or binding.status != "ENABLED":
            raise TenantResourceAccessError("当前租户无权访问该资源")

    def bind(
        self,
        resource_id: UUID,
        db: Session,
        attributes: dict[str, Any] | None = None,
    ) -> Any:
        """创建或重新启用当前租户的资源绑定。"""

        existing_binding = self.get_binding(resource_id, db)
        normalized_attributes = attributes or {}

        if existing_binding:
            existing_binding.status = "ENABLED"
            self._apply_supported_attributes(existing_binding, normalized_attributes)
            db.add(existing_binding)
            return existing_binding

        binding_model = self.binding_definition.model
        binding_values = {
            "tenant_id": self.tenant_id,
            self.binding_definition.resource_id_field: resource_id,
            "status": "ENABLED",
        }
        supported_fields = binding_model.model_fields
        for field_name, field_value in normalized_attributes.items():
            if field_name in supported_fields:
                binding_values[field_name] = field_value

        binding = binding_model(**binding_values)
        db.add(binding)
        return binding

    def unbind(self, resource_id: UUID, db: Session) -> None:
        """停用当前租户与业务资源的绑定。"""

        binding = self.get_binding(resource_id, db)
        if not binding:
            return

        binding.status = "DISABLED"
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
        if enabled_only:
            statement = statement.where(binding_model.status == "ENABLED")
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
