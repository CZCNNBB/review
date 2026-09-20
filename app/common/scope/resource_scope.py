"""业务模块使用的资源作用域抽象。"""

from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID

from sqlmodel import Session


class ResourceScope(ABC):
    """定义资源过滤、访问校验和绑定的统一接口。"""

    @abstractmethod
    def apply_filter(self, statement: Any, resource_id_column: Any) -> Any:
        """为业务查询追加当前作用域的资源过滤条件。"""

    @abstractmethod
    def require_access(self, resource_id: UUID, db: Session) -> None:
        """确认当前作用域可以访问指定资源。"""

    @abstractmethod
    def bind(
        self,
        resource_id: UUID,
        db: Session,
        attributes: dict[str, Any] | None = None,
    ) -> Any:
        """把业务资源绑定到当前作用域。"""

    @abstractmethod
    def unbind(self, resource_id: UUID, db: Session) -> None:
        """停用当前作用域与业务资源的绑定。"""


class GlobalResourceScope(ResourceScope):
    """未启用租户能力时使用的全局空操作作用域。"""

    def apply_filter(self, statement: Any, resource_id_column: Any) -> Any:
        """全局模式不追加过滤条件。"""

        return statement

    def require_access(self, resource_id: UUID, db: Session) -> None:
        """全局模式允许访问全部业务资源。"""

        return None

    def bind(
        self,
        resource_id: UUID,
        db: Session,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        """全局模式不创建租户绑定。"""

        return None

    def unbind(self, resource_id: UUID, db: Session) -> None:
        """全局模式不执行租户解绑。"""

        return None

