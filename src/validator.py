"""校验领域事件信封与分事件负载的基础字段。

校验是无状态的：只检查单条记录自身的结构与必备字段。
跨记录的约定（同一聚合版本递增、先授权后撤回等）由事件存储保证，
样例事件链的顺序性在 tests/ 中验证。
"""

from datetime import datetime

REQUIRED = ("event_id", "event_type", "aggregate_type", "aggregate_id", "occurred_at", "version", "summary")

EVENT_TYPES = frozenset({
    "CHILD_PROFILE_REGISTERED",
    "AGE_STAGE_CHANGED",
    "EMERGENCY_CONTACT_SET",
    "POLICY_ASSIGNED",
    "USAGE_SUMMARY_ISSUED",
    "GUARDIAN_LINKED",
    "GUARDIAN_UNLINKED",
    "GUARDIAN_CONFLICT_RESOLVED",
    "CUSTODY_DELEGATED",
    "CUSTODY_ENDED",
    "POLICY_VERSION_PUBLISHED",
    "FEATURE_CONSENTED",
    "FEATURE_CONSENT_REVOKED",
    "SCHOOL_WINDOW_AUTHORIZED",
    "SCHOOL_WINDOW_REVOKED",
    "SCHEDULE_APPLIED",
    "SPENDING_LIMIT_SET",
    "DECISION_AUDITED",
})

AGGREGATE_TYPES = frozenset({
    "child_profile",
    "guardian_authority",
    "policy_version",
    "feature_consent",
    "school_window",
    "spending_limit",
    "feature_decision",
})

# 每种事件允许记录在哪些聚合上。
EVENT_AGGREGATES = {
    "CHILD_PROFILE_REGISTERED": {"child_profile"},
    "AGE_STAGE_CHANGED": {"child_profile"},
    "EMERGENCY_CONTACT_SET": {"child_profile"},
    "POLICY_ASSIGNED": {"child_profile"},
    "USAGE_SUMMARY_ISSUED": {"child_profile"},
    "GUARDIAN_LINKED": {"guardian_authority"},
    "GUARDIAN_UNLINKED": {"guardian_authority"},
    "GUARDIAN_CONFLICT_RESOLVED": {"guardian_authority"},
    "CUSTODY_DELEGATED": {"guardian_authority"},
    "CUSTODY_ENDED": {"guardian_authority"},
    "POLICY_VERSION_PUBLISHED": {"policy_version"},
    "FEATURE_CONSENTED": {"feature_consent"},
    "FEATURE_CONSENT_REVOKED": {"feature_consent"},
    "SCHOOL_WINDOW_AUTHORIZED": {"school_window"},
    "SCHOOL_WINDOW_REVOKED": {"school_window"},
    "SCHEDULE_APPLIED": {"school_window"},
    "SPENDING_LIMIT_SET": {"spending_limit"},
    "DECISION_AUDITED": {"feature_decision"},
}

# 十一项决定因子：每次放行或拦截都必须记录当时的取值，供审计与重放。
DECISION_FACTORS = (
    "age_stage",
    "guardianship",
    "school_window",
    "emergency_contacts",
    "location_precision",
    "acquaintance_social",
    "stranger_contact",
    "ranking_rewards",
    "content_rating",
    "spending_limit",
    "health_prompts",
)

OUTCOMES = frozenset({"allowed", "denied", "limited"})

AGE_STAGES = frozenset({"preschool", "lower_primary", "upper_primary", "teen"})

# 需监护人逐项授权的高风险能力；通话、求助、必要定位默认开放，不在此列。
CONSENT_FEATURES = frozenset({
    "precise_location",
    "acquaintance_social",
    "stranger_contact",
    "ranking_rewards",
    "payment",
    "content_above_default",
})

GUARDIAN_ROLES = frozenset({"primary", "secondary"})

LIMIT_PERIODS = frozenset({"daily", "weekly", "monthly"})

WEEKDAYS = frozenset({"mon", "tue", "wed", "thu", "fri", "sat", "sun"})

# 使用摘要不得携带聊天全文（R-08）。
SUMMARY_FORBIDDEN_KEYS = ("messages", "chat_log", "transcripts")


def _parse_datetime(value: object) -> datetime | None:
    """解析带时区的 ISO 8601 时间；不带时区或格式错误时返回 None。"""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _is_clock(value: object) -> bool:
    return isinstance(value, str) and len(value) == 5 and value[2] == ":" and value[:2].isdigit() and value[3:].isdigit()


def validate_event(record: dict) -> list[str]:
    if not isinstance(record, dict):
        return ["记录必须是对象"]
    errors = [f"缺少字段：{name}" for name in REQUIRED if name not in record]

    for name in ("event_id", "aggregate_id", "summary"):
        if name in record and (not isinstance(record[name], str) or not record[name]):
            errors.append(f"{name} 必须是非空字符串")

    event_type = record.get("event_type")
    if event_type is not None and event_type not in EVENT_TYPES:
        errors.append(f"未知事件类型：{event_type}")
    aggregate_type = record.get("aggregate_type")
    if aggregate_type is not None and aggregate_type not in AGGREGATE_TYPES:
        errors.append(f"未知聚合类型：{aggregate_type}")

    if "version" in record:
        version = record["version"]
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            errors.append("version 必须是正整数")

    if "occurred_at" in record and _parse_datetime(record["occurred_at"]) is None:
        errors.append("occurred_at 必须是带时区的 ISO 8601 时间")

    if event_type in EVENT_AGGREGATES and aggregate_type in AGGREGATE_TYPES:
        if aggregate_type not in EVENT_AGGREGATES[event_type]:
            errors.append(f"事件 {event_type} 不能记录在聚合 {aggregate_type} 上")

    checker = _PAYLOAD_CHECKS.get(event_type)
    if checker is not None:
        errors.extend(checker(record))
    return errors


def _missing(record: dict, *names: str) -> list[str]:
    return [f"{record.get('event_type')} 缺少字段：{name}" for name in names if name not in record]


def _check_child_registered(record: dict) -> list[str]:
    errors = _missing(record, "age_stage")
    stage = record.get("age_stage")
    if stage is not None and stage not in AGE_STAGES:
        errors.append(f"未知年龄阶段：{stage}")
    return errors


def _check_age_stage_changed(record: dict) -> list[str]:
    errors = _missing(record, "from_stage", "to_stage")
    for name in ("from_stage", "to_stage"):
        if name in record and record[name] not in AGE_STAGES:
            errors.append(f"未知年龄阶段：{record[name]}")
    if not errors and record["from_stage"] == record["to_stage"]:
        errors.append("from_stage 与 to_stage 不能相同")
    return errors


def _check_emergency_contacts(record: dict) -> list[str]:
    errors = _missing(record, "contacts")
    contacts = record.get("contacts")
    if isinstance(contacts, list):
        if not contacts:
            errors.append("contacts 至少保留一名紧急联系人")
        for item in contacts:
            if not isinstance(item, dict) or not item.get("label") or not item.get("phone"):
                errors.append("contacts 的每一项都需要 label 与 phone")
                break
    elif "contacts" in record:
        errors.append("contacts 必须是数组")
    return errors


def _check_policy_assigned(record: dict) -> list[str]:
    return _missing(record, "policy_version_ref", "assigned_by")


def _check_usage_summary(record: dict) -> list[str]:
    errors = _missing(record, "period")
    for key in SUMMARY_FORBIDDEN_KEYS:
        if key in record:
            errors.append(f"使用摘要不得携带聊天内容字段：{key}（R-08）")
    period = record.get("period")
    if isinstance(period, dict):
        start = _parse_datetime(period.get("start"))
        end = _parse_datetime(period.get("end"))
        if start is None or end is None:
            errors.append("period 需要带时区的 start 与 end")
        elif start >= end:
            errors.append("period.start 必须早于 period.end")
    elif "period" in record:
        errors.append("period 必须是对象")
    return errors


def _check_guardian_linked(record: dict) -> list[str]:
    errors = _missing(record, "guardian", "role")
    role = record.get("role")
    if role is not None and role not in GUARDIAN_ROLES:
        errors.append(f"未知监护角色：{role}")
    return errors


def _check_guardian_unlinked(record: dict) -> list[str]:
    return _missing(record, "guardian")


def _check_conflict_resolved(record: dict) -> list[str]:
    return _missing(record, "disputed_capability", "prevailing_guardian", "resolution_rule")


def _check_custody_delegated(record: dict) -> list[str]:
    errors = _missing(record, "custody")
    custody = record.get("custody")
    if isinstance(custody, dict):
        errors.extend(f"custody 缺少字段：{name}" for name in ("delegate", "starts_at", "ends_at") if name not in custody)
        starts = _parse_datetime(custody.get("starts_at"))
        ends = _parse_datetime(custody.get("ends_at"))
        if ("starts_at" in custody and starts is None) or ("ends_at" in custody and ends is None):
            errors.append("custody 的起止时间必须带时区")
        elif starts is not None and ends is not None and starts >= ends:
            errors.append("custody.starts_at 必须早于 custody.ends_at")
    elif "custody" in record:
        errors.append("custody 必须是对象")
    return errors


def _check_custody_ended(record: dict) -> list[str]:
    errors = _missing(record, "reason")
    reason = record.get("reason")
    if reason is not None and reason not in ("expired", "revoked"):
        errors.append("reason 必须是 expired 或 revoked")
    return errors


def _check_policy_version_published(record: dict) -> list[str]:
    errors = _missing(record, "policy_version_ref")
    supersedes = record.get("supersedes")
    if supersedes is not None and supersedes == record.get("policy_version_ref"):
        errors.append("supersedes 不能指向自身")
    return errors


def _check_feature_consent(record: dict) -> list[str]:
    errors = _missing(record, "feature", "guardian")
    feature = record.get("feature")
    if feature is not None and feature not in CONSENT_FEATURES:
        errors.append(f"未知可授权能力：{feature}")
    return errors


def _check_school_window_authorized(record: dict) -> list[str]:
    errors = _missing(record, "window", "control_scope", "authorized_by")
    window = record.get("window")
    if isinstance(window, dict):
        days = window.get("days")
        if not isinstance(days, list) or not days or not set(days) <= WEEKDAYS:
            errors.append("window.days 必须是非空星期数组（mon…sun）")
        for name in ("start", "end"):
            if not _is_clock(window.get(name)):
                errors.append(f"window.{name} 必须是 HH:MM 格式")
    elif "window" in record:
        errors.append("window 必须是对象")
    scope = record.get("control_scope")
    if "control_scope" in record and (not isinstance(scope, list) or not scope):
        errors.append("control_scope 必须是非空数组（最小控制集）")
    return errors


def _check_school_window_revoked(record: dict) -> list[str]:
    return _missing(record, "revoked_by")


def _check_schedule_applied(record: dict) -> list[str]:
    return _missing(record, "applied_by")


def _check_spending_limit(record: dict) -> list[str]:
    errors = _missing(record, "limit")
    limit = record.get("limit")
    if isinstance(limit, dict):
        period = limit.get("period")
        if period not in LIMIT_PERIODS:
            errors.append("limit.period 必须是 daily、weekly 或 monthly")
        amount = limit.get("amount")
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount < 0:
            errors.append("limit.amount 必须是非负数值")
        currency = limit.get("currency")
        if not (isinstance(currency, str) and len(currency) == 3 and currency.isupper() and currency.isalpha()):
            errors.append("limit.currency 必须是三位大写货币代码")
    elif "limit" in record:
        errors.append("limit 必须是对象")
    return errors


def _check_decision(record: dict) -> list[str]:
    errors = _missing(record, "subject", "outcome", "policy_version_ref", "factors")
    outcome = record.get("outcome")
    if outcome is not None and outcome not in OUTCOMES:
        errors.append("outcome 必须是 allowed、denied 或 limited")
    factors = record.get("factors")
    if isinstance(factors, dict):
        missing = [name for name in DECISION_FACTORS if name not in factors]
        if missing:
            errors.append("factors 缺少决定因子：" + "、".join(missing))
    elif "factors" in record:
        errors.append("factors 必须是对象")
    if outcome in ("denied", "limited") and not (record.get("restores_at") or record.get("restore_hint")):
        errors.append("拦截或限制必须给出 restores_at 或 restore_hint（R-07）")
    if "restores_at" in record and _parse_datetime(record["restores_at"]) is None:
        errors.append("restores_at 必须是带时区的 ISO 8601 时间")
    subject = record.get("subject")
    if isinstance(subject, str) and subject.startswith("payment.") and "entry_point" not in record:
        errors.append("支付类决定必须记录 entry_point，连续奖励与倒计时入口不得绕过额度（R-06）")
    return errors


_PAYLOAD_CHECKS = {
    "CHILD_PROFILE_REGISTERED": _check_child_registered,
    "AGE_STAGE_CHANGED": _check_age_stage_changed,
    "EMERGENCY_CONTACT_SET": _check_emergency_contacts,
    "POLICY_ASSIGNED": _check_policy_assigned,
    "USAGE_SUMMARY_ISSUED": _check_usage_summary,
    "GUARDIAN_LINKED": _check_guardian_linked,
    "GUARDIAN_UNLINKED": _check_guardian_unlinked,
    "GUARDIAN_CONFLICT_RESOLVED": _check_conflict_resolved,
    "CUSTODY_DELEGATED": _check_custody_delegated,
    "CUSTODY_ENDED": _check_custody_ended,
    "POLICY_VERSION_PUBLISHED": _check_policy_version_published,
    "FEATURE_CONSENTED": _check_feature_consent,
    "FEATURE_CONSENT_REVOKED": _check_feature_consent,
    "SCHOOL_WINDOW_AUTHORIZED": _check_school_window_authorized,
    "SCHOOL_WINDOW_REVOKED": _check_school_window_revoked,
    "SCHEDULE_APPLIED": _check_schedule_applied,
    "SPENDING_LIMIT_SET": _check_spending_limit,
    "DECISION_AUDITED": _check_decision,
}
