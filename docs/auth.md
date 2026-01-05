# Authentication & Authorization (Login + Roles)

本项目目前主要通过 `X-API-Key`（`API_AUTH_TOKEN` / `ADMIN_API_KEYS`）进行访问控制，但需求希望 **区分 user 与 admin**：admin 拥有 user 的全部能力，并额外拥有管理控制台与治理接口的写权限。

本文先给出**可落地的设计**（文档先行），后续实现必须严格对齐本文。

## 1) 现状（Current State）

- **后端鉴权**：`src/utils/security.py::verify_api_key()` 仅校验 `X-API-Key`，并对所有接口统一生效（`src/agents/http_api.py::require_auth()`）。
- **前端鉴权**：`frontend/src/services/apiClient.ts` 默认通过 `VITE_API_KEY` 注入 `X-API-Key`。
- **问题**：
  - 无“登录态/用户身份”，无法区分 user/admin，也无法落地 RBAC。
  - admin 接口（`/v1/admin/*`）目前与普通查询接口使用同一套 key 机制，权限粒度不足。

## 2) 目标（Target State）

- **引入登录**：提供 `POST /v1/auth/login`，返回 access token（JWT）。
- **RBAC**：token 内包含角色（role）声明：`user` / `admin`。
- **权限继承**：`admin` ⊇ `user`。
- **前端行为**：
  - `/admin/*` 必须为 **admin** 才能访问（否则跳转到登录页/无权限提示）。
  - 普通 Chat（`/`）为 user 可用；是否允许匿名由配置决定。

## 3) 角色与权限矩阵（RBAC）

| 能力 | anonymous | user | admin |
|---|---:|---:|---:|
| 调用 `POST /v1/query` / SSE `POST /v1/query?stream=true` | 可选（配置） | ✅ | ✅ |
| 调用 `GET /v1/session*` | 可选（配置） | ✅ | ✅ |
| 调用 `GET /v1/slots` | ✅ | ✅ | ✅ |
| 访问前端 `/admin/*` 页面 | ❌ | ❌ | ✅ |
| 调用 `GET /v1/metrics` / `GET /v1/status` | ✅（可选） | ✅ | ✅ |
| 调用 `GET /v1/admin/*`（只读） | ❌ | ❌ | ✅ |
| 调用 `POST/DELETE /v1/admin/*`（写治理） | ❌ | ❌ | ✅ |

> 注：为简化 MVP，可先将 `/v1/metrics`、`/v1/status` 保持 “需要登录但不区分角色”，但 `/v1/admin/*` 必须 admin。

## 4) Token 方案（推荐）

### 4.1 Access Token (JWT)

- Header：`Authorization: Bearer <access_token>`
- Claims（建议）：
  - `sub`: user_id（字符串）
  - `role`: `"user"` 或 `"admin"`
  - `name`: 展示名（可选）
  - `iat`, `exp`: 发行/过期时间

### 4.2 刷新策略（MVP）

MVP 推荐：
- 只做短期 access token（例如 8h），**不做 refresh token**；到期重新登录即可。
- 后续需要“长期登录”时，再引入 refresh token + rotation。

## 5) API 设计（Auth Endpoints）

### 5.1 `POST /v1/auth/login`

Requires `username` + `password`.

- `password == AUTH_ADMIN_PASSWORD` -> `role=admin`
- `password == AUTH_ADMIN_READONLY_PASSWORD` -> `role=admin_readonly`
- otherwise validate against SQLite users table -> `role=user`

Request?????

```json
{ "username": "jane.doe", "password": "********" }
```

Response?????

```json
{
  "access_token": "<jwt>",
  "token_type": "bearer",
  "role": "admin"
}
```

### 5.2 `POST /v1/auth/register`

Creates a normal user account (role is always `user`). Requires reset question + answer.

Request?????

```json
{
  "username": "jane.doe",
  "password": "********",
  "reset_question": "First school name?",
  "reset_answer": "Sunrise Elementary"
}
```

Response?????

```json
{
  "user_id": "<uuid>",
  "username": "jane.doe",
  "role": "user"
}
```

### 5.3 `GET /v1/auth/me`


返回当前登录用户与 role，用于前端启动时恢复登录态。

### 5.4 `POST /v1/auth/logout`（可选）

MVP 若只用 JWT 且无 server-side session，可省略；前端删除 token 即可。

### 5.5 `GET /v1/auth/reset-question`

Returns the reset question for a username (used for password reset).

### 5.6 `POST /v1/auth/reset-password`

Resets a password with username + reset answer + new password.

### 5.7 `POST /v1/auth/password`

Changes password for the current logged-in user.

### 5.8 `POST /v1/auth/reset-question`

Updates the reset question + answer for the current logged-in user.

## 6) 配置与密钥（Configuration）

新增（建议）：
- `JWT_SECRET`：签名密钥（必须仅从环境变量读取）
- `JWT_EXPIRES_SECONDS`：token 过期时间
- `AUTH_ADMIN_PASSWORD`：管理员登录密码（MVP 唯一的“管理员凭据”）
- `AUTH_ADMIN_READONLY_PASSWORD`??????????????
- `PASSWORD_HASH_ITERATIONS`?PBKDF2 ??????? 120000?
- `AUTH_ALLOW_ANONYMOUS`：是否允许匿名访问 query/session（可选）

保留（兼容）：
- `API_AUTH_TOKEN` / `ADMIN_API_KEYS`：仍可作为 **dev/ops** 的备用访问方式（例如本地联调、运维脚本），但生产建议以 JWT 登录为主。

你可以参考示例配置文件：`configs/env.example`（复制为本地 `.env` 并填入真实值）。

## 7) 前端实现规范（Login + Guards）

### 7.1 Token 存储

- 推荐：`localStorage` 存 `access_token`（MVP），key：`rag.auth.access_token`
- Axios 拦截器：
  - 若 token 存在：注入 `Authorization: Bearer ...`
  - `X-API-Key` 可保留用于 dev，但上线建议停用或仅对 admin/ops 使用

### 7.2 路由守卫

- `/admin/:section`：
  - 未登录 → 跳转 `/login`
  - 已登录但 role!=admin → 显示 “No permission”
- `/`（chat）：
  - 未登录：根据 `AUTH_ALLOW_ANONYMOUS` 决定是否允许继续或跳转登录

### 7.3 UI 行为

- 左侧栏底部新增 **Account** 区：
  - 显示当前用户（name/role）
  - Logout
  - Admin badge（role=admin）

## 8) 迁移步骤（Suggested Rollout）

1. **后端**：新增 auth endpoints + JWT 校验依赖（`require_user` / `require_admin`），并对 `/v1/admin/*` 强制 admin。
2. **前端**：新增 `/login` 页面 + token 存储 + axios interceptor 注入 Authorization。
3. **前端**：对 `/admin/*` 加守卫（Route-level），并在 UI 显示当前账号。
4. **渐进移除**：将 `VITE_API_KEY` 仅用于本地；生产默认不再依赖 `X-API-Key`。


