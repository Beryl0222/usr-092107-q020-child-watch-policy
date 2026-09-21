"""校验领域事件信封与各事件类型的载荷约定。

schema（contracts/domain.schema.json）约束信封字段与枚举；本模块补充
跨字段规则：事件与聚合的挂载关系、各事件类型必须携带或禁止出现的
载荷字段，以及后继版本纠正等不变量。
"""

from __future__ import annotations

from datetime import datetime

REQUIRED = ("event_id", "event_type", "aggregate_type", "aggregate_id", "occurred_at", "version", "summary")

EVENT_TYPES = (
    "GUARDIAN_LINKED",
    "GUARDIAN_RELATION_CHANGED",
    "GUARDIAN_CONFLICT_RESOLVED",
    "CUSTODY_DELEGATED",
    "EMERGENCY_CONTACT_SET",
    "POLICY_ASSIGNED",
    "POLICY_VERSION_SUCCEEDED",
    "FEATURE_CONSENTED",
    "FEATURE_CONSENT_REVOKED",
    "SCHEDULE_APPLIED",
    "FRIEND_LINKED",
    "STRANGER_CONTACT_BLOCKED",
    "PAYMENT_LIMIT_ENFORCED",
    "RESTRICTION_EXPLAINED",
    "USAGE_SUMMARY_DELIVERED",
    "DECISION_AUDITED",
    "DECISION_REPLAYED",
)

AGGREGATE_TYPES = (
    "child_profile",
    "guardian_authority",
    "consent_grant",
    "policy_version",
    "school_window",
    "social_circle",
    "spending_limit",
    "usage_summary",
    "feature_decision",
)

# 每种事件只能挂在唯一聚合上，保证事件流可按聚合重放。
EVENT_AGGREGATE = {
    "GUARDIAN_LINKED": "guardian_authority",
    "GUARDIAN_RELATION_CHANGED": "guardian_authority",
    "GUARDIAN_CONFLICT_RESOLVED": "guardian_authority",
    "CUSTODY_DELEGATED": "guardian_authority",
    "EMERGENCY_CONTACT_SET": "child_profile",
    "POLICY_ASSIGNED": "policy_version",
    "POLICY_VERSION_SUCCEEDED": "policy_version",
    "FEATURE_CONSENTED": "consent_grant",
    "FEATURE_CONSENT_REVOKED": "consent_grant",
    "SCHEDULE_APPLIED": "school_window",
    "FRIEND_LINKED": "social_circle",
    "STRANGER_CONTACT_BLOCKED": "social_circle",
    "PAYMENT_LIMIT_ENFORCED": "spending_limit",
    "RESTRICTION_EXPLAINED": "feature_decision",
    "USAGE_SUMMARY_DELIVERED": "usage_summary",
    "DECISION_AUDITED": "feature_decision",
    "DECISION_REPLAYED": "feature_decision",
}

# 各事件类型必须携带的载荷字段。
REQUIRED_PAYLOAD_FIELDS = {
    "GUARDIAN_LINKED": ("priority",),
    "CUSTODY_DELEGATED": ("starts_at", "ends_at"),
    "POLICY_ASSIGNED": ("policy_version",),
    "POLICY_VERSION_SUCCEEDED": ("supersedes_version",),
    "FEATURE_CONSENTED": ("feature",),
    "FEATURE_CONSENT_REVOKED": ("feature",),
    "SCHEDULE_APPLIED": ("window_start", "window_end"),
    "PAYMENT_LIMIT_ENFORCED": ("outcome",),
    "RESTRICTION_EXPLAINED": ("feature", "resume_at"),
    "DECISION_AUDITED": ("policy_version", "basis"),
    "DECISION_REPLAYED": ("original_event_id", "policy_version"),
}

# 各事件类型禁止出现的载荷字段（隐私与付费护栏红线）：
# - 好友关系不得携带班级名单，跨品牌场景同样适用；
# - 家长只收到使用摘要，事件不得包含聊天全文；
# - 付费放行不得依据连续奖励或倒计时绕过额度。
FORBIDDEN_PAYLOAD_FIELDS = {
    "FRIEND_LINKED": ("class_roster", "class_list", "classmates"),
    "USAGE_SUMMARY_DELIVERED": ("messages", "chat_log", "message_content", "chat_transcript"),
    "PAYMENT_LIMIT_ENFORCED": ("streak_override", "countdown_override"),
}


def validate_event(record: dict) -> list[str]:
    errors = [f"缺少字段：{name}" for name in REQUIRED if name not in record]

    event_type = record.get("event_type")
    if event_type is not None and event_type not in EVENT_TYPES:
        errors.append(f"未知事件类型：{event_type}")

    aggregate_type = record.get("aggregate_type")
    if aggregate_type is not None and aggregate_type not in AGGREGATE_TYPES:
        errors.append(f"未知聚合类型：{aggregate_type}")

    expected = EVENT_AGGREGATE.get(event_type)
    if expected and aggregate_type in AGGREGATE_TYPES and aggregate_type != expected:
        errors.append(f"事件 {event_type} 应挂在聚合 {expected}，而非 {aggregate_type}")

    version = record.get("version")
    if "version" in record and (not isinstance(version, int) or isinstance(version, bool) or version < 1):
        errors.append("version 必须是正整数")

    occurred_at = record.get("occurred_at")
    if isinstance(occurred_at, str):
        try:
            datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
        except ValueError:
            errors.append("occurred_at 必须是 ISO 8601 日期时间")

    payload = record.get("payload")
    if payload is not None and not isinstance(payload, dict):
        errors.append("payload 必须是对象")
        payload = None
    payload = payload or {}

    for field in REQUIRED_PAYLOAD_FIELDS.get(event_type, ()):
        if field not in payload:
            errors.append(f"事件 {event_type} 的 payload 缺少字段：{field}")

    for field in FORBIDDEN_PAYLOAD_FIELDS.get(event_type, ()):
        if field in payload:
            errors.append(f"事件 {event_type} 的 payload 不得包含字段：{field}")

    if event_type == "POLICY_VERSION_SUCCEEDED":
        supersedes = payload.get("supersedes_version")
        if isinstance(supersedes, int) and isinstance(version, int) and supersedes >= version:
            errors.append("后继版本必须高于被纠正的版本")

    if event_type == "DECISION_AUDITED" and "basis" in payload and not payload["basis"]:
        errors.append("决定依据 basis 不得为空，否则无法重放")

    return errors
