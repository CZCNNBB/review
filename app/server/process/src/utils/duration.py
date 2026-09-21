"""审批耗时计算。

运行表只保存时间字段，耗时统一由查询接口计算，避免时间与耗时两份数据不一致。
SQLite 测试环境取回的时间不带时区，这里统一按 UTC 对齐后再相减。
"""

from datetime import datetime, timezone


def utc_now() -> datetime:
    """返回带 UTC 时区的当前时间。"""

    return datetime.now(timezone.utc)


def to_utc(value: datetime) -> datetime:
    """把时间对齐到 UTC，缺少时区信息时按 UTC 解释。"""

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def elapsed_ms(
    started_at: datetime | None,
    finished_at: datetime | None = None,
) -> int | None:
    """计算毫秒耗时，结束时间为空时按当前时间计算进行中的耗时。"""

    if started_at is None:
        return None

    end_time = finished_at if finished_at is not None else utc_now()
    delta = to_utc(end_time) - to_utc(started_at)
    return max(0, int(delta.total_seconds() * 1000))
