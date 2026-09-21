import json
import unittest
from pathlib import Path

from src import validator
from src.validator import validate_event

ROOT = Path(__file__).parents[1]


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def decision_record(**overrides) -> dict:
    record = {
        "event_id": "evt-test-001",
        "event_type": "DECISION_AUDITED",
        "aggregate_type": "feature_decision",
        "aggregate_id": "dec-test-01",
        "occurred_at": "2026-09-21T10:00:00+08:00",
        "version": 1,
        "summary": "测试用决定记录",
        "subject": "ranking_rewards.view",
        "outcome": "allowed",
        "policy_version_ref": "pv-2026.09.3",
        "factors": {name: "not_applicable" for name in validator.DECISION_FACTORS},
    }
    record.update(overrides)
    return record


class ContractTest(unittest.TestCase):
    def test_sample_matches_envelope(self) -> None:
        sample = load(ROOT / "data" / "sample.json")
        self.assertEqual(validate_event(sample), [])

    def test_event_chain_samples_are_valid(self) -> None:
        paths = sorted((ROOT / "data" / "events").glob("*.json"))
        self.assertTrue(paths, "事件链样例目录为空")
        for path in paths:
            with self.subTest(path=path.name):
                self.assertEqual(validate_event(load(path)), [])

    def test_event_chain_versions_and_ids(self) -> None:
        events = [load(p) for p in sorted((ROOT / "data" / "events").glob("*.json"))]
        events.sort(key=lambda e: e["occurred_at"])
        self.assertEqual(len({e["event_id"] for e in events}), len(events), "event_id 不得重复")
        seen: dict[tuple[str, str], int] = {}
        for event in events:
            key = (event["aggregate_type"], event["aggregate_id"])
            seen[key] = seen.get(key, 0) + 1
            self.assertEqual(event["version"], seen[key], f"{key} 的版本应逐条递增")

    def test_schema_and_validator_agree(self) -> None:
        schema = load(ROOT / "contracts" / "domain.schema.json")
        self.assertEqual(tuple(schema["required"]), validator.REQUIRED)
        self.assertEqual(set(schema["properties"]["event_type"]["enum"]), set(validator.EVENT_TYPES))
        self.assertEqual(set(schema["properties"]["aggregate_type"]["enum"]), set(validator.AGGREGATE_TYPES))
        factor_required = schema["$defs"]["decision_factors"]["required"]
        self.assertEqual(set(factor_required), set(validator.DECISION_FACTORS))


class EnvelopeTest(unittest.TestCase):
    def test_missing_field_is_reported(self) -> None:
        record = decision_record()
        del record["summary"]
        self.assertIn("缺少字段：summary", validate_event(record))

    def test_version_must_be_positive_int(self) -> None:
        for bad in (0, -1, "1", 1.5, True):
            with self.subTest(version=bad):
                self.assertIn("version 必须是正整数", validate_event(decision_record(version=bad)))

    def test_unknown_event_and_aggregate_types(self) -> None:
        errors = validate_event(decision_record(event_type="NOPE", aggregate_type="nope"))
        self.assertIn("未知事件类型：NOPE", errors)
        self.assertIn("未知聚合类型：nope", errors)

    def test_occurred_at_requires_timezone(self) -> None:
        errors = validate_event(decision_record(occurred_at="2026-09-21T10:00:00"))
        self.assertIn("occurred_at 必须是带时区的 ISO 8601 时间", errors)

    def test_event_must_match_aggregate(self) -> None:
        errors = validate_event(decision_record(aggregate_type="child_profile"))
        self.assertIn("事件 DECISION_AUDITED 不能记录在聚合 child_profile 上", errors)


class DecisionTest(unittest.TestCase):
    def test_replay_fields_are_required(self) -> None:
        record = decision_record()
        for name in ("subject", "outcome", "policy_version_ref", "factors"):
            del record[name]
        errors = validate_event(record)
        for name in ("subject", "outcome", "policy_version_ref", "factors"):
            self.assertIn(f"DECISION_AUDITED 缺少字段：{name}", errors)

    def test_all_decision_factors_must_be_present(self) -> None:
        factors = {name: "x" for name in validator.DECISION_FACTORS}
        del factors["school_window"]
        errors = validate_event(decision_record(factors=factors))
        self.assertIn("factors 缺少决定因子：school_window", errors)

    def test_denied_decision_needs_restore_info(self) -> None:
        errors = validate_event(decision_record(outcome="denied"))
        self.assertIn("拦截或限制必须给出 restores_at 或 restore_hint（R-07）", errors)
        self.assertEqual(validate_event(decision_record(outcome="denied", restore_hint="放学后恢复")), [])
        self.assertEqual(validate_event(decision_record(outcome="limited", restores_at="2026-09-21T16:30:00+08:00")), [])

    def test_payment_decision_needs_entry_point(self) -> None:
        record = decision_record(subject="payment.purchase", restores_at="2026-10-01T00:00:00+08:00")
        self.assertIn("支付类决定必须记录 entry_point，连续奖励与倒计时入口不得绕过额度（R-06）", validate_event(record))
        record["entry_point"] = "countdown"
        self.assertEqual(validate_event(record), [])

    def test_payment_entry_point_records_reward_and_countdown(self) -> None:
        for entry in ("streak_reward", "countdown"):
            with self.subTest(entry_point=entry):
                record = decision_record(
                    subject="payment.purchase",
                    entry_point=entry,
                    restores_at="2026-10-01T00:00:00+08:00",
                )
                self.assertEqual(validate_event(record), [])


class GuardianTest(unittest.TestCase):
    def base(self, **overrides) -> dict:
        record = {
            "event_id": "evt-test-101",
            "event_type": "CUSTODY_DELEGATED",
            "aggregate_type": "guardian_authority",
            "aggregate_id": "child-001",
            "occurred_at": "2026-09-21T08:00:00+08:00",
            "version": 1,
            "summary": "测试用托管记录",
            "custody": {
                "delegate": "guardian-grandpa-03",
                "starts_at": "2026-09-21T08:00:00+08:00",
                "ends_at": "2026-09-22T20:00:00+08:00",
            },
        }
        record.update(overrides)
        return record

    def test_custody_end_must_follow_start(self) -> None:
        custody = {
            "delegate": "guardian-grandpa-03",
            "starts_at": "2026-09-22T08:00:00+08:00",
            "ends_at": "2026-09-21T20:00:00+08:00",
        }
        self.assertIn("custody.starts_at 必须早于 custody.ends_at", validate_event(self.base(custody=custody)))

    def test_conflict_resolution_records_rule(self) -> None:
        record = self.base(event_type="GUARDIAN_CONFLICT_RESOLVED")
        del record["custody"]
        errors = validate_event(record)
        for name in ("disputed_capability", "prevailing_guardian", "resolution_rule"):
            self.assertIn(f"GUARDIAN_CONFLICT_RESOLVED 缺少字段：{name}", errors)


class ConsentTest(unittest.TestCase):
    def test_consent_feature_must_be_known(self) -> None:
        record = {
            "event_id": "evt-test-201",
            "event_type": "FEATURE_CONSENTED",
            "aggregate_type": "feature_consent",
            "aggregate_id": "child-001:chat",
            "occurred_at": "2026-09-21T09:00:00+08:00",
            "version": 1,
            "summary": "测试用授权记录",
            "feature": "chat",
            "guardian": "guardian-mother-01",
        }
        self.assertIn("未知可授权能力：chat", validate_event(record))
        record["feature"] = "ranking_rewards"
        self.assertEqual(validate_event(record), [])


class SummaryTest(unittest.TestCase):
    def base(self, **overrides) -> dict:
        record = {
            "event_id": "evt-test-301",
            "event_type": "USAGE_SUMMARY_ISSUED",
            "aggregate_type": "child_profile",
            "aggregate_id": "child-001",
            "occurred_at": "2026-09-21T09:00:00+08:00",
            "version": 1,
            "summary": "测试用摘要记录",
            "period": {"start": "2026-09-14T00:00:00+08:00", "end": "2026-09-20T23:59:59+08:00"},
        }
        record.update(overrides)
        return record

    def test_summary_must_not_carry_chat_content(self) -> None:
        self.assertIn(
            "使用摘要不得携带聊天内容字段：messages（R-08）",
            validate_event(self.base(messages=[{"from": "a", "text": "..."}])),
        )
        self.assertEqual(validate_event(self.base()), [])

    def test_summary_period_must_be_ordered(self) -> None:
        period = {"start": "2026-09-20T00:00:00+08:00", "end": "2026-09-14T00:00:00+08:00"}
        self.assertIn("period.start 必须早于 period.end", validate_event(self.base(period=period)))


class SpendingLimitTest(unittest.TestCase):
    def test_limit_shape(self) -> None:
        record = {
            "event_id": "evt-test-401",
            "event_type": "SPENDING_LIMIT_SET",
            "aggregate_type": "spending_limit",
            "aggregate_id": "child-001",
            "occurred_at": "2026-09-21T09:00:00+08:00",
            "version": 1,
            "summary": "测试用额度记录",
            "limit": {"period": "monthly", "amount": 50.0, "currency": "cny"},
        }
        self.assertIn("limit.currency 必须是三位大写货币代码", validate_event(record))
        record["limit"]["currency"] = "CNY"
        self.assertEqual(validate_event(record), [])


if __name__ == "__main__":
    unittest.main()
