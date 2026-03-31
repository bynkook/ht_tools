"""
FastAPI Router: MCP Command
/mcp 슬래시 커맨드 처리 — FastMCP Doc Server 연동
"""
import json
import logging
import toml
from pathlib import Path
from typing import Any
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from fastmcp import Client

from ..dependencies import verify_token

router = APIRouter()
logger = logging.getLogger(__name__)

# ht_tools/ 루트 기준: routers/ → ai_gateway/ → ht_tools/
BASE_DIR = Path(__file__).resolve().parent.parent.parent
SECRETS_PATH = BASE_DIR / "secrets.toml"


def get_doc_server_url() -> str:
    with open(SECRETS_PATH, "r", encoding="utf-8") as f:
        secrets = toml.load(f)
    return secrets.get("doc_server", {}).get("base_url", "http://127.0.0.1:8002/mcp")


class McpCommandRequest(BaseModel):
    action: str                       # "search" | "read" | "list"
    query: str | None = None          # search 시 검색어
    category: str | None = None       # search/list 시 카테고리 필터
    filename: str | None = None       # read 시 파일 경로
    max_results: int = 5


@router.post("", dependencies=[Depends(verify_token)])
async def mcp_command(body: McpCommandRequest):
    """
    [POST] /mcp-command

    /mcp 슬래시 커맨드 처리 엔드포인트.
    FastMCP Doc Server(포트 8002)에 연결하여 문서를 검색·조회한다.

    Actions:
    - search:     search_docs(query, category) 도구 호출 — 문서 검색
    - read:       read_doc(filename) 도구 호출 — 문서 전체 내용 반환
    - list:       list_categories_detail() 또는 list_docs_detail(category) 도구 호출
                  카테고리 목록(문서 수 포함) 또는 파일 목록(최종 수정일 포함) 마크다운 표 반환

    Returns:
        {"success": True, "content": "..."} on success
        {"success": False, "content": "오류 메시지"} on Doc Server connection error
    """
    doc_server_url = get_doc_server_url()
    try:
        async with Client(doc_server_url) as client:

            if body.action == "search":
                if not body.query:
                    raise HTTPException(status_code=400, detail="검색어(query)가 필요합니다.")
                tool_args: dict[str, Any] = {"query": body.query, "max_results": body.max_results}
                if body.category:
                    tool_args["category"] = body.category
                result = await client.call_tool("search_docs", tool_args)

            elif body.action == "read":
                if not body.filename:
                    raise HTTPException(status_code=400, detail="파일 경로(filename)가 필요합니다.")
                tool_args: dict[str, Any] = {"filename": body.filename}
                if body.category:
                    tool_args["category"] = body.category
                result = await client.call_tool("read_doc", tool_args)

            elif body.action == "list":
                if body.category:
                    result = await client.call_tool("list_docs_detail", {"category": body.category})
                    data = result.data if result.data is not None else None
                    if data is None:
                        raw = "\n".join(c.text for c in result.content if hasattr(c, "text"))
                        data = json.loads(raw) if raw else {}
                    error = data.get("error")
                    if error:
                        content = f"⚠️ {error}"
                    else:
                        files = data.get("files", [])
                        if not files:
                            content = f"**'{body.category}'** 카테고리에 문서가 없습니다."
                        else:
                            lines = [
                                f"## 📁 `{body.category}` 문서 목록 ({len(files)}개)",
                                "",
                                "| 파일명 | 최종 수정일 |",
                                "|:---|:---|",
                            ]
                            for f in files:
                                lines.append(f"| `{f['filename']}` | {f['last_modified']} |")
                            content = "\n".join(lines)
                else:
                    result = await client.call_tool("list_categories_detail", {})
                    data = result.data if result.data is not None else None
                    if data is None:
                        raw = "\n".join(c.text for c in result.content if hasattr(c, "text"))
                        data = json.loads(raw) if raw else {}
                    categories = data.get("categories", [])
                    if not categories:
                        content = "등록된 카테고리가 없습니다."
                    else:
                        total_docs = sum(c["doc_count"] for c in categories)
                        lines = [
                            f"## 📚 문서 카테고리 목록  ({len(categories)}개 카테고리 · 총 {total_docs}개 문서)",
                            "",
                            "| 카테고리 | 문서 수 |",
                            "|:---|---:|",
                        ]
                        for cat in categories:
                            lines.append(f"| {cat['name']} | {cat['doc_count']} |")
                        content = "\n".join(lines)
                return {"success": True, "content": content}

            else:
                raise HTTPException(status_code=400, detail=f"알 수 없는 action: {body.action}")

        # call_tool() → CallToolResult
        # .data : 원시 Python 값 (str 반환 도구면 str)
        # .content : list[ContentBlock] (fallback)
        if result.data is not None:
            content = str(result.data)
        else:
            content = "\n".join(
                c.text for c in result.content if hasattr(c, "text")
            )
        return {"success": True, "content": content}

    except HTTPException:
        raise
    except Exception as e:
        logger.warning("FastMCP Doc Server 오류: %s", e)
        return {
            "success": False,
            "content": (
                f"⚠️ Doc Server 연결 실패: {e}\n"
                "서버가 실행 중인지 확인하세요 (fastmcp/run_server.bat)"
            ),
        }


class RagSearchRequest(BaseModel):
    query: str
    category: str | None = None
    filename_filter: str | None = None  # @<파일명> 문법용: 특정 파일로 검색 제한
    max_docs: int = 10
    snippet_chars: int = 1500


def _classify_query_shape(query: str) -> dict:
    """질문 형태를 약하게 추정해 budget에 작은 bias만 준다.

    Note: fastmcp/tools.py의 _classify_query_shape와 동일한 로직을 유지한다.
    두 프로젝트가 독립 레포이므로 공유 모듈 불가 — 변경 시 양쪽 동시 적용 필요.
    """
    query_lower = query.lower()
    raw_tokens = [t for t in query.split() if t.strip()]
    procedural_keywords = ("절차", "단계", "방법", "순서", "비교", "차이", "예외", "주의")
    expand_hint = any(keyword in query_lower for keyword in procedural_keywords)
    compact_hint = len(raw_tokens) <= 2 and len(query.strip()) <= 20 and not expand_hint
    return {"expand_hint": expand_hint, "compact_hint": compact_hint}


def _decide_prompt_budget(query: str, snippets: list[dict]) -> dict:
    """질문 길이와 coverage-first 원칙으로 prompt budget 결정."""
    shape = _classify_query_shape(query)
    unique_docs = len({snippet.get("filename", "") for snippet in snippets if snippet.get("filename")})

    if shape["compact_hint"]:
        max_total = 6
        max_total_chars = 6000
    elif shape["expand_hint"]:
        max_total = 12
        max_total_chars = 12000
    else:
        max_total = 9
        max_total_chars = 9000

    min_docs_covered = min(unique_docs, max(3, min(6, max_total)))
    return {
        "max_per_doc": 3,
        "max_total": max_total,
        "max_total_chars": max_total_chars,
        "min_docs_covered": min_docs_covered,
    }


def _select_prompt_snippets(
    snippets: list[dict],
    max_per_doc: int = 2,
    max_total: int = 6,
    max_total_chars: int = 4500,
    min_docs_covered: int = 4,
) -> list[dict]:
    """Prompt 조립용 coverage-first + budget 적용."""
    selected: list[dict] = []
    doc_counts: dict[str, int] = {}
    total_chars = 0
    covered_docs: set[str] = set()

    # 1차: 상위 문서 coverage 확보
    for snippet in snippets:
        if len(selected) >= max_total or len(covered_docs) >= min_docs_covered:
            break
        filename = snippet.get("filename", "")
        if not filename or filename in covered_docs:
            continue
        snippet_text = str(snippet.get("snippet", "")).strip()
        if not snippet_text:
            continue
        next_total = total_chars + len(snippet_text)
        if selected and next_total > max_total_chars:
            continue

        selected.append(snippet)
        doc_counts[filename] = 1
        covered_docs.add(filename)
        total_chars = next_total

    # 2차: 남는 budget으로 추가 snippet 채우기
    for snippet in snippets:
        if len(selected) >= max_total:  # 1차에서 이미 채워진 경우 방어
            break
        filename = snippet.get("filename", "")
        if not filename or doc_counts.get(filename, 0) >= max_per_doc:
            continue
        if any(
            selected_item.get("filename") == filename
            and selected_item.get("start") == snippet.get("start")
            and selected_item.get("end") == snippet.get("end")
            for selected_item in selected
        ):
            continue

        snippet_text = str(snippet.get("snippet", "")).strip()
        if not snippet_text:
            continue

        next_total = total_chars + len(snippet_text)
        if selected and next_total > max_total_chars:
            continue

        selected.append(snippet)
        doc_counts[filename] = doc_counts.get(filename, 0) + 1
        total_chars = next_total

        if len(selected) >= max_total:
            break

    return selected


@router.post("/rag-search", dependencies=[Depends(verify_token)])
async def rag_search(body: RagSearchRequest):
    """
    [POST] /mcp-command/rag-search

    RAG 파이프라인 전용 검색 엔드포인트.
    FastMCP search_docs_rag 도구를 호출하여 BM25 관련성 랭킹 + 최신 우선으로
    문서 스니펫을 검색하고, LLM에 주입할 systemPrompt를 조립하여 반환한다.

        Returns:
        {
          "success": bool,
          "files": [{ "filename": str, "snippet": str, "bm25_score": float }],
          "snippets": [{ "filename": str, "snippet": str, "snippet_score": float }],
          "query": str,
          "category": str | None,
          "system_prompt": str | None  # LLM systemPrompt로 바로 주입 가능
        }
    """
    doc_server_url = get_doc_server_url()
    try:
        tool_args: dict[str, Any] = {
            "query": body.query,
            "category": body.category,
            "max_docs": body.max_docs,
            "snippet_chars": body.snippet_chars,
        }
        if body.filename_filter:
            tool_args["filename_filter"] = body.filename_filter

        async with Client(doc_server_url) as client:
            result = await client.call_tool("search_docs_rag", tool_args)

        # search_docs_rag가 -> dict를 반환하므로 result.data가 이미 dict
        # (FastMCP 공식 권고: dict 반환 시 json.dumps/loads 불필요)
        data = result.data
        if data is None:
            raw = "\n".join(c.text for c in result.content if hasattr(c, "text"))
            data = json.loads(raw) if raw else {}

        # filename_filter 모드에서 파일 미발견 시 404
        if data.get("error"):
            raise HTTPException(status_code=404, detail=data["error"])

        files = data.get("files", [])
        snippets = data.get("snippets", [])

        if not files and not snippets:
            return {
                "success": True,
                "files": [],
                "snippets": [],
                "query": body.query,
                "category": body.category,
                "system_prompt": None,
            }

        category_label = f" ({body.category})" if body.category else " (전체)"
        if snippets:
            if body.filename_filter:
                # 단일 파일 @mention 모드: 더 많은 스니펫 허용 (문서 커버리지 불필요)
                budget = {
                    "max_per_doc": 12,
                    "max_total": 12,
                    "max_total_chars": 14000,
                    "min_docs_covered": 1,
                }
            else:
                budget = _decide_prompt_budget(body.query, snippets)
            selected_snippets = _select_prompt_snippets(snippets, **budget)
            doc_blocks = "\n\n---\n\n".join(
                f"📄 파일: {s['filename']}\n🔹 발췌 구간: {s.get('start', '-')}-{s.get('end', '-')}\n\n{s['snippet']}"
                for s in selected_snippets
            )
        else:
            selected_snippets = []
            doc_blocks = "\n\n---\n\n".join(
                f"📄 파일: {f['filename']}\n\n{f['snippet']}"
                for f in files[:4]
            )
        system_prompt = (
            f"당신은 사내 문서 기반 질문 답변 어시스턴트입니다.\n"
            f"아래 참고 문서{category_label}를 바탕으로 사용자의 질문에 답하세요.\n"
            f"참고 문서에 없는 내용은 '제공된 문서에서 찾을 수 없습니다'라고 솔직하게 답하세요.\n\n"
            f"=== 참고 문서 ===\n\n{doc_blocks}\n\n=================="
        )

        # Context budget 로깅: 실제 비용·품질 저하 원인 측정용
        prompt_chars = len(system_prompt)
        prompt_tokens_est = prompt_chars // 2  # 한국어 기준 대략 1토큰 ≈ 2자
        logger.info(
            "RAG prompt budget — query=%r category=%s snippets=%d chars=%d tokens≈%d",
            body.query,
            body.category or "all",
            len(selected_snippets) if snippets else len(files[:4]),
            prompt_chars,
            prompt_tokens_est,
        )

        return {
            "success": True,
            "files": files,
            "snippets": selected_snippets if snippets else [],
            "query": body.query,
            "category": body.category,
            "system_prompt": system_prompt,
        }

    except Exception as e:
        logger.warning("RAG 검색 오류: %s", e)
        return {
            "success": False,
            "files": [],
            "snippets": [],
            "query": body.query,
            "category": body.category,
            "system_prompt": None,
        }
