# Repository Guidelines & Agents Conventions

## 1) Project Structure & Module Organization

保持工作区简洁、可发现性强；按下列结构组织模块与资产：

```
repo-root/
  src/
    agents/               # 核心 orchestrators / agent 实现
    pipelines/            # （可选）端到端流程编排
    utils/                # 复用的通用工具与适配层
    schemas/              # Pydantic/TypedDict 等请求/响应/事件模型
    cli.py                # 统一 CLI 入口：python -m src.cli --config ...
  tests/
    unit/                 # 单测；与 src 目录镜像
    integration/          # 集成/端到端/外部依赖交互
    fixtures/             # 测试夹具与样例数据（json/yaml/csv）
  assets/
    prompts/
      templates/          # 提示词模板（可按场景/模型/语言分层）
      examples/           # 脱敏示例与基准样例
    data/
      raw/                # 原始数据（不可修改）
      processed/          # 清洗/特征化中间产物
      snapshots/          # 数据/提示词快照：YYYYMMDD_vN/
  configs/                # dev.yaml / prod.yaml / local.yaml 等
  scripts/                # 可运行脚本：data_prep/ deploy/ smoke/
  docs/                   # 架构/决策记录/运维手册
  .github/
    PULL_REQUEST_TEMPLATE.md
    ISSUE_TEMPLATE.md
```

> 约定：`src/` 作为代码根命名空间；新增模块时优先落位到 `agents/`（编排/交互）、`pipelines/`（工作流）、`utils/`（跨模块复用），面向外部的 Schema 放入 `schemas/`，减少循环依赖与“上帝模块”。

---

## 2) Build, Test, and Development Commands

**环境与依赖（自仓库根目录执行）：**

```bash
# Python venv
python -m venv .venv
# Windows
.venv\Scripts\Activate.ps1
# macOS/Linux
source .venv/bin/activate

# 安装后端依赖
python -m pip install -r requirements.txt
# 刷新锁定文件（仅在需要时）
pip freeze > requirements-lock.txt
```

**测试与覆盖率：**

```bash
# 全量测试（静默）
python -m pytest -q
# 快速冒烟
python -m pytest -q -m "smoke"
# 覆盖率目标 ≥ 85%
pytest --cov=src --cov-report=term-missing
```

**端到端演练（可分享配置）：**
```bash
python -m src.cli --config configs/dev.yaml
```

**格式化与静态检查（提交前必须本地通过）：**
```bash
black src tests --line-length 100
ruff check src tests
```

- 代码风格遵循 **PEP 8**；公共模块/函数要求 docstring 与类型注解。  
- `pytest -m` 使用内置/自定义 **markers** 管理测试子集（如 `smoke`、`slow`）。  
- `black` 默认 88，可在项目统一设为 100 并在 CI 校验；团队保持一致最重要。  
- `ruff` 作为快速一体化 linter（整合 flake8/isort/pyupgrade 等）。

---

## 3) Coding Style & Naming Conventions

- **缩进** 4 空格；**行宽** 100；UTF-8；避免超 3 层嵌套。  
- **命名**：模块/函数/变量 `snake_case`；类 `PascalCase`；常量 `UPPER_SNAKE_CASE`。  
- **类型**：所有公共函数必须显式类型注解（参数+返回）；公共类/方法提供 docstring（统一风格）。  
- **异常**：自定义异常以 `XxxError` 结尾；捕获时记录上下文与关键信息（勿打印敏感内容）。  
- **日志**：结构化日志（JSON）；关键路径写入事件与耗时，便于可观测。  
- **依赖倒置**：模块间通过接口/适配层交互，降低耦合；禁止 utils 变成“上帝模块”。

---

## 4) Testing Guidelines

- **布局**：`tests/unit` 镜像 `src` 目录；跨模块/外部系统放 `tests/integration`。  
- **命名**：`test_<module>.py`；夹具放 `tests/fixtures/<feature>.json|yaml`。  
- **标记**：为 `smoke`、`slow`、`e2e` 等自定义 markers，并在 `pytest.ini` 注册。  
- **隔离**：测试应无全局副作用；文件/网络/端口用临时资源；并发测试避免共享状态。  
- **外部依赖**：对第三方 API/模型服务用 mock/stub（如 `respx`/`pytest-mock`），仅在 integration 中做最小真连。  
- **覆盖率**：目标 ≥ 85%，对关键分支/异常路径补足。报告用 `--cov-report html`。

---

## 5) Commit & Pull Request Guidelines

- **提交规范**：遵循 **Conventional Commits**（`feat: ...`、`fix: ...`、`refactor:`、`docs:`、`test:`、`chore:`；必要时 `BREAKING CHANGE:`）。  
- **信息密度**：标题 ≤ 72 字符；正文说明动机、风险、回滚方式。  
- **分支策略**：`main`（稳定） / `develop`（集成） / `feature/*` / `hotfix/*`。  
- **PR 模板**（`.github/PULL_REQUEST_TEMPLATE.md`）：  
  - 变更摘要（What/Why）  
  - 风险与兼容性（含迁移步骤/回滚）  
  - 验证清单（`pytest -q`、`smoke`、端到端命令）  
  - 截图/日志（行为变更）  
- **合并门槛**：至少 1 名维护者 Review + CI 全绿；禁止格式化与大逻辑改动混提。

---

## 6) Security & Configuration Tips

- **环境变量**：仅从环境读取密钥；维护 `.env.example`（字段注释齐全）。遵循 12-Factor **Config** 原则。  
- **禁止入库**：不得提交真实凭据/令牌/原始敏感响应；示例统一脱敏保存到 `assets/prompts/examples/`。  
- **git 忽略**：`.env`、`.venv/`、`__pycache__/`、`*.pyc`、临时数据/快照、构建产物等。  
- **最小权限**：API Key、服务账号启用最小权限与定期轮换；记录轮换步骤到 `docs/configuration.md`。  
- **接口防护**：签名/时间戳/防重放、限流、IP 允许列表（若面向公网）。  
- **日志合规**：严禁输出敏感字段；必要时做字段脱敏或加密。  

---

## 7) Dependencies & Versions (Pinned)

> 说明：后端**不本地部署模型**，通过 **SiliconFlow API** 调用推理，因此无需 `torch/transformers` 等本地推理依赖。以下为“稳定/社区验证良好”的建议版本起点；实际以团队统一锁定为准。

### 7.1 Backend — `requirements.txt`

```txt
# Web & ASGI
fastapi==0.117.1
uvicorn==0.26.1

# HTTP 客户端与健壮性
httpx==0.26.2
aiohttp==3.8.4
tenacity==8.2.2

# 序列化 & 配置 & 日志
orjson==3.9.9
python-dotenv==1.0.0
structlog==23.3.0

# Dialog / Orchestration（如使用）
rasa==3.6.21
rasa-sdk==3.13.0

# 缓存/状态
redis==5.0.10

# Dev & Test
pytest==7.4.0
pytest-asyncio==0.21.0
black==25.9.0
ruff==0.6.9
isort==5.13.2
flake8==7.1.1
mypy==1.11.2
pre-commit==3.8.0
coverage==7.6.1
```

### 7.2 Frontend — `package.json`（关键依赖建议）

```json
{
  "dependencies": {
    "react": "19.1.1",
    "react-dom": "19.1.1",
    "react-router-dom": "7.5.0",
    "axios": "1.7.7",
    "react-hook-form": "7.53.0",
    "zod": "3.23.8",
    "tailwindcss": "3.4.13"
  },
  "devDependencies": {
    "typescript": "5.5.4",
    "vite": "5.4.10",
    "eslint": "9.11.1",
    "prettier": "3.3.3",
    "@types/react": "19.0.2",
    "@types/react-dom": "19.0.2"
  }
}
```

> 备注：React 19 已稳定；如需要 SSR/同构可考虑 Next.js（另行锁版本）。React/TS 生态更新较快，**锁定次版本并保持锁文件**（`package-lock.json`/`yarn.lock`）对复现至关重要。

---

## 8) CI, Lockfiles & Reproducibility

- **Python**：以 `requirements.txt`（人读）+ `requirements-lock.txt`（机器锁定）双轨管理；发布/部署用锁定文件。  
- **Node**：始终提交 lockfile；CI 用 `npm ci`/`pnpm install --frozen-lockfile` 确保可复现。  
- **Pre-commit**：在 `.pre-commit-config.yaml` 中挂 `black`/`ruff`/`isort`/`eslint` 钩子，拒绝未格式化代码进入主干。  
- **PR 必带**：验证命令、影响面、回滚方式；对行为变更附截图或日志。  
- **文档沉淀**：关键架构决策与权衡写入 `docs/`（ADR/决策记录）。

---

## 9) Runbooks & Ops（可选但推荐）

- **runbooks/**：常见故障排查（限流/超时/鉴权失败/回滚/密钥轮换）。  
- **Observability**：统一结构化日志 + 指标（P95/P99 延迟、外呼成功率、重试率）。  
- **安全演练**：定期做 API key 泄露演练与权限巡检。  
