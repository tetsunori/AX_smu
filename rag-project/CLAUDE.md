# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Teaching material for a 10-day AI service development course (상명대 천안캠퍼스, 2026.08.18 ~ 08.31). `README.md` holds the day-by-day curriculum. The deliverables are two portfolio systems, each a **separate, self-contained uv project**:

- `rag-system/` — days 1–6: RAG + Text2SQL data-retrieval workflow (LangGraph `StateGraph`)
- `agent-system/` — days 7–10: tool-based agents (LangChain v1 `create_agent` + middleware + skills)

They have their own `pyproject.toml`, `uv.lock`, `.venv`, `.env`, and Jupyter kernel. Never run a command for one project from the other's directory, and don't consolidate their dependencies.

Content (comments, docstrings, prompts, notebook prose) is written in Korean — match that when editing. Several file and directory names are Korean too (`workspace/회의록/`, `datasets/2026 주요업무계획.pdf`).

## Commands

Setup (per project):

```bash
cd rag-system            # or: cd agent-system
uv sync
# Windows kernel registration
.venv\Scripts\python.exe -m ipykernel install --user --name=ai-service-rag --display-name="ai service rag"
```

Kernel names: `ai-service-rag` / `ai-service-agent` — notebooks expect these to exist. Copy `.env.example` to `.env` in the project root (not the repo root).

Run LangGraph Studio (opens `http://127.0.0.1:2024`):

```bash
# rag-system: from rag-system/
uv run langgraph dev

# agent-system: from the specific agent's directory, e.g. agent-system/src/skill-agent/
$env:PYTHONUTF8=1; uv run langgraph dev --no-reload --allow-blocking     # PowerShell
PYTHONUTF8=1 uv run langgraph dev --no-reload --allow-blocking           # bash/zsh
```

Streamlit demo:

```bash
cd rag-system && uv run streamlit run src/demo/streamlit_example.py
```

There is no test suite, linter, or formatter configured. Verification is manual: run the relevant notebook cell, LangGraph Studio, or the Streamlit demo.

### Windows specifics

`PYTHONUTF8=1` is in both `.env.example` files and is required — Korean file content and Korean filenames break under the default Windows codepage. `agent-system` additionally needs `--no-reload --allow-blocking` because its tools and middleware do blocking sync file I/O.

## rag-system architecture

`src/ai/` is a LangGraph workflow that routes a question to one of three paths. The package is imported as `ai.*` (absolute), enabled by `[tool.setuptools.packages.find] where = ["src"]`.

```
classify_intent ──general──▶ general_answer ─────────────────────▶ END
        │
        ├──vector──▶ vector_search ⇄ rewrite_query ──▶ generate_answer ──▶ END
        │                (retry until relevant, max 2)
        └─database─▶ database_query (self-loop on SQL error, max 2) ──▶ generate_answer
```

- `state.py` — `AgentState(MessagesState)` carries `intent`, `vector_results`, `sql_query`, `db_results`, `retry_count`, `error`. `InputState` narrows the Studio input surface to just `messages`.
- `nodes.py` — all nodes plus the three routing functions (`route_by_intent`, `check_vector_results`, `check_db_results`). Retriever and Text2SQL engine are lazily built and module-cached (`get_cached_*`) so importing the graph doesn't hit the network. Nodes that need context re-write the latest question into a standalone one using the full message history before searching.
- `retriever.py` — `VectorRetriever` fans out to two Qdrant strategies in a `ThreadPoolExecutor` and dedups by hash of the first 200 chars: `ParentDocumentRetriever` (searches child chunks in `cheonan_child_chunks`, then returns the reassembled parent page) and `MetadataFilteredRetriever` (`cheonan_metadata`, filtered on `metadata.category`). Category values are enumerated in the `VectorSearchQuery` structured-output schema in `nodes.py` — the same list appears in that node's system prompt, so **any category change must be made in both places**.
- `text2sql.py` — PostgreSQL (Supabase) via LangChain `SQLDatabase`; caches `get_table_info()` at init, generates SELECT-only SQL, and accepts `previous_error` for retry feedback. Table descriptions are hardcoded in the prompt (`organizations`, `departments`, `office_floors`).

**The notebooks build the data that `src/` reads.** `src/ai` will fail against an empty Qdrant/Supabase, so the notebooks are a prerequisite, not just a demo: `03` → collection `cheonan_docs`, `04` → `cheonan_child_chunks`, `05` → `cheonan_metadata`, `06` → loads `datasets/*.csv` into `database/cheonan_city.db` (SQLite, gitignored) for `07`. `src/ai/retriever.py` and `text2sql.py` point at Qdrant Cloud and Supabase, while notebooks `06`/`07` use local SQLite — that difference is intentional (local first, cloud later in the curriculum).

Embeddings are `text-embedding-3-large`; changing that invalidates every existing collection.

## agent-system architecture

Three progressively richer agents, each a standalone directory with its own `langgraph.json`, `agent.py`, `tools.py`:

| Directory | Purpose | Notable pieces |
|---|---|---|
| `src/domain-agent/` | Day-7 scaffold, deliberately full of `TODO`s for teams to fill in | `FILE_TOOLS` + `execute_python_code` |
| `src/middleware-agent/` | Day-8 document workspace assistant over `workspace/` | `workspace_index_middleware`, `auto_backup_middleware` |
| `src/skill-agent/` | Day-9 skills / progressive disclosure | `SkillMiddleware`, `load_skill`, `fetch_url` |

Each `agent.py` uses flat sibling imports (`from tools import TOOLS`) and each `langgraph.json` declares `"dependencies": ["."]` with `"env": "../../.env"`. Consequence: **cwd must be the agent's own directory**. `uv run` still resolves the venv by walking up to `agent-system/pyproject.toml`.

Middleware patterns to follow when adding more:

- `@before_agent` (`workspace_index_middleware`) — returns `{"messages": [SystemMessage(...)]}` to inject a pre-built file index, so the model doesn't need a `list_directory` round-trip. It walks `os.getcwd()`, which is why cwd matters.
- `@wrap_tool_call` (`auto_backup_middleware`) — async; inspects `request.tool_call["name"]`, does its side effect, then `await handler(request)`. Failures are logged and swallowed so the underlying tool still runs.
- `AgentMiddleware` subclass (`SkillMiddleware`) — appends to `request.system_message.content_blocks` and calls `request.override(system_message=...)`. It implements **both** `wrap_model_call` and `awrap_model_call` with identical logic; LangGraph Studio and `astream`/`ainvoke` take the async path, so a sync-only implementation silently does nothing there.

### Skills

`src/skill-agent/skills/<name>/SKILL.md` with YAML frontmatter (`name`, `description`). `middleware.py` regex-parses the frontmatter at import time into the module-level `SKILLS` list and injects only the descriptions; the body is loaded on demand by the `load_skill` tool. Adding a skill = adding a directory; no registration code. `description` is written in English (it is the model's routing signal), the body in Korean.

`make_tool_prompt.txt` and `make_skill_tool_prompt.txt` are meta-prompts students paste into an LLM to generate new tools/skills — they define the house style for tools: `@tool(parse_docstring=True)`, Google-style docstrings, full type hints, imports inside the function.

## Conventions

- Model is referenced as the string `"gpt-5.4-mini"`, passed to `init_chat_model(...)` (rag-system) or `create_agent(model=...)` (agent-system). It is hardcoded at each call site, not centrally configured.
- Tools return **human-readable strings, including for errors** (`f"오류: 파일을 찾을 수 없습니다: {file_path}"`) rather than raising — the model reads and recovers from them. Keep that contract.
- Nodes return partial state dicts (only the keys they change), never a full state object.
- `print()` with emoji prefixes (`[Workspace Index] ✅ ...`) is the intended tracing mechanism for classroom visibility; keep it in new nodes/middleware.
- `day*_team_project_template.ipynb` and `src/domain-agent/` are student starting points. Their `TODO`s and placeholder prompts are the assignment — don't complete them unless asked.
- Gitignored artifacts that get regenerated: `database/`, `qdrant_db/`, `.langgraph_api/`, `.venv`, `.env`.
- `git_guide.md` is the collaboration guide taught on day 2; `실습환경설치가이드.html` is the environment setup handout.
