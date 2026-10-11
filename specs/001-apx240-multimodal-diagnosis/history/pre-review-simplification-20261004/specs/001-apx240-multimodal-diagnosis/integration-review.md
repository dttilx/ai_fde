# APX-240 设计合并与缺陷审查报告

修订 2.0.0 · 2026-10-04。本次为设计文档合并，不执行实现任务，不修改考试源文件和 Constitution 1.0.0。

本报告记录发现的问题、相互冲突的旧决定、采用的解决方案和仍未验证的条件。不是删掉旧方案以后宣布“全部通过”：旧方案、原任务和被替代契约均可查阅，设计检查不等于业务测试。

## 1. 合并结果与历史保留

当前依据是 spec.md、plan.md、research.md、data-model.md、contracts/、quickstart.md、tasks.md 和根目录 APX-240-Agent-架构设计方案.md。design-amendment-jev-access.md 保留为已合并的提案历史，不能与当前正式契约并列使用。

合并前14个文件原样保存到 [合并前快照](history/pre-jev-access-20261004/manifest.json)，包含 Constitution、根架构、原规格/计划/任务/契约等；manifest 记录 SHA256。原70个任务各保留一次映射，见 [任务修订映射](task-revision-map.json)。新增24项，当前94项全部未执行；编号因依赖顺序调整，不可再按旧编号实施。

核心架构保持个人可维护的 Next.js + FastAPI 模块化单体、PostgreSQL/pgvector、MinIO、数据库持久化 Job、本地 worker、LangGraph PostgreSQL checkpoint。只增加 access 与知识评估能力，不增加微服务、GraphRAG、权限平台或设备控制。

Jev 集成位于 scope过滤→结构化/关键词/向量混合检索→评估及分路→生成上下文之间；引用支持评估是另一个明确阶段。所有候选都有评估阶段记录，实际调用受许可、可用性和累计预算约束。跳过不代表评估成功，必要安全/报警资料不由 Jev 删除。

## 2. 审查范围和严重性

来源：题库第六题及通用提交要求、APX-240手册7页、项目 Constitution、合并前14文件、已接受的 Jev/权限提案、当前7个Schema与94任务。对照手册报警顺序、来源事实和真实交付要求，不用模型常识补造设备条款。

CRITICAL 为违背不可违反原则的契约/验收漏洞；HIGH 为可造成越权、错误安全处置或无法实现的冲突；MEDIUM 为覆盖、可用性、运维和语义不足；LOW 为治理与表达问题。“已修订”仅表示文档决定闭合，相关实现/验收仍待任务执行。以下所有旧内容均保留在快照，并非从历史删除。

## 3. 发现及采用决定

| ID/级别 | 原设计不足或冲突与定位 | 合并后的决定和落点 |
|---|---|---|
| C01 CRITICAL | 原 spec SC-005只要求90%场景每个原因/步骤有引用，与 Constitution 证据优先和逐项溯源不一致 | SC-005改为可发布报告100%逐项有效引用；schema与服务验证并行，错/缺引用不能发布 |
| C02 CRITICAL | 原报告 known_facts 的状态允许未确认/矛盾混入已知事实，与事实边界冲突；报告缺独立历史比较 | v2只允许CONFIRMED/CORRECTED当前事实；未知、矛盾、手册值和历史事实分区，FR-031和报告契约 |
| C03 CRITICAL | 原 data-model恢复转移从NEEDS_INFORMATION/WAITING_EXPERT直接到检索或生成，可能绕过重新安全检查 | 全部恢复先重新安全检查；专家/人工确认不能覆盖禁止动作，plan§6及恢复任务 |
| C04 CRITICAL | 原轻量角色约定没落实可验证身份、事件与来源scope；新Jev提案若仅过滤来源仍可能通过输入事实外发保密内容 | 可信服务端会话+角色/范围；所有输入及派生lineage共同校验外发依据，缺依据DENY；source先过滤，再检索/模型，FR-025～029/037 |
| H01 HIGH | 原模型仅5种DiagnosisRun枚举，但转移列WAITING_EXPERT/CONFLICT_BLOCKED，映射又把等待视为ESCALATED | Run直接使用10图状态；等待可恢复，ESCALATED明确终止；Job RUNNING不混作诊断状态 |
| H02 HIGH | 原research 8steps/120wall-time与tasks32steps/120active-time冲突，真实图含暂停与重放 | 统一32节点/3检索/5不同追问/20调用/12000tokens/5恢复/120活动秒；人工等待不计活动时间，版本和ledger记录 |
| H03 HIGH | Jev最多8段×3轮已24次请求，超过整个诊断20工具上限，且未留生成/引用余量 | 默认4、每轮最多8、动态缩减，预留6调用，原子预留及UNKNOWN保守扣减；SKIPPED_BUDGET保留候选并明确降级 |
| H04 HIGH | 两类资料容易被误认为两种数据库或“技术资料就是公开”；脱敏可能被误用为外发授权 | classification、内部read scope和egress三轴独立；单PG逻辑隔离；批准或脱敏不等于允许发往某provider |
| H05 HIGH | 原actor_id/role记录不说明身份来源，专家身份和电气/机械资质混用 | 本地opaque session、CSRF、server grants；角色≠设备维修资质；QualificationGrant带来源/范围/期限，SAFE-04独立执行 |
| H06 HIGH | 原data-model允许CASE_REVIEWER或EXPERT发布案例，与独立审核边界含混 | 分配的CASE_REVIEWER审核/发布；EXPERT单独不能发布；默认不自审；单人演示例外必须显式配置并审计 |
| H07 HIGH | 引入保修后可能假定保修期、失保条款或先等服务商再停机；手册无这些合同事实 | 保修可选UNKNOWN/ACTIVE/EXPIRED，确认日期代码比较；限制需有合同来源；不阻断报障与紧急停机，不承诺自动保修审批 |
| H08 HIGH | 原“全部SAFE在检索前完成”无法在检索前判断检索无覆盖与新发现冲突 | 先本地风险/禁止动作/资质门，再检索后由同一独立安全服务补SAFE-05支持/冲突门；任何建议前必须通过适用检查 |
| H09 HIGH | 原仅A203/A310/SAFE-01重点演示，不能证明手册其它报警顺序；A205无额外危险描述也须停机 | 7报警至少完整/缺失/历史差异21参考场景；A205报警直接安全阻断，A401禁止绕过、A520摩擦停止，AlarmStep约束 |
| H10 HIGH | 原schema check_sequence非空可能迫使高风险报告生成普通排查；安全/停止/升级字段溯源不充分 | 安全阻断报告普通steps为空，立即处置有来源；所有实质指令与升级理由引用，shape+运行期支持验证 |
| H11 HIGH | 原citation_ids只证明引用存在，不能证明来源支持陈述；单段失败也不能否定多来源联合支持 | 先本地ID/release/locator/quote/ACL，再按陈述+引用集合评估；语义UNKNOWN/跳过逐条人工核验，冲突不能一键接受 |
| H12 HIGH | 复核新增缺口：REPORT_REVIEW要求ClaimReview ID，却没有创建记录的接口 | 增加POST claim-reviews，绑定claim/report哈希及版本，明确ACCEPT/CORRECT/REJECT；T039服务和T046面板可完整落地 |
| H13 HIGH | 复核新增冲突：若每次恢复重新生成并再次interrupt，报告审核可能永远完成不了 | 无事实变化REPORT_REVIEW先安全复核后发布原已审核hash；变化则使审核失效，新草稿再审；INFORMATION变化才重新检索 |
| H14 HIGH | 原 /information新诊断版本和新线程语义不清，重复请求有no-op与409冲突 | 同run/thread追加证据/报告版本；写请求重复/stale/并发409无新效果，logout仍幂等204；native checkpoint与应用版本分开 |
| H15 HIGH | 原Job七状态没有明确人工等待映射，worker可能一直占用；进程重启/并发租约描述不足 | 段Job SUCCEEDED+result_kind PAUSED，释放worker，恢复新Job同线程；DB lease/fencing及超时对账，不增加Job WAITING |
| H16 HIGH | 原将LangGraph checkpoint、业务副作用和预算当作天然原子提交，重放可能重复报告/工单 | durable invocation/outbox及checkpoint引用对账；稳定effect key、CAS、原子预算；明确非框架天然exactly-once，增加崩溃窗口验收 |
| H17 HIGH | 高权限专家恢复原线程可能把私有来源带给普通工程师；换run可绕过预算 | run固定scope，只收窄；更广来源显式linked run与限制输出，共享同一ledger；当前撤权重新校验，不只信旧快照 |
| H18 HIGH | 根架构/原方案含自动ASR/视频声音承诺，但FFmpeg不会识别漏气或金属摩擦 | 首版关键帧+可见现象，声音为用户TEXT/FORM定位观察；无经过验证音频适配器不能自动产生声音结论，原ASR决定保留历史 |
| H19 HIGH | 原任务文字事实快照依赖后置媒体Evidence，P1实现顺序不成立 | 通用TEXT/FORM Evidence提前T027，媒体T055只扩展；诊断PendingHumanAction先于US5表，P1验收传递依赖无US5 |
| H20 HIGH | 二次复核发现T016/024/034/040/041/048/055/094新增前置写在文件列表，没有进入depends on | 全部移入显式依赖；T024补T004避免pyproject修改冲突；图执行补身份/scope/Jev阶段测试门禁；T053补危险分支T047 |
| H21 HIGH | 维修模型repair/restart evidence强制非空，同时允许不完整真实反馈，接口不可实现 | UNVERIFIED允许空/nullable或复机失败；READY_FOR_REVIEW由服务端验证确认根因、维修证据及成功复机证据，新版本后才可案例审批 |
| M01 MEDIUM | 原SC-00690%允许缺事实时偶尔不追问；只规定不得最终确认不足以验收 | 参考缺事实场景100%进入必要追问/专家；保留未确认，不把H03漏气工单直接判当前接头松动 |
| M02 MEDIUM | H03漏气与WO-240-051滤网堵塞可能被误称来源互相矛盾 | 区分不同过去事件与当前同事实冲突；报告对照相同/不同条件，按证据强度排序POSSIBLE原因，不能当当前根因 |
| M03 MEDIUM | 原公开graph schema、内部checkpoint状态及Manifest边界不清 | 分离PublicGraphStatus与InternalLangGraphState；公开摘要不含prompt/秘密/隐藏推理，audit/checkpoint也受scope |
| M04 MEDIUM | 原quickstart让OCR128与文字165在未复核时直接冲突阻断诊断 | 未复核结果只是候选，先确认/修正；确认后当前事实冲突才进入CONFLICT_BLOCKED；可疑危险候选不能简单排除 |
| M05 MEDIUM | 原视频/图片无数字限制、不说明扫码无权资产、处理失败与扫描能力 | 明确5图10MB/25Mpx、1视频60s100MB/8帧/30s解码；QR不授权或作根因；无scanner标NOT_PERFORMED，外部可访问部署要求扫描隔离 |
| M06 MEDIUM | 原普通全文检索未说明中文分词，无法凭PostgreSQL默认英文配置兑现中文混合检索 | 首版规范报警/术语词表+参数化关键词匹配+pgvector/RRF，保留分数/来源；不额外部署检索平台 |
| M07 MEDIUM | 原同PDF重导入是否同版本、chunk引用定位、真实embedding外发边界含混 | 同checksum+parser/index配置幂等复用，不同配置新release；页/章/表/段可定位，embedding也过外发网关 |
| M08 MEDIUM | 原索引/媒体/缓存访问控制可能只关注SQL主表，URL、SSE、摘要导出仍泄露 | 来源过滤前置，派生scope取交集；缓存重授权，SSE每次敏感交付重查，MinIO私有；60sURL不能即时撤销，严格场景用代理 |
| M09 MEDIUM | Jev置信度/总report confidence可能被理解为根因准确率或自动放行 | Report用evidence_sufficiency/limitations，Jev单项分布仅辅助；阈值版本化、需APX样例实测，必要资料不能由低分删除 |
| M10 MEDIUM | 原提案自动排除“无关”候选，领域未校准时有误删证据风险 | 首版FOLDED可展开/可审计，不永久丢弃；疑似攻击隔离而非模型取得工具授权；安全和冲突优先 |
| M11 MEDIUM | 原fixture路径完整但可能把固定输出作为市售模型实际运行证明 | 明确REAL/FIXTURE/RULE/HUMAN及实际model；独立真实市售模型和获许可模拟输入Jev验收，fixtures只证明流程 |
| M12 MEDIUM | 原现场可用性检查让SAFE场景也找“主要原因/下一普通排查”，可能与停机矛盾 | A203找原因/合法下一步；SAFE找立即停机、禁止事项、专家、来源；不适用项明确N/A，5分钟4项检查 |
| M13 MEDIUM | 原无Docker/本地存储降级可能被理解为不要PostgreSQL，违反持久checkpoint要求 | Docker可替换本地PG，但PG仍必须；文件系统只替代媒体storage，不能替代业务/checkpoint DB |
| M14 MEDIUM | 原交付主要检查quickstart，没有真实入口、输入说明、规则说明、输出和实测5项闭环 | T093收集5项私密提交材料，T094最终验收显式依赖；源文件标虚构考试、不得公开分发，部署真实结果必须记录 |
| M15 MEDIUM | 不覆盖记录可能被误理解无限保留文件，缺删除/备份/取消边界 | 配置保留策略与tombstone，删除媒体标来源不可用；私有备份恢复实测；取消只能挡后续结果，不能撤回已发provider的内容 |
| L01 LOW | 根架构还保留8steps、旧状态机/未来图谱/旧ASR等历史表述，与现行LangGraph/tasks不一致 | 根概览同步当前2.0；原全文保留，spec仍按需求而非技术依赖描述，无新增图谱任务 |
| L02 LOW | 原检查表勾选容易被解读为功能已经验收；feature被称Git branch但当前无Git库 | 保留文档质量检查，注明业务未验证；称feature identifier，94实现任务全部未勾选 |

以上42项为本次发现记录：4项CRITICAL、21项HIGH、15项MEDIUM、2项LOW。级别说明风险性质。所有解决方案已有明确设计落点，业务有效性仍需执行任务证明。

## 4. 治理和版本决定

Constitution不变。当前设计修订2.0.0与JSON契约v2是显式破坏性设计修订：事实区、状态、空安全steps、身份、复核和反馈完整性均变化。当前尚无实现客户端，无业务数据迁移声称；实现时用v2统一，不混读v1。旧契约完整保留以解释差异。

批准案例、批准扩大内部读scope、批准外部provider处理是三个不同动作。本人可以决定软件流程、默认DENY和轻量实现，不能替来源权利人给予考试资料外发许可、不能替厂家编造保修条件、不能替现场管理方授予维修资质。

每次后续变更要记录作用于FR/SC/模型/契约/任务；有新source/provider/prompt/rubric/ranking/graph配置需新版本和回归。不得把未执行任务勾选，不以删掉验收要求解决失败，不把未确认案例入库。

## 5. 仍未满足、不能假定完成的事项

| 条件/级别 | 为什么仍未解决 | 已定义行为与完成证据 |
|---|---|---|
| D01 HIGH：源资料外部处理许可 | 考试保密约束未给任何外部provider处理授权，不能由本设计批准 | 默认DENY；本地处理或许可模拟资料演示真实Jev。若要求考试原文实际经外部Jev，先取得并记录provider/purpose/期限对应处理依据，否则此项BLOCKED |
| D02 HIGH：真实模型与账号可用性 | Jev账号/可固定版本/留存地域条款、LLM/VLM/embedding具体型号以及现场硬件未知 | 开发fixture可运行但不充当完整验收；选择实际市售模型并记录模型/模式/真实输入输出，部署前验证可用与许可 |
| D03 HIGH：没有业务实现 | 本次仅设计；没有运行中的入口或实际故障测试结果 | 完成94任务及私有现场提交；安全、ACL、并发恢复、语义支持必须实测，不能用文档覆盖率声称生产就绪 |
| D04 MEDIUM：评估阈值/性能未测 | 0.90/0.80只是保守初值，3s/15s与30s/60s性能受网络/模型/媒体影响 | 真实标注样例对比普通混合RAG、Jev路由和人工结论，记录错误/延迟/成本；不承诺供应商营销速度或零幻觉 |
| D05 MEDIUM：现场维修资质与保修数据 | 手册只要求授权，未给具体人员/合同日期/服务条款 | QualificationGrant由可信管理来源初始化；保修无数据UNKNOWN；禁止默认授权或猜失保 |
| D06 MEDIUM：非本地部署与运维 | TLS、扫描器、备份恢复、模型故障和撤权的实现效果尚未验证 | 本地演示保留明确限界；对其他人可访问部署须完成HTTPS/扫描隔离与访问回归，备份私有且做恢复验证 |

不增加企业平台来掩盖这些条件。条件不妨碍完成设计和本地fixture开发；不能被自动标成真实验收通过。真实JeV测试用获许可模拟材料不等于获得考试资料外发授权。

## 6. 实际执行的设计验证

[设计验证记录](design-validation-results.json)：94任务连续编号、每项目标/文件/显式依赖/验证；原70各映射一次；FR001～040与SC001～016均有任务引用；7用户故事分别有实现和独立验收；A203/SAFE-01/A310及对应E2E传递依赖不含US5。覆盖率指文档映射56/56，非功能实现率或性能达标率。检查[P]仍以文件不冲突和前置完成为条件，不保证可无限并行。

[契约形状验证](contract-validation-results.json)：7个JSON Schema语法检查及11个正反例通过，涵盖安全报告空排查/拒绝危险普通步骤、未确认事实、缺引用、缺审核、Job暂停、外发依据和公开状态禁止秘密字段。这些仅验证结构，不证明引用内容正确、权限无绕过或LangGraph恢复实现有效。

合并前14快照SHA256一致，当前Constitution与快照一致。当前正式Markdown文件链接检查；source DOCX/PDF未改。本次没有执行任何实现任务或应用测试。

## 7. Jev官方依据与适用限度

Jev支持state+typed questions的System One接口，问句key只做映射，实际条件写instructions；Score、Choice、Noul可组合。采用其公开接口契约，模型版本按实际响应记录，不能仅记录latest别名。见[官方API](https://docs.typesafe.ai/api)。

在检索后评估片段、将证据与冲突分路，再生成回答，是官方[RAG片段评估示例](https://docs.typesafe.ai/cookbooks/classifying_rag_passages)展示的集成方式；本项目按安全需求保留必要来源和可复核折叠，不直接复制其丢弃策略。引用先定位再检查支持，参考[引用复核示例](https://docs.typesafe.ai/cookbooks/citation_check)。这支持设计形态，不证明Jev在APX-240上的效果，需要本项目真实对比。
