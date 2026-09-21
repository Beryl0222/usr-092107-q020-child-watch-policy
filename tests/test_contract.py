import json
import unittest
from pathlib import Path

from src.validator import AGGREGATE_TYPES, EVENT_TYPES, validate_event

ROOT = Path(__file__).parents[1]


def load_samples() -> list[dict]:
    paths = [ROOT / "data" / "sample.json", *sorted((ROOT / "data" / "samples").glob("*.json"))]
    return [json.loads(path.read_text(encoding="utf-8")) for path in paths]


def valid_record(**overrides) -> dict:
    record = {
        "event_id": "evt-test-001",
        "event_type": "FEATURE_CONSENTED",
        "aggregate_type": "consent_grant",
        "aggregate_id": "child-001",
        "occurred_at": "2026-09-21T12:00:00+08:00",
        "version": 1,
        "summary": "测试记录",
        "payload": {"feature": "step_ranking"},
    }
    record.update(overrides)
    return record


class ContractTest(unittest.TestCase):
    def test_sample_matches_envelope(self) -> None:
        sample = json.loads((ROOT / "data" / "sample.json").read_text(encoding="utf-8"))
        self.assertEqual(validate_event(sample), [])

    def test_all_samples_are_valid(self) -> None:
        for sample in load_samples():
            with self.subTest(event_id=sample["event_id"]):
                self.assertEqual(validate_event(sample), [])

    def test_samples_cover_every_event_and_aggregate(self) -> None:
        samples = load_samples()
        self.assertEqual({s["event_type"] for s in samples}, set(EVENT_TYPES))
        self.assertEqual({s["aggregate_type"] for s in samples}, set(AGGREGATE_TYPES))


class EnvelopeRuleTest(unittest.TestCase):
    def test_unknown_event_type_rejected(self) -> None:
        errors = validate_event(valid_record(event_type="SOMETHING_ELSE"))
        self.assertTrue(any("未知事件类型" in e for e in errors))

    def test_event_must_attach_to_its_aggregate(self) -> None:
        errors = validate_event(valid_record(aggregate_type="child_profile"))
        self.assertTrue(any("consent_grant" in e for e in errors))

    def test_version_must_be_positive_integer(self) -> None:
        self.assertIn("version 必须是正整数", validate_event(valid_record(version=0)))

    def test_occurred_at_must_be_iso_datetime(self) -> None:
        errors = validate_event(valid_record(occurred_at="昨天傍晚"))
        self.assertTrue(any("occurred_at" in e for e in errors))


class PayloadRuleTest(unittest.TestCase):
    def test_friend_link_must_not_expose_class_roster(self) -> None:
        record = valid_record(
            event_type="FRIEND_LINKED",
            aggregate_type="social_circle",
            payload={"friend_ref": "f-1", "cross_brand": True, "class_roster": ["同桌甲"]},
        )
        self.assertTrue(any("class_roster" in e for e in validate_event(record)))

    def test_usage_summary_must_not_contain_chat_transcript(self) -> None:
        record = valid_record(
            event_type="USAGE_SUMMARY_DELIVERED",
            aggregate_type="usage_summary",
            payload={"period": "2026-W38", "chat_log": ["……"]},
        )
        self.assertTrue(any("chat_log" in e for e in validate_event(record)))

    def test_payment_must_not_bypass_limit_via_streak_or_countdown(self) -> None:
        for override in ("streak_override", "countdown_override"):
            record = valid_record(
                event_type="PAYMENT_LIMIT_ENFORCED",
                aggregate_type="spending_limit",
                payload={"outcome": "allowed", override: True},
            )
            self.assertTrue(any(override in e for e in validate_event(record)))

    def test_decision_audit_requires_policy_version_and_basis(self) -> None:
        record = valid_record(event_type="DECISION_AUDITED", aggregate_type="feature_decision", payload={})
        errors = validate_event(record)
        self.assertTrue(any("policy_version" in e for e in errors))
        self.assertTrue(any("basis" in e for e in errors))

    def test_restriction_explanation_requires_resume_time(self) -> None:
        record = valid_record(
            event_type="RESTRICTION_EXPLAINED",
            aggregate_type="feature_decision",
            payload={"feature": "step_ranking"},
        )
        self.assertTrue(any("resume_at" in e for e in validate_event(record)))

    def test_custody_delegation_requires_time_window(self) -> None:
        record = valid_record(
            event_type="CUSTODY_DELEGATED",
            aggregate_type="guardian_authority",
            payload={"delegate_guardian_id": "guardian-003"},
        )
        errors = validate_event(record)
        self.assertTrue(any("starts_at" in e for e in errors))
        self.assertTrue(any("ends_at" in e for e in errors))

    def test_successor_version_must_exceed_corrected_version(self) -> None:
        record = valid_record(
            event_type="POLICY_VERSION_SUCCEEDED",
            aggregate_type="policy_version",
            version=4,
            payload={"supersedes_version": 4},
        )
        self.assertTrue(any("后继版本" in e for e in validate_event(record)))


if __name__ == "__main__":
    unittest.main()
