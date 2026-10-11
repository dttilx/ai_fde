#  现场故障诊断 Agent

个人项目，面向虚构的 APX-240 考试设备。仅用于应用演示，不可用于真实设备维修。
已接通 A203、A310 追问恢复、SAFE-01 停机升级，以及图片/视频上传和候选证据复核；功能进度以 `specs/001-apx240-multimodal-diagnosis/tasks.md` 为准。

## 本地启动

要求 Python 3.11+、uv、Node.js 24、Docker Desktop（Linux 容器）。

```powershell
.\scripts\setup_local.ps1
cd backend
uv sync --locked
uv run alembic upgrade head
uv run python ../scripts/manage_demo_access.py --create-fixtures
uv run python ../scripts/import_knowledge.py
uv run python ../scripts/manage_templates.py --simulate-fixture-approval
uv run python ../scripts/initialize_assets.py
uv run python ../scripts/initialize_checkpoints.py
uv run python ../scripts/prepare_media_fixtures.py
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

另一个终端：

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev -- --port 3010
```

前端：http://127.0.0.1:3010；API 健康检查：http://127.0.0.1:8000/health。
数据库只监听本机 55432，MinIO 服务 59000，管理界面 59001。
脚本生成随机本地凭据，存入忽略的 `.env`。应用使用受限数据库账号和私有 bucket 服务账号。
基础开发采用明确标记的 FIXTURE，不需要外部模型密钥；fixture 不证明真实模型质量。
知识初始化需要本工作区现有私有 PDF 副本、manifest 与 `knowledge/seed/` 中的解析种子；缺失时导入会失败，不会填入虚构知识。本项目尚未提供从零生成全部私有种子的脚本。
演示登录凭据保存在被忽略的 `.private/demo-credentials.json`，不要公开或粘贴到日志。
模板管理默认只创建 DRAFT；上面的显式参数模拟 fixture 模板批准并记录审计，不代表真实人工审定，不能用于 REAL 模式。模板源引用、代码或知识版本变化需要重新验证；未验证时进入报告复核而非自动发布。

工作台可先创建事件、补充图片或视频，再逐项接受、修正或拒绝候选证据并开始诊断。原始候选保留，未确认证据不能进入诊断；OCR/文字冲突会触发专家暂停。QR 实际解码只定位设备，不证明故障根因。

本地示例位于 `knowledge/fixtures/media/`：OCR 仅支持明确标记的自绘模拟图片；任意现场图片没有真实 OCR/VLM 时返回 UNAVAILABLE，不套用示例读数。视频实际提取最多 8 个带时间戳的关键帧；当前没有真实 VLM，因此不推断现场现象或声音。限制：5 张图片、每张 10 MiB/2500 万像素；1 段视频、100 MiB/60 秒、解码 30 秒。默认私有 MinIO，预览通过重新检查权限的 API；本地未扫描标记 NOT_PERFORMED，外部部署必须配置扫描器。

模型协议适配器与真实模型验收分开记录，详见 `docs/provider-selection.md`。尚未配置密钥、实际模型版本或资料外发许可，不代表真实生成、OCR/VLM/语义检索或 Jev 已验收。

## 开发检查

```powershell
cd backend
uv run pytest
uv run ruff check .
uv run mypy app
```

前端分别运行 `npm.cmd run lint`、`npm.cmd test`、`npm.cmd run build`。
无需 Redis。没有 Docker 时可使用本地 PostgreSQL/pgvector 和文件媒体 provider；
文件 provider 仅替代媒体存储，不能替代持久化数据库/checkpoint。
题库、手册、解析种子和现场资料保持私有，不能发送给未获许可的外部服务或复制到公开仓库。
