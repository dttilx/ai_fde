# Jev 隐私与人工介入策略

设计修订2.2.0 · 2026-10-04。本文件补充现行spec/plan/contracts；2.0原文件完整保存在history/pre-review-simplification-20261004/。Constitution不变，没有执行业务任务。

## 1. 本次明确改变什么

原2.0要求所有最终报告都REPORT_REVIEW暂停；Jev策略跳过可能进一步要求逐条人工审核。现改为基于证据与规则的例外复核，Jev状态与本地引用支持核验状态分别记录。资料外发授权不变且不能由用户随手确认替代。

保留LangGraph的REPORT_REVIEW/HIGH_RISK/EXPERT能力，触发变为条件式。图片等候选仍必须人工确认；AI仍不能确认最终根因；专家处理危险/冲突/无覆盖/资质边界，正式案例仍需人工审核。

## 2. Jev发送什么、绝不自动发送什么

Jev通过后端固定官方endpoint调用，只接收通过授权的结构化最小投影，不接收完整事件、Graph state/checkpoint或原始报障。

| 允许字段（仍须原资料许可） | 默认不进Jev请求 |
|---|---|
| 报警码；本次确认且必要的温度/电流/压力等白名单读数；必要的标准现象标签 | 姓名/联系方式/账号、客户厂名/地址、设备序列号/QR原值、内部事件/工单ID、绝对时间、合同/保修信息 |
| 每次随机来源别名P1/P2，来源类别与获准的最小技术摘录 | PDF/手册全文、任意自由文本、图片/视频/音频、MinIO URL/对象key、本地路径、资产完整档案 |
| 核验引用时的模板化技术陈述，以及同样获准的引用集合 | 原始报告、任意LLM自由生成段落、prompt/运行日志/完整历史、身份权限列表、密钥 |

白名单读数初版metric=set_temperature_c/actual_temperature_c/heating_current_a/upstream_pressure_mpa/device_pressure_mpa；每次最多8项。现象标签由已确认事实映射，未知不能补造。包括技术参数在内的字段也可能是商业秘密，白名单只是允许结构，不是外发授权。

每请求最多2个摘录，每段800字符，技术陈述最多500字符；question IDs与静态instructions由服务构造，不能拼入未检查自由文本。合并多来源支持时拆分会损失上下文，必须显式PARTIAL/UNKNOWN或本地核验/人工，不假装分段检查证明整体支持。

## 3. 后端调用前的确定性处理

1. 检查当前身份、事件与来源范围；读取原始资料仅限后端。
2. 检查每个贡献输入的provider/purpose/期限/依据，原DENY直接拦截，不能先脱敏再升级为APPROVED。
3. 从获准字段构造projection，不使用“发给另一个云模型帮我脱敏”的方式。
4. 本地去掉标识/个人字段，随机alias映射只保存本地；技术摘录需先经发布时人工批准外发的版本，运行期不得任意摘要重写解除限制。
5. 检查JSON schema、长度、敏感标识/路径/URL/密钥等规则；残留或不确定则跳过。规则检测不保证识别所有商业秘密，发布许可仍是必要条件。
6. 原子预留预算；只向配置白名单中的官方HTTPS endpoint调用，禁用任意base_url/未审批代理和跨域重定向；现有timeout/retry约束继续生效。
7. 本地记录EgressReceipt：请求ID、输入hash、来源版本、projection_version、policy/basis refs、provider/mode/模型/usage、允许或跳过原因。默认日志不保存请求正文，receipt按事件范围保护；授权调试留存必须单独配置有限期限。

已批准的来源release+字段用途+provider policy可复用授权，运行期逐次代码检查，不逐次弹人工审批。缓存按projection/source/rubric/model/policy版本绑定，命中重授权；alias不能跨事件恢复内部ID。撤权后停止新调用，不能撤回已发数据。

原手册/工单即使抹掉客户名仍可能是保密资料；许可未确认就SKIPPED_POLICY。需要真实Jev展示时，用自主编写、明确允许处理的模拟技术片段和事件，保持REAL模式；原题资料走本地处理。严禁把“技术资料类”当公开资料。

## 4. 供应商条件与个人项目选择

2026-10-04查阅[TypeSafe隐私政策](https://typesafe.ai/legal/privacy-policy)：承诺不使用输入训练/微调，但有数据留存表述，并说明服务在美国托管。[官方Legal说明](https://docs.typesafe.ai/legal)提供企业ZDR选项，需要单独确认；普通API账户不能宣称零留存。本文未验证任何账户已启用ZDR，也未验证私有化或本地Jev部署能力。

ProviderDataProfile记录terms_url/version/checked_at、retention_mode UNVERIFIED|STANDARD|ZDR_VERIFIED、region声明/已确认范围、review_actor、允许数据origin与用途。origin=EXAM_SOURCE|LIVE_FIELD|SELF_AUTHORED_SIMULATION|PUBLIC_REFERENCE，不代替classification/read/egress三轴。

个人项目默认：真实Jev只处理明确获许可模拟材料或已批准的非敏感技术投影。考试原文和真实现场敏感资料默认不外发。若以后必须外发真实现场敏感内容，需要来源权利人的处理依据和provider留存/地域条件；要求ZDR时必须有账户合同配置证据。ZDR不能代替来源授权，也不保证零泄露。不为当前演示购买企业套餐或增加代理服务作为隐私捷径。

## 5. 按风险触发人工介入

| 环节 | 正常路径 | 人工触发 |
|---|---|---|
| 文字/表单 | 提交即确认明确观察，推测仍未确认；无需再次点击事实确认 | 缺必要事实只问会影响决策的信息 |
| 图片/OCR/视频/QR | 一屏展示候选与来源，用户选择后批量确认/修正/拒绝一次；不预选接受 | 矛盾/危险/无法判断保留提示；不因批量操作抹去风险 |
| 检索结果 | 代码路由、Jev评估或显式降级，不让工程师审核每个片段 | 必要知识缺失/真实事实矛盾交专家 |
| 引用支持 | 先本地核验；可用已验证模板和谓词证明则RULE支持，Jev受限不自动导致人工 | 非模板生成陈述、来源不足或未知支持进入异常陈述清单 |
| 常规报告 | AUTO_VALIDATED直接显示有证据的建议报告，不额外暂停 | 不满足自动条件才REPORT_REVIEW；严格演示配置FORCE_REVIEW可保留全部复核路径 |
| 专家接管 | 高风险立即通知停机，不等确认 | 同一snapshot危险/冲突/资质问题合并一张待办，HIGH_RISK与EXPERT不串联重复点击；新事实需重新安全判断 |
| 维修与案例 | 根因、执行者、维修及复机证据集中一张表单；完整性由代码检查 | CASE_REVIEWER一次查看并明确选择批准范围/发布，后台分别审计审核和发布，不扩大发送许可 |

批量确认是减少操作次数，不是取消逐条证据的明确决定。批量ClaimReview每条仍需decision/source/hash，前端不默认全选通过。已有有效审核可在同一claim内容、证据、引用、scope/资质/政策版本未变化时复用，不在每次graph重放重复询问。

## 6. 自动报告的严格条件

ReportReleaseDecision记录release_mode AUTO_VALIDATED|HUMAN_REVIEWED|PENDING_REVIEW、policy_version、check refs、template refs、report/evidence/source hashes、actor/scope版本、reason codes。

AUTO_VALIDATED只用于AI建议报告，且必须全部满足：
- 独立风险门与检索后支持门CLEAR，没有未解决危险、证据冲突、必要事实缺失、无覆盖或资质/服务边界；
- 当前已确认事实快照，所有ID/出处/引用/顺序/资质/预算检查通过；
- 每个实质原因/指令都匹配已验证的版本化模板及明确谓词，并以当前证据及引用集核验；未约束的LLM自由文本不得改变实质含义；
- 原因永远POSSIBLE；手册步骤、安全前提、停止与专家条件保留；不能自动确认根因或批准复机；
- 当前身份与全部资料使用权限再次通过；保存不可覆盖的报告及release decision。

模板来自人工审定的本地知识release，包含render规则、事实字段/单位/时间适用条件、源引用及反例测试。已验证模板配置是发布时治理，不是运行期每次人工审核。默认示例A203只有完整事实及必要授权均已明确时才能走自动路径。模板不存在/变更未验证时必须例外复核，不能用Jev置信度或另一个LLM说“通过”替代条件。

Jev高置信度不单独使报告自动发布。非模板自由生成内容即使Jev称支持，首版仍进入REPORT_REVIEW；无法支持则修改/删除该陈述并保留历史，或升级。专家修订报告始终HUMAN_REVIEWED。PENDING_REVIEW可查看草稿而不冒充最终结果。高风险停机通知始终即时自动呈现。

## 7. 接口、任务与验收影响

新增批量Evidence review与ClaimReview入口，每请求最多20项，逐项expected version及明确decision；一次事务全部通过才提交，任意冲突409无半批静默成功，复核记录逐项追加。案例review可显式publish_on_approval=true，必须绑定publication_scope及policy version；审核与发布分别鉴权/审计，后台Job失败显示APPROVED_UNPUBLISHED，重试不重新审核未变内容、不重复发布。

A203验收：普通完整授权模板AUTO_VALIDATED无REPORT_REVIEW暂停；FORCE_REVIEW同场景验证interrupt/resume；缺事实/资质/自由生成未支持内容不能自动发布。A310只对必要信息暂停，已补全且模板全部通过可直接出报告；新增危险转单一专家待办。媒体一批复核，案例一张审核表，停止通知零等待。

隐私验收：截获模拟HTTP请求，未授权发送数为0；允许请求只含严格字段，原始description/姓名/QR/序列号/对象URL/原工单ID/合同/图像及密钥不出现；state、instructions、question criteria、重试及日志一起检查。脱敏但无许可必须被拦；改hostname/redirect/失效provider条件也拦；人工点击不能绕过DENY。真实Jev用模拟输入，记录模式和实际模型；保留语义有无投影损失对照，不承诺匿名化完全消除风险。

当前94任务不增加新平台，扩展既有外发适配器、报告发布、证据面板和审核任务。本次只更新设计，后续实测才证明交互次数和信息保护有效。

## 8. Contract closure 2.2
Report v4 allows nonblocking optional follow-up in AUTO reports. Every question has a server-derived blocking flag; safety, missing applicable facts, conflict, coverage or authorization uncertainty always remains blocking. The UI cannot flip this flag to release a report.
Jev v2 adds typed material presence/P1 indicator, door/reclose status, visible jam, affected module/panel and onset-phase observations to cover seven alarms. Only confirmed necessary authorized inputs are projected; null/UNKNOWN/empty represents unknown or omitted, never inferred absence. No raw prose, identities, timestamps or maintenance IDs are added. Source/input DENY still prevails. Projection context loss returns PARTIAL/UNKNOWN.
A Jev support result is an auxiliary assessment; only verified local template proof or applicable human review satisfies publication policy for a material claim. Non-template generated claims remain human-reviewed even with high Jev confidence.
