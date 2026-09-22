"""业务动作定义、参数规则校验和租户可用性判断业务逻辑。

本模块只维护业务动作本身和它的参数规则，不执行任何外部 HTTP 请求，也不直接读取
租户绑定表。租户能否使用某个动作由调用方通过租户资源作用域判断。
"""

from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.common.scope import ResourceScope
from app.server.integration.src.constants import (
    ACTION_STATUS_ENABLED,
    DEFAULT_SUCCESS_STATUS_CODES,
    RULE_EXECUTION_PAYLOAD_INVALID,
)
from app.server.integration.src.models.business_action_model import (
    BusinessAction,
    utc_now,
)
from app.server.integration.src.repository.business_action_repository import (
    BusinessActionRepository,
)
from app.server.integration.src.schemas.business_action_schema import (
    BusinessActionCreateRequest,
    BusinessActionUpdateRequest,
)
from app.server.integration.src.service.exceptions import (
    BusinessActionConflictError,
    BusinessActionNotFoundError,
    BusinessActionStateError,
    BusinessActionValidationError,
)
from app.server.process.src.service.process_validation import ValidationIssue
from app.server.process.src.utils.json_schema import (
    validate_instance,
    validate_object_schema,
)


class BusinessActionService:
    """提供业务动作的维护、查询和执行参数校验能力。"""

    def __init__(self, repository: BusinessActionRepository | None = None):
        """初始化业务动作服务并允许测试注入 Repository。"""

        self.repository = repository or BusinessActionRepository()

    # ------------------------------------------------------------------
    # 管理能力
    # ------------------------------------------------------------------

    def create_action(
        self,
        request: BusinessActionCreateRequest,
        db: Session,
    ) -> BusinessAction:
        """创建业务动作，写入前先校验请求参数 Schema 本身合法。"""

        existing_action = self.repository.get_by_code(request.action_code, db)
        if existing_action:
            raise BusinessActionConflictError(
                f"业务动作标识 {request.action_code} 已存在"
            )

        action = BusinessAction(
            action_code=request.action_code,
            name=request.name,
            description=request.description,
            http_method=request.http_method,
            relative_path=request.relative_path,
            request_schema_json=self._normalize_request_schema(
                request.request_schema_json
            ),
            success_status_codes_json=self._normalize_success_status_codes(
                request.success_status_codes
            ),
            timeout_ms=request.timeout_ms,
        )
        self.repository.add(action, db)
        self._commit_or_conflict(db, "业务动作标识已存在")
        db.refresh(action)
        return action

    def list_actions(
        self,
        db: Session,
        status: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[BusinessAction]:
        """分页查询业务动作列表。"""

        return self.repository.list_actions(
            db,
            status=status,
            offset=offset,
            limit=limit,
        )

    def get_action(self, action_id: UUID, db: Session) -> BusinessAction:
        """查询业务动作，不存在时抛出领域异常。"""

        action = self.repository.get_by_id(action_id, db)
        if action is None:
            raise BusinessActionNotFoundError("业务动作不存在")
        return action

    def update_action(
        self,
        action_id: UUID,
        request: BusinessActionUpdateRequest,
        db: Session,
    ) -> BusinessAction:
        """更新业务动作的展示信息、调用配置或状态。"""

        action = self.get_action(action_id, db)
        update_data = request.model_dump(exclude_unset=True)

        # 请求参数 Schema 需要先校验再落库，避免保存一份之后每次校验都会失败的规则。
        if "request_schema_json" in update_data:
            update_data["request_schema_json"] = self._normalize_request_schema(
                update_data["request_schema_json"]
            )

        # 接口字段名与数据库列名不同，转换后再统一写入模型。
        if "success_status_codes" in update_data:
            success_status_codes = update_data.pop("success_status_codes")
            update_data["success_status_codes_json"] = (
                self._normalize_success_status_codes(success_status_codes)
            )

        for field_name, field_value in update_data.items():
            setattr(action, field_name, field_value)

        action.updated_at = utc_now()
        self.repository.add(action, db)
        db.commit()
        db.refresh(action)
        return action

    # ------------------------------------------------------------------
    # 发起审批时使用的能力
    # ------------------------------------------------------------------

    def resolve_tenant_action(
        self,
        action_code: str,
        action_scope: ResourceScope,
        db: Session,
    ) -> BusinessAction:
        """确认当前租户可以使用指定业务动作，并返回动作配置。

        校验顺序固定为：动作存在、动作已启用、当前租户已经绑定该动作。前两步只与
        全局配置有关，第三步在缺少绑定时统一返回无权访问，不向调用方暴露其他租户
        是否拥有该动作。
        """

        action = self.repository.get_by_code(action_code, db)
        if action is None:
            raise BusinessActionNotFoundError(f"业务动作 {action_code} 不存在")
        if action.status != ACTION_STATUS_ENABLED:
            raise BusinessActionStateError(f"业务动作 {action_code} 已停用")

        action_scope.require_access(action.id, db)
        return action

    @staticmethod
    def validate_execution_payload(
        action: BusinessAction,
        execution_payload: dict,
    ) -> None:
        """按业务动作的请求 Schema 校验执行参数，错误信息带具体字段路径。"""

        request_schema = action.request_schema_json
        if not isinstance(request_schema, dict) or not request_schema:
            return

        payload_issues = validate_instance(
            execution_payload,
            request_schema,
            root_path="execution_payload",
        )
        if not payload_issues:
            return

        raise BusinessActionValidationError(
            "业务执行参数校验未通过",
            [
                ValidationIssue(
                    code=RULE_EXECUTION_PAYLOAD_INVALID,
                    message=issue.message,
                    field=issue.path,
                )
                for issue in payload_issues
            ],
        )

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_request_schema(schema: dict | None) -> dict:
        """校验请求参数 Schema 合法且根类型为对象。"""

        normalized_schema = dict(schema or {})
        try:
            return validate_object_schema(normalized_schema, label="业务动作请求参数")
        except ValueError as exc:
            raise BusinessActionValidationError(str(exc)) from exc

    @staticmethod
    def _normalize_success_status_codes(status_codes: list[int] | None) -> list[int]:
        """整理成功状态码，未配置时保存为空数组表示全部 2xx。"""

        if status_codes is None:
            return list(DEFAULT_SUCCESS_STATUS_CODES)
        return list(status_codes)

    @staticmethod
    def _commit_or_conflict(db: Session, message: str) -> None:
        """提交事务，并将数据库唯一约束错误转换为领域冲突。"""

        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise BusinessActionConflictError(message) from exc
