"""人员与组织模块领域异常。"""


class OrganizationError(Exception):
    """人员与组织模块异常基类。"""


class OrganizationNotFoundError(OrganizationError):
    """人员、部门、成员或租户不存在。"""


class OrganizationConflictError(OrganizationError):
    """人员组织数据违反唯一性或重复绑定规则。"""


class OrganizationValidationError(OrganizationError):
    """人员组织数据违反跨实体业务规则。"""

