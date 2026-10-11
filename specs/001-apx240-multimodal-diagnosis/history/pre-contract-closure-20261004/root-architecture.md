# APX-240 自动封装设备故障诊断 Agent — 当前架构总览

版本2.1.0，2026-10-04。已合并Jev、资料权限和考试要求补齐；这是设计，不是可运行实现。

## 1. 当前设计入口与历史保留

完整现行定义见：
- [功能规格](specs/001-apx240-multimodal-diagnosis/spec.md)
- [技术方案](specs/001-apx240-multimodal-diagnosis/plan.md)
- [数据模型](specs/001-apx240-multimodal-diagnosis/data-model.md)
- [研究决策](specs/001-apx240-multimodal-diagnosis/research.md)
- [API与Schema](specs/001-apx240-multimodal-diagnosis/contracts/http-api.md)
- [验收说明](specs/001-apx240-multimodal-diagnosis/quickstart.md)
- [任务](specs/001-apx240-multimodal-diagnosis/tasks.md)
- [合并冲突/不足/决定/剩余条件](specs/001-apx240-multimodal-diagnosis/integration-review.md)

原版全文包括旧Loop、GraphRAG增强、预算、ASR和阶段安排已完整存入 [原始架构快照](specs/001-apx240-multimodal-diagnosis/history/pre-jev-access-20261004/APX-240-Agent-架构设计方案.md)。没有无声删除；新正文替代旧运行约定，旧决策保留可审查。最高约束仍为Constitution1.0.0；需求在spec，具体技术在plan/contracts，tasks不能自行定义不同规则。

## 2. 产品职责与亮点

根据不完整报障输出故障现象、当前事实、可能原因、证据、安全前置条件、排查顺序、补充信息和停止/升级判断。现场试用入口与真实市售模型自测是交付要求。设备与资料为虚构考试材料，不能作为真实维修指导，原文件禁止公开流出。

四个亮点：多模态候选可纠正；LangGraph诊断可暂停重启恢复；Jev评估检索来源且引用可核对；维修证据审核后沉淀范围受控的新案例。

## 3. 架构与模块

Next.js/React/TypeScript工作台 → FastAPI模块化单体 → PostgreSQL/pgvector + 私有MinIO。

access管可信身份/scope/资质；incidents管事件/资产/可选保修；evidence管文字与媒体候选/版本；safety独立确定性规则；diagnosis用LangGraph；knowledge做分层混合RAG/Jev；expert与feedback管人工修订、维修和审核。shared提供Job、外发网关、存储、日志与审计。无Redis硬依赖，无微服务或企业权限平台。

## 4. 安全与事实

危险文字即时通知，不能等待模型/媒体/身份政策查询结果产生维修建议。前置安全门先于普通检索，检索后无覆盖/新冲突再查独立SAFE-05，建议前全部通过。A205报警本身停机；SAFE-01不许危险试运行。专家确认不解除禁令。

本次确认事实、模型观察、未知、矛盾和手册值分区；历史根因不作为当前确认根因。历史相同点/差异/缺失与排名支持反证都进入报告。普通排查严格按手册报警模板和人员资质；危险报告允许没有普通检查。

## 5. 资料与权限

两类：TECHNICAL_REFERENCE与FIELD_RECORD；另有事件/设备范围及DENY/APPROVED_REDACTED/APPROVED_RAW外发政策。通用非公开，脱敏非许可。账号身份由后端会话验证；工程师/专家/审核人分别授权，维修电气/机械资质独立；管理员不默认审批维修。

数据库检索先scope过滤。媒体、引用、Job/SSE、checkpoint、导出及缓存都检查同一资源边界。组合输入/派生输出继承各来源限制，Jev/LLM/VLM/embedding共用网关。题库/手册原文外发许可未知默认DENY，可用合法模拟资料真实验证Jev，原题真实模型可配置受控本地市售模型。

## 6. RAG与Jev

结构化安全/报警 + 关键词/向量混合 → 必要来源保留/RRF去重 → policy最小化 → Jev相关性、适用性、历史差异/冲突、异常指令评估 → 当前证据/历史/待核实集合 →报告。

Jev评分不确认根因、不授予权限。必要来源与冲突不能被低分抹掉。首版无关来源折叠且可审查，校准前不永久删除。评估真实/fixture/缓存/策略跳过/预算跳过/不可用明确显示。引用先代码查ID/版本，再对陈述及引用集合做语义复核或经验证的本地模板核验或异常陈述人工复核。

默认4候选评估/每轮最多8、并发2、请求3秒/轮15秒；总预算预留6次后续调用，动态缩减，不承诺3轮全量8候选。每请求/重试计预算，未知usage保守扣账。

## 7. LangGraph与Job

prepare → safety_gate → retrieve → decide → ask_information/expert_review/finalize。七节点，十状态见正式契约。等待专家/冲突仍可恢复，终止ESCALATED分开；thread=run_id、PostgreSQLcheckpointer。

暂停Job成功PAUSED释放worker，恢复同thread新Job，现行身份/范围/资质/政策再次校验并重查安全；锁/版本/幂等/fencing及副作用对账防重复。专家扩大资料范围须关联新run且共享budget，不把专家checkpoint给工程师。无事实变化的REPORT_REVIEW在安全复核后直接发布审核过的原草稿，不再检索/生成/反复暂停；逐条审核使用版本/hash绑定接口。

共享上限32步骤、3检索、5不同追问、20工具请求、12000tokens、5恢复、120累计活动秒，报告2500tokens；人等待不计。取消不能撤回已发送的数据，只阻止后续调用/输出。

## 8. 媒体、保修与反馈

图片5张/单张10MB/2500万像素；视频1个/60秒/100MB/8帧。OCR/VLM结果候选，接受/修正/拒绝后入事实。QR仅资产关联；无自动声学识别，声音由人确认定位。可选非风险媒体允许排除走文字，已知风险不准抹除。

保修记录确认日期/服务方/政策来源，不猜失保。不完整/复机失败维修反馈明确UNVERIFIED；实际执行者、资质、根因人工确认、维修与成功复机证据齐全后追加READY_FOR_REVIEW版本；CASE_REVIEWER审批、脱敏和scope发布后才能进正式索引，旧证据/报告保留。

## 9. 验证与不扩大范围

A203/SAFE-01/A310独立验收，不依赖维修闭环；七报警回归、Jev真实允许输入、错引用/历史比较、权限/外发、恢复失败、媒体降级与五项交付一并验收。无GraphRAG/Neo4j/因果图、PLC/设备参数、模型训练、全MES、多租户平台或自动保修理赔任务。

未解决的资料许可、provider留存地域/账号/模型、硬件可用性与实测性能在integration-review列出，不能凭文档宣称已经满足。

## 10. 本轮隐私与交互减负

[隐私/复核规范](specs/001-apx240-multimodal-diagnosis/privacy-review-policy.md)：Jev仅接收获许可的最小技术投影，原始报障/图片/视频/身份/QR/合同/checkpoint不进其请求；脱敏不能放宽禁止外发。正常来源授权复用、代码逐次检查，不逐次人工批准。

完整、低风险、来源及模板已验证且资质明确的建议报告自动显示；未支持的自由生成或风险问题才人工暂停，FORCE_REVIEW保留报告复核演示。媒体一次显式批量确认，专家一次处理同snapshot风险，根因/维修/复机一个表单，案例一次明确审核发布且后台分别鉴权审计。没有取消候选确认、专家风险接管或正式案例审核。
