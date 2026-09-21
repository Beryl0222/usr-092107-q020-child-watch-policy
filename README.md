# 儿童手表保护策略台

本仓库记录该项目已确认的领域对象、事件名称和基础校验方式，便于不同系统交换一致的数据。

## 资料范围

- `contracts/domain.schema.json`：领域事件信封、聚合类型与事件名称。
- `data/sample.json`、`data/samples/`：用于本地联调的中文样例，每种事件与聚合至少一条。
- `src/validator.py`：信封校验，以及事件与聚合挂载、载荷必填/禁用字段等跨字段规则。
- `tests/`：验证样例符合约定，并覆盖各条红线规则的负向用例。

## 功能开放的共同决定因素

每次授权由以下因素共同决定，缺一不可：年龄阶段、监护关系、学校时段、紧急联系人、
定位精度、熟人社交、陌生人联系、排行奖励、内容分级、消费额度、健康提示。
每次授权与策略切换都记录 `DECISION_AUDITED`，载荷必须含 `policy_version` 与 `basis`
（决定依据），否则无法重放。

## 默认姿态与逐项授权

- 低龄用户默认仅开放：通话（白名单）、求助（SOS）、必要定位。
- 高风险能力（陌生人联系、排行奖励、支付、跨品牌好友等）默认关闭，由监护人逐项
  `FEATURE_CONSENTED` 开启，并可随时 `FEATURE_CONSENT_REVOKED` 撤回，撤回立即生效。

## 监护冲突与家庭变化的解决顺序

1. 安全能力（求助、紧急联系）任何角色不可关闭；
2. 有效时段内的临时托管人（`CUSTODY_DELEGATED`，必须含起止时间）；
3. 第一顺位监护人（`GUARDIAN_LINKED` 登记 `priority`）；
4. 其余监护人按登记顺位；
5. 学校仅在授权时段内执行最小控制集；
6. 同级冲突取更严格的方案。

每次冲突解决记录 `GUARDIAN_CONFLICT_RESOLVED`（含 `resolution_rule`）；家庭关系变化
记录 `GUARDIAN_RELATION_CHANGED`，自 `effective_at` 起适用新顺位。

## 隐私与最小化

- 好友关系（`FRIEND_LINKED`）不得携带班级名单字段，跨品牌好友同样适用；
- 家长只收到使用摘要（`USAGE_SUMMARY_DELIVERED`），事件不得包含聊天全文；
- 学校时段（`SCHEDULE_APPLIED`）必须含起止时间，时段外不得实施控制；
- 个人、机构及商业敏感信息仅向履行职责所需的调用方开放。

## 版本与更正

记录一经接收，标识、发生时间与版本不得原地改写；更正使用新的后继记录。
健康规则等错误标签通过 `POLICY_VERSION_SUCCEEDED` 纠正，必须注明 `supersedes_version`，
且后继版本号必须高于被纠正版本。

## 付费护栏

消费额度由策略版本给出；每次放行或拦截记录 `PAYMENT_LIMIT_ENFORCED`（含 `outcome`）。
连续奖励、倒计时等营销机制不得作为放行依据，载荷出现 `streak_override` 或
`countdown_override` 即视为违规。

## 儿童可理解的限制说明

`RESTRICTION_EXPLAINED` 必须含 `feature` 与 `resume_at`，让孩子能看懂某项限制何时恢复。

## 审计与重放

安全人员通过 `DECISION_REPLAYED`（引用 `original_event_id` 与当时的 `policy_version`）
重放一次错误放行所使用的策略版本和决定依据。每种事件只能挂在唯一聚合上，
保证事件流可按聚合重放；对照关系见 `src/validator.py` 的 `EVENT_AGGREGATE`。

## 本地检查

```bash
python3 -m unittest discover -s tests
```
