# 开发资料汇编

> 本文件整合仓库内所有技术说明，涵盖业务背景、系统架构、实现细节、配置、观测方案与近期计划，团队只需查阅此文即可了解整体脉络。需求细节仍以 `function_req.md` 为准。

## 目录

1. 文档定位
2. 系统背景与目标
3. 架构与模块视图
4. 后端实现与接口
5. 前端实现概览
6. 配置、环境与依赖
7. 观测性与运维
8. 近期进展与待办
9. 下一步建议

---

## 1. 文档定位

- `docs/development_compilation.md`（本文）：技术实现、运维与路线图的唯一引用入口。
- `function_req.md`：沿用原有 SRS，定义功能 / 非功能需求、验收标准与里程碑。所有实现与验收讨论应回链到该需求文档。

## 2. 系统背景与目标

- **业务动机**：为中国出国留学生及其顾问提供双语（中/英）咨询助手，替代静态 FAQ 与高负载人工；回答需附带可核验引用。
- **流程范围**：覆盖 ingest → normalize → chunk → hybrid index → retrieve → rerank → prompt compose → SiliconFlow 生成 → cite & slot update → 可选升级/转人工。
- **用户角色**：学生（提问/自助引导）、顾问（复核/补充）、管理员（语料维护、指标监控）。
- **质量目标**（见 `function_req.md` §8）：5 秒内返回 ≥2 条引用；reranker 降级需提示低置信；支持 PDPA/隐私删除与 30/90 天留存策略；流式接口需在 0.5 s 内给出首个 token。

## 3. 架构与模块视图

1. **数据摄取**：经授权的 PDF/HTML/TXT 进入清洗管线，保留段落/页锚并写入版本化快照；chunker 采用重叠语义切分，输出 doc/chunk 元数据、语言标签、领域标签、freshness 与 URL。
2. **索引层**：并行维护向量（SiliconFlow embedding）与 BM25 索引，混合检索由 retriever 合并得分；索引状态通过 `/v1/status` 和健康探针暴露（文档数、chunk 数、最近构建时间、错误列表）。
3. **查询编排**：FastAPI 服务内的 Query Agent 负责槽位聚合、检索、重排、调用 SiliconFlow chat API，并在响应中回传 citations、diagnostics、slot prompts、trace_id 以及（可选）附件元数据。
4. **前端体验**：React/Vite 客户端提供聊天面板、槽位提示、session picker、检索控制、模拟 streaming、附件上传、Usage & Health 卡片、偏好抽屉与本地 pin/导出能力。
5. **附件与存储**：`assets/uploads/` 作为统一附件目录，`storage.save_upload_file()` 负责写文件、计算 SHA256、保存 `UploadRecord` JSON；FastAPI 挂载 `/uploads/<file>` 静态服务。
6. **观测性**：`RequestMetrics` 记录 rerank/phase counters 与 latency；`configure_tracing()` 在配置 OTLP 后发出 `rag.retrieval/rerank/generation` 以及 `siliconflow.rerank` spans，并以 question hash 替代原文。

## 4. 后端实现与接口

- **核心端点**
  - `POST /v1/ingest`: 接收源文、语言、领域标签、freshness、overlap 参数，触发重建并返回 doc_id、版本、chunk_count 与健康摘要。
  - `POST /v1/query`: 支持 `language`、`slots`、`session_id`、`reset_slots`、`top_k`、`k_cite`、生成参数（temperature/top_p/max_tokens/stop/model）以及 `attachments` 列表。响应包括 answer/citations/diagnostics/slot 状态/trace_id/low_confidence。
  - `POST /v1/query?stream=true`: 规划中的 SSE 协议，定义 `chunk`/`citations`/`completed`/`error` 事件，自适配 Accept: text/event-stream。
  - `GET /v1/slots`: 返回槽位目录（含本地化 prompt、required 标记、数据类型、取值范围）。
  - `POST /v1/upload` + `GET /v1/upload/{id}`: 处理 PDF/图像（<=10 MB），校验 MIME、写入本地存储、返回 `UploadInitResponse` / `UploadRecord`，并提供下载 URL。
  - Admin 端点（slots/retrieval/stop-list）允许运维调整槽位、检索参数、敏感词并输出审计日志。
- **Agent 逻辑**
  - Retrieval → rerank → generation 三段依次执行，并通过 `metrics.record_phase` 记录耗时。
  - Rerank 失败路径会累计 `rerank_retry::attempt/exhausted`、`rerank_fallback::*`、`rerank_language::*`，并在 diagnostics 中揭示 fallback 情况。
  - `QueryResponse.attachments` 直接回传请求中的上传 ID，便于客户端标注上下文。
- **SiliconFlow 集成**
  - 环境变量：`SILICONFLOW_API_KEY/Base/Model/Embed_Model/Rerank_Model/Timeout/Max_Attempts/Backoff` 等；缺 key 时返回 `[offline]` 以便 CI。
  - `_call_siliconflow` 使用 async HTTPX，默认 3 次指数退避并提供可选 circuit breaker，事件同时注入 metrics/logging/tracing。

## 5. 前端实现概览

- **技术栈**：React 19、TypeScript 5.9、Vite 5、TailwindCSS、自定义 ESLint（100 字符行宽）、Vitest + RTL、React Query、React Hook Form、Zod、i18next、Axios 拦截器。
- **主要模块**
  - `app/`：应用壳 + 路由；`components/`：聊天面板、上下文栏、Usage 卡片；`hooks/`：React Query 抽象与 streaming hook；`services/apiClient.ts`：Axios 客户端 + DTO；`state/`：查询 key 与本地存储 key；`locales/`：中英 JSON；`utils/i18n.ts` 初始化多语。
- **特性**
  - 聊天控制台：支持 session 切换、本地持久化、键盘快捷键、Explain-like-new、检索参数调节。
  - 槽位体验：缺失 banner、建议 chips、slot 表单同步后端校验错误。
  - Streaming：`VITE_STREAMING_MODE` 控制 simulate/server/off，Stop/Cancel 可打断流式响应。
  - 附件上传：文件队列（queued → uploading → ready → error），阻止未完成上传的发送，并在记录中展示名称/大小/状态。
  - 偏好抽屉：语言、Explain-like-new 默认值、保留策略、主题；可导出对话 JSON；Pinned 会话最多 3 条。
  - Usage & Health：展示 `/v1/status` latency/quality 指标，联动低置信提示。
- **脚本**：`npm run dev/build/preview/lint/test/test:watch`；`npm run test -- --coverage` 生成 HTML 报告；`npm audit` 定期检查高危依赖。

## 6. 配置、环境与依赖

- **后端**
  - 建议使用 `.venv` + `python -m pip install -r requirements.txt`。
  - 必配环境变量：`SILICONFLOW_API_KEY/Base/Model`、`SILICONFLOW_EMBED_MODEL`、`SILICONFLOW_RERANK_MODEL`、`API_AUTH_TOKEN`、`API_RATE_LIMIT`、`API_RATE_WINDOW`、`LOG_LEVEL`。
  - Tracing（可选）：`OTEL_EXPORTER_OTLP_ENDPOINT/HEADERS/INSECURE`、`OTEL_SERVICE_NAME`、`TRACING_SAMPLE_RATIO`。未安装 OTEL SDK 时自动降级为 no-op。
  - CLI：`python -m src.cli ingest <file>`、`python -m src.cli query "question" --language zh`。
  - `.env` 为 `API_AUTH_TOKEN` 的唯一来源，可运行 `python scripts/set_api_token.py` 自动生成随机令牌并写入。
  - 质量门槛：`python -m pytest -q`、`python -m pytest -q -m "smoke"`、`pytest --cov=src --cov-report=term-missing`、`black src tests --line-length 100`、`ruff check src tests`。
  - ȫ�� CORS ����：`CORS_ALLOW_ORIGINS=*` (Ĭ��)�������ԭ�򣬿���ͬʱ����`CORS_ALLOW_CREDENTIALS=false/true`；��Ϊ `*` ʱΪ����������ͻᱻ�Զ�����Ϊ false��
  - �Զ���� OPTIONS ��Ӧ����ȷ����������Ӧͷ������չʾ���Զ���� list ��ͨ���޸� `CORS_ALLOW_ORIGINS`/`CORS_ALLOW_CREDENTIALS` �����ơ�
- **前端**
  - `.env` 示例：
    ```
    VITE_API_BASE=http://localhost:8000/v1
    VITE_API_KEY=dev-secret
    VITE_DEFAULT_LANGUAGE=en
    VITE_STREAMING_MODE=simulate
    VITE_STREAMING_CHUNK_SIZE=18
    VITE_STREAMING_TICK_MS=35
    ```
  - `npm install` → `npm run dev`；正式部署使用 `npm run build` + `npm run preview` 验证。
- **其他约束**
  - 全局编码 UTF-8，行宽 100，缩进 4 空格；公共函数需 docstring + 类型注解。
  - 密钥仅从环境变量读取；`.env` 不入库；`.env.example` 保持字段注释齐全。

## 7. 观测性与运维

- **指标体系**
  - Counters：`rerank_model::<name>`、`rerank_retry::attempt/success_after_retry/exhausted`、`rerank_fallback::disabled/error/empty_response/circuit_open`、`rerank_language::<lang>`、`rerank_circuit::opened/open_skip/recovered`。
  - 延迟：`metrics.record_phase` 输出 `retrieval_ms`、`rerank_ms`、`generation_ms`、`end_to_end_ms`，并在 `/v1/status` 与后续 `/v1/metrics` 中暴露。
- **日志格式**
  - JSON 结构化日志包含 trace_id、session_id、language、attempt、idle_for 等字段；关键事件：`siliconflow_rerank_retry`、`siliconflow_rerank_empty`、`siliconflow_rerank_fallback`、`siliconflow_rerank_circuit_*`。
- **Tracing**
  - `configure_tracing()` 根据环境变量自动初始化 OTLP 导出，使用 `ParentBased(TraceIdRatioBased)` 采样；span 属性统一 hash question 内容并记录 top_k、k_cite、language、fallback、duration、result_count、missing_slots。
  - 启用流程：安装 `opentelemetry-sdk` 与 `opentelemetry-exporter-otlp-proto-http` → 设置 OTEL 环境变量 → 重启 API → 通过 CLI 触发查询验证 spans → 在 Grafana Tempo/Honeycomb/Jaeger 中检查。
- **告警建议**
  - Rerank fallback 比例 >5%（10 分钟）→ Warning。
  - Generation P95 >3s（10 分钟）→ Critical。
  - Trace 吞吐 <1 span/min → Warning。
  - 触发时按照 runbook：确认 SiliconFlow 可用性、检查 circuit breaker 状态、根据需要调低采样或提升超时。
- **仪表盘实践**
  - Grafana：配置 JSON（/v1/status 或后续 `/v1/metrics` JSON 数据源）、Prometheus（counter/histogram）、Loki（日志），展示 phase latency、fallback rate、span volume、活跃 session。
  - Prometheus：抓取 `rag_*` counters/histograms + OTEL Exporter metrics（`otelcol_receiver_accepted_spans`）。

## 8. 近期进展与待办

- **已交付**
  - Manifest/Prompt/文档查找缓存，减少重复磁盘读取。
  - Rerank 重试、超时、熔断 + 语言粒度指标；Optional OpenTelemetry span `siliconflow.rerank`。
  - `/v1/query` 附件字段、`/v1/upload` API、`assets/uploads/` 管理、前端上传状态机与阻塞策略。
  - 观测性：`time_phase` / `time_phase_endpoint` 计时、Grafana 面板、Prometheus 规则、OTLP Runbook。
  - 前端：偏好抽屉、Usage 卡片、模拟 streaming、Vitest 覆盖、会话 pin/导出。
- **进行中**
  - 评估独立 metrics exporter（`/v1/metrics` → OTLP metrics pipeline），决定是否开放 Pull/Push 兼容模式。
- **未完成 / 风险**
  - SSE streaming 已在后端落地（`POST /v1/query?stream=true`，事件：`chunk`/`citations`/`completed`/`error`），前端可通过 `VITE_STREAMING_MODE=server` 启用；仍需补齐更完善的断线重连与 UI 级别的“流式状态”细节。
  - 附件缺少 OCR/反病毒/PII 扫描与定期清理，需在数据保留策略前完成。
  - Chronograf 或其他 dashboard 映射仍待确认数据源。
  - Server-side pin/archive、反馈 API、偏好同步、会话保留等功能仍处路线图阶段（见 `function_req.md`）。

## 9. 下一步建议

1. **完善 `/v1/query` SSE 体验**：在前端默认启用 `VITE_STREAMING_MODE=server` 时验证 stop/cancel、断线重连与 tracing 关联；并补齐 UI 对 metrics/citations 的更细粒度呈现。
2. **补齐附件合规链路**：在上传流程中插入 OCR/病毒/PII 检测，完善 retention/删除 API，并在观测指标与日志中记录扫描结果。
3. **发布 metrics exporter**：明确 `/v1/metrics` JSON 格式或推送至 Prometheus/OTLP 的策略，同时更新仪表盘数据源与告警表达式。
4. **隐私/合规 Runbook**：围绕 PDPA 留存/删除、API key 轮换、trace 采样调整建立可执行 runbook，与需求文档中的合规条款形成闭环。
5. **版本化文档**：为重要配置或操作指南创建 `docs/snapshots/<date>_vN/`，并在 PR 模板中加入“更新开发资料汇编”检查项，确保该文件长期保持最新状态。
