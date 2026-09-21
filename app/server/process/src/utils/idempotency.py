"""审批实例内部幂等键和请求摘要生成。"""

import hashlib
import json
from typing import Any, Mapping
from uuid import UUID


def build_idempotency_key(
    process_id: UUID,
    business_key: str,
    tenant_id: UUID | None = None,
) -> str:
    """生成审批实例的内部幂等键。

    幂等键由租户、流程和业务单据标识共同决定：同一业务单据在不同流程下可以各自
    发起一次审批，而重复提交完全相同的请求会命中同一个实例。

    租户作用域尚未接入，tenant_id 为空时使用固定的全局占位段，接入租户后相同
    调用仍然生成一致的幂等键。原始串可能超过字段长度，因此保存摘要而不是原文。
    """

    tenant_segment = str(tenant_id) if tenant_id is not None else "global"
    raw_key = f"{tenant_segment}|{process_id}|{business_key}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def build_request_digest(payload: Mapping[str, Any]) -> str:
    """计算发起审批请求内容的规范化摘要。

    幂等键只表达“同一个业务单据”，不能说明请求内容是否相同。金额、执行参数或业务
    动作变化时如果仍然直接返回原实例，调用方会误以为新内容已经提交，付款类审批还
    可能继续使用旧参数。因此额外保存请求摘要，重放时比对。

    键排序、分隔符固定且不做 ASCII 转义，保证同一份内容每次得到相同摘要。
    """

    canonical_payload = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()
