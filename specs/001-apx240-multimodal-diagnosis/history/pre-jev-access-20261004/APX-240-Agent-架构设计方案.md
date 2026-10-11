# APX-240 自动封装设备故障诊断 Agent

## 1. 文档目的

本文档定义 APX-240 自动封装设备故障诊断 Agent 的产品边界、系统架构、Agent Loop、知识检索、证据治理、多模态输入和维修反馈闭环。

设计依据：

- 《FDE 实习生考试题库.docx》第六题“制造设备故障诊断助手”；
- 《06题 APX-240 自动封装设备说明书.pdf》；
- 参考项目 `Large-Model-Application-main` 中的模块化单体、有限 Agent Loop、证据溯源、人工接管和反馈治理设计。

本文档的目标不是构建完整的工业控制平台，而是设计一个能现场试用、判断有依据、边界清晰、可持续沉淀的诊断应用。

## 2. 产品定位

### 2.1 产品职责

Agent 负责：

1. 接收不完整的现场报障；
2. 从文字、结构化字段和可选的图片、视频、OCR、QR 结果中提取证据；
3. 检查安全红线；
4. 基于 APX-240 手册、报警码、历史案例和维修记录进行检索；
5. 区分已知事实、可能原因、缺失信息和矛盾信息；
6. 在信息不足时追问；
7. 给出有证据的排查顺序和升级判断；
8. 接收维修结果，形成待审核的新案例。

### 2.2 明确不负责的内容

第一版不负责：

- 直接启停设备或下发 PLC 指令；
- 修改热封温度、气压或伺服参数；
- 短接安全门或绕过报警；
- 带电拆线、带压拆装、接触加热部件；
- 自动确认最终根因；
- 用未经审核的事件自动更新生产知识库；
- 训练或微调基础大模型；
- 建设完整的 MES、SCADA、EAM 或工单管理平台。

Agent 是诊断和决策辅助系统，不是设备控制系统和自动维修系统。

## 3. 题目要求映射

题目要求的最终输出字段为：

| 题目要求 | 系统对应模块 |
|---|---|
| 故障现象 | 事件标准化与报告生成 |
| 可能原因 | 报警码检索、案例检索、证据排序 |
| 证据来源 | Citation / Evidence Service |
| 排查顺序 | 报警码规则与安全规则 |
| 需要补充的信息 | 信息完整性检查和追问节点 |
| 是否升级专家 | Safety Gate 与升级状态机 |

说明书第 7 页进一步要求：

- 已知事实；
- 安全前置条件；
- 停止条件/升级。

因此最终报告也必须包含这些字段。

## 4. 总体架构

```text
┌─────────────────────────────────────────┐
│             Next.js 现场诊断工作台        │
│ 报障录入 | 证据复核 | 诊断时间线 | 专家接管 │
│ 维修回填 | 案例审核 | 引用抽屉             │
└───────────────────┬─────────────────────┘
                    │ HTTPS / SSE
┌───────────────────▼─────────────────────┐
│         FastAPI 模块化单体后端            │
│ Incident | Evidence | Safety | Diagnosis │
│ Knowledge | Cases | Expert | Feedback    │
└─────────────┬───────────────┬───────────┘
              │               │
              │               └──────────────┐
              ▼                              ▼
┌────────────────────────┐      ┌────────────────────────┐
│ 有界 Agent 编排器       │      │ 多模态解析服务           │
│ Prepare → Retrieve      │      │ OCR / VLM / QR / ASR     │
│ → Decide → Finish       │      └────────────────────────┘
└─────────────┬──────────┘
              ▼
┌─────────────────────────────────────────┐
│ 证据与知识层                              │
│ 结构化规则 | 手册库 | 报警码库             │
│ 历史案例 | 维修记录 | 设备资产库           │
│ PostgreSQL + pgvector / OpenSearch        │
└─────────────────────────────────────────┘
```

建议采用模块化单体，而不是第一版就拆成多个微服务。模块之间通过明确的领域对象和接口隔离，长时间任务、多模态推理和后续高并发需求再独立部署。

## 5. 核心业务流程

```text
创建报障事件
    ↓
上传文字、图片、视频或 QR
    ↓
媒体隔离扫描与解析
    ↓
用户确认 OCR / 视觉 / QR 候选证据
    ↓
生成 FaultEvent
    ↓
安全红线检查
    ├─ 高风险：立即停机并升级专家
    └─ 普通风险：进入诊断 Loop
    ↓
提取报警码、读数、模块、时间和现象
    ↓
分库检索与证据合并
    ↓
判断信息是否足够
    ├─ 不足：输出必要追问，状态 NEEDS_INFORMATION
    ├─ 矛盾：停止进一步操作，状态 WAITING_EXPERT
    ├─ 高风险：状态 ESCALATED
    └─ 足够：输出诊断报告，状态 COMPLETED
    ↓
现场人员回填维修结果
    ↓
专家确认后生成 VerifiedCase
```

## 6. Agent Loop 设计

### 6.1 Loop 节点

Agent Loop 使用有限状态图实现，不采用无上限的自主循环。

```text
INTAKE
  → EVIDENCE_REVIEW
  → SAFETY_GATE
  → PREPARE
  → RETRIEVE
  → DECIDE
      ├─ RETRIEVE_MORE → RETRIEVE
      ├─ NEEDS_INFORMATION → FINISH
      ├─ ESCALATE → FINISH
      └─ FINAL → FINISH
  → REPORT
  → FOLLOW_UP
```

### 6.2 每个节点的职责

| 节点 | 职责 | 不允许做的事 |
|---|---|---|
| INTAKE | 接收输入并创建事件 | 不直接生成根因 |
| EVIDENCE_REVIEW | 确认 OCR、VLM、QR 候选 | 不把候选结果自动当事实 |
| SAFETY_GATE | 命中 SAFE-01 至 SAFE-05 | 不被普通模型结论覆盖 |
| PREPARE | 标准化事件、准备查询 | 不补全缺失读数 |
| RETRIEVE | 查询指定知识库 | 不把历史案例当当前结论 |
| DECIDE | 决定继续检索、追问、升级或结束 | 不执行设备动作 |
| FINISH | 形成结构化报告 | 不输出无来源的确定结论 |
| FOLLOW_UP | 接收维修结果并进入审核 | 不自动发布新知识 |

### 6.3 Loop 预算

第一版建议使用以下硬限制：

```json
{
  "max_steps": 8,
  "max_retrieval_rounds": 3,
  "max_tool_calls": 3,
  "max_questions": 5,
  "timeout_seconds": 120,
  "max_report_tokens": 2500
}
```

达到预算后，Agent 输出当前可确认信息和停止原因，不继续猜测。

### 6.4 决策动作

模型只允许返回以下动作：

```text
RETRIEVE_MORE
NEEDS_INFORMATION
ESCALATE
FINAL
```

不提供“执行维修”“修改设备参数”等动作。

## 7. 多模态输入与证据管线

### 7.1 输入类型

| 输入 | 第一版定位 | 证据用途 |
|---|---|---|
| 文字描述 | 必须支持 | 报警、现象、时间和人工观察 |
| 结构化表单 | 必须支持 | 温度、气压、电流、设备编号 |
| 图片 | 推荐支持 | 面板读数、外观异常、部件状态 |
| OCR | 推荐支持 | 报警码、仪表文字、控制面板 |
| QR | 可选增强 | 设备资产定位 |
| 视频/音频 | 后续增强 | 摩擦声、漏气声、周期性振动 |

### 7.2 证据对象

所有输入统一成 Evidence 对象：

```json
{
  "evidence_id": "evi-001",
  "type": "OCR",
  "content": "实际温度 128°C",
  "source_media_id": "media-001",
  "confidence": 0.96,
  "status": "CONFIRMED",
  "observed_at": "2026-10-03T14:20:00+08:00",
  "locator": {"page": null, "bbox": [120, 80, 340, 160]}
}
```

Evidence 状态：

```text
CANDIDATE → CONFIRMED
CANDIDATE → CORRECTED
CANDIDATE → REJECTED
```

只有 `CONFIRMED` 和经人工修正的 `CORRECTED` 证据进入诊断上下文。

### 7.3 OCR 和视觉模型边界

- OCR 识别失败时，标注“无法读取”，不能猜测文字；
- VLM 只能输出“观察到的可见现象”；
- 图片不能证明内部线路、继电器或加热回路状态；
- 视频分析结果必须标明时间范围和模型置信度；
- QR 只用于设备定位，不直接证明故障原因。

## 8. 安全控制架构

### 8.1 安全规则优先级

```text
安全红线
  > 当前设备状态
  > 当前报警码
  > 正常参数
  > 维修记录
  > 历史案例
  > 模型常识
```

### 8.2 规则示例

```json
{
  "rule_id": "SAFE-01",
  "triggers": ["烟雾", "焦味", "异常高温", "剧烈振动", "金属摩擦", "部件松脱"],
  "decision": "ESCALATE",
  "actions": ["立即停机", "禁止继续试运行", "升级专家"],
  "source": "APX-240说明书第3页"
}
```

### 8.3 安全输出卡

高风险场景不与普通诊断混排，而显示独立的安全卡片：

```text
安全等级：高
立即动作：停机并隔离风险
禁止动作：继续试运行、绕过安全门、带电拆线
必须介入：授权电气/机械维修人员或专家
依据：SAFE-01、SAFE-02、SAFE-03
```

## 9. RAG 架构

### 9.1 知识库分层

| 知识库 | 主要内容 | 默认权重 |
|---|---|---:|
| safety_rules | SAFE-01 至 SAFE-05 | 最高 |
| alarm_codes | A101 至 A900 | 高 |
| equipment_manual | 模块和正常参数 | 高 |
| historical_cases | H01 至 H05 | 中 |
| maintenance_records | WO-240 工单 | 中 |
| verified_cases | 人工确认的新案例 | 中高 |
| asset_registry | 设备编号、QR 和专属历史 | 查询过滤 |

### 9.2 资料处理流程

```text
原始 PDF / 表格 / 工单
  → 文档解析
  → 结构化抽取
  → 章节/表格切块
  → 生成 citation anchor
  → 关键词索引 + 向量索引
  → 检索评测
  → 发布 Index Release
```

### 9.3 结构化与向量化并存

报警码、正常参数和安全规则必须结构化保存。例如 A203：

```json
{
  "alarm_code": "A203",
  "meaning": "热封温度低",
  "possible_causes": [
    "未预热",
    "设定错误",
    "加热器开路",
    "继电器/线路故障",
    "T1偏差"
  ],
  "check_sequence": [
    "核对设定与预热",
    "读取实际温度和加热电流",
    "停机锁定",
    "授权电气人员检查"
  ]
}
```

自然语言故障描述、历史案例和维修记录可以进行向量化，但向量相似度不能替代安全规则和报警码匹配。

### 9.4 查询路由

```text
有报警码 → alarm_codes + equipment_manual
有温度/气压/电流 → equipment_manual + alarm_codes
有设备编号/QR → asset_registry + maintenance_records
提到“上次维修” → historical_cases + maintenance_records
出现安全词 → safety_rules 直接拦截
```

### 9.5 混合检索

检索由四部分组成：

1. 编号和专有名词的关键词检索；
2. 故障描述的向量检索；
3. 设备型号、模块、报警码和资料版本过滤；
4. 根据当前证据进行重排序。

推荐优先级：

```text
当前安全规则
  > 当前报警码
  > 当前读数对应的正常参数
  > 当前设备维修记录
  > 历史案例
```

### 9.6 GraphRAG 的使用边界

可以建立轻量故障关系图：

```text
A203 ──MANIFESTS_AS──> 热封温度低
热封温度低 ──COMPATIBLE_WITH──> H1加热回路开路
H1加热回路开路 ──MITIGATED_BY──> 授权电气维修
```

但第一版不需要建设复杂的 Neo4j 平台。关系图的价值主要是：

- 连接报警、模块、症状、原因和动作；
- 解释为什么某个历史案例相关；
- 检查排查顺序是否跨越安全边界。

## 10. 查询路由与证据合并

Agent 不直接把检索文本放进 Prompt，而是先生成 EvidenceBundle：

```json
{
  "confirmed_facts": [],
  "observed_facts": [],
  "possible_causes": [],
  "sources": [],
  "missing_information": [],
  "contradictions": [],
  "safety_decision": {}
}
```

事实状态必须明确：

```text
CONFIRMED       用户或资料明确提供
OBSERVED        OCR/VLM 观察结果
POSSIBLE        有资料支持的可能原因
UNCONFIRMED     尚未确认
CONTRADICTED    存在冲突
```

如果现场读数与历史记录不一致，EvidenceBundle 必须保留两者，并生成差异说明。

## 11. 报告生成契约

最终报告采用结构化 JSON 存储，同时在前端渲染为易读报告：

```json
{
  "status": "COMPLETED",
  "fault_phenomenon": "出现A203，热封实际温度低于设定值",
  "known_facts": [],
  "possible_causes": [],
  "evidence_sources": [],
  "safety_preconditions": [],
  "check_sequence": [],
  "missing_information": [],
  "stop_conditions": [],
  "escalate_expert": false,
  "confidence": 0.0
}
```

生成限制：

- `COMPLETED` 必须至少有一条引用；
- `NEEDS_INFORMATION` 必须有缺失信息；
- `ESCALATED` 必须有安全或证据原因；
- 每个可能原因必须关联来源；
- 不允许输出未经引用的确定根因；
- 不允许输出危险操作建议。

## 12. 诊断状态机

```text
DRAFT
  → EVIDENCE_REVIEW
  → QUEUED
  → RUNNING
  → NEEDS_INFORMATION
  → COMPLETED
  → WAITING_EXPERT
  → EXPERT_REVISED
  → CLOSED
```

状态解释：

| 状态 | 含义 |
|---|---|
| DRAFT | 报障已创建，尚未提交 |
| EVIDENCE_REVIEW | 正在确认 OCR、视觉和二维码候选 |
| QUEUED | 已进入诊断队列 |
| RUNNING | Agent 正在执行有限 Loop |
| NEEDS_INFORMATION | 需要补充现场信息 |
| COMPLETED | 已形成有证据的诊断建议 |
| WAITING_EXPERT | 风险、冲突或知识缺口需要专家 |
| EXPERT_REVISED | 专家已形成新版本结论 |
| CLOSED | 维修结果已确认并归档 |

AI 报告不可被专家直接覆盖，专家修订以新版本保存。

## 13. 后端模块设计

```text
backend/
├─ incidents/       故障事件和生命周期
├─ evidence/        媒体、OCR、VLM、QR 和证据复核
├─ safety/          安全规则和升级判断
├─ diagnosis/       Agent Loop、状态和报告契约
├─ knowledge/       文档、切块、索引、引用
├─ cases/           历史案例、维修案例、案例审核
├─ assets/          设备资产和 QR 映射
├─ expert/          专家接管和修订
├─ feedback/        诊断质量反馈
└─ audit/           运行事件、版本和追踪
```

服务层通过接口注入：

```text
EvidenceService
SafetyDecisionService
KnowledgeRetriever
CitationService
DiagnosisOrchestrator
ExpertReviewService
CaseCurationService
```

路由层只处理 HTTP、鉴权和参数转换，不直接执行模型推理和知识库逻辑。

## 14. 前端工作台设计

### 14.1 报障页

字段：

- 设备编号 / QR 扫描；
- 报警码；
- 故障描述；
- 发生时间；
- 温度、气压、电流；
- 异常声音、气味、振动；
- 图片、视频上传。

### 14.2 证据复核页

展示：

- 原图和 OCR 框；
- VLM 观察结果；
- QR 解码结果；
- 置信度；
- 接受、修正、拒绝操作；
- 证据状态。

### 14.3 诊断时间线

展示：

```text
报障创建
  → 证据确认
  → 安全检查
  → 查询报警码
  → 查询历史案例
  → 生成诊断
```

不展示模型内部思维链，只展示可审计的步骤、动作、引用和结果。

### 14.4 报告页

使用分区展示：

- 安全处置卡；
- 已知事实；
- 可能原因；
- 排查步骤；
- 缺失信息；
- 专家升级；
- 引用来源抽屉。

### 14.5 维修反馈页

字段：

- 最终确认根因；
- 实际维修动作；
- 执行角色；
- 复机验证；
- 是否复发；
- 是否生成候选案例。

## 15. 关键数据模型

### 15.1 Incident

```text
incident_id
asset_id
reported_by
reported_at
status
raw_description
alarm_codes
normalized_event
```

### 15.2 DiagnosisRun

```text
diagnosis_run_id
incident_id
agent_graph_version
prompt_version
model_release_id
index_release_id
status
report_json
started_at
completed_at
```

### 15.3 Citation

```text
citation_id
source_type
source_file
page_or_section
chunk_id
content
content_checksum
index_release_id
```

### 15.4 VerifiedCase

```text
case_id
source_incident_id
alarm_codes
observed_symptoms
confirmed_root_cause
repair_action
restart_validation
review_status
reviewed_by
```

## 16. 闭环与知识治理

闭环分为四级：

```text
Raw Event
  → Maintenance Record
  → Expert Confirmed Case
  → Published Knowledge
```

只有专家确认、证据完整且复机验证通过的事件，才可以进入 `VerifiedCase`。

知识等级：

```text
CANONICAL       官方说明书和安全规则
VERIFIED_CASE    人工确认的新案例
HISTORICAL       旧维修记录
RAW_EVENT        未确认事件
```

默认诊断检索 `CANONICAL` 和 `VERIFIED_CASE`；`HISTORICAL` 作为参考；`RAW_EVENT` 不进入生产诊断索引。

## 17. 参考场景设计

### 场景 A：A203 信息充分

输入：

> A203，设定温度 165°C，实际温度 128°C，加热电流 0A，已预热 10 分钟。

预期行为：

- 匹配 A203；
- 引用 H02 和 WO-240-042；
- 将 H1 加热回路开路列为可能原因；
- 要求停机、锁定挂牌；
- 指定授权电气维修人员；
- 不直接写“已确认根因”。

### 场景 B：A310 信息不足

输入：

> 设备报警 A310，好像有漏气。

预期行为：

- 不直接断定下游接头松动；
- 追问上游压力和设备端压力；
- 询问是否有持续漏气声；
- 给出停机泄压前置条件；
- 状态为 `NEEDS_INFORMATION`。

### 场景 C：安全红线

输入：

> 设备出现焦味，热封区域温度突然升高。

预期行为：

- 立即触发 SAFE-01；
- 建议停机并升级专家；
- 禁止继续试运行；
- 禁止徒手接触加热部件；
- 不继续普通原因检索。

### 场景 D：二维码和图片

输入：设备二维码、控制面板照片和故障描述。

预期行为：

- 先确认二维码对应设备；
- OCR 提取报警码和读数；
- 展示识别候选并等待确认；
- 将确认后的证据加入 FaultEvent；
- 识别失败时明确要求重新拍摄。

## 18. 验收标准

### 功能验收

- 可以直接打开 Web 入口；
- 可以输入文字报障；
- 可以上传至少一种图片格式；
- 可以识别和引用 A101、A203、A205、A310、A401、A520、A900；
- 可以引用 H01 至 H05 和 WO-240 工单；
- 输出题目要求的全部字段；
- 信息不足时进入 `NEEDS_INFORMATION`；
- 高风险场景进入 `ESCALATED` 或 `WAITING_EXPERT`；
- 可以回填维修结果；
- 未审核事件不会进入正式知识库。

### 质量验收

- 事实和推断不混淆；
- 每个可能原因有来源；
- 历史案例不覆盖当前证据；
- 现场读数和维修记录冲突时能明确说明差异；
- 不输出带电拆线、绕过联锁等危险建议；
- 诊断结果可查看模型、提示词和知识索引版本；
- 原始 AI 报告和专家修订可以同时保留。

## 19. 实施优先级

### P0：必须完成

1. 文字报障；
2. APX-240 手册、报警码、案例和工单知识库；
3. 安全规则层；
4. 有界 Agent Loop；
5. 结构化报告；
6. 引用和证据显示；
7. 缺失信息追问；
8. 专家升级；
9. 一个可现场打开的 Web 入口。

### P1：重点增强

1. 图片上传和 OCR；
2. 证据候选复核；
3. 设备资产和 QR 映射；
4. 诊断时间线；
5. 维修结果回填；
6. 候选案例审核。

### P2：后续扩展

1. 视频和音频分析；
2. 轻量 GraphRAG；
3. 离线现场工作包；
4. 多设备族；
5. 检索评测和诊断质量看板；
6. 与工单系统或设备台账系统对接。

## 20. 最终设计结论

APX-240 Agent 的核心不是“聊天 + 向量库”，而是：

```text
多模态证据采集
  + 安全规则拦截
  + 有界 Agent Loop
  + 分层混合 RAG
  + 证据引用与冲突检查
  + 专家接管
  + 维修结果闭环
```

参考项目中最值得复用的设计是有限 Loop、版本 Manifest、引用溯源、人工复核、追加式反馈和多模态候选确认。与参考项目相比，本项目应缩小企业基础设施范围，把复杂度集中在 APX-240 的安全诊断体验、证据质量和现场可用性上。

