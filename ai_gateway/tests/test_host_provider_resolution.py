import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.mcp.config import load_mcp_settings
from services.mcp.host import GenericMcpHost


class FakeProvider:
    async def call_tool_dict(self, tool_name, tool_args):
        return {"tool_name": tool_name, "tool_args": tool_args}

    async def list_category_catalog(self):
        return [{"name": "회의록"}]

    async def validate_category(self, category):
        return {"name": category}

    async def execute_manual_command(self, **kwargs):
        return {
            "success": True,
            "content": f"manual:{kwargs['action']}",
            "kwargs": kwargs,
        }


def _build_host() -> GenericMcpHost:
    settings = load_mcp_settings(
        {
            "mcp": {
                "providers": {
                    "internal_docs": {
                        "base_url": "http://127.0.0.1:8002/mcp",
                        "transport": "streamable_http",
                    },
                    "legal_cases": {
                        "base_url": "http://127.0.0.1:8003/mcp",
                        "transport": "streamable_http",
                    },
                }
            }
        }
    )
    return GenericMcpHost(settings)


def _fake_manifest(
    *, supports_rag: bool = True, manual_commands=("list", "search", "read")
):
    return SimpleNamespace(
        capability_policy=SimpleNamespace(
            supports_rag_context=supports_rag,
            supports_search=True,
            supports_document_read=True,
            supports_category_catalog=True,
            manual_commands=manual_commands,
        )
    )


def test_host_defaults_to_internal_docs_provider_when_no_provider_override_is_given():
    host = _build_host()
    observed = {}

    @asynccontextmanager
    async def fake_connect_provider(provider_id, *, settings):
        observed["provider_id"] = provider_id
        observed["settings"] = settings
        yield FakeProvider()

    with patch("services.mcp.host.connect_provider", fake_connect_provider):
        result = asyncio.run(host.list_category_catalog())

    assert observed["provider_id"] == "internal_docs"
    assert observed["settings"] is host.settings
    assert result == [{"name": "회의록"}]


def test_host_forwards_explicit_provider_override_to_registry_connection():
    host = _build_host()
    observed = {}

    @asynccontextmanager
    async def fake_connect_provider(provider_id, *, settings):
        observed["provider_id"] = provider_id
        observed["settings"] = settings
        yield FakeProvider()

    with (
        patch("services.mcp.host.connect_provider", fake_connect_provider),
        patch(
            "services.mcp.host.require_provider_manifest", return_value=_fake_manifest()
        ),
    ):
        result = asyncio.run(
            host.execute_tool_action(
                action="search_docs_rag",
                arguments={"query": "품질 관련 내용"},
                provider_id="legal_cases",
            )
        )

    assert observed["provider_id"] == "legal_cases"
    assert observed["settings"] is host.settings
    assert result == {
        "tool_name": "search_docs_rag",
        "tool_args": {"query": "품질 관련 내용"},
    }


def test_host_delegates_manual_mcp_command_to_provider_adapter():
    host = _build_host()
    observed = {}

    @asynccontextmanager
    async def fake_connect_provider(provider_id, *, settings):
        observed["provider_id"] = provider_id
        observed["settings"] = settings
        yield FakeProvider()

    with patch("services.mcp.host.connect_provider", fake_connect_provider):
        result = asyncio.run(
            host.execute_manual_command(
                action="search",
                query="품질 관련 내용",
                session_category="회의록",
                session_provider_id="internal_docs",
                rag_enabled=True,
                max_results=7,
                provider_id="internal_docs",
            )
        )

    assert observed["provider_id"] == "internal_docs"
    assert observed["settings"] is host.settings
    assert result["success"] is True
    assert result["content"] == "manual:search"
    assert result["kwargs"]["query"] == "품질 관련 내용"
    assert result["kwargs"]["session_category"] == "회의록"
    assert result["kwargs"]["session_provider_id"] == "internal_docs"
    assert result["kwargs"]["rag_enabled"] is True
    assert result["kwargs"]["max_results"] == 7


def test_host_delegates_category_validation_to_provider_adapter():
    host = _build_host()
    observed = {}

    @asynccontextmanager
    async def fake_connect_provider(provider_id, *, settings):
        observed["provider_id"] = provider_id
        observed["settings"] = settings
        yield FakeProvider()

    with patch("services.mcp.host.connect_provider", fake_connect_provider):
        result = asyncio.run(host.validate_category("회의록"))

    assert observed["provider_id"] == "internal_docs"
    assert observed["settings"] is host.settings
    assert result == {"name": "회의록"}


def test_host_rejects_rag_search_when_manifest_disables_rag_context():
    host = _build_host()

    class FakePolicy:
        supports_rag_context = False

    class FakeManifest:
        capability_policy = FakePolicy()

    async def fail_execute_tool_action(self, **kwargs):
        raise AssertionError(
            "execute_tool_action should not run when capability check fails"
        )

    with (
        patch(
            "services.mcp.host.require_provider_manifest", return_value=FakeManifest()
        ),
        patch.object(GenericMcpHost, "execute_tool_action", fail_execute_tool_action),
    ):
        try:
            asyncio.run(
                host.run_rag_search(query="위약금", provider_id="internal_docs")
            )
        except ValueError as error:
            assert (
                str(error)
                == "MCP provider does not support RAG context search: internal_docs"
            )
        else:
            raise AssertionError(
                "Expected ValueError for unsupported RAG context search"
            )


def test_host_manual_command_does_not_prevalidate_category_before_provider_call():
    host = _build_host()
    observed = {}

    @asynccontextmanager
    async def fake_connect_provider(provider_id, *, settings):
        observed["provider_id"] = provider_id
        yield FakeProvider()

    async def fail_validate_category(self, category, *, provider_id=None):
        raise AssertionError(
            "validate_category should not run before provider manual command delegation"
        )

    with (
        patch("services.mcp.host.connect_provider", fake_connect_provider),
        patch.object(GenericMcpHost, "validate_category", fail_validate_category),
    ):
        result = asyncio.run(
            host.execute_manual_command(
                action="list",
                target="회의록",
                provider_id="internal_docs",
            )
        )

    assert observed["provider_id"] == "internal_docs"
    assert result["success"] is True


def test_host_run_rag_search_balances_unscoped_results_across_categories():
    settings = load_mcp_settings(
        {
            "mcp": {
                "host": {
                    "doc_search": {
                        "max_docs": 4,
                        "snippet_chars": 1200,
                        "unscoped_fanout_enabled": True,
                        "unscoped_fanout_per_category_docs": 2,
                        "unscoped_fanout_category_limit": 0,
                    }
                },
                "providers": {
                    "internal_docs": {
                        "base_url": "http://127.0.0.1:8002/mcp",
                        "transport": "streamable_http",
                    }
                },
            }
        }
    )
    host = GenericMcpHost(settings)
    observed_categories = []

    async def fake_list_category_catalog(self, *, provider_id=None):
        return [{"name": "회의록"}, {"name": "팀주간업무"}]

    async def fake_execute_tool_action(self, *, action, arguments, provider_id=None):
        observed_categories.append(arguments.get("category"))
        category = arguments.get("category")
        if category == "회의록":
            return {
                "files": [
                    {
                        "filename": "minutes.md",
                        "snippet": "회의 안전 점검",
                        "category": category,
                    }
                ],
                "snippets": [
                    {
                        "filename": "minutes.md",
                        "snippet": "회의 안전 점검",
                        "category": category,
                        "start": 1,
                        "end": 10,
                    }
                ],
            }
        if category == "팀주간업무":
            return {
                "files": [
                    {
                        "filename": "weekly.md",
                        "snippet": "업무 안전 조치",
                        "category": category,
                    }
                ],
                "snippets": [
                    {
                        "filename": "weekly.md",
                        "snippet": "업무 안전 조치",
                        "category": category,
                        "start": 1,
                        "end": 10,
                    }
                ],
            }
        raise AssertionError(f"Unexpected category: {category}")

    with (
        patch.object(
            GenericMcpHost, "list_category_catalog", fake_list_category_catalog
        ),
        patch.object(GenericMcpHost, "execute_tool_action", fake_execute_tool_action),
        patch(
            "services.mcp.host.require_provider_manifest", return_value=_fake_manifest()
        ),
    ):
        result = asyncio.run(
            host.run_rag_search(query="안전", provider_id="internal_docs")
        )

    assert observed_categories == ["회의록", "팀주간업무"]
    assert [item["filename"] for item in result["files"]] == ["minutes.md", "weekly.md"]
    assert [item["filename"] for item in result["snippets"]] == [
        "minutes.md",
        "weekly.md",
    ]
    assert result["retrieval_meta"]["mode"] == "category_fanout"
    assert result["retrieval_meta"]["categories_queried"] == ["회의록", "팀주간업무"]


# ── full_read_mode 동적 read_doc 삽입 테스트 ──────────────────────────────────

from unittest.mock import AsyncMock, MagicMock

from services.mcp.shared_planner.models import PlannerDecision, PlannerToolPlan


def _make_search_plan(
    full_read_mode: bool = False, category: str | None = None
) -> PlannerToolPlan:
    params: dict = {"query": "표준계약서", "max_docs": 5, "snippet_chars": 1500}
    if full_read_mode:
        params["full_read_mode"] = True
    if category:
        params["category"] = category
    from services.mcp.shared_planner.models import PlannerDecisionProvenance

    return PlannerToolPlan(
        provider="internal_docs",
        action="search_docs_rag",
        params=params,
        provenance=PlannerDecisionProvenance(
            decision_source="keyword_rule",
            matched_rule="doc_search_target + search_action",
            normalized_query="표준계약서 부당특약 검토",
            provider_candidates=("internal_docs.search_docs_rag",),
            selected_provider="internal_docs",
            selected_action="search_docs_rag",
        ),
    )


def _make_issue_plan() -> PlannerToolPlan:
    from services.mcp.shared_planner.models import PlannerDecisionProvenance

    return PlannerToolPlan(
        provider="lexguard",
        action="document_issue_tool",
        params={},
        provenance=PlannerDecisionProvenance(
            decision_source="keyword_rule",
            matched_rule="document_analysis",
            normalized_query="표준계약서 부당특약 검토",
            provider_candidates=("lexguard.document_issue_tool",),
            selected_provider="lexguard",
            selected_action="document_issue_tool",
        ),
    )


def test_host_full_read_mode_inserts_read_doc_and_chains_full_content():
    """full_read_mode=True: search_docs_rag TOP1 파일명으로 read_doc 삽입, 전문이 document_issue_tool에 전달돼야 한다."""
    host = _build_host()

    search_raw = {
        "snippets": [
            {
                "filename": "표준계약서.md",
                "snippet": "계약서 내용 일부",
                "start": 0,
                "end": 100,
            }
        ],
        "files": [{"filename": "표준계약서.md"}],
    }
    read_raw = {"content": "전체 계약서 전문 내용입니다.", "filename": "표준계약서.md"}
    issue_raw = {"issues": [{"type": "부당특약", "description": "불공정 조항 발견"}]}

    call_log: list[dict] = []

    async def fake_run_rag_search(
        self,
        *,
        query,
        category=None,
        filename_filter=None,
        max_docs=5,
        snippet_chars=1500,
        provider_id=None,
    ):
        call_log.append({"step": "search_docs_rag", "category": category})
        return {"raw_result": search_raw, "system_prompt": None}

    async def fake_execute_tool_action(self, *, action, arguments, provider_id=None):
        call_log.append({"step": action, "arguments": dict(arguments)})
        if action == "read_doc":
            return read_raw
        if action == "document_issue_tool":
            return issue_raw
        raise AssertionError(f"Unexpected action: {action}")

    fake_decision = PlannerDecision(
        route="catalog_match",
        clean_query="표준계약서 부당특약 검토",
        plans=(_make_search_plan(full_read_mode=True), _make_issue_plan()),
    )

    mock_planner = MagicMock()
    mock_planner.plan = MagicMock(return_value=fake_decision)
    host._planner = mock_planner

    with (
        patch.object(GenericMcpHost, "validate_planner_decision", new=AsyncMock()),
        patch.object(GenericMcpHost, "run_rag_search", fake_run_rag_search),
        patch.object(GenericMcpHost, "execute_tool_action", fake_execute_tool_action),
        patch(
            "services.mcp.host.require_provider_manifest", return_value=_fake_manifest()
        ),
    ):
        asyncio.run(host.build_chat_resolution(user_text="표준계약서 부당특약 검토"))

    steps = [c["step"] for c in call_log]
    assert steps == ["search_docs_rag", "read_doc", "document_issue_tool"], (
        f"예상: [search_docs_rag, read_doc, document_issue_tool], 실제: {steps}"
    )

    read_call = next(c for c in call_log if c["step"] == "read_doc")
    assert read_call["arguments"]["filename"] == "표준계약서.md"

    issue_call = next(c for c in call_log if c["step"] == "document_issue_tool")
    assert (
        issue_call["arguments"].get("document_text") == "전체 계약서 전문 내용입니다."
    )


def test_host_full_read_mode_fallback_when_filename_not_available():
    """full_read_mode=True이지만 파일명 없으면 read_doc 삽입 안 하고 snippet 체이닝으로 fallback해야 한다."""
    host = _build_host()

    search_raw_no_filename = {
        "snippets": [{"snippet": "계약서 내용 일부"}],  # filename 없음
        "files": [],
    }
    issue_raw = {"issues": []}

    call_log: list[dict] = []

    async def fake_run_rag_search(self, **kwargs):
        call_log.append({"step": "search_docs_rag"})
        return {"raw_result": search_raw_no_filename, "system_prompt": None}

    async def fake_execute_tool_action(self, *, action, arguments, provider_id=None):
        call_log.append({"step": action, "arguments": dict(arguments)})
        if action == "document_issue_tool":
            return issue_raw
        raise AssertionError(f"Unexpected action: {action}")

    fake_decision = PlannerDecision(
        route="catalog_match",
        clean_query="표준계약서 부당특약 검토",
        plans=(_make_search_plan(full_read_mode=True), _make_issue_plan()),
    )

    mock_planner = MagicMock()
    mock_planner.plan = MagicMock(return_value=fake_decision)
    host._planner = mock_planner

    with (
        patch.object(GenericMcpHost, "validate_planner_decision", new=AsyncMock()),
        patch.object(GenericMcpHost, "run_rag_search", fake_run_rag_search),
        patch.object(GenericMcpHost, "execute_tool_action", fake_execute_tool_action),
        patch(
            "services.mcp.host.require_provider_manifest", return_value=_fake_manifest()
        ),
    ):
        # snippet fallback 시 document_text가 snippet 텍스트로 채워지므로 ValueError 아님
        asyncio.run(host.build_chat_resolution(user_text="표준계약서 부당특약 검토"))

    steps = [c["step"] for c in call_log]
    assert "read_doc" not in steps, "파일명 없으면 read_doc 삽입되지 않아야 합니다"
    assert "document_issue_tool" in steps


def test_host_standalone_document_issue_tool_executes_without_document_text():
    """체이닝 없이 단독 document_issue_tool 실행 시 document_text 없이 그대로 실행되어야 한다.

    document_text 유무에 따른 중단은 host/executor 책임이 아니라 lexguard 서버 책임이다.
    """
    host = _build_host()

    fake_decision = PlannerDecision(
        route="catalog_match",
        clean_query="표준계약서 부당특약 검토",
        plans=(_make_issue_plan(),),  # 단독 — 선행 retrieval 없음
    )

    mock_planner = MagicMock()
    mock_planner.plan = MagicMock(return_value=fake_decision)
    host._planner = mock_planner

    call_log: list[dict] = []

    async def fake_execute_tool_action(self, *, action, arguments, provider_id=None):
        call_log.append({"step": action, "arguments": dict(arguments)})
        return {"issues": []}

    with (
        patch.object(GenericMcpHost, "validate_planner_decision", new=AsyncMock()),
        patch.object(GenericMcpHost, "execute_tool_action", fake_execute_tool_action),
        patch(
            "services.mcp.host.require_provider_manifest", return_value=_fake_manifest()
        ),
    ):
        asyncio.run(host.build_chat_resolution(user_text="표준계약서 부당특약 검토"))

    steps = [c["step"] for c in call_log]
    assert "document_issue_tool" in steps, (
        "단독 document_issue_tool도 정상 실행되어야 합니다"
    )
    issue_call = next(c for c in call_log if c["step"] == "document_issue_tool")
    assert "document_text" not in issue_call["arguments"], (
        "선행 retrieval 없으면 document_text가 params에 없어야 합니다"
    )


def test_host_read_doc_to_document_issue_tool_chaining_regression():
    """기존 경로: read_doc → document_issue_tool 체이닝이 정상 동작해야 한다 (회귀 테스트)."""
    host = _build_host()

    from services.mcp.shared_planner.models import PlannerDecisionProvenance

    read_plan = PlannerToolPlan(
        provider="internal_docs",
        action="read_doc",
        params={"filename": "표준계약서.md"},
        provenance=PlannerDecisionProvenance(
            decision_source="keyword_rule",
            matched_rule="doc_read_full",
            normalized_query="표준계약서.md 읽어줘",
            provider_candidates=("internal_docs.read_doc",),
            selected_provider="internal_docs",
            selected_action="read_doc",
        ),
    )

    read_raw = {"content": "전체 계약서 전문", "filename": "표준계약서.md"}
    issue_raw = {"issues": []}
    call_log: list[dict] = []

    async def fake_execute_tool_action(self, *, action, arguments, provider_id=None):
        call_log.append({"step": action, "arguments": dict(arguments)})
        if action == "read_doc":
            return read_raw
        if action == "document_issue_tool":
            return issue_raw
        raise AssertionError(f"Unexpected action: {action}")

    fake_decision = PlannerDecision(
        route="catalog_match",
        clean_query="표준계약서.md 부당특약 검토",
        plans=(read_plan, _make_issue_plan()),
    )

    mock_planner = MagicMock()
    mock_planner.plan = MagicMock(return_value=fake_decision)
    host._planner = mock_planner

    with (
        patch.object(GenericMcpHost, "validate_planner_decision", new=AsyncMock()),
        patch.object(GenericMcpHost, "execute_tool_action", fake_execute_tool_action),
        patch(
            "services.mcp.host.require_provider_manifest", return_value=_fake_manifest()
        ),
    ):
        asyncio.run(host.build_chat_resolution(user_text="표준계약서.md 부당특약 검토"))

    issue_call = next(c for c in call_log if c["step"] == "document_issue_tool")
    assert issue_call["arguments"].get("document_text") == "전체 계약서 전문"


def test_host_read_doc_result_key_normalization():
    """fastmcp structured_content로 {"result": "..."} 형태로 반환될 때도 체이닝이 정상 동작해야 한다.

    실제 fastmcp 서버는 read_doc 응답을 structured_content {"result": "..."} 형태로 반환한다.
    이 경우 normalize_context_result가 "result" → "content" 로 정규화해야 체이닝이 성공한다.
    """
    host = _build_host()

    from services.mcp.shared_planner.models import PlannerDecisionProvenance

    read_plan = PlannerToolPlan(
        provider="internal_docs",
        action="read_doc",
        params={"filename": "표준계약서.md"},
        provenance=PlannerDecisionProvenance(
            decision_source="keyword_rule",
            matched_rule="doc_read_full",
            normalized_query="표준계약서.md 읽어줘",
            provider_candidates=("internal_docs.read_doc",),
            selected_provider="internal_docs",
            selected_action="read_doc",
        ),
    )

    # fastmcp server returns structured_content {"result": "..."} — not "content"
    read_raw_result_key = {"result": "전체 계약서 전문 (result 키)"}
    issue_raw = {"issues": []}
    call_log: list[dict] = []

    async def fake_execute_tool_action(self, *, action, arguments, provider_id=None):
        call_log.append({"step": action, "arguments": dict(arguments)})
        if action == "read_doc":
            return read_raw_result_key
        if action == "document_issue_tool":
            return issue_raw
        raise AssertionError(f"Unexpected action: {action}")

    fake_decision = PlannerDecision(
        route="catalog_match",
        clean_query="표준계약서.md 부당특약 검토",
        plans=(read_plan, _make_issue_plan()),
    )

    mock_planner = MagicMock()
    mock_planner.plan = MagicMock(return_value=fake_decision)
    host._planner = mock_planner

    with (
        patch.object(GenericMcpHost, "validate_planner_decision", new=AsyncMock()),
        patch.object(GenericMcpHost, "execute_tool_action", fake_execute_tool_action),
        patch(
            "services.mcp.host.require_provider_manifest", return_value=_fake_manifest()
        ),
    ):
        asyncio.run(host.build_chat_resolution(user_text="표준계약서.md 부당특약 검토"))

    issue_call = next(c for c in call_log if c["step"] == "document_issue_tool")
    assert (
        issue_call["arguments"].get("document_text") == "전체 계약서 전문 (result 키)"
    ), (
        "read_doc의 'result' 키가 document_text로 체이닝되지 않음 — "
        f"실제 arguments: {issue_call['arguments']}"
    )
