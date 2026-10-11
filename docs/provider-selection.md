# Provider 选择与实测记录

## 当前默认模式

| 能力 | 当前 provider | 版本/来源 | 真实调用 |
|---|---|---|---|
| 诊断模板与规则 | fixture provider | 项目内 APX-240 种子 | 否 |
| OCR | fixture/PaddleOCR-compatible adapter | 接口已固定，现场版本待登记 | 否 |
| 视觉分析 | fixture/VLM adapter | 接口已固定，现场版本待登记 | 否 |
| 视频关键帧 | OpenCV/FFmpeg bounded adapter | 本地依赖 | 否 |
| Embedding/RAG | local fixture + pgvector/keyword | 知识 release 绑定 | 否 |
| Jev | OpenAI-compatible System One adapter | `.env` 中仅保留服务端密钥 | **未调用** |

## 真实 provider 开启前必须补充

- provider、模型和版本；
- 许可证和数据处理条款；
- 输入 schema、上下文能力和最大长度；
- 运行机器 RAM/VRAM、网络和延迟；
- 允许处理的数据分类、保留策略和 egress basis；
- 经过脱敏的自编造输入、原始响应、耗时和费用记录。

缺少上述任何一项时，真实评估状态为 `BLOCKED`，fixture 结果不得替代真实质量结论。

