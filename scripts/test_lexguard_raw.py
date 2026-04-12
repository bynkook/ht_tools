"""
lexguard-mcp 전체 tool 응답 구조 검증 스크립트.

목적:
  - 모든 tool의 성공/실패 케이스별 실제 raw_result 구조 확인
  - build_legal_context_system_prompt()의 transport 실패 판별 조건 확정
  - FabriX의 tool_result_to_dict()가 받는 structuredContent 구조를 실물 검증

실행 (로컬 서버):
  powershell -Command "& '.venv\\Scripts\\python.exe' scripts/test_lexguard_raw.py"

실행 (원격 서버):
  powershell -Command "$env:LEXGUARD_URL='https://lexguard-mcp.onrender.com/mcp'; & '.venv\\Scripts\\python.exe' scripts/test_lexguard_raw.py"

결과 파일로 저장:
  powershell -Command "& '.venv\\Scripts\\python.exe' scripts/test_lexguard_raw.py 2>&1 | Tee-Object scripts/test_lexguard_results.txt"

환경변수:
  LEXGUARD_URL  - MCP 엔드포인트 (기본: http://127.0.0.1:9099/mcp)
  TIMEOUT       - 요청 타임아웃 초 (기본: 30)
"""

import asyncio
import io
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any

import httpx

# Windows cp949 터미널에서 유니코드 출력이 깨지는 것 방지
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

LEXGUARD_URL = os.environ.get("LEXGUARD_URL", "http://127.0.0.1:9099/mcp")
TIMEOUT = float(os.environ.get("TIMEOUT", "30"))


# ─────────────────────────────────────────────────────────────
# 테스트 케이스 정의
# ─────────────────────────────────────────────────────────────


@dataclass
class Case:
    label: str
    tool: str
    args: dict
    expect_success: bool  # True=정상 응답 기대, False=실패 응답 기대


CASES: list[Case] = [
    # ── health ──────────────────────────────────────────────────────────────
    Case(
        label="health / 서버 상태 확인",
        tool="health",
        args={},
        expect_success=True,
    ),
    # ── legal_qa_tool ────────────────────────────────────────────────────────
    Case(
        label="legal_qa_tool / 정상: 연장근로 한도 질문",
        tool="legal_qa_tool",
        args={"query": "연장근로 한도가 얼마나 되나요?", "max_results_per_type": 2},
        expect_success=True,
    ),
    Case(
        label="legal_qa_tool / 실패 유도: 검색 결과 0건 (무의미 질문)",
        tool="legal_qa_tool",
        args={"query": "xyzqwerty_절대없는키워드_99999", "max_results_per_type": 1},
        expect_success=False,
    ),
    # ── law_article_tool ─────────────────────────────────────────────────────
    Case(
        label="law_article_tool / 정상: 근로기준법 제50조",
        tool="law_article_tool",
        args={"law_name": "근로기준법", "article_number": "50"},
        expect_success=True,
    ),
    Case(
        label="law_article_tool / 정상: 법령명만 (조문번호 생략 → 개요 반환)",
        tool="law_article_tool",
        args={"law_name": "민법"},
        expect_success=True,
    ),
    Case(
        label="law_article_tool / 실패 유도: 존재하지 않는 법령명",
        tool="law_article_tool",
        args={"law_name": "가나다라마바사법_절대없음_99999"},
        expect_success=False,
    ),
    # ── law_comparison_tool ──────────────────────────────────────────────────
    Case(
        label="law_comparison_tool / 정상: 형법 신구법 비교",
        tool="law_comparison_tool",
        args={"law_name": "형법", "compare_type": "신구법"},
        expect_success=True,
    ),
    Case(
        label="law_comparison_tool / 실패 유도: 존재하지 않는 법령 비교",
        tool="law_comparison_tool",
        args={"law_name": "가나다법_절대없음_99999", "compare_type": "신구법"},
        expect_success=False,
    ),
    # ── precedent_lookup_tool ────────────────────────────────────────────────
    Case(
        label="precedent_lookup_tool / 정상: 키워드 검색 (부당해고)",
        tool="precedent_lookup_tool",
        args={"keyword": "부당해고", "per_page": 3},
        expect_success=True,
    ),
    Case(
        label="precedent_lookup_tool / 정상: 사건번호 직접 검색",
        tool="precedent_lookup_tool",
        args={"case_number": "2020다200614"},
        expect_success=True,
    ),
    Case(
        label="precedent_lookup_tool / 실패 유도: 검색 결과 없음",
        tool="precedent_lookup_tool",
        args={"keyword": "xyzqwerty_절대없는판례키워드_99999"},
        expect_success=False,
    ),
    # ── interpretation_tool ──────────────────────────────────────────────────
    Case(
        label="interpretation_tool / 정상: 근로자성 법령해석",
        tool="interpretation_tool",
        args={"query": "근로자성 판단 기준", "per_page": 3},
        expect_success=True,
    ),
    Case(
        label="interpretation_tool / 실패 유도: 검색 결과 없음",
        tool="interpretation_tool",
        args={"query": "xyzqwerty_절대없는해석_99999"},
        expect_success=False,
    ),
    # ── administrative_appeal_tool ───────────────────────────────────────────
    Case(
        label="administrative_appeal_tool / 정상: 부당해고 행정심판",
        tool="administrative_appeal_tool",
        args={"query": "부당해고 행정심판", "per_page": 3},
        expect_success=True,
    ),
    Case(
        label="administrative_appeal_tool / 실패 유도: 검색 결과 없음",
        tool="administrative_appeal_tool",
        args={"query": "xyzqwerty_절대없는행정심판_99999"},
        expect_success=False,
    ),
    # ── constitutional_decision_tool ─────────────────────────────────────────
    Case(
        label="constitutional_decision_tool / 정상: 표현의 자유 헌재결정",
        tool="constitutional_decision_tool",
        args={"query": "표현의 자유", "per_page": 3},
        expect_success=True,
    ),
    Case(
        label="constitutional_decision_tool / 실패 유도: 검색 결과 없음",
        tool="constitutional_decision_tool",
        args={"query": "xyzqwerty_절대없는헌재결정_99999"},
        expect_success=False,
    ),
    # ── committee_decision_tool ──────────────────────────────────────────────
    Case(
        label="committee_decision_tool / 정상: 개인정보보호위원회 결정",
        tool="committee_decision_tool",
        args={
            "committee_type": "개인정보보호위원회",
            "query": "개인정보 유출",
            "per_page": 3,
        },
        expect_success=True,
    ),
    Case(
        label="committee_decision_tool / 실패 유도: 잘못된 committee_type",
        tool="committee_decision_tool",
        args={"committee_type": "존재하지않는위원회_99999", "query": "테스트"},
        expect_success=False,
    ),
    # ── special_administrative_appeal_tool ───────────────────────────────────
    Case(
        label="special_administrative_appeal_tool / 정상: 조세심판원",
        tool="special_administrative_appeal_tool",
        args={"tribunal_type": "조세심판원", "query": "부가가치세", "per_page": 3},
        expect_success=True,
    ),
    Case(
        label="special_administrative_appeal_tool / 실패 유도: 잘못된 tribunal_type",
        tool="special_administrative_appeal_tool",
        args={"tribunal_type": "존재하지않는심판원_99999", "query": "테스트"},
        expect_success=False,
    ),
    # ── local_ordinance_tool ─────────────────────────────────────────────────
    Case(
        label="local_ordinance_tool / 정상: 서울시 조례 검색",
        tool="local_ordinance_tool",
        args={"query": "주거환경", "local_government": "서울특별시", "per_page": 3},
        expect_success=True,
    ),
    Case(
        label="local_ordinance_tool / 실패 유도: 검색 결과 없음",
        tool="local_ordinance_tool",
        args={"query": "xyzqwerty_절대없는조례_99999"},
        expect_success=False,
    ),
    # ── administrative_rule_tool ─────────────────────────────────────────────
    Case(
        label="administrative_rule_tool / 정상: 고용노동부 행정규칙",
        tool="administrative_rule_tool",
        args={"query": "근로시간", "agency": "고용노동부", "per_page": 3},
        expect_success=True,
    ),
    Case(
        label="administrative_rule_tool / 실패 유도: 검색 결과 없음",
        tool="administrative_rule_tool",
        args={"query": "xyzqwerty_절대없는행정규칙_99999"},
        expect_success=False,
    ),
    # ── document_issue_tool ──────────────────────────────────────────────────
    Case(
        label="document_issue_tool / 정상: 프리랜서 계약서 분석",
        tool="document_issue_tool",
        args={
            "document_text": (
                "제1조 (계약의 목적) 본 계약은 갑(위탁자)과 을(수탁자) 간의 "
                "소프트웨어 개발 용역 계약이다.\n"
                "제2조 (업무 내용) 을은 갑의 지시에 따라 매일 오전 9시부터 오후 6시까지 "
                "갑의 사무실에 출근하여 업무를 수행한다.\n"
                "제3조 (보수) 갑은 을에게 월 300만원을 지급한다. 4대보험은 적용하지 않는다.\n"
                "제4조 (계약 해지) 갑은 언제든지 계약을 해지할 수 있다."
            ),
            "auto_search": True,
            "max_clauses": 2,
            "max_results_per_type": 2,
        },
        expect_success=True,
    ),
    Case(
        label="document_issue_tool / 실패 유도: 내용 없는 문서 (auto_search=False)",
        tool="document_issue_tool",
        args={"document_text": ".", "auto_search": False, "max_clauses": 1},
        expect_success=False,
    ),
]


# ─────────────────────────────────────────────────────────────
# MCP 통신 헬퍼
# ─────────────────────────────────────────────────────────────


async def call_mcp_tool(
    client: httpx.AsyncClient,
    tool_name: str,
    arguments: dict,
) -> dict:
    """MCP tools/call → JSON-RPC 응답 dict 반환 (SSE / plain JSON 모두 처리)."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    resp = await client.post(LEXGUARD_URL, json=payload, headers=headers)
    resp.raise_for_status()

    content_type = resp.headers.get("content-type", "")
    if "text/event-stream" in content_type:
        result_data = None
        for line in resp.text.splitlines():
            if line.startswith("data:"):
                raw = line[5:].strip()
                if raw:
                    try:
                        result_data = json.loads(raw)
                    except json.JSONDecodeError:
                        pass
        return result_data or {"_parse_error": "no data line", "raw": resp.text[:300]}
    return resp.json()


def extract_raw_result(mcp_response: dict) -> dict:
    """
    FabriX tool_result_to_dict() 동일 우선순위로 raw_result 추출:
      1. structuredContent
      2. content[*].text 합산 후 JSON 파싱
      3. {"raw_text": ...}
    """
    result = mcp_response.get("result", {})
    if "structuredContent" in result:
        return result["structuredContent"]
    blocks = result.get("content", [])
    texts = [b.get("text", "") for b in blocks if isinstance(b, dict)]
    combined = "\n".join(t for t in texts if t)
    if combined:
        try:
            return json.loads(combined)
        except json.JSONDecodeError:
            pass
        return {"raw_text": combined[:500]}
    return {}


# ─────────────────────────────────────────────────────────────
# 출력 헬퍼
# ─────────────────────────────────────────────────────────────

SEP = "-" * 72
SEP2 = "=" * 72


def h1(text: str) -> None:
    print(f"\n{SEP2}\n  {text}\n{SEP2}")


def h2(text: str) -> None:
    print(f"\n{SEP}\n  {text}\n{SEP}")


def info(key: str, val: Any) -> None:
    print(f"  {key:<28} = {val!r}")


def dump_json(data: dict, limit: int = 3000) -> None:
    s = json.dumps(data, ensure_ascii=False, indent=2)
    if len(s) > limit:
        print(s[:limit])
        print(f"  ... (총 {len(s)} chars, truncated)")
    else:
        print(s)


def analyze(raw: dict, is_error_mcp: bool) -> None:
    """failure 판별에 필요한 핵심 필드 요약."""
    print()
    print("  [핵심 필드 분석]")
    info("  isError (MCP 레벨)", is_error_mcp)
    info("  success", raw.get("success"))
    info("  success_transport", raw.get("success_transport"))
    info("  success_search", raw.get("success_search"))
    info("  has_legal_basis", raw.get("has_legal_basis"))
    info("  missing_reason", raw.get("missing_reason"))
    info("  error", raw.get("error"))
    info("  error_code", raw.get("error_code"))
    info("  _meta.response_type", (raw.get("_meta") or {}).get("response_type"))
    print(f"  {'top-level keys':<28} = {list(raw.keys())}")
    results_sub = raw.get("results")
    if isinstance(results_sub, dict):
        print(f"  {'results 하위 keys':<28} = {list(results_sub.keys())}")


# ─────────────────────────────────────────────────────────────
# 실행
# ─────────────────────────────────────────────────────────────


@dataclass
class Summary:
    total: int = 0
    received: int = 0
    errors: list[str] = field(default_factory=list)


async def run_case(client: httpx.AsyncClient, case: Case, summary: Summary) -> None:
    expect_tag = "SUCCESS 기대" if case.expect_success else "FAILURE 유도"
    h2(f"[{expect_tag}] {case.label}")
    print(f"  tool : {case.tool}")
    print(f"  args : {json.dumps(case.args, ensure_ascii=False)}")

    summary.total += 1
    try:
        mcp_resp = await call_mcp_tool(client, case.tool, case.args)
        result_block = mcp_resp.get("result", {})
        is_error_mcp = result_block.get("isError", False)
        raw = extract_raw_result(mcp_resp)
        analyze(raw, is_error_mcp)
        print("\n  [raw_result 전체]")
        dump_json(raw)
        summary.received += 1
    except httpx.TimeoutException:
        msg = f"TIMEOUT ({TIMEOUT}s) — {case.label}"
        print(f"\n  TIMEOUT: {msg}")
        summary.errors.append(msg)
    except httpx.ConnectError as e:
        msg = f"CONNECT ERROR: {e}"
        print(f"\n  {msg}")
        summary.errors.append(f"{msg} — {case.label}")
    except httpx.HTTPStatusError as e:
        msg = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
        print(f"\n  {msg}")
        summary.errors.append(f"{msg} — {case.label}")
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        print(f"\n  {msg}")
        summary.errors.append(f"{msg} — {case.label}")


async def run_all() -> None:
    h1("lexguard-mcp 전체 tool 응답 구조 검증")
    print(f"  endpoint : {LEXGUARD_URL}")
    print(f"  timeout  : {TIMEOUT}s")
    print(f"  cases    : {len(CASES)}")

    summary = Summary()
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for case in CASES:
            await run_case(client, case, summary)

    h1("결과 요약")
    print(f"  총 케이스  : {summary.total}")
    print(f"  응답 수신  : {summary.received}")
    print(f"  연결 오류  : {len(summary.errors)}")
    if summary.errors:
        print("\n  오류 목록:")
        for e in summary.errors:
            print(f"    - {e}")
    print()


if __name__ == "__main__":
    asyncio.run(run_all())
