# 儿童手表保护策略台

本仓库记录该项目已确认的领域对象、事件名称和基础校验方式，便于不同系统交换一致的数据。

## 资料范围

- `contracts/domain.schema.json`：领域事件信封、聚合类型、事件名称与分事件必备字段。
- `data/sample.json`：一条用于本地联调的中文样例。
- `data/events/`：一条完整的事件链样例（建档 → 逐项授权 → 学校时段 → 拦截 → 托管冲突 → 使用摘要），覆盖下文的常驻规则。
- `src/`：事件信封与分事件负载的最小校验代码。
- `tests/`：验证样例符合基础约定，并保证 schema 与校验代码一致。

## 决定因素

每项功能是否开放，由以下十一项因素共同决定。每次放行或拦截都必须把当时的取值完整记入 `DECISION_AUDITED.factors`，缺一项即无法重放。

| 因子键 | 含义 | 约定取值 |
| --- | --- | --- |
| `age_stage` | 年龄阶段 | `preschool` / `lower_primary` / `upper_primary` / `teen` |
| `guardianship` | 监护关系状态 | `standard` / `temporary_custody` / `disputed` |
| `school_window` | 是否处于学校授权时段 | `in_window` / `out_of_window` |
| `emergency_contacts` | 对方是否紧急联系人 | `listed` / `unlisted` / `not_applicable` |
| `location_precision` | 当前定位精度 | `precise` / `coarse` / `hidden` |
| `acquaintance_social` | 熟人社交 | `open` / `limited` / `closed` |
| `stranger_contact` | 陌生人联系 | `open` / `limited` / `closed` |
| `ranking_rewards` | 排行奖励 | `on` / `off` |
| `content_rating` | 内容分级上限 | `age_6` / `age_9` / `age_12` |
| `spending_limit` | 消费额度状态 | 如 `{"period": "monthly", "remaining": 12.0, "currency": "CNY"}` |
| `health_prompts` | 健康提示规则 | 如 `{"rule_version": "pv-2026.09.3", "enabled": true}` |

## 常驻规则

下列规则编号供 `DECISION_AUDITED.rules_applied` 引用，也是排查争议时的共同语言。

| 编号 | 规则 |
| --- | --- |
| R-01 | 低龄默认：仅语音通话、紧急求助、必要定位（粗精度）默认开放，其余高风险能力默认关闭。 |
| R-02 | 高风险能力由监护人逐项开启（`FEATURE_CONSENTED`），可随时撤回（`FEATURE_CONSENT_REVOKED`），撤回即生效。 |
| R-03 | 监护冲突顺序：生效中的临时托管人 → 主要监护人 → 其余监护人按绑定先后；家庭关系变化（解除绑定）后立即按新关系重算。 |
| R-04 | 跨品牌好友仅交换必要标识，班级名单等群组信息不开放。 |
| R-05 | 健康提示等规则的错误标签通过发布后继版本纠正（`supersedes` 指向前驱），不原地改写历史记录。 |
| R-06 | 连续奖励、倒计时等付费入口与常规入口共用同一消费额度决定，不得绕过；支付类决定必须记录 `entry_point`。 |
| R-07 | 拦截或限制必须给出恢复时间（`restores_at`）或恢复条件（`restore_hint`），措辞儿童可读。 |
| R-08 | 监护人获得使用摘要（`USAGE_SUMMARY_ISSUED`），不提供聊天全文。 |
| R-09 | 学校仅在监护人授权的时段内实施授权的最小控制集，时段外不施加控制。 |
| R-10 | 每次决定记录策略版本与全部决定因子，支持安全人员重放。 |

## 功能默认态

- **默认开放**：语音通话、紧急求助、必要定位（粗精度）。低龄用户建档后即可使用，无需授权。
- **逐项授权**：`precise_location`（精确定位）、`acquaintance_social`（熟人社交）、`stranger_contact`（陌生人联系）、`ranking_rewards`（排行奖励）、`payment`（支付）、`content_above_default`（超出默认分级的内容）。每项授权是独立聚合（`feature_consent`，标识为 `儿童标识:能力`），开启与撤回各记一条事件。

## 监护冲突与家庭关系变化

1. 存在生效中的临时托管（`CUSTODY_DELEGATED` 起止时间内）时，托管人在其 `scope` 范围内优先。
2. 无托管时主要监护人（`role: primary`）优先。
3. 其余监护人按 `GUARDIAN_LINKED` 绑定先后排序。
4. 家庭关系变化（`GUARDIAN_UNLINKED`）或托管结束（`CUSTODY_ENDED`）后，立即按新关系重算顺序。

每次冲突的解决结果记入 `GUARDIAN_CONFLICT_RESOLVED`，携带争议能力、胜出监护人与所依据的规则编号。

## 聚合与事件

| 聚合 | 事件 | 说明 |
| --- | --- | --- |
| `child_profile` | `CHILD_PROFILE_REGISTERED`、`AGE_STAGE_CHANGED`、`EMERGENCY_CONTACT_SET`、`POLICY_ASSIGNED`、`USAGE_SUMMARY_ISSUED` | 建档与年龄阶段、紧急联系人、策略版本指派、使用摘要 |
| `guardian_authority` | `GUARDIAN_LINKED`、`GUARDIAN_UNLINKED`、`GUARDIAN_CONFLICT_RESOLVED`、`CUSTODY_DELEGATED`、`CUSTODY_ENDED` | 监护绑定与解除、冲突解决、临时托管 |
| `policy_version` | `POLICY_VERSION_PUBLISHED` | 策略版本发布；更正通过 `supersedes` 指向被纠正的前驱版本 |
| `feature_consent` | `FEATURE_CONSENTED`、`FEATURE_CONSENT_REVOKED` | 高风险能力逐项授权与撤回 |
| `school_window` | `SCHOOL_WINDOW_AUTHORIZED`、`SCHOOL_WINDOW_REVOKED`、`SCHEDULE_APPLIED` | 学校时段授权、撤销与最小控制执行 |
| `spending_limit` | `SPENDING_LIMIT_SET` | 消费额度设定与调整 |
| `feature_decision` | `DECISION_AUDITED` | 每次放行或拦截的审计记录 |

聚合标识约定：`guardian_authority`、`spending_limit` 使用儿童标识；`feature_consent` 使用 `儿童标识:能力`；`school_window` 使用 `儿童标识:学校`；`feature_decision` 使用决定标识。同一聚合上 `version` 从 1 起逐条递增。

每次授权（`FEATURE_CONSENTED` / `FEATURE_CONSENT_REVOKED`）与策略切换（`POLICY_ASSIGNED`）都会留下事件，供审计。

## 审计与重放

`DECISION_AUDITED` 携带 `policy_version_ref` 与完整的 `factors`。排查一次错误放行时：

1. 取出该决定的 `policy_version_ref`，确认当时生效的策略版本（含其 `supersedes` 链）。
2. 取出 `factors` 与 `subject`，用同一策略版本重新评估。
3. 重放结果应与 `outcome` 一致；不一致说明策略版本内容或因子采集存在问题，按 R-05 发布后继版本纠正。

## 记录不可变与数据最小化

记录一经接收，标识、发生时间与版本不得原地改写；更正使用新的后继记录。个人、机构及商业敏感信息仅向履行职责所需的调用方开放：监护人只见使用摘要而非聊天全文（R-08），跨品牌好友不见班级名单（R-04），学校只在授权时段拿到最小控制集（R-09）。

## 本地检查

```bash
python3 -m unittest discover -s tests
```
