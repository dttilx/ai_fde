# Implementation Plan: APX-240 Multimodal Field Diagnosis Loop

**Revision**: 2.1.0 | **Date**: 2026-10-04 | **Feature identifier**: 001-apx240-multimodal-diagnosis (workspace has no Git repository)

原文完整保存于 history/pre-jev-access-20261004/。integration-review.md 记录所有替换决策、发现与剩余条件；本文件是当前技术方案，非实现完成声明。

## 1. 技术选型与范围

| 部分 | 当前决定 | 替代方案与取舍 |
|---|---|---|
| 工作台 | Next.js、React、TypeScript | Python页面可更轻，但不利于证据复核和状态交互 |
| 后端 | Python 3.11+、FastAPI、Pydantic、SQLAlchemy/Alembic | 不拆微服务，模块与事务边界更易个人维护 |
| 数据与检索 | PostgreSQL、pgvector；精确结构化、关键词、向量 + RRF | 不新增 OpenSearch/多套向量库；中文关键词首版用规范词表与参数化关键词匹配，不能声称默认英文全文配置能分词中文 |
| 媒体 | 私有 MinIO/S3适配器；文件系统降级 | 数据库仅元数据，不保存大文件；无需公共bucket |
| 编排 | LangGraph、PostgreSQL checkpointer | 仅诊断图，不编排整个应用；放弃自定义暂停恢复框架 |
| Job | PostgreSQL持久化任务、本地in-process worker | Redis可后续适配，第一版不要求 |
| OCR/VLM | PaddleOCR兼容适配器、可替换视觉provider | 本地OCR优先；真实型号需配置与实测，fixture不冒充识别能力 |
| 视频/QR | FFmpeg/OpenCV、QR本地解码 | 短视频关键帧；声音为人工定位观察，无自动ASR/声学故障识别承诺 |
| Jev | 官方异步SDK或System One HTTP适配器 | 检索结果评估必须存在；不使用OpenAI接口套其独立契约；受限输入显式跳过 |
| LLM/Embedding | 可替换市售模型、本地/获许可外部provider、fixture | 生成模型不能被Jev替代；embedding外发也受策略限制 |
| 身份 | 本地账号、不透明服务端会话、三个角色 + scope/资质 | 不建SSO或权限引擎，未来接入企业身份系统 |
| 验证与运行 | pytest、JSON Schema、Playwright；Compose数据库/MinIO + 本地前后端 | 不上Kubernetes；源资料与含秘密配置不进公开仓库 |

规模：单组织、APX-240设备族、七报警/五案例/五工单，少于20演示并发用户。多组织管理、GraphRAG、设备控制、训练、完整MES/SCADA/EAM、自动保修审批均不在范围。

性能目标是待测目标：普通页面动作2秒内，文字活动执行30秒内，单图/受限视频处理60秒内；人工等待单独计时。性能验收记录硬件、模式、媒体大小、网络、P50/P95、超时与样本；未达到目标必须报告，不伪称保障。

## 2. 模块职责

| 模块 | 输入/输出与依赖 | 明确不负责 |
|---|---|---|
| access | 验证会话、事件/资产/来源scope、角色资质；输出可信ActorContext；依赖DB/审计 | 不由模型授予权限，不做完整企业身份平台 |
| incidents | 原始描述、结构化事实、资产/可选保修；生成事件与成员范围 | 不确认故障根因 |
| evidence | 通用文字/表单证据从文字MVP起存在；媒体生成候选、复核追加版本 | 不自动把图片观察变事实，不解析声音根因 |
| safety | 本地已审核SAFE/报警模板；前置风险与检索后支持检查；安全通知 | 不依赖Jev或LLM批准安全 |
| diagnosis | LangGraph、预算、同线程恢复、报告/manifest、待人工动作 | 不发送设备指令，不泄露高权限checkpoint |
| knowledge | 本地资料导入、定位/版本、scope混合检索、Jev结果评估、引用 | 不检索未审核案例，不学习未审核事件 |
| expert | 分配专家接管、事实处理、追加修订 | EXPERT不等于CASE_REVIEWER/电气资质 |
| feedback | 执行者/维修证据/复机验证、草稿、审核/脱敏/共享发布 | 不自动污染生产索引 |
| shared | DB、私有storage、Job、模型外发网关、版本/审计/配置 | 不包含业务根因决策 |

## 3. 端到端与安全顺序

入口验证身份/资源，保存报障即做快速本地安全检查；明确危险文本立即通知，不等待媒体或保修。媒体候选只能复核后进入正式上下文；可明确排除未使用媒体继续文字路径。若可疑媒体尚未核实导致风险不明，只能澄清/升级，不能用排除按钮抹去已知风险。

prepare固定事实快照 → safety_gate风险检查 → retrieve(scope过滤 →精确报警/必要来源→混合检索→外发检查→Jev) → 独立安全服务做支持/冲突检查 → decide →追问/专家/草稿 → finalize引用/模板/权限验证 → 自动建议报告或例外人工复核。

前置安全门查SAFE-01～04、已知矛盾和风险不明；SAFE-05的无覆盖/检索新冲突在检索后再检查。不得要求检索前已经知道所有检索结果，但任何排查建议前两道检查均完成。读取本地安全/报警规则是规则执行，不是允许危险场景普通RAG。A205报警本身触发停止；SAFE-01/危险A520不进入普通检索。

安全自然语言不能只做子字符串搜索：“无焦味”“昨天有现已停机”“不确定是不是焦味”要保留否定、时间、歧义。规则高危肯定描述立即阻断；歧义作风险不明；结构化安全字段辅助确认。模型补充风险信号只能增加核实/阻断，不能反向放行。没有描述所有症状不等于强制无限追问，按已提供事实及适用动作决定必要问题。

## 4. 身份与资料政策

会话Cookie HttpOnly；非localhost部署HTTPS/Secure；写请求校验CSRF。密码使用成熟哈希库；退出/停用后服务端会话立即无效。后台产生ActorContext，客户端actor_id/role字段不构成授权。

FIELD_ENGINEER处理授权事件，EXPERT仅处理分配事件，CASE_REVIEWER负责分配草稿的发布；管理员本地管理账号/grants，不自动成为技术审批者。QualificationGrant记录电气/机械授权、来源、范围、有效期；拆线/绝缘/回路等步骤由SAFE-04映射资质。无资质只能转相应人员处理，系统不能发现场工作许可。

资源分类TECHNICAL_REFERENCE/FIELD_RECORD与外发DENY/APPROVED_REDACTED/APPROVED_RAW分别记录。本组织技术资料亦非公网；现场资料按事件成员/资产范围。所有Incident/Media/Evidence/来源/输入自由文本有policy，派生摘要/报告/关键帧继承依赖资料最严格限制：读范围取交集、外发要求全部满足。不因批准案例、删除姓名或改成向量而解除限制。

源考试资料默认禁止外发，直到处理依据被记录；许可单独限定provider、purpose、期限和版本。Jev、LLM、VLM、远程embedding全部经统一网关，输入state/questions/instructions/日志/重试同样检查。自建允许处理的模拟资料用于真实Jev测试；本地市售模型可处理受控考试资料完成真实模型验收。当前不能保证现场机器能运行哪个模型，属于部署条件，不用fixture掩盖。

每个读取/变更端点包括媒体URL、Job/SSE、引用、导出和checkpoint检查资源范围。敏感不存在/无权限统一返回404；角色不足403；UI不显示未授权资料数量/标题。SQL scope先过滤再检索，缓存命中重新授权。

MinIO私有；缩略图继承媒体权限。短链接60秒内仍可能继续有效，严格撤销场景用后端鉴权下载。应用数据库与迁移账号分离，默认不做RLS/权限引擎。终端用户没有数据库/对象存储账号，连接只能经后端；runtime账号不持有schema迁移/超级用户权限，worker只使用其所需服务凭据，MinIO服务凭据限定私有bucket操作。数据库、checkpointer初始化由独立管理过程执行，密码与API key不进入前端或checkpoint。访问范围首版由应用层强制并通过跨事件测试，不声称数据库按每个终端用户做RLS隔离。

## 5. RAG、Jev与引用

七类逻辑集合：安全、报警、手册、历史案例、工单、已审核案例、资产；classification与collection是两个不同维度。PDF提取保留七页章节/表格定位与checksum；受控源文件路径，不向公开仓库复制。相同checksum与解析/索引配置复用release，源或配置变化新release。检索release不可覆盖。

结构化命中保留报警模板；关键词/向量各最多20条，在授权范围内RRF(k=60)去重，非必要候选最多8条。手册/案例/工单保持多样性，必要source独立保留。小规模授权集合用精确向量距离，避免近似过滤丢失召回。中文用报警/工单正则及行业同义词表，向量补足语义；未来分词器非当前必需。

每次节点来源读取、外部调用和发布前重查现行访问/外发政策；所有候选都经过Jev stage；真实调用仅对允许处理、预算足够且未命中有效缓存的候选执行。每段state最小事实+来源上下文；Score判断相关性，Choice判断技术/历史/背景/无关/未知与历史差异/当前冲突线索，Noul判断试图越权指挥模型的异常文本。问题条件写在instructions，question key仅结果映射。

必要安全/精确报警不能被Jev删改；历史差异进入对照、当前冲突线索保留并核实。明显无关且无冲突的评估首版仅折叠（FOLDED）而不永久排除，保留可审核来源。Jev评分不是根因概率。疑似攻击来源隔离、必要源完整性问题升级；判别器不是唯一安全屏障，片段不产生工具权限。

Jev首轮默认评估4条、每轮最多8条、并发2；单次3秒/每轮15秒；可重试错误最多重试一次，SDK与Job不能重复放大重试。调度前保留6次剩余工具额度给生成/引用/恢复，预算不够的候选标SKIPPED_BUDGET而非无关；三轮不能保证每轮8条都外部调用。每次实际调用/重试计工具，usage计token；无usage扣预留保守上限并标UNKNOWN，不按0算。

版本化Rubric v1规定四相关等级与明确“无法判断”；无关折叠条件初值可为无关Choice且p>=0.90、confidence>=0.80、无冲突线索、相关性最低等级，不用于安全判断。首版模板验证的常规建议报告可自动发布，非模板/未解决语义问题例外复核；真实标注样例校准前不将自动评估称最终验证。保守阈值变化发布新ranking_policy版本。

原因claim与source逐项先查ID/release/checksum/locator/摘录权限，再按外发许可用Jev Choice判断支持/矛盾/未支持/未知，单次同样计预算。具体操作模板一致性由代码验证。最多一轮草稿修复；本地版本化模板能证明支持时记RULE而不逐条人工；剩余不确定明确人工核对，决策性矛盾必须修正/核实不能一键照旧发布。

评估状态SUCCESS、PARTIAL、UNAVAILABLE、SKIPPED_POLICY、SKIPPED_BUDGET、NO_CANDIDATES、FIXTURE、CACHED均可追溯。无key/许可拒绝/超时保留普通混合检索和本地必要来源，不能假装Jev通过。所有来源无法通过生成provider外发时，用确定性安全/报警结构化草稿、本地市售模型或转人工；禁止凭空输出。

## 6. 图、Job与恢复

节点：prepare/safety_gate/retrieve/decide/ask_information/expert_review/finalize。图状态十种，以contracts/graph-state.schema.json为公共摘要；另有internal-graph-state.schema.json描述内部快照/计数/manifest，不把两者混用。

DiagnosisRun.status直接采用十状态，RUNNING只用于Job；WAITING_EXPERT/CONFLICT_BLOCKED可恢复，ESCALATED是终止转交，COMPLETED/ESCALATED/FAILED终止。FINALIZING可以interrupt REPORT_REVIEW，此时Job SUCCEEDED/result_kind PAUSED，不代表诊断完成。

thread_id等于diagnosis_run_id，PostgreSQL native checkpoint_id和应用checkpoint_version分开。resume按最新会话/范围/角色/资质、interrupt_id/type、expected version和幂等键检查，数据库事务预留ResumeRequest+新Job；每线程fenced lease防并发。重复key、旧版本或并发409无新effects；/information调用同一服务，追加事实/报告版本，不创建新线程。

每个恢复先到safety_gate，旧事实纠正追加record并标supersedes，不覆盖原记录；旧危险不能仅通过“专家确认”按钮解除。新的可信事实与隔离依据重新评估，仅授权人员处置，AI不批准复机。

安全复核后按interrupt类型路由：INFORMATION新增事实再检索；REPORT_REVIEW无事实/草稿变化时直接提交已审核且hash一致的原草稿，不再生成或再次暂停。证据/报告hash变化使审核失效，追加新草稿重新执行发布策略，仍需人工时重新审核；EXPERT/HIGH_RISK按已核实结果继续阻断或进入允许分支。逐条ClaimReview通过独立写接口提交并绑定陈述及报告版本，恢复接口只引用有效审核记录。

预算持久化在DiagnosisBudgetLedger，跨重试/恢复/linked run累计：32节点步骤、3检索轮、5不同追问、20工具/外部请求、12000token、5恢复、120活动秒；输出单报告上限2500tokens。归一化代码/纯数据库事务不伪造LLM工具次数；节点/检索/tool均有清晰计量规则；检索调用也计工具。预算先预留、再结算，失败与重放也消耗；人等待排除；执行停机不依赖预算。

取消：当前Job CANCELLED，图FAILED/failure_reason USER_CANCELLED，fencing阻止迟到结果及恢复。checkpoint不可用FAILED/CHECKPOINT_UNAVAILABLE，不能隐式启动空线程。worker崩溃凭持久化租约过期及fencing恢复，不假设线程会自动释放；节点外部副作用按run/node/input/effect key幂等。

run固定资料scope不随专家加入扩大；需更广资料用linked run，由专家作用域生成，输出仍限其来源权限。原证据保留；预算ledger共用，不能新run规避上限。撤权后禁止复用旧敏感快照；凭据不入checkpoint；用户只取公共summary。LangGraph内部checkpoint、预算和业务提交不是一个天然事务，用执行记录/outbox及checkpoint引用对账测试处理中断窗口，不宣传框架天然exactly-once。

## 7. 报告、多模态与反馈

报告已知事实只代表本次确认输入；模型观察、未知、矛盾、手册参数分区；历史事实作为历史比较。原因POSSIBLE有rank/支持反对缺失证据/排序理由。所有原因、安全要求、排查、停止与升级都有引用；历史相似不确认当前根因。

check_sequence遵循alarm_step_ref，已完成步骤可跳过但保留完成依据；隔离和资质不能跳过。安全升级report普通steps为空，以安全停止指令代替。evidence_sufficiency代替未经验证的总confidence。

通用Evidence从文字MVP存在；SOURCE为TEXT/FORM/OCR/VISION/VIDEO，QR只资产定位记录不进故障事实；统一CANDIDATE/CONFIRMED/CORRECTED/REJECTED/UNAVAILABLE，复核追加。图快照只包含确认/修正版本。

图片最多5张/单张10MB；视频每事件1个/60秒/100MB/最多8帧；解码超时30秒，图片解码最大2500万像素，视频先验证编码/尺寸/时长，不凭扩展名；损坏/超限/不支持显式拒绝。无防病毒scanner时本地演示标NOT_PERFORMED，不声称clean；部署至他人可访问环境必须配置扫描/隔离，scan报告模式需可见。用户可排除非必要候选，但可疑危险须澄清。声音仅用户观察关联视频时间点。

保修可选UNKNOWN/ACTIVE/EXPIRED及来源/服务方，日期代码比较；限制必须有合同依据。Warranty未确认不阻断报障，不猜失保。维修反馈可先以UNVERIFIED保存不完整或复机失败记录；确认根因、授权executor、维修证据与成功复机证据齐全后，服务端追加READY_FOR_REVIEW版本；仍需案例审批。CASE_REVIEWER审核，脱敏与scope另批准，索引发布幂等且可退役新release。

## 8. 项目结构与垂直切片

backend/app/{access,incidents,evidence,safety,diagnosis,knowledge,expert,feedback,shared}/各有models/schemas/service/routes（按需要）。knowledge/passage_assessment.py与shared/providers/{jev,egress,llm,embeddings,fixtures}.py；diagnosis/{graph,nodes,state,checkpoints,resume,budgets,report,citation_assessment}.py。frontend保留报障、复核、时间线、专家、反馈、审核；新增Session、RetrievalAssessment、CitationAssessment面板。

实现顺序：基础与access/egress → 本地知识/资质安全/图 → 文字Evidence与报告 → Jev fixture链路 → A203独立验收 → SAFE-01 → A310 → 媒体 → 真实provider/恢复 → 专家/反馈 → 综合验收。Jev真实受限情况不阻断确定性MVP，完整Jev验收需真实允许输入；P1不依赖维修闭环。

## 9. 可追溯性、验证与交付

Manifest记录图/prompt/generator与Jev实际模型、索引/release、证据快照、引用、检索候选与路由、rubric/ranking版本、actor/scope/egress版本、工具/usage/延迟、checkpoint/Job/ledger及明确降级。审计原始payload受控不进公开日志，无隐藏推理。

按quickstart覆盖七报警、未知码、错引用、对照/事实冲突、安全否定歧义、媒体失败/越限、跨事件权限、外发阻止、缓存撤权、暂停并发/重启、取消/超时、案例审核分享。真实市售模型与Jev分别记input/output/model/mode，对比评估不得只用fixture。收集五项考试提交材料，安全演示没有原因时标不适用而非要求参与者寻找虚构原因。

备份演示DB与媒体并做至少一次恢复验证；保留策略由显式配置约束，删除媒体需tombstone并说明引用不可用，不以“不可覆盖”承诺无限保留。演示提供空队列/健康状态、任务失败与预算可见，不建设监控集群。

## 10. Constitution Check 与未确定条件

设计层面满足安全、事实复核、有界、引用、人工负责、版本不可覆盖及模块化约束；不把文档检查称实际安全测试通过。Constitution 1.0.0未改。具体实现以tasks和契约验证。

外部处理考试资料的许可、Jev账号/可固定模型/留存与地域条件、其他provider数据条款、现场硬件与本地真实模型能力仍未知，见integration-review.md。未知输入默认DENY，采用本地处理/模拟测试/明确人工路径；不需要现在停止文档合并，但完整真实现场验收依赖实际部署配置。

## 11. 隐私投影与例外复核（2.1.0）

[隐私与介入策略](privacy-review-policy.md)是本轮新增规范。Jev不接收完整Graph state；shared/providers/jev_payload.py只构造获准的结构化读数/现象、随机来源别名和最小批准摘录。provider条件、外发依据与payload白名单自动检查，授权按release/provider/purpose/version复用，不逐请求弹确认。脱敏不放宽DENY；原考试资料未知许可仍本地处理，真实Jev用明确获许可的模拟数据。其他远程模型同样受原网关控制。

新增ReportReleaseDecision与TemplateRegistry（diagnosis/release_policy.py、knowledge/templates.py），严格本地模板/引用集谓词证明可替代因Jev不可用导致的逐陈述人工核验。AUTO_VALIDATED必须安全CLEAR、事实/出处/顺序/权限/资质/预算全部通过，只能输出POSSIBLE建议，不能确认根因/复机。其他情况REPORT_REVIEW；FORCE_REVIEW保留演示和测试路径。Jev高分不能单独批准报告。报告契约升级v3，其他原有schema保留v2。

前端将Evidence与ClaimReview集中在一屏，显式选择逐项决定后批量提交；高风险/冲突待办按snapshot合并而不连续HIGH_RISK→EXPERT重复点击。维修确认/动作/复机证据一张表，案例审核与发布可一次明确选择批准scope，后台两步分别鉴权/审计/幂等，失败为APPROVED_UNPUBLISHED并允许受控重试。不完整RepairOutcome保持UNVERIFIED，不满足READY_FOR_REVIEW不得创建CaseDraft，符合Constitution“维修确认后形成案例”的要求。
