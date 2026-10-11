# 实施记录

2026-10-04，依据设计 2.2.0。基础层已验证，US1 正在集成验收；尚未完成整个功能。

| 任务 | 实际验证 |
|---|---|
| T001 | 模块目录和包可导入 |
| T002/T004 | 后端健康检查测试通过；ruff、mypy 通过；uv.lock 锁定依赖 |
| T003/T005 | 前端单元测试、ESLint、Next.js 生产构建通过；package-lock.json 锁定依赖 |
| T006 | Compose PostgreSQL 健康，pgvector 0.8.5；应用角色无超级用户/建库/建角色能力；MinIO health 200、匿名 bucket 403、scoped 服务账号初始化成功 |

环境：Windows、Python 3.13.5、Node 24.14.1、Docker Desktop。
镜像下载初次受到现有镜像源限制；使用已缓存的官方版本 cpuv1，未更改全局 Docker 配置。
全部模型暂为 FIXTURE；未调用任何外部模型，未发送考试资料。

## 基础层 T007–T026

48 项 pytest 测试通过；ruff 与 mypy 通过。真实 PostgreSQL/MinIO 上验证存储、迁移升级/回滚（隔离测试数据库）、知识导入幂等、配置变更新 release、session/CSRF/停用、派生权限交集、Job 七状态/超时/取消 fencing、预算 reservation、effect replay/outbox/checkpoint 匹配及独立安全门。新 Python 进程恢复 PostgreSQL 中的 LangGraph interrupt，恢复新增 A205 后未进入普通检索。

LangGraph 当前是七节点基础图，完整报告节点将在 T040/T041 接入；模型 fixture 不代表真实诊断质量。PDF 的 NUL 字形以替代符保存，并带 UNMAPPED_GLYPH 警告和原始文本 hash；未猜测缺失符号。应用数据库和原题文件未被迁移回滚测试删除或修改。

## US1 集成进展（上述基础层记录之后）

已接入真实数据库上的 Incident、EvidenceSnapshot、DiagnosisRun、报告/引用版本、七节点诊断服务、同 thread 的恢复接口和本地 worker。最近一次完整后端回归为 54 项通过；随后 A203 专项 5 项和 ClaimReview 专项 2 项通过，尚不能把专项数量直接作为最新完整回归结果。

A203 参考读数以 RULE/FIXTURE 生成 AUTO_VALIDATED 报告，包含 A203/H02/WO-240-042；强制复核以 PostgreSQL checkpoint 暂停、释放 Job，并追加 HUMAN_REVIEWED 报告。缺失事实暂停补充，危险/矛盾输入不进入普通检索。非参考读数必须逐项审核，审核批次为原子事务；修订创建新草稿并使旧审批失效。所有根因仍为未确认。

前端登录、文字报障、时间线、报告、引用抽屉、信息补充和审核面板已接通。ESLint、TypeScript/Next 生产构建通过；工作台组件正在拆分。浏览器强制复核测试已通过一次；普通流程因测试中页码写错失败，已根据实际来源第 6 页修正，等待重跑，不能算通过。桌面/手机截图尚未完成验证。

本机 3000 端口被已有 Docker 服务使用，项目改为 3010，未修改该服务。当前环境恢复后需再启动 API 与前端完成浏览器回归；恢复过程中的测试不计成功。未调用真实模型或外部 Jev，未外发考试资料。图片/OCR/QR、视频、A310 专项、专家业务接管、维修反馈和案例发布尚未完成；本记录不代表 tasks.md 中 T027 以后任务全部完成。

## 测试真实性审查

用户要求排查兜底式测试后，新增反例先捕获 7 个类型校验失败，修正业务校验后 74 项单元测试通过；三种独立错误注入分别导致 23、5、9 项断言失败。详见 `docs/test-integrity-audit.md`。当前基础设施尚未恢复，未把全量集成或浏览器回归标为通过。

## 环境恢复与最新验收（2026-10-04）

上述环境阻塞现已解除。完全退出 Docker Desktop 后，备份残留 socket 所在的运行时目录并重新启动；未恢复出厂、删除数据卷或修改原题资料。Docker 引擎 29.2.1 正常响应，PostgreSQL healthy、MinIO 正常运行。

恢复后的完整后端回归：`uv run pytest -q`，97 项通过。真实浏览器 A203 普通报告与强制人工复核两个场景通过，覆盖报告引用和暂停恢复；手机测试检查无横向溢出。桌面截图已查看，截图位于 `.private/output/playwright/`。

API 位于 http://127.0.0.1:8000，工作台位于 http://127.0.0.1:3010。以上为 RULE/FIXTURE 路径验证，真实模型与外部 Jev 仍未调用；US1 及整个功能的剩余任务尚未全部完成。本节更新最新状态，前述结果保留为历史记录。

## 文字证据、资产与恢复边界（2026-10-04 后续）

T027：保留原始报障、TEXT/FORM 来源与证据快照，保修记录新增确认与版本字段；数据库限制 Evidence 五种状态并拒绝覆盖原始输入/证据快照。未知、非 APX-240 和无访问授权的资产保持明确失败。迁移在独立数据库验证升级/回滚/再升级，应用库仅升级。

T028：新增授权资产查询、保修日期计算、版本化 ServiceRestriction。只有已确认且有来源的日期才可计算 ACTIVE/EXPIRED；未知保修不阻断报障或紧急停机。有效条款指定服务方时不自动授予维修权限，进入专家授权核实；恢复与发布前重新检查服务边界。资格查询与报告引用过滤设备范围、有效期、有效状态和非空来源，业务 EXPERT 角色不能替代技术资格。

T029：事件创建、查询、幂等、原始输入和现场危险提示已接通，并验证缺失事实/推测保留未知信息。反例先捕获 9 项解析断言失败，追加“我觉得当前”反例再捕获 1 项失败；修正后推测、历史、否定、近似读数和非有限数字不补成当前事实。前端仅发送当前问题的非空明确答案，不将空白转为 0、未知布尔转为 false。

新增恢复验收：错误 checkpoint/hash/interrupt 无副作用；并发恢复仅一成功一409、一个新 Job、一次预算和一次新报告；暂停取消保留原草稿且不能恢复；无事件授权的专家不能读取报告、Job、checkpoint 或恢复。相关较大任务 T042/T069/T071 尚有其他未完成要求，未整项打勾。

前端单元测试 9 项、ESLint 与生产构建通过；A203 浏览器测试 3 项通过，覆盖 AUTO、FORCE_REVIEW 和未知预热追问后同一诊断恢复。完整后端最新结果另记录于测试审查文档。

仍存在的缺口：TemplateRegistry 治理尚未完整接入自动发布（当前是窄范围 RULE/FIXTURE 谓词，不应宣称生产模板治理已完成）；完整报告字段展示、Jev 评估缓存/真实 provider、节点失败恢复全矩阵、SAFE-01/A310 独立验收、多模态及维修案例闭环仍待后续任务。保修和条款维护目前仅受控初始化/数据管理，不提供普通用户自行批准条款的入口。保留原有不足，不以已通过的局部验收替代全部 US1 完成。

## 模板绑定与报告展示（2026-10-04 后续）

已补上 T039/T041 的模板注册表与发布校验部分：DRAFT/VERIFIED/RETIRED、知识 release key、源引用 hash/位置/类别、渲染/谓词/事实解析指纹绑定；当前 proof 绑定模板 payload hash，恢复和报告查询重新核验，退役/改变引用/改变代码不能复用旧 proof。运行时代码指纹与源文本共同绑定，排除工作目录路径、行号和 marshal 序列化差异，并用独立 Python 进程验证一致性。仍保留完整任务未完成状态：自动修复、全套生产模板批准与其他治理要求尚未完成。

新增 `scripts/manage_templates.py`，默认只建 DRAFT；`--simulate-fixture-approval` 是显式、审计化的模拟批准，只允许 FIXTURE 模式、演示 EXPERT 与有效电气资格/引用范围。不是实际人工审定，不适用于 REAL 模式；模型和普通诊断请求不能批准模板。报告限制明确标注模拟批准。正常 AUTO 浏览器验收以这个显式 fixture 前提运行；缺少批准或绑定失效仍需复核，不隐藏失败。

已补上 T046 的只读 DiagnosisReport 组件，展示已确认/未确认信息、手册参数、历史同异/缺失、可选或必须追问、停止与升级条件、政策依据，保留引用抽屉和原有人工复核。布尔事实用“是/否”展示；明确手册参数不是本次现场读数。桌面与手机截图已查看，手机无横向溢出。修改/拒绝陈述的完整前端交互等要求仍待补齐，因此 T046 不整项勾选。

补充单位反例先出现3项真实失败，修正 K/mA/kPa 不直接当 C/A/MPa，并验证 A203 的单位不一致输入进入追问而非自动发布。

最终回归：后端158项通过、ruff/mypy通过；前端9项单测、ESLint、生产构建通过；3项真实浏览器 A203 场景通过。中途曾出现旧 worker 版本混用和指纹跨进程不稳定导致的失败，修复后重跑；未以失败结果充当成功。另有浏览器精确文本断言因装饰勾选字符失败，已将装饰与事实文本分为独立元素并隐藏装饰的无障碍读出，保留原断言后通过。

测试错误注入：注册表基线13项通过，故意绕过 registered_support 触发11项断言失败，无基础设施错误。历史缺口保留为历史记录；真实模型/Jev、真实模板人工批准、SAFE/A310完整独立验收、多模态、反馈发布与故障恢复矩阵仍未完成。任务计数保持29/94：本轮为较大任务的部分交付，不虚增整项完成数。

## 访问边界、诊断持久化与混合检索（2026-10-04 后续）

本轮完成并勾选 T030–T034，累计34/94，剩余60项。US1整体尚未完成；下个顺序为评估/审核模型与 Jev fixture 路由等 T035–T039，不越过其依赖直接宣布其他用户故事验收完成。

T030/T031：共享操作守卫分别检查可信角色、资源可见性和 WRITE 权限。未知授权类型不算 READ；资源无授权、策略拒绝、跨组织仍404，已可见资源的写权限不足返回403。独立账号验收覆盖现场工程师、专家、案例审核角色、资产可读不授予事件访问、SAFE/七报警码基线、技术资格不随业务角色自动获得、可读原题来源仍外发拒绝。既有派生政策交集测试继续通过。

T032：新增增量迁移 `0004d_diagnosis_integrity.py`，未重建或覆盖现有历史。数据库限制十种状态和非负 checkpoint，并拒绝倒退/跳跃、改变事件/执行人/知识范围/账本、借用另一事件的快照、把引用绑定到不对应的知识 release。报告/证据/恢复记录保留原 append-only 约束；专家待办原始理由不可覆盖，分配执行人允许变化。15项直接数据库验收加独立数据库升级/回滚/再升级通过。

T033：UNKNOWN 观察值保留为未确认信息，不再建成 CONFIRMED 事实；明确 false 与未知分开。22项标准化单测覆盖单位、推测、历史、否定、近似、溢出、重复文本/表单冲突和用户原因推测。先捕获 UNKNOWN 进入事实的实际失败，再修改解析；重新显式初始化新的模拟模板绑定，未声称真实人工批准。

T034：提取 fixture index/query-token/RRF 工具，保留结构化精确、安全/报警固定来源、关键词和 pgvector 路径。SQL授权范围在排序前应用；已审核案例通过状态、审核人、发布标识、设备型号与报警过滤，独立案例 release 不替换手册 release。资产经授权单独查询，不作为根因引用或提升来源权限。引用快照核对内容、位置、类别、hash 和 release；模板初始化调用同步补齐这些字段。14项 PostgreSQL 路由/伪造引用测试通过；自编案例仅在测试事务中存在并回滚，不是维修发布流程的验收。

最新验证：后端197项通过，ruff通过，mypy85源文件通过；浏览器 A203 AUTO、FORCE_REVIEW、未知预热追问/同一线程恢复3项通过。收紧引用输入时曾出现模板初始化旧调用缺少字段的12项失败/错误，已修复调用并完整复跑，未降级校验或将异常返回为成功。

扩展错误注入：引用路由基线14项通过，故意绕过引用来源校验时5项断言失败、0基础设施错误；注册表基线13通过/绕过11断言失败，既有三组注入仍被捕获。记录位于 `.private/test-audit/sensitivity.json`。

限制保持明确：向量目前为16维 hash fixture，证明数据库检索与融合链路而非真实语义质量；报告仍为 RULE/FIXTURE；未接实际 LLM 或 Jev。真实语义 provider、完整 Jev 预算/缓存、SAFE-01/A310故事完整验收、多模态和维修案例治理继续保持未完成状态。API与工作台仍为8000/3010，原数据与历史版本保留。

## Jev 检索评估、权限缓存与预算（2026-10-04 后续）

完成 T035–T038，累计38/94，剩余56项；US1整体和真实 Jev 接入尚未完成。T039 的完整陈述审核、语义支持与修订流程继续保持未完成，已有局部能力不能代替整项验收。

新增两次增量迁移至0004f，保存不可覆盖的 provider profile、逐贡献来源处理凭证、评估记录、输入/权限/策略/证据 hash、调用预留和有效期缓存。旧评估创建时间保持未知，不伪造为迁移时间；在独立数据库验证升级/回滚/再升级，应用库未重建。

Jev 阶段接到真实检索节点：确认事实投影为最小类型化字段，原题资料默认拒绝发送；只有显式许可的自编模拟资料进入本地 fixture。默认4/最多8候选、并发2、单次3秒、单轮15秒、最多一次重试，预留调用与Token在调用前提交，保留6次后续工具调用空间。超时用量未知时保守扣留，不返还未知成本；调用前后及缓存命中均检查当前权限，撤销许可后不使用已返回结果。缓存绑定来源、模型、rubric、输入、策略与授权范围，不能跨权限复用。

必要依据、历史对照和冲突来源保留；低相关材料仅符合严格条件时折叠，不删除。fixture 返回 UNKNOWN/null，不伪造模型评分。实际观察的型号和状态写入评估/Manifest；工作台读取真实记录，展示策略跳过、预算跳过、模拟、缓存及不可用，不再显示固定状态。模型错误响应、型号不匹配和异常错误文本不能冒充成功或泄漏到前端。

补充验收覆盖 A101/P1、A401安全门、A520伺服卡阻、A900模块/面板；不充分事实标为未知，ABNORMAL/RUNNING 不能擅自转换为 ALARM/STEADY_RUN。核对原始报警种子发现最初的 A401/A520 信息完整性映射写反，已修正并加入独立原文断言，不删除该不足记录。集成 fixture 曾因 detached ID 和过宽预留查询导致真实失败，修复 fixture/查询后重新完整验证，未放宽业务断言。

验证：完整后端234项通过，ruff通过，mypy88个源文件通过；前端12项单测、ESLint及生产构建通过，A203浏览器3项通过，覆盖评估状态和授权来源展开、引用抽屉及手机无横向溢出。错误注入新增Jev基线23项全通过，故意折叠必要来源后10项断言失败、0基础设施错误，既有五种错误仍被捕获。

本轮没有配置或调用真实 Jev/LLM；provider profile 明确标记仅本地模拟，不构成原题外发授权。真实 Jev 协议与语义效果留在 T066/T067，真实 embedding 仍未接入。SAFE-01/A310完整独立验收、多模态、专家业务接管、维修结果/案例发布和故障恢复全矩阵继续待做。当前下一项为 T039，不重新生成任务或宣称项目已完成。

## T039 本地引用支持与人工审核追加（2026-10-04）

本轮推进T039，新增 GET /api/diagnoses/{id}/citation-assessments：逐项返回陈述/报告hash、引用集合、规则验证/人工审核/未知支持、是否仍需审核和历史引用标识。读者必须具有事件与全部报告引用权限；可读引用或检索相关性不等于支持当前结论，历史参考不确认当前根因。生成、人工修订与发布阶段保存不可覆盖的 CitationAssessment，查询动态重新检查当前审核有效性。

引用查验补齐 source_ref、source_type、checksum 和具体页码/章节，对照真实来源记录，不仅对照数据库引用ID。重复陈述ID直接拒绝，防止字典覆盖。逐项接受、修订、拒绝与原子批量接口保留；接受凭证严格绑定报告/陈述hash、证据快照、执行人授权版本、来源/事件策略、资源授权与资格。失效、陌生或额外ID不能凑成有效集合；拒绝的陈述阻断旧批准。审核技术资格从服务端报告中的实际操作要求派生，不将业务专家角色或固定电气资格代替所有技术资格。

修订只追加新草稿，保留原稿与原审核，旧审核不能复用到新内容；新草稿逐项重新核对后发布第三个不可覆盖版本。禁止将修订文本变为最终根因确认或复机批准。单项审核可立即显示为HUMAN，但其余未知项仍需审核，不能用一条批准替代整份报告。报告仍是建议，工程师的模拟审核不是实际维修或根因证据。

先写反例捕获接口缺失与额外审核ID被错误接受；最初根因修订反例误用有效模板报告而没有待审列表，修正测试输入为非模板读数，再验证业务拒绝。实现时错误使用模型名和测试Job字段导致导入/字段错误，已修正并完整重跑，不把这些错误计为业务断言成功。旧API进程曾仍占用8000：核对命令行中的本项目venv/uvicorn路径后停旧进程，重新测试；旧进程混用的通过结果不作为最新验收。前端一次未监听3010导致4项连接失败，重新启动后再验收，未放宽断言。

最新验证在旧worker停止后执行：后端249项通过，ruff/mypy88源文件通过，前端12项单测/ESLint通过，启动当前API后4项浏览器流程通过。新增非参考读数浏览器验收检查所有审核框默认未选、无说明不能提交、没有逐项审核不能发布；其余AUTO、FORCE_REVIEW、缺预热补充恢复继续通过。审核敏感性专项15项基线全通过，故意绕过accepted_reviews后3项断言失败、0基础设施错误；专项写入.private/test-audit/claims-sensitivity.json，保留完整敏感性历史结果。

T039仍未整项勾选：获许可资料的Jev引用集合语义fixture调用及最多一轮自动草稿修复尚未接入。当前只如实提供本地RULE/HUMAN/UNKNOWN支持查询，不能宣称已完成Jev语义支持检查或自动修复；真实外部Jev仍未调用。累计完成数保持38/94，剩余56项。下一步先补T039剩余路径再进入依赖它的T040；此时不需要用户补材料或密钥。API8000和工作台3010已重新启动，原始资料和历史版本保留。

## T039/T040 完成与发布顺序修正（2026-10-05）

完成并勾选 T039、T040，累计40/94，剩余54项。上述38/94和T039未完成的段落保留为当时状态；本段记录随后补齐的能力。US1整体仍未完成，T041发布流程部分完成，T042及后续故事任务继续按依赖执行。

新增类型化 CLAIM_SUPPORT 评估和本地 FixtureJevClaimEvaluator。默认fixture只返回UNKNOWN，ScriptedClaimFixture仅用于测试SUPPORTS/UNSUPPORTED/CONTRADICTS/异常型号分支。评估按完整引用集合检查ID、来源版本、摘录、hash和当前访问/处理许可；原题资料保持DENY，不投影文本、不调用transport。只对明确授权的自编模拟资料构建最小JEV_MINIMAL_V2输入，绑定全部贡献来源、事实快照、目的、profile、权限hash、实际型号和调用凭证。超过两份引用不能静默丢弃其余引用，保留PARTIAL/需审核。

调用复用既有预算预留、超时、重试和六次后续工具调用空间。所有引用贡献来源在调用前后重新授权，缓存键加入当前处理许可结果，防止自然到期且版本未变时复用结果。发现旧冲突判定在许可撤销后仍会阻断新决策，已增加决策时的绑定、快照和许可检查：历史评估保留，失效评估不再参与决策。加入独立撤销反例，不删除前述不足。

Jev支持不授予发布资格：未知非模板陈述仍需逐项人工审核。当前有效的CONTRADICTS阻断普通报告审核并通过LangGraph转到EXPERT interrupt；修订该冲突需要专家角色以及实际技术资格/来源权限。UNSUPPORTED最多触发一轮保守自动修复：仅撤回缺乏支持的候选原因，不生成替代根因，不改写安全要求/排查步骤；以账本绑定的唯一预留限制重复修复，追加新草稿、原稿和评估引用，修订稿仍需人工审核。

Agent图版本2.5包含七个节点；继续检索回到安全门，知识缺失、信息不足和引用冲突分别走专家/追问/阻断。七项硬预算分别为32步、3轮检索、5个不同追问字段、20次工具调用、12000累计Token、5次恢复、120000毫秒累计实际执行。真实数据库验证每项恰好达到边界后下一操作被拒绝，账本版本和预留不被失败操作改写；循环测试确认第四次检索工具执行前拒绝且每轮先安全检查。既有同线程恢复、跨进程checkpoint、并发恢复、重复提交、人工取消和保守未知用量测试继续通过。

修正发布顺序不足：原先AUTO报告在后续引用检查前已标PUBLISHED，现在先追加DRAFT/PENDING_REVIEW，再在检查、当前模板证明、预算和fence通过后追加AUTO发布版，原草稿不覆盖。人工发布也绑定本轮引用评估ID。故障注入证明引用阶段失败时Job失败、DiagnosisRun保留精确原因、报告仍是DRAFT，没有兜底报告；A203必要H02缺失时转专家，不编造报告。历史报告按原状态保留，不伪装成已按新流程生成。

尚未完成的不足：引用冲突后的旧草稿虽不会发布，但工作台仍可能展示旧草稿中的排查段落；需要明确WITHHELD/停止排查的展示与阻断报告契约，在T041/T046/T050补齐，现场正式试用前必须验收。T042的专家扩大资料范围linked-runs接口与父子关系/共享账本还未实现，不能宣称已有完整专家范围提升流程。SAFE-01/A310独立故事、多模态和维修案例治理也未全部交付。以上不足未删除或计为完成。

最终验证：270项完整后端通过，ruff通过，mypy90源文件通过；前端12项单测通过。Jev支持专项10项基线全部通过；故意关闭自动修复、绕过投影前处理许可检查时各2项业务断言失败，0基础设施错误，结果写入.private/test-audit/support-sensitivity.json。没有接真实Jev、生成模型或语义embedding，也没有根因/复机自动确认。API8000恢复，工作台3010保留。

最终恢复当前API后，4项真实浏览器A203回归全部通过（AUTO、FORCE_REVIEW、预热追问/恢复、非模板逐项审核），33.5秒；源码校验和完整270项结果仍为本轮最终版本。未重复创建前端服务，既有3010进程继续运行。

## T041–T050 报告阻断、范围提升和安全故事完成（2026-10-05）

累计完成50/94；上述40/94和当时不足保留为历史，不删除。T041追加WITHHELD冲突报告，清空普通原因/排查/安全前置段，保留SAFE-05停止处置和父草稿。工作台优先展示停止提示。T042新增专家linked-runs：明确申请更宽且已获授权的资料范围，父子线程分别保留，共用预算，消耗一次恢复额度；普通工程师不能读取子线程报告/checkpoint/Job。迁移0004g增加同事件、同账本、严格扩范围和追加不可覆盖约束。

T043–T046完成A203与报告事实/手册/历史分离、引用、模板版本和非参考审核验收，以及引用支持面板。T047–T050完成即时SAFE-01来源页码、独立安全前置模块和专家处置界面。专家确认只记录处置并终止到ESCALATED，不解除风险，不授权试运行；恢复提交后角色撤销会使Job失败；新增风险快照产生新的专家暂停而不是沿用旧确认。未变化的风险快照只保留一个专家待办。压力、线路、加热、伺服、清卡和开护罩前置条件都检查现有事实、资格和资产服务条款；省略asset_id不能绕过条款。

验证：后端全量287项通过（278.91秒）；ruff/mypy通过。前端15项单元测试、lint和生产构建通过。A203四项浏览器验收通过，SAFE-01单独浏览器验收通过。首次安全浏览器定位误把Next页面播报alert与业务alert混用，调整到包含实际安全文字的alert后通过；未改业务判断来满足测试。真实外部Jev/LLM仍未调用。

仍待完成：A310独立闭环及其前端验收、媒体识别/复核、专家修订、维修审核和全场景集成。已开始T051–T054，尚未以局部测试替代全部验收。原文第134行记录的WITHHELD展示和linked-runs缺口现已补齐；未完成事项仍明确保留。

## T051–T054 A310 同线程追问完成（2026-10-05）

累计54/94。A310先检索原题报警依据，再追问上游压力、设备端压力和持续漏气声；逐轮问题绑定原证据快照与报警引用，追加保存，已答字段从当前待答集合移除。/information与/resume复用同一恢复服务；支持部分回答、严格布尔/数值类型和负数拒绝，保留原证据，预算不重置，补充危险观察后安全先阻断。人等待释放Job执行资源。

新增A310独立报告保留手册排查顺序和引用，H03历史接头松动与WO-240-051历史滤芯堵塞明确区分；不把历史根因变成本次事实。明确模拟审核的窄参考模板仅在0.64/0.41MPa、确认持续漏气声、机械资格、当前资料/代码版本和安全授权通过时AUTO；其他读数或FORCE_REVIEW保留人工复核。模板现在按报警码绑定，旧缺报警绑定的注册项不能作为当前证明，防止旧项绕过新版本退役。

验证：后端全量294项通过（314.84秒），另新增8项压力模板/无设备控制路由测试全部通过；ruff/mypy96源文件通过。A310/A203/注册治理25项集成回归通过；前端18项单测、lint和生产构建通过。浏览器五项A203/SAFE流程通过，A310单独流程通过，证明部分提交、同URL/thread恢复和无额外报告暂停。最初A310浏览器使用不符合实际段落前缀的exact文本定位导致失败，改为明确匹配“未确认项”后通过；未修改根因未确认内容。LangGraph重放曾生成空问题记录，现绑定原问题快照避免重复副作用，断言只保留三问题与二问题两轮。

T055–T063多模态开始实现，当前尚未完成或勾选；真实模型/Jev未调用。历史不足继续保留。

## 2026-10-05 多模态阶段闭合：63/94
T055–T063 已验证并勾选。统一 Evidence、私有 MinIO 上传与 Job、严格文件解码/上限、checksum 绑定自绘 OCR fixture、实际像素 QR、本地有界视频帧、原子显式批量复核、快照门与恢复安全重检、工作台上传/复核已完成。任意图片没有真实 OCR/VLM 时明确 UNAVAILABLE，视频没有真实视觉模型时只提供实际帧与限制；不是模型质量验收。
原始 MEDIA 与每一代 EVIDENCE 权限都实时约束派生报告、Job、checkpoint 与 Jev 输入。撤销原候选权限后确认版本不能继续访问；复制策略交集限制 provider/purpose/有效期，不能因修正拓宽外发。
后端全量 324 passed（364.67 秒），ruff/mypy 通过；前端既有本轮 20 单元、lint/build、7 浏览器流程通过。补充的 10 个 Jev HTTP 单元测试不包含在上述324里，单独与8个通用传输测试一起18 passed。没有外部模型请求。
T064–T066 实际协议适配器正在接入；T067 真实 Jev 和模型验收需要实际精确模型、许可、密钥及环境，目前 BLOCKED/NOT_RUN。原阶段不足记录保留，不回写历史。

## 2026-10-05 provider、向量与事件阶段：68/94
T064、T065、T066、T068 已完成。OpenAI-compatible 结构化生成适配器只接受未发布草稿、保留安全/事实/引用/发布字段并再次本地校验；真实 embedding 使用不可变的 source_embeddings 表，绑定 checksum、实际模型、维度和索引版本，与 fixture hash16 隔离；System One 适配器严格按官方 `state/model/questions` 和 typed `answers/usage` 解析，仅输出检索/引用评估提示，不能发布报告或确认根因。所有真实 HTTP 请求前后重查外发策略，禁止重定向和隐式代理，真实模型必须显式版本；未配置私有 Jev profile/key 时返回 BLOCKED，不调用远程服务。
节点、暂停、恢复和报告事件使用 PostgreSQL append-only 序号、effect_key 幂等和每条事件重新授权的 SSE；不输出原始模型输入、拒绝来源或隐藏推理。新增 HTTP 适配器、Jev wire、向量隔离和事件单元测试通过。当前完成 68/94；T067 现场真实模型评估仍 NOT_RUN/BLOCKED。

## 2026-10-05 expert/feedback基础闭环：75/94
T073–T076 已完成：专家审核记录与角色边界、不可覆盖的 EXPERT 报告版本、维修结果的版本化提交和 READY_FOR_REVIEW 服务器校验。未完成或不提前标记 T077：案例审核发布仍需补齐显式发布 Job、知识 release、scope/脱敏审核。T069–T072 仍待专门验收文件，不能用现有分散测试代替。
本阶段实现保持个人项目规模：沿用模块化单体、同一 PostgreSQL、现有轻量角色，不新增权限平台或服务拆分。维修反馈缺失、失败复机、未授权执行者和未确认维修证据都会停留在 UNVERIFIED/阻断状态。

## 2026-10-05 工作台状态展示
T081 已完成：把节点时间线和 LangGraph/Job/Checkpoint 状态拆成前端组件，显示人工等待释放 worker、恢复创建新 Job 和同线程关系。前端 20 tests、lint、build 通过。T080 专家/维修/案例页面仍待完成，不用占位页面冒充完成。
当前 checked 任务数：72/94（T001–T066、T068、T073–T076、T081）；T067 真实 provider、T069–T080 其余闭环仍按任务状态保留。

## 2026-10-05 恢复和失败处理
T069 已完成：新增 PostgreSQL checkpoint 重启恢复、缺失 checkpoint fail-closed、provider transport failure、Job cancellation fencing 验收；2 个图恢复测试和 2 个 provider/worker 测试通过。当前完成 73/94。
回顾需求：没有把恢复机制扩展成新的服务；人工等待仍是暂停的 Diagnosis Job，恢复才创建新 Job；累计预算和原始版本不重置。真实 provider 失败不会伪装成 fixture 成功。

## 2026-10-05 最终验证
后端全量 350 passed / 445.75s；前端 20 tests passed，lint/build 通过。适配器重定向异常修复后重新全量确认。最新任务勾选 73/94；真实 provider、T070–T080 余项及后续提交验收仍未勾选。
## 2026-10-05 — 权限/报警参考与案例发布执行器

- 完成并验证 T071：保修记录按确认时间和版本计算有效状态，资格授予按 APX-240 范围、有效期、依据和 active 状态过滤；未知保修信息不阻断安全停机。
- 完成并验证 T072：新增 `knowledge/seed/acceptance-scenarios.json` 和七报警参考验收，覆盖完整/缺失/复核场景、A205 单独安全阻断、手册第 4 页来源绑定和安全前置引用。
- 新增资源边界验收 `backend/tests/acceptance/test_access_egress.py`；跨角色不能读取事件、诊断或 checkpoint，Jev 不具备批准依据时不产生输入哈希。
- 修复案例发布的实际执行链：增加 `CASE_PUBLICATION` in-process worker executor；发布后的 APPROVED_CASE 写入显式 SOURCE policy/grant，仍使用 `DENY` egress；发布重复提交无副作用。
- 新增 `backend/tests/acceptance/test_expert_feedback.py`，验证维修结果 → CaseDraft → CASE_REVIEWER 审核 → 发布 Job → VerifiedCase 的最小闭环和重复发布保护。T077/T078 仍保留未完成，待补齐发布失败重试、专家修订、角色拒绝和前端 E2E。
- 本轮定向结果：报警/保修 11 passed；资源边界 2 passed；案例闭环 1 passed；Ruff 全量通过。
- 当前任务勾选数：75/94。T070、T077/T078 及后续 E2E、契约、运维和现场验收仍未勾选。

2026-10-05 回归更正：T071/T072 尚未覆盖全部任务条件，恢复未完成，当前仍为 73/94。新增案例引用 checksum 使用 JSON hash 导致 CITATION_SOURCE_CHANGED；已改为原文 SHA-256，并将案例读者限制为原事件可读范围，撤销测试案例的旧广泛授权。完整发布审核、幂等重试和权限测试仍待完成；上述最小闭环测试不能证明全部任务完成。
## 2026-10-05 — 回归修复与七报警验收补齐

- 首次全量回归暴露 `CITATION_SOURCE_CHANGED`：案例发布内容的 checksum 曾使用 `content_hash(JSON 字符串)`，与引用校验要求的原文 SHA-256 不一致。已修正为原文 SHA-256，并为案例来源补充页码/章节 locator。
- 案例发布的 SOURCE 权限现在继承原事件的 readable_by 范围，不向所有现场账号广泛授权；Jev egress 仍为 DENY。
- `CASE_PUBLICATION` 已注册 in-process worker，发布 Job 可完成并留下 VerifiedCase；跨角色发布和重复发布仍返回明确拒绝且不产生第二条版本。
- 新增七报警种子验收场景共 21 条，定向测试与保修/资格测试合计 11 passed，Ruff 全量通过。
- 重新验证 A203 与案例闭环：6 passed。当前任务勾选数恢复为 75/94；T077/T078 仍未勾选，因为完整的发布失败重试、专家修订/角色拒绝和前端 E2E 尚未全部覆盖。
## 2026-10-05 — 全量回归结果

- 在撤销历史测试私有来源授权、修复案例引用版本隔离后，后端全量 `uv run pytest -q` 通过：**357 passed in 493.64s**。
- `uv run ruff check app tests` 通过；前端 `npm.cmd test` 为 **20 passed**，lint/build 均通过。
- 真实 LLM/VLM/Embedding/Jev 仍未运行，原因是当前没有真实密钥和批准的外发资料范围；没有将 fixture 结果写成真实模型验收。
- 当前 `tasks.md` 勾选 **75/94**。T070、T077–T080、T082–T094 仍是后续工作，不能把本轮回归解释为全部功能已完成。
## 2026-10-05 — 案例发布状态与范围确认

- 审核接口保存 `approved_scope`，默认沿用请求范围；发布来源的 metadata 绑定报警码、案例 release 和审阅者。
- `VerifiedCase` 在发布事务中先记录 `APPROVED_UNPUBLISHED`，由 `CASE_PUBLICATION` Job 成功后写入 `PUBLISHED` 和 `published_at`；缺失记录或 worker 失败不会产生已发布假象。
- 本轮定向验证：A203 与专家/维修/案例闭环 **6 passed**，Ruff 全量通过。
- 任务进度仍为 **75/94**；T077 还缺 `publish_on_approval` 的明确契约和失败重试验收，T078/T079 还缺完整角色拒绝、自审禁止、专家修订及案例范围测试，因此暂不勾选。
## 2026-10-05 — 契约验证补充

- 新增 `backend/tests/contract/test_report_schema.py`：验证 A203 结构化报告符合 report v4，可能原因、安全前置条件和排查步骤的 `citation_ids` 都指向报告引用；Job/Graph 非法状态会被 JSON Schema 拒绝。
- 定向结果：2 passed；Ruff 通过。
- T082 仍未勾选，因为完整 HTTP、事件、权限、Jev payload 和内部图状态契约还没有一次性覆盖完成。
## 2026-10-05 — 现场反馈页面细化

- 维修反馈页现在提交确认依据、执行人、维修证据、资格依据和复机证据 ID，避免页面看起来可以提交但后端永远只能收到空执行人。
- 案例审核页增加批准共享范围 JSON 和显式发布 Job 操作；专家仍没有发布按钮权限。
- 前端回归：20 tests passed，lint/build passed。
- T080 仍未勾选，待 Playwright E2E 实际验证页面与权限、引用和发布状态联动。

## 2026-10-05 — 当前轮实现审查

- 案例发布范围收紧为显式 `reader_user_ids`，创建草稿时绑定同组织的 `CASE_REVIEWER`，并要求范围属于原事件可读范围；审核人不能是提交人或维修执行人。
- 维修资格引用现在校验真实 `QualificationGrant` 的 ID、APX-240 范围、有效期、active 和非空依据；维修/复机证据重新执行当前访问授权。
- 待发布案例的 SOURCE 状态为 `PENDING_PUBLICATION`，只有 `CASE_PUBLICATION` Job 在重新检查审核人、脱敏状态、范围和 fence 后才激活为 `ACTIVE`；失败不会进入生产检索。
- 专家修订重新检查事件权限，并生成真实新 `report_version_id` 与新内容 hash；前端动态路由已按 Next.js 16 的 Promise params 约定修正，CSRF 令牌保存在会话存储供独立页面请求使用。
- 新增纯契约测试 3 项；前端 lint/build 通过。浏览器和数据库集成测试当前被 Docker Desktop 引擎错误阻断（PostgreSQL 端口不可用），没有把阻断当成通过。
- 当前仍不能诚实标记全部 94 项：T067/T092 真实模型与 Jev、T070/T077–T079 权限/案例完整验收、T082–T094 的数据库/浏览器/现场验证仍需实际环境或现场输入。此前的历史记录保留，不覆盖为成功。

## 2026-10-05 — Docker 恢复后的回归

- Docker Desktop 引擎恢复后，PostgreSQL/pgvector 和 MinIO 健康；重新初始化演示账号、APX-240 资产和 fixture 知识 release。
- 案例权限/发布定向验收通过：`test_expert_feedback.py` 2 项、`test_case_scope.py` 1 项、访问与契约组合测试通过；发现并修正了 append-only `SourceRecord` 不允许由 worker 更新 metadata 的问题，改为通过 `VerifiedCase.status=PUBLISHED` 控制检索可见性。
- SAFE-01 全套 9 项通过；A203、A310、多模态和访问边界组合回归通过。
- 前端 Playwright 9 项全部通过。多模态修正/拒绝候选进入人工报告复核，测试明确验证其不会自动发布；案例页面显示专家不能替代案例审核人。
- 后端全量回归首轮实际结果为 368 passed / 6 failed；失败集中在媒体队列污染、链接运行夹具权限和新增已发布案例语义，已将后两类修复并用 26 项相关回归重新验证通过。没有把首轮 368/6 解释成全量通过。
- 浏览器端到端首次恢复后 9/9 通过；对应 T083–T086 已按实际独立场景勾选。全量后端回归首轮暴露 6 个集成失败：其中 3 个由新案例发布状态断言、3 个由测试夹具权限/媒体队列污染引起，正在隔离修复，不能写成全量通过。
- T071/T072/T090 的先前完成标记已撤回，原因是原测试没有覆盖任务要求的全部条件；当前任务计数以 `tasks.md` 为准。
- Jev 配置门、现场评估门和备份恢复门均真实返回 `BLOCKED`（分别缺 profile/key、缺实际模型/硬件测量、缺私有 dump），没有伪造 READY。
- `scripts/verify_quickstart.ps1` 在 Docker 恢复后重新通过：PostgreSQL/pgvector、MinIO、migration head 和 fixture A203/SAFE-01/A310/媒体/案例治理共 26 项通过。
- 最新案例权限、外发边界和契约回归 16 项通过；本轮没有增加外部模型调用，也没有要求密钥。
- 新增迁移 `0008_feedback_integrity`，对 `RepairOutcome` 加数据库级 append-only 约束；`CaseDraft` 和 `VerifiedCase` 保留必要的审核/发布状态变更。对应覆盖测试已通过。

## 2026-10-05 — 案例发布失败重试补齐

案例发布 Job 新增 `POST /api/jobs/{id}/retry`：只允许被分配的 CASE_REVIEWER 在 FAILED/TIMED_OUT 状态下操作，使用状态版本和 Idempotency-Key，重新校验草稿审批 hash、脱敏状态、角色版本和 CASE_DRAFT 写权限；复用原 Job、release 和 VerifiedCase，不创建第二个案例或扩大共享范围。越权、过期状态、审批内容变化和重复请求均无副作用。

验证：案例闭环含成功发布与模拟失败重试、工程师越权和重复提交，`test_expert_feedback.py` 3 passed；Job 状态契约 4 passed；Ruff 通过。当前 `tasks.md` 勾选数 79/94。真实 Jev/外部模型、现场实测和私有备份介质仍保持 BLOCKED，未用 fixture 替代这些门槛。

## 2026-10-05 — 验收目录回归结果

案例发布重试改动后的 `tests/acceptance` 回归实际结果为 108 passed / 3 failed。失败集中在 `test_linked_runs.py`，单独运行该文件为 3 passed；完整目录运行时，跨测试持久化的来源授权撤销导致专家无法读取父运行的完整原始 scope，返回 404，属于现有测试隔离/fixture 问题，不能把整目录写成通过。案例重试、A203、媒体、安全、权限和报警定向测试仍通过。该问题暂不通过放宽生产访问校验来修复，避免专家读取未授权来源。

最新定向核心回归：A203、A310、SAFE-01、证据复核、案例发布重试、访问边界、保修资格和七报警参考共 29 passed（101.28s）；Ruff 全量通过。后端已在 8000 重启，工作台3010、PostgreSQL55432和MinIO59000保持监听。完整验收目录的 linked-run 隔离失败仍未伪装成完成，任务计数仍为79/94。

## 2026-10-05 — 前端和 Jev 配置回归

前端 Playwright 9/9、Vitest 20/20、lint 和 production build 通过。新增 `.env.example` 中的空 Jev 配置项，真实密钥仍只保存在本地 `.env`，当前 PROVIDER_MODE 仍为 FIXTURE，因此没有真实请求和费用。当前本地 API、工作台、PostgreSQL、MinIO 均在运行。

## 2026-10-05 — linked-run 隔离修复后完整验收

修正 `backend/tests/acceptance/test_linked_runs.py` 的测试夹具：为专家补齐父运行已有 source scope 的明确 READ grant/policy，避免完整目录中其他测试撤销历史来源后把授权污染误报为 linked-run 业务失败；生产访问校验未放宽。完整后端验收目录重新运行结果为 **111 passed / 396.99s**，Ruff 通过。当前任务文件仍保持 79/94，未将真实 Jev、现场性能、备份恢复或尚未完成的前端权限深测标为完成。

完整后端验收后，append-only integrity 定向测试 3 passed；Quickstart 脚本重新验证 27 passed，Docker PostgreSQL/pgvector、MinIO 和 migration head 均正常。真实 provider 仍由独立权限门控制，没有因为本地 key 配置而自动切换或发起请求。

## 2026-10-05 — 专家/维修/案例页面继续补齐

专家页面新增依据证据 ID 输入并提交到专家修订接口；案例审核页新增发布 Job ID、状态版本和失败重试操作；维修页继续明确复机证据缺失时只能保持 UNVERIFIED。前端 Vitest 20 passed、lint/build 通过，Playwright 增至 10 passed；后端 HTTP/报告/Job 契约定向测试 10 passed，Ruff 通过。页面验收仍不替代真实后端权限联动，因此 T080/T087 已在后续页面和 Playwright 工作流验证中完成。

## 2026-10-05 — 案例审核真实状态联动

新增 `GET /api/case-drafts/{draft_id}`，只向被授权的 CASE_REVIEWER 返回草稿状态、维修摘要、脱敏状态和 CASE_PUBLICATION Job 状态；未授权工程师保持404。案例页面改为先读取真实草稿，再按状态显示批准、拒绝、发布和失败重试动作，避免未授权页面展示审核控件。案例定向后端 7 passed；前端 Playwright 10 passed、Vitest 20 passed、lint/build 通过。真实 Jev、现场和备份门仍未触发。

## 2026-10-05 — 审核工作台真实状态读取

案例审核页不再使用静态占位字段：后端新增 `GET /api/case-drafts/{id}`，按 CASE_DRAFT 授权返回草稿和最新发布 Job；前端先读取状态，未授权时隐藏批准/发布控件，已授权时按 DRAFT/APPROVED/FAILED 等状态显示动作。补充 HTTP 契约。`uv run python -m compileall -q app`、Ruff、后端案例/契约定向测试通过；前端 Playwright 10 passed、Vitest 20 passed、build 通过。当前任务清单仍 79/94，未把实测依赖任务提前完成。

## 2026-10-05 — 权限边界与验收材料

访问边界新增媒体内容、媒体 Job、证据列表的跨角色拒绝测试，`test_access_egress.py` 5 passed，Ruff 通过。新增私有 `docs/submission.md` 和 `docs/field-demo-checklist.md`，包含 A203/A310/SAFE-01、多模态复核、专家和维修案例演示步骤，并明确 Jev、现场性能、真实视频质量和备份恢复在无授权/实测资料时保持 BLOCKED。

## 2026-10-05 — 继续补充边界与完整性验证

跨角色媒体边界再增加视频帧访问拒绝；访问、七报警、保修/资格和 append-only integrity 组合定向回归 **19 passed**，Ruff 通过。现有 21 条报警场景种子继续用于规则覆盖，但尚未把仅规则层场景夸大为完整七报警端到端诊断验收。

## 2026-10-05 — 案例审核发布闭环完成

T077 已按真实实现勾选：CaseDraft 创建、指定 CASE_REVIEWER 审核、脱敏和显式范围审批、`publish_on_approval`、VerifiedCase/KnowledgeRelease、CASE_PUBLICATION Job、失败重试和重复发布保护均已通过案例验收。`test_expert_feedback.py` 3 passed。T078/T079 仍保留，待专家修订和更完整案例范围验收覆盖。

## 2026-10-05 — 专家修订与案例范围验收完成

T078/T079 已勾选。新增真实 acceptance 覆盖：专家打开待办并追加新报告版本、原 AI 报告 hash 保持不变；专家不能审核案例；审核范围不能扩大；`publish_on_approval` 与失败重试不重复创建案例/release；维修证据、执行资格、复机证据和共享范围均由服务端复核。案例测试 4 passed，Ruff 通过。T080 页面已实现但仍需授权草稿的真实浏览器联调，暂不勾选。

## 2026-10-05 — 专家/案例前端授权状态测试

专家反馈 E2E 增加授权草稿场景：审核人读取维修摘要、选择明确读者范围、确认脱敏并提交仅审核动作；未授权草稿仍隐藏审核控件。该文件 3 passed；Vitest 20 passed，lint/build 通过。后端案例闭环测试 4 passed，T077–T079 已完成；T080/T087 已在后续授权状态和工作流测试中勾选。

## 2026-10-05 — 运行时契约闭环

发现并修正 `citation-assessment.schema.json` 与实际 `/citation-assessments` 返回值不一致：接口返回的是带 `diagnosis_run_id` 和 `assessments[]` 的集合，集合项包含 RULE/HUMAN/NOT_CALLED、claim hash、证据快照 hash、范围和历史引用。同步更新 schema，并增加运行时 graph/checkpoint、retrieval、citation、Job 四类响应校验。契约测试 3 passed，Ruff 通过。T082 已由后续 contract 套件和运行时响应校验勾选；真实 Jev 评估仍单独属于 T067。

## 2026-10-05 — 本地验收面收敛

完成并标记 T072、T080、T082、T087：七报警/安全引用规则、专家/维修/案例审核页面、HTTP/JSON Schema 运行时契约、以及专家反馈浏览器工作流均有可执行验证。资格/保修与规则套件定向回归 14 passed；后端 contract 套件 11 passed；前端 Playwright 全量 11 passed。当前任务清单为 86/94。T067（真实 Jev）、T070（完整权限/导出等深测）、T071（暂停期间资格撤销专测）、T090（完整保留/撤销完整性）、T091（私有备份恢复）、T092（现场/真实模型性能）、T093/T094（依赖上述实测材料）仍保持未完成，避免把 fixture 或模拟页面写成真实现场结果。

Quickstart clean-start script rerun after the task updates: **28 passed in 102.14s**. PostgreSQL/pgvector and MinIO healthy, Alembic `0008_feedback_integrity` head confirmed. Fixture path remains fully runnable; real-provider path remains opt-in and was not called.


## 2026-10-05 — 资格撤销与隔离数据库恢复演练

补充 T071：报告暂停期间撤销 FIELD_ENGINEER 的有效 ELECTRICAL 资格后，恢复请求返回 `QUALIFICATION_REQUIRED`，不写入 ResumeRequest、不创建新 Job；同一会话提交烟雾/焦味报障仍立即触发 SAFE-01。资格/保修测试 8 passed，访问边界 5 passed，完整性测试 4 passed，Ruff 通过。

新增 `scripts/verify_local_database_restore.ps1`：在新的隔离 PostgreSQL 数据库执行 pg_dump/pg_restore，校验 migration head、报告、checkpoint、Job、append-only trigger 和孤儿报告；本次结果 `DATABASE_RESTORE_PASSED`，源数据库未修改。媒体对象恢复、运行时重启和保留策略仍未宣称完成。

## 2026-10-05 — MinIO 隔离恢复演练

新增 `scripts/verify_minio_restore.py`，使用临时 bucket 和自描述 fixture 对象验证 MinIO 上传、导出到私有备份目录、删除、恢复和 SHA-256 校验；本次 `MINIO_ISOLATED_RESTORE_PASSED`，生产 `apx240-media` bucket 未触碰。T091 仍未整体勾选，因为完整灾备还需要媒体 tombstone、队列/checkpoint、保留策略和故障恢复验证。

## 2026-10-05 — SSE 会话撤销和隔离媒体权限回归

访问边界新增 SSE 建立前的会话撤销验证，以及 Job、retrieval-assessment、citation-assessment、linked-run 和 incident stream 的跨角色拒绝检查；`test_access_egress.py` 6 passed。MinIO 隔离恢复脚本已通过，生产 bucket 未触碰。完整权限深测 T070 仍保留，因为导出、缓存和所有批量接口还需要一次完整清单式验收。

## 2026-10-05 — 权限深测继续收敛

补充 SSE 会话撤销前置检查，以及跨角色对 Job、检索评估、引用评估、linked-run、incident stream 的拒绝测试；完整性测试覆盖维修结果的 UPDATE/DELETE 数据库触发器。相关组合回归 **18 passed**，Ruff 通过。T070/T090 仍不提前勾选，分别还缺完整批量资源清单和留存/撤销审计场景。

## 2026-10-05 — 撤销审计追加性

新增会话撤销审计回归：注销会话生成 `SESSION_REVOKED` 审计记录，数据库禁止删除该记录；访问边界套件 **7 passed**。该结果补强了 T090 的撤销审计覆盖，但完整 retention/tombstone 仍需单独演练，任务不提前勾选。

## 2026-10-05 — 备份脚本容器降级路径

修正 `verify_backup_restore.ps1` 的 Windows/容器兼容性：主机没有 `pg_restore` 时，将 dump 临时复制到 PostgreSQL 容器并执行只读 `pg_restore --list`，本次输出 `READY_FOR_PRIVATE_RESTORE_DRILL`。脚本仍不覆盖数据库；完整隔离恢复继续由 `verify_local_database_restore.ps1` 执行。

## 2026-10-05 — 私有自测与 provider 记录模板

新增 `docs/self-test-results.md`、`docs/provider-selection.md`、`docs/jev-evaluation.md` 和 `docs/field-evaluation.md`，记录已实际通过的 fixture/本地基础设施结果，并把真实 Jev、现场性能和隐私授权要求明确标为 BLOCKED。未把依赖外部条件的 T067/T092/T093/T094 虚构为完成。

## 2026-10-05 — 公共诊断投影隐私边界

权限套件新增公共诊断投影检查：输入中的自编造原始身份标记不会出现在诊断 JSON、节点审计或报告投影中，报告仍包含可解析 citation_ids；同时保留跨角色、SSE 撤销、Job/评估/linked-run 拒绝和审计追加性验证。`test_access_egress.py` **8 passed**。T070 仍需清点不存在的 export/current-node 接口并完成所有批量 endpoint 的 ACL/CAS 证明后再勾选。

## 2026-10-05 — 前端角色边界与权限深测收口

专家修订页和维修回填页新增 `/api/me` 角色校验：无 EXPERT、FIELD_ENGINEER 权限时隐藏写入控件；授权页面继续展示追加证据字段。新增未授权前端 E2E，相关 Playwright 5 passed，前端 lint/build 通过。结合后端 8 项权限/egress/SSE/linked-run/公共投影测试，T070 已勾选。项目当前任务进度 **88/94**。导出、current-node 等接口在当前契约中不存在，已作为不适用边界保留，未虚构端点。

前端全量 Playwright 在角色校验改动后重新运行：**12 passed**。专家、维修页面的未授权控件隐藏和授权字段展示均通过。

## 2026-10-05 — 留存 tombstone 与联合恢复收口

新增媒体 tombstone 轻量流程：仅 EXPERT 可提交、按 checksum CAS 校验、追加不可删除的 `MEDIA_TOMBSTONED` 审计记录，原始 MediaAsset/checksum/storage_ref 保留，后续媒体读取返回 410；不物理删除对象，也不声称撤回已下载文件。新增 `backend/tests/integration/test_retention.py`，验证重复提交、越权、checksum 冲突、原对象保留和审计追加性。

身份检查闪现已修复：专家/维修页面只有 `/api/me` 返回允许角色后才渲染写入表单。Ruff、A203/A310/retention 回归 **13 passed**，前端相关 E2E **5 passed**。T090、T091 已勾选；T067/T092/T093/T094 仍依赖真实 Jev、现场评估或最终人工演示。

Quickstart 在 tombstone 和权限闪现修正后重新运行：**28 passed in 105.01s**；PostgreSQL/pgvector、MinIO 健康，Alembic head `0008_feedback_integrity`。真实 providers 仍保持 permission-gated。

## 2026-10-06 — 诊断页补充媒体入口修正

修复前端状态条件：已存在诊断运行时，原“创建事件并补充图片/视频”按钮错误复用 `canStart`，导致按钮变灰、无法给当前事件补充媒体。现在已有 `incident_id` 时按钮显示“为当前事件补充图片 / 视频”，允许上传到同一事件；上传后仍必须完成候选证据复核，再创建新的诊断运行，不覆盖原运行。前端 lint/build 通过，A203/证据/专家相关 Playwright **7 passed**。

## 2026-10-06 — 本地 OCR 与 QR 能力收口

- 新增 `LocalOCR`（RapidOCR ONNX Runtime）像素识别适配器，支持从 APX-240 面板图片识别报警码、设定温度、实际温度、加热电流和原始 OCR 文本；输出仍保持 `CANDIDATE`，必须人工接受/修正/拒绝后才进入诊断。
- `OCR_PROVIDER=rapidocr` 已写入本地环境；默认诊断、RAG、视觉模型仍保持 fixture 模式，未调用外部模型或 Jev。
- QR 不是 fixture 猜测：现有流程使用 OpenCV `QRCodeDetector` 真实解码，并限制为 `apx240://asset/<id>`；随后校验资产是否为 APX-240，覆盖有效、未知、非 APX-240 和无历史记录场景。
- 介质候选和证据复核验收：`7 passed`。视觉大模型仍未配置，因此视觉候选会明确显示“无法判断”，不会伪造视觉结论。
