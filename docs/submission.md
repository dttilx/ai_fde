# APX-240 私有验收提交材料

本文件仅用于本地验收，不用于公开发布题目资料、设备说明书或现场媒体。

## 启动

1. 启动 Docker Desktop、PostgreSQL/pgvector 和 MinIO。
2. 在项目根目录运行 `scripts/setup_local.ps1`（首次）和 `scripts/verify_quickstart.ps1`。
3. 启动后端 `backend`: `uv run uvicorn app.main:app --host 127.0.0.1 --port 8000`。
4. 启动前端 `frontend`: `npm.cmd run dev -- --port 3010`。
5. 使用 `.private/demo-credentials.json` 中的本地演示账号。

## 演示顺序

- A203：观察安全门、报警/手册/历史工单引用、可能原因和“根因未确认”。
- SAFE-01：输入烟雾或焦味，确认立即停机、专家升级和没有普通排查步骤。
- A310：输入“似乎漏气”，按要求补充压力和持续漏气声，确认同一诊断线程恢复。
- 图片/OCR/QR/视频：上传后先查看候选证据，显式确认/修正/拒绝后再诊断。
- 维修闭环：填写维修证据和复机验证，创建草稿，使用 CASE_REVIEWER 审核后再发布。

## 真实条件门

Jev、外部模型、现场性能和备份恢复必须记录真实模型/版本、授权范围、输入脱敏结果、响应和耗时；没有批准资料或实测结果时状态保持 `BLOCKED`，不能用 fixture 结果替代。

## 自测结果

详细结果见 `docs/self-test-results.md`。当前仅报告 fixture、本地规则、隔离 PostgreSQL 和隔离 MinIO 的真实执行结果；Jev、现场性能和完整 retention 仍为 BLOCKED。
