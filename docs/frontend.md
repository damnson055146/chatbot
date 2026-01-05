# Frontend (React) — Architecture & Development Guide

本项目的前端位于 `frontend/`，技术栈为 **React + TypeScript + Vite + TailwindCSS**，并使用 **React Router** 进行路由、**React Query** 进行数据获取与缓存。

## 1) 快速开始

在仓库根目录：

```bash
cd frontend
npm install
npm run dev
```

默认访问：`http://localhost:5173`

后端建议使用 `scripts/run_dev.bat` 同时启动并自动同步 `API_AUTH_TOKEN` 与 `VITE_API_KEY`（见 `scripts/README.md`）。

## 2) 环境变量

在 `frontend/.env` 配置（不会入库）：

```txt
VITE_API_BASE=http://localhost:8000/v1
VITE_API_KEY=dev-secret-token
VITE_DEFAULT_LANGUAGE=en

# Streaming
VITE_STREAMING_MODE=server
VITE_STREAMING_CHUNK_SIZE=18
VITE_STREAMING_TICK_MS=35
```

- **`VITE_STREAMING_MODE=server`**：前端使用后端 SSE：`POST /v1/query?stream=true`（`Accept: text/event-stream`），支持 Stop/Cancel。
- **`VITE_STREAMING_MODE=off`**：前端走非流式 `POST /v1/query`。

## 3) 路由与功能入口（ChatGPT 风格导航）

路由定义在 `frontend/src/app/routes.tsx`：

- **Chat**：`/`（主聊天页）
- **Admin console**：`/admin/:section?`
  - `/admin/status`
  - `/admin/metrics`
  - `/admin/sources`
  - `/admin/audit`
  - `/admin/config`
- **Library**：`/library`（占位页，后续承接知识库/附件/素材）
- **Explore**：`/explore`（占位页，后续承接模板/探索工作流）
- **Release notes**：`/release-notes`（占位页）

侧边栏入口位于 `frontend/src/components/chat/ChatSidebar.tsx`：

- 顶部 **Workspace**：Chat/Library/Explore
- 固定 **Admin**：Status/Metrics/Sources/Audit/Release notes
- 中部为 Conversation 搜索 + Pinned + Conversations 列表
- 底部 Settings

## 3.1) 登录与权限（user/admin）

项目将引入登录与 RBAC（user/admin），并要求：

- `/admin/*` 仅 **admin** 可访问（前端路由守卫 + 后端接口鉴权）
- admin 具备 user 的所有能力

详细设计见 `docs/auth.md`。

## 4) 关键模块

- **聊天页**：`frontend/src/components/query/QueryConsolePage.tsx`
  - 发送：`postQuery()` 或 `streamQuery()`（取决于 `VITE_STREAMING_MODE`）
  - SSE 事件：`chunk` / `citations` / `completed` / `error`
  - Stop generating：`AbortController` 取消请求
- **Admin 控制台**：`frontend/src/components/admin/AdminConsolePage.tsx`
  - Metrics 可视化：`frontend/src/components/admin/MetricsDashboard.tsx`
  - Sources 管理：`frontend/src/components/admin/SourcesManager.tsx`
- **API Client**：`frontend/src/services/apiClient.ts`

## 5) 开发规范（建议）

- **类型优先**：API payload 与页面状态保持显式类型；避免 `any` 扩散。
- **数据获取**：通过 React Query（`useQuery/useMutation`）管理缓存与刷新。
- **UI 一致性**：优先复用现有的卡片/按钮/排版风格，保持 ChatGPT-like 体验。


