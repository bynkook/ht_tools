# AGENTS.md - ht_fools readme

This document provides essential context for AI coding agents working on the FabriX project.

## Quick Reference

| Command | Description |
|---------|-------------|
| `setup_project.bat` | Initial setup (venv + dependencies) |
| `run_project.bat` | Start all services (development mode) |
| `service_project.bat` | Start all services (production/network mode) |
| `reset_create_admin.bat` | Reset DB and create admin user |
| `migrate_db.bat` | Run migrations with backup (server-safe) |

## Build Commands

### Frontend (React + Vite)
```bash
cd frontend
npm install              # Install dependencies
npm run dev              # Development server (port 5173)
npm run build            # Production build
npm run lint             # ESLint check
npm run preview          # Preview production build
```

### Backend - Django (port 8000)
```bash
.venv\Scripts\activate
cd django_server
python manage.py makemigrations <app_name>   # Create migration
python manage.py migrate                     # Apply migrations
python manage.py runserver                   # Development server
python manage.py test                        # Run Django tests
```

### Backend - FastAPI (port 8001)
```bash
.venv\Scripts\activate
uvicorn ai_gateway.main:app --host 127.0.0.1 --port 8001 --reload
```

## Test Commands

```bash
# Python tests (pytest)
pytest test/test_contents_validation.py -v                    # Run specific test file
pytest test/test_contents_validation.py::TestContentsValidation::test_01_single_valid_element -v  # Single test
pytest test/ -v                                               # Run all tests

# Frontend tests (if configured)
cd frontend && npm run test
```

## Architecture

```
Browser
  |
  v
React (5173) ----+--> Django (8000)   : Auth, History, DB, Data Explorer API
                 +--> FastAPI (8001)  : AI proxy, SSE streaming, image processing
```

### Port Map
- `5173`: Vite frontend
- `8000`: Django + DRF (REST API)
- `8001`: FastAPI gateway (SSE streaming)

### Key Directories
- `django_server/apps/`: Django applications
  - `authentication/`: Login/signup/JWT
  - `fabrix_chat/`: Model-based chat sessions
  - `fabrix_agent_chat/`: Agent-based chat sessions
  - `data_explorer/`: Data exploration + DuckDB
  - `image_inspector/`: Image comparison logic
  - `user_settings/`: User preferences
  - `core/`: Shared utilities
- `frontend/src/`: React application
  - `api/djangoApi.js`: Django API client
  - `api/fastapiApi.js`: FastAPI API client
  - `features/`: Feature-based components
- `ai_gateway/`: FastAPI application
  - `routers/`: API endpoints
  - `services/`: Business logic (rate limiter, image processor)

## Phase 1 MCP Host Worktree Rules

This worktree is the dedicated branch/worktree for **FabriX Chat -> generic MCP host conversion**.

### Standards Precedence

When implementation guidance conflicts, use this order:

1. **MCP Specification + official architecture docs**
2. **Official MCP SDKs + official MCP dev tools**
3. **Reference host projects**
4. **Agent skills**
5. **FabriX-specific legacy behavior and local conventions**

### Official MCP References

- **MCP architecture/specification**
  - Treat FabriX as the **Host**
  - Treat each provider connection as an MCP **Client**
  - Treat `fastmcp` doc search as the first MCP **Server**
- **Official SDKs**
  - Prefer **`modelcontextprotocol/python-sdk`** as the primary backend/client reference
  - Use **`modelcontextprotocol/typescript-sdk`** for transport/middleware semantics
  - For TypeScript SDK, prefer **stable v1.x semantics for production behavior** over `main` branch pre-alpha guidance
- **Official dev tool**
  - Use **`modelcontextprotocol/inspector`** as the first-line capability/transport validation tool

### Reference Host Projects

- **`mark3labs/mcphost`**
  - Reference for config-driven registry design
  - Reference for local/remote/builtin server classification
  - Reference for allowlist/denylist tool controls
  - Reference for hooks and non-interactive execution concepts
- **`OpenAgentPlatform/Dive`**
  - Reference for host UX vs host core separation
  - Reference for multi-provider host thinking
  - Reference for operator-facing control surfaces, slash commands, and `@` interactions

Never copy a reference project blindly. Reuse the pattern, not the product-specific surface area.

### Phase 1 MCP Design Rules

- Keep **generic host core** separate from **FabriX UX adapters**
- `/mcp` and `@filename` remain **manual override UX**, not host-core architecture
- Design registry/config so later providers can be added without restructuring the chat core
- Keep provider-specific logic inside provider adapters
- Normalize tool/resource/prompt output before merging into chat context
- Remove legacy hardcoded MCP paths after the new path is stable; do not keep permanent duplicate routes

### Phase 1 Skills Strategy

Use skills deliberately to improve quality and speed, but only after checking official references first.

- **Always useful**
  - `find-skills`
  - `python-code-style`
  - `python-design-patterns`
  - `python-project-structure`
  - `vercel-react-best-practices`
- **High-value MCP-related candidates**
  - `jlowin/fastmcp@fastmcp-client-cli`
  - `coleam00/second-brain-skills@mcp-client`
  - `frankxai/claude-skills-library@mcp-architecture-expert`
  - `github/awesome-copilot@documentation-writer`

Recommended workflow:

1. Read official MCP docs/SDK guidance
2. Compare with `mcphost` / `Dive`
3. Invoke the relevant skill
4. Implement
5. Validate provider behavior with Inspector or an equivalent MCP client

### External MCP Provider Reference

Current providers for Phase 1–4:

**1. fastmcp doc-search (Phase 1)**
- Local doc-search MCP server: `C:\Users\BgKing\mycode\fastmcp`
- Default endpoint: `http://127.0.0.1:8002/mcp`
- Typical start command:

```bash
cd ..\fastmcp
run_server.bat
```

**2. lexguard-mcp legal QA (Phase 4)**
- Local legal QA MCP server: `C:\Users\BgKing\mycode\lexguard-mcp` (외부 폴더, 별도 venv)
- Default endpoint: `http://127.0.0.1:9099/mcp`
- Remote endpoint: `https://lexguard-mcp.onrender.com/mcp`
- Typical start command (local):

```bash
cd ..\lexguard-mcp
.venv\Scripts\activate
python -m src.main
```

> Adding a new MCP provider only requires: (1) a new `[mcp.providers.<id>]` entry in `secrets.toml`,
> (2) a new adapter in `ai_gateway/services/mcp/providers/`, (3) a manifest entry in `providers/__init__.py`,
> and (4) an activation rules JSON in `shared_planner/rules/`. No changes to chat router or UI needed.

## Code Style Guidelines

### dos batch file(.bat)

1. add 'chcp 65001 > nul' after '@echo off'
2. file encoding is 'utf-8' without BOM.
3. always use 'REM' to add non-code comments. never use '::'.
4. line endings MUST be Windows CR+LF (`\r\n`). Never LF-only. Agents writing .bat files must ensure CRLF — most editors and the Write tool default to LF, which causes silent failures on Windows CMD.

> **⚠️ Agent shell safety**: The `> nul` redirect is a Windows CMD construct.
> **NEVER execute `.bat` file contents directly in bash/shell commands.**
> Running `chcp 65001 > nul` in bash creates a literal file named `nul` in the working directory.
> To read or verify a `.bat` file, use the Read tool only. To run it, use `cmd /c <file>.bat`.

### Python (Django/FastAPI)

**Imports ordering:**
1. Standard library
2. Third-party (django, fastapi, rest_framework, etc.)
3. Local imports

```python
# Standard library
import logging
from pathlib import Path

# Third-party
from django.db import transaction
from rest_framework import viewsets, status, permissions
from fastapi import APIRouter, HTTPException

# Local
from .models import ChatSession
from .serializers import ChatSessionSerializer
```

**Naming conventions:**
- Classes: PascalCase (`ChatSessionViewSet`)
- Functions/methods: snake_case (`get_queryset`, `perform_create`)
- Variables: snake_case (`current_session_id`)
- Constants: UPPER_SNAKE_CASE (`MAX_HISTORY_TURNS`)
- Private helpers: prefix with underscore (`_get_file_metadata_helper`)

**Error handling:**
- Use DRF `Response` with appropriate status codes
- Log errors with `logging.getLogger(__name__)`
- Return JSON error objects with `error` key

```python
logger = logging.getLogger(__name__)

# Good
try:
    response.raise_for_status()
    return Response(data, status=status.HTTP_200_OK)
except httpx.HTTPStatusError as e:
    logger.error(f"HTTP error: {e.response.status_code}")
    return Response({'error': str(e)}, status=e.response.status_code)
```

**Django ORM:**
- Always use `select_related` / `prefetch_related` to avoid N+1 queries
- Use `transaction.atomic()` for multi-step operations

```python
# Good
queryset = ChatSession.objects.filter(user=request.user).prefetch_related('messages')

# Multi-step save
@transaction.atomic
def messages(self, request, pk=None):
    session = self.get_object()
    serializer.save(session=session)
    session.save()  # Update timestamp
```

**FastAPI specifics:**
- Use shared HTTP client: `request.app.state.http_client`
- NEVER create new `httpx.AsyncClient()` per request
- SSE responses: `StreamingResponse(generator, media_type="text/event-stream")`

### JavaScript/React (Frontend)

**Imports ordering:**
1. React and React ecosystem
2. Third-party libraries
3. Local components/APIs

```javascript
import React, { useState, useEffect, useCallback } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { fetchEventSource } from '@microsoft/fetch-event-source';
import { Bot, Sparkles } from 'lucide-react';

import ChatBubble from './components/ChatBubble';
import { modelChatApi } from '../../api/djangoApi';
```

**Naming conventions:**
- Components: PascalCase (`ChatPage`, `ChatBubble`)
- Functions: camelCase (`handleSend`, `updateLastMessage`)
- Constants: UPPER_SNAKE_CASE (`MAX_HISTORY_TURNS`)
- Refs: suffix with `Ref` (`messagesEndRef`, `abortControllerRef`)

**API Layer:**
- Django endpoints → `djangoApi.js`
- FastAPI endpoints → `fastapiApi.js`
- Never mix in same component for different purposes

```javascript
// Django API - for CRUD, auth, sessions
import { modelChatApi } from '../../api/djangoApi';
await modelChatApi.createSession(modelId, title);

// FastAPI API - for streaming, file processing
import { getFastApiUrl } from '../../api/axiosConfig';
await fetchEventSource(getFastApiUrl('/chat-messages'), { ... });
```

**SSE Handling:**
- Server returns snake_case fields: `event_status`, `finish_reason`
- Handle both cases defensively:
```javascript
const eventStatus = parsed.event_status ?? parsed.eventStatus;
const finishReason = parsed.finish_reason ?? parsed.finishReason;
```

**Error Display:**
- Use top red banner with `AlertCircle` icon
- Pattern:
```javascript
{error && (
  <div className="bg-red-50 text-red-600 px-4 py-3 flex items-center gap-2">
    <AlertCircle size={16} />
    {error}
  </div>
)}
```

## Non-Negotiable Rules

## Safety & Root Cause Principles

### 안전성 검토 원칙 (Safety Assessment)

코드 작성 전 Plan 수립 단계에서 작업의 안전성을 반드시 평가한다.

**High Risk로 분류하여 신중하게 접근해야 하는 작업:**
- 기능 추가/변경, 아키텍처 변경 등 대규모 코드 변경
- 엔드 유저의 사용자 경험 또는 품질을 저하시킬 오류 발생 가능성이 높은 작업
- 예측하기 어려운 버그 발생 가능성이 높은 복잡한 작업

**High Risk 작업 대응 방식:**
- 작업 전 위험 요소를 명시적으로 나열하고 사용자에게 알린다
- 변경 범위를 최소화(Minimal Diff)하여 영향 범위를 좁힌다
- 한 번에 큰 변경보다 단계적·점진적 변경을 우선한다
- 불확실한 경우 코드 작성 전에 사용자에게 확인을 요청한다

### Root Cause 탐색 원칙 (Root Cause Analysis)

오류 수정 시 증상 제거가 아닌 근본 원인을 먼저 탐색한다.

- 오류의 근본 원인(Root Cause)을 파악한 후 수정 방향을 결정한다
- Temporary fix(임시 우회, 예외 무시, 하드코딩 방어 등)는 가급적 사용하지 않는다
- Temporary fix가 불가피한 경우, 반드시 `# TODO: temporary fix - <이유>` 주석을 남긴다
- 동일 오류가 다른 경로에서도 재현될 수 있는지 확인하고 함께 수정한다

### Security
- **NEVER** commit API keys, tokens, or secrets
- Secrets go in root `secrets.toml` only (gitignored)
- SQL queries must be SELECT-only with validation

### API Layer Separation
- Django endpoints: `djangoClient` / `djangoApi.js`
- FastAPI endpoints: `fastApiClient` / `fastapiApi.js`
- Do NOT mix responsibilities

### Frontend API Runtime Rules
- Base URL is built dynamically from `window.location.protocol` + `window.location.hostname` (port only differs)
- Auth token storage is `sessionStorage` (`authToken`)
- Both `djangoClient` and `fastApiClient` inject `Authorization: Token <token>` via request interceptors

### Gateway Prefixes (Prefix + Role)
- `/health`: health check and liveness
- `/chat-messages`: model chat streaming gateway + model list/rate-limit status
- `/agent-messages`: agent chat streaming gateway + agent list/file upload/rate-limit status
- `/image-compare`: image compare processing + preview

### HTTP Client (FastAPI)
- ALWAYS use shared client: `request.app.state.http_client`
- NEVER create `httpx.AsyncClient()` per request

### Database
- SQLite in WAL mode
- N+1 prevention with `select_related`/`prefetch_related`

### UI Consistency
- Sidebar header format: `[Icon][Title][Home][Shrink]`
- Error display: top red banner with `AlertCircle`

## Tool Usage Reliability Rules

These rules are mandatory because repeated shell/filesystem mistakes slow down work and create false errors.

### General

- Prefer repo-native tools first: **`view` / `rg` / `glob` / `apply_patch`**
- Use shell only when file tools cannot do the job or when execution is required
- Prefer absolute **Windows-style** paths with backslashes for every external file/tool operation
- Resolve ambiguous relative paths before reading or executing anything

### Shell / PowerShell

- Always confirm the intended working tree and branch before destructive or branch-changing Git commands
- Chain related commands in a single call when they share the same context
- Always disable pagers for Git: use `git --no-pager`
- Prefer PowerShell/native commands over CMD/DOS aliases
- Reuse a named shell session for multi-step work instead of spawning ad hoc shells
- For long-running commands, use a stable `shellId`, then continue with `read_powershell`
- If a prior shell command was interrupted, inspect current state before retrying blindly
- Avoid interactive prompts when a non-interactive flag exists
- When a command depends on another repo/worktree, state or set the target path explicitly before execution

### Filesystem / File Reading

- For files inside this repository/worktree, prefer **`view`** over external filesystem tools
- For multiple known files, batch reads instead of reading one-by-one
- Before using filesystem tools on non-repo paths, verify the path is accessible and use the correct absolute path
- Do not mix slash styles in paths; normalize to `C:\...`
- If a file is tagged or already known, read that exact file directly rather than re-searching
- If a read fails, verify:
  1. the path is absolute
  2. the path is inside an allowed directory
  3. the file actually exists
  4. the tool choice is appropriate (`view` vs filesystem tool vs shell)

### MCP/Provider Validation

- When provider behavior is unclear, validate the provider directly before debugging FabriX integration
- Use Inspector or an equivalent direct MCP client to confirm:
  - transport connectivity
  - advertised tools/resources/prompts
  - input/output shape
- Do not assume FabriX-side bugs until provider-side behavior is confirmed

### Worktree Safety

- Distinguish clearly between:
  - `C:\Users\BgKing\mycode\ht_tools` -> main/local baseline
  - `C:\Users\BgKing\mycode\ht_tools_mcphost` -> MCP host worktree
- Assume ports, DB files, caches, and logs may conflict across worktrees unless checked
- Before running app servers from both trees, confirm port ownership and runtime separation
- When editing branch-specific planning/docs, ensure the command is run from the MCP host worktree

## Conversation Context Format (Chat APIs)

The `contents` array format for FabriX APIs:
```
[user1, ai1, user2, ai2, ..., currentUserInput]
```
- Last element is ALWAYS current user input
- Default history limit: `MAX_HISTORY_TURNS = 5` (10 messages)
- Backend validates based on `contents[-1]`
- **Before API send, exclude `role: 'system'` messages** (including `/memory list` output) to prevent context pollution

## Rate Limiting (FastAPI)

- Implementation: `ai_gateway/services/rate_limiter_v2.py`
- Default limits: `100 RPM`, `1,000,000 TPM`
- Limiter scope: `global_shared` (shared FabriX account protection)
- Soft/Hard control:
  - Soft throttle starts around 80% load (`soft_throttle_delay`, server-led slowdown)
  - Hard limit returns HTTP 429
- 429 handling:
  - Prioritize `Retry-After` for retry timing
  - Response includes `Retry-After` and `X-RateLimit-*` metadata headers
- Operational status endpoints:
  - `GET /chat-messages/rate-limit-status`
  - `GET /agent-messages/rate-limit-status`
- Operating assumption (Windows): single-process / single-worker baseline

## Chat Runtime

- FabriX Chat / FabriX Agent Chat streaming paths now use the real FabriX upstream only.
- Legacy test-only runtime branching has been removed from the chat routers.
- Offline chat testing should be introduced as a separate test-mode design rather than by re-adding runtime branches to production chat routes.

## Data Explorer Specifics

- Visualization: Graphic Walker (native React)
- SQL transpile: Official `gw-dsl-parser` ONLY
- Computation: DuckDB server-side mode
- SQL: SELECT-only, forbidden patterns validated
- Errors: Sanitize in production (no stack traces)
- Projection model: keep full source in `raw_main_table`, recreate `main_table` as selected-columns projection
- Cache rebuild flow: cache status -> rebuild start -> rebuild status polling
- Frontend 429 behavior: `throttledUntilRef` blocks extra calls until `Retry-After` expires
- Frontend loading split: Data Explorer shell renders first; Graphic Walker chart engine is lazy-loaded when the first dataset/preset chart is actually needed
- Initial empty-state guidance is only for first entry; dataset/preset reloads must use a dedicated dataset-loading UI instead of reusing the empty-state message

### Current limitation (Data Explorer)
- This guide keeps endpoint depth at `prefix + role`; detailed request/response field specs are intentionally excluded.

## Image Inspector Specifics

- FastAPI handles heavy processing with endpoint roles under `/image-compare` (`/process`: compare, `/preview`: crop preview)
- Concurrency control uses `asyncio.Semaphore(5)` (separate from chat global rate limiter)
- One compare call returns `file1_base64`, `file2_base64`, `overlay_base64`; mode switching is frontend-only view logic
- Frontend cache key includes pages, diff settings, CAD settings, quality settings, and crop rect

### Current limitation (Image Inspector)
- Page-count mismatch warning UI is not currently implemented; page navigation is clamped per file page range.

## Reference Documents

For detailed implementation:
- `.github/copilot-instructions.md` - Canonical development guide
- `README.md` - General overview
- `GEMINI.md` - Extended documentation
- `doc.md/` - Feature-specific docs
- `doc.md/phase1_fabrix_generic_mcp_host_plan.md` - Canonical Phase 1 MCP host migration plan
- MCP architecture docs - Official host/client/server model and protocol layering
- Official MCP SDK docs - Python SDK first for backend/client implementation guidance
- `mark3labs/mcphost` - Host registry/configuration reference
- `OpenAgentPlatform/Dive` - Host UX/reference product comparison

Last updated: 2026-04-07 (Phase 1 MCP host standards, reference hosts, skill strategy, and tool reliability rules added)
