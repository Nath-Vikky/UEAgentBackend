# 环境搭建文档

## 环境要求

- Python `>=3.11,<3.14`
- 建议项目内虚拟环境目录固定为 `.venv`

## 创建虚拟环境

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```

`requirements-dev.txt` 当前会安装：

- 基础后端依赖
- 测试 / lint 依赖
- Phase 2 所需的 RAG 依赖组

当前补充说明：

- 在 Python 3.13 环境下，`unstructured` 的旧版依赖仍和 `qdrant-client` 的 `numpy` 约束冲突
- 因此当前 `rag` 依赖组会在 Python 3.13 上自动跳过 `unstructured`
- 如果你需要完整验证 `Docling + Unstructured` 双解析链路，建议临时使用 Python 3.12

## 配置 `.env`

在 `backend/` 目录执行：

```powershell
Copy-Item .env.example .env
```

至少确认以下字段：

- `APP_HOST`
- `APP_PORT`
- `DATABASE_URL`
- `QDRANT_URL`
- `CHAT_MODEL`
- `EMBEDDING_MODEL`
- `EMBEDDING_ENABLED`
- `RAG_MODE`
- `RAG_FALLBACK_MODE`
- `KB_SOURCE_PATHS`
- `KB_CHUNK_SIZE`
- `KB_CHUNK_OVERLAP`
- `OPENAI_API_KEY`
- `LANGSMITH_API_KEY`

### 知识库相关字段说明

- `KB_SOURCE_PATHS`
  - 默认扫描 `../backend.md`、`../forward.md` 和 `./docs`
- `KB_MAX_FILE_BYTES`
  - 单文件导入大小限制
- `KB_CHUNK_SIZE`
  - 普通文档切片大小
- `KB_CHUNK_OVERLAP`
  - 相邻切片重叠大小

## 初始化数据库

```bash
alembic upgrade head
```

## 启动服务

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## 首次验收

### 基础服务

- `GET /api/v1/system/health`
- `GET /api/v1/system/bootstrap`
- `GET /api/v1/system/runtime-profiles`

### 知识库

- `GET /api/v1/knowledge-base/status`
- `POST /api/v1/knowledge-base/refresh`

### 项目问答

- `POST /api/v1/tasks/project-qa`
- `POST /api/v1/chat/runs`
