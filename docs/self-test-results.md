# APX-240 私有自测结果

本文件记录本地 fixture 模式和隔离基础设施结果，不代表真实 Jev、现场设备或真实视觉模型质量。

## 已通过

| 检查 | 结果 | 证据 |
|---|---|---|
| Quickstart | 28 passed | `scripts/verify_quickstart.ps1` |
| 后端完整验收 | 111 passed | `backend/tests/acceptance` |
| 前端 Playwright | 11 passed | `frontend/tests/e2e` |
| HTTP/JSON Schema | 11 passed | `backend/tests/contract` |
| 资格/保修/权限/完整性组合 | 18 passed | 定向回归 |
| PostgreSQL 隔离恢复 | DATABASE_RESTORE_PASSED | `scripts/verify_local_database_restore.ps1` |
| MinIO 隔离恢复 | MINIO_ISOLATED_RESTORE_PASSED | `scripts/verify_minio_restore.py` |

## 必演路径

- A203：通过，包含 SAFE gate 顺序、A203/H02/WO-240-042 引用和可能原因未确认语义。
- A310：通过，追问上游压力、设备侧压力和持续漏气声，恢复后保持同一 thread 并累计预算。
- SAFE-01：通过，立即停机、升级专家，不生成普通排查步骤。
- 多模态证据：通过 fixture 候选、接受、修正、拒绝和失败降级路径。
- 专家/维修/案例：通过角色边界、追加报告版本、UNVERIFIED 阻断和审核发布路径。

## 尚未宣称通过

- 真实 Jev 请求、外部模型质量、真实图片/视频质量；
- 现场硬件网络、P50/P95 延迟和媒体处理目标；
- 完整 retention/tombstone、队列和 checkpoint 灾备演练；
- 任何原始题目资料或现场隐私数据的外发合规结论。

