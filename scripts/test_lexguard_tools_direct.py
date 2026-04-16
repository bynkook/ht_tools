"""
LexGuard 4대 핵심 tool 직접 호출 테스트.

이 파일은 planner / tool chaining / 최종 LLM orchestration 이전 단계에서,
"tool 1회 호출 계약(contract)"을 검증하기 위한 direct test 이다.

핵심 목적:
  - LexguardProvider 를 직접 사용해 4개 tool 각각의 요청/응답 계약 확인
  - raw MCP 응답 구조를 그대로 저장하고 사람이 검토 가능하게 보존
  - tool별 성공/실패/비정상 기준을 maintainer 답변과 실제 observed payload 기준으로 명시

이 파일이 직접 검증하는 것:
  - 단일 tool call 의 입력/출력 구조
  - transport 성공 / tool-level 성공 / 명백한 비정상 상태 구분
  - raw response shape 확인

이 파일이 직접 검증하지 않는 것:
  - document_issue_tool 이후 retry_plan.suggested_queries 를 사용한 추가 legal_qa_tool 호출
  - law_article_tool / legal_qa_tool / law_comparison_tool 조합을 통한 최종 답변 합성
  - response_policy 를 읽은 downstream LLM 의 자연어 보고서 생성 품질

────────────────────────────────────────────────────────────
Maintainer-confirmed tool contract summary
────────────────────────────────────────────────────────────

1) legal_qa_tool
   - 입력 스키마 핵심: query, max_results_per_type
   - 응답 스키마 핵심: success, results, citations(+ laws/precedents/interpretations 계열)
   - direct success 판단 (upstream emitted payload 기준):
       success == True
       results 가 dict 타입으로 존재 (내부 비어있어도 무방)
   - 주의: success_search 는 emitted payload 에 포함되지 않음 (schema-runtime drift)
       legal_qa_tool 은 formatter 의 smart_search_tool branch 를 거치지 않고
       default raw return 경로로 반환되므로 success_search 를 판정 기준으로 쓰면 안 됨

2) law_article_tool
   - 입력 스키마 핵심: law_name, article_number, hang, ho, mok
   - 응답 스키마 핵심: content, title, law_id, article_number, note
   - maintainer 답변 기준:
       content 에 조문 본문이 있으면 정상
       "조문 내용을 찾을 수 없습니다." 가 오면 비정상/버그
       note 가 동반되면 비정상 케이스로 간주 가능

3) law_comparison_tool
   - 입력 스키마 핵심: law_name, compare_type
   - 응답 스키마 핵심: law_name, comparison, error/error_code
   - direct success 판단:
       error 없음
       law_name 존재
       comparison 비어있지 않음

4) document_issue_tool
   - 입력 스키마 핵심: document_text, auto_search, max_clauses, max_results_per_type
   - 응답 스키마 핵심:
       success_transport, analysis_success, document_analysis,
       success_search, has_legal_basis, missing_reason,
       citations, legal_basis_block_text, retry_plan, response_policy
   - maintainer-confirmed intended usage:
       document_issue_tool 는 "최종 보고서 생성기"가 아니라
       downstream LLM 에게 넘기는 "중간 분석 패키지"이다.
       response_policy 는 LLM 작성 지시이고,
       retry_plan.suggested_queries 는 LLM 이 추가 legal_qa_tool 호출 등에 사용할 수 있는 힌트이다.
   - direct 정상 동작 판단(maintainer 답변 기준):
       success_transport == True
       analysis_success == True
       document_analysis.detected == True
       missing_reason 이 API_ERROR_* 가 아니면 정상 범주 가능
    - contract success:
        success_transport == True (또는 transport 에러 없음)
        analysis_success == True
        document_analysis.detected == True
        missing_reason 이 API_ERROR_* 가 아니면 정상 범주 가능
    - 풍부한 근거까지 확보된 enriched success:
        success_search == True
        has_legal_basis == True
        missing_reason is None
        citations non-empty

────────────────────────────────────────────────────────────
document_issue_tool 의 intended workflow (LLM API 설계 참고)
────────────────────────────────────────────────────────────

단계 A. 1차 분석 패키지 생성
  - client/LLM 이 document_issue_tool(document_text=..., auto_search=True) 호출
  - tool 은 문서 유형 식별, clause 추출, clause_issues, clause_basis_hints,
    suggested_queries 등을 포함한 document_analysis 를 반환

단계 B. tool 내부 2차 검색 시도
  - auto_search=True 이면 tool 내부에서 법령/판례/해석례 검색 시도
  - 결과가 있으면 success_search=True / has_legal_basis=True
  - 결과가 없으면 missing_reason=NO_MATCH 로 종료할 수 있음
  - 이 NO_MATCH 는 비정상/오류가 아니라 "분석은 되었지만 근거 미발견" 상태일 수 있음

단계 C. downstream LLM orchestration
  - FabriX 는 tool 결과를 거의 그대로 json.dumps(raw_result) 하여 LLM 에 전달
  - LLM 은 response_policy 를 읽고 답변 형식을 결정
  - has_legal_basis=False 이면 retry_plan.suggested_queries 를 사용해
    legal_qa_tool 추가 호출을 수행할 수 있음
  - 필요 시 legal_qa_tool 결과에서 나온 법령명/조문을 바탕으로
    law_article_tool 추가 호출을 수행할 수 있음
  - 최종 자연어 보고서는 이 multi-step workflow 를 거쳐 완성될 수 있음

즉 document_issue_tool 단독 응답이 항상 완결된 최종 보고서 데이터여야 하는 것은 아니며,
이 direct test 는 "1회 호출 계약"을 검증하는 용도임을 전제로 한다.

실행:
  powershell -Command "& '.venv\\Scripts\\python.exe' scripts/test_lexguard_tools_direct.py"

원격 서버:
  powershell -Command "$env:LEXGUARD_URL='https://lexguard-mcp.onrender.com/mcp'; & '.venv\\Scripts\\python.exe' scripts/test_lexguard_tools_direct.py"

환경변수:
  LEXGUARD_URL  - MCP 엔드포인트 (기본: http://127.0.0.1:9099/mcp)
  TIMEOUT       - 요청 타임아웃 초 (기본: 60)
  OUTPUT_DIR    - 응답 저장 디렉터리 (기본: scripts/lexguard_responses)
"""

import asyncio
import io
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from fastmcp.exceptions import ToolError

# Windows cp949 터미널 유니코드 출력 방지
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# 프로젝트 루트를 sys.path에 추가
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from ai_gateway.services.mcp.config import McpServerConfig
from ai_gateway.services.mcp.providers.lexguard import (
    DEFAULT_LEXGUARD_SERVER_URL,
    DOCUMENT_ISSUE_TOOL,
    LAW_ARTICLE_TOOL,
    LAW_COMPARISON_TOOL,
    LEGAL_QA_TOOL,
    LexguardProvider,
)

LEXGUARD_URL = os.environ.get("LEXGUARD_URL", DEFAULT_LEXGUARD_SERVER_URL)
TIMEOUT = float(os.environ.get("TIMEOUT", "60"))
OUTPUT_DIR = Path(
    os.environ.get(
        "OUTPUT_DIR", os.path.join(os.path.dirname(__file__), "lexguard_responses")
    )
)

# ─────────────────────────────────────────────────────────────
# 내장 문서 샘플 (외부 파일 불필요)
# ─────────────────────────────────────────────────────────────

# 서비스 이용약관형 계약서 - 2차 검색 친화 샘플
FREELANCE_CONTRACT_TEXT = """\
[서비스 이용약관]

제1조 (목적)
본 약관은 회사가 제공하는 온라인 서비스의 이용과 관련하여 회사와 이용자 간 권리·의무를 정한다.

제2조 (계약의 해지)
회사는 사전 통지 없이 언제든지 이용계약을 해지할 수 있으며, 이용자는 이에 대해 이의를 제기할 수 없다.

제3조 (손해배상 및 위약벌)
이용자가 약관을 위반할 경우 이용자는 손해 발생 여부와 관계없이 위약벌로 1억원을 즉시 지급하여야 한다.

제4조 (환불 및 면책)
이용자가 이미 지급한 이용요금은 어떠한 경우에도 환불되지 않으며, 회사는 서비스 장애나 데이터 손실에 대하여 책임을 지지 않는다.

제5조 (관할)
본 약관과 관련한 모든 분쟁은 회사 본점 소재지 법원을 전속적 합의관할로 한다.
"""

# 임대차 계약서 샘플 (2차 법적 근거 검색 성공 가능성 강화)
LEASE_CONTRACT_TEXT = """\
[부동산 임대차 계약서]

임대인(갑): 이대동 / 임차인(을): 박세입

제1조 (목적물)
서울시 강남구 테헤란로 123, 오피스텔 501호 (전용면적 25㎡)

제2조 (임대차 기간 및 보증금)
임대차 기간: 2024. 03. 01. ~ 2025. 02. 28. (12개월)
보증금: 20,000,000원 / 월세: 800,000원
을은 계약갱신요구권을 행사할 수 없으며, 갑이 갱신을 거절하면 즉시 퇴거하여야 한다.

제3조 (계약 해제 및 위약금)
갑 또는 을이 계약을 임의로 해제할 경우 위약금은 보증금의 10%로 한다.
단, 갑이 일방적으로 퇴거를 요구할 경우 을은 통보 후 7일 이내에 퇴거해야 한다.
임대인이 보증금 반환을 지연하더라도 을은 이의를 제기하지 않는다.

제4조 (관리비 및 공과금)
관리비는 별도로 을이 전액 부담하며, 관리비 항목과 금액은 갑이 임의로 결정할 수 있다.

제5조 (원상복구)
계약 종료 시 을은 임차물을 원상복구하여 반환해야 하며, 원상복구 비용이 보증금을
초과할 경우 을이 초과분을 추가 지급한다.

제6조 (관할)
본 계약과 관련한 분쟁은 임대인 주소지 관할 법원을 전속적 합의관할로 한다.
"""


# ─────────────────────────────────────────────────────────────
# 테스트 케이스 정의
# ─────────────────────────────────────────────────────────────


@dataclass
class ToolCase:
    label: str
    tool: str
    args: dict[str, Any]
    desc: str  # 테스트 의도 설명


# TOOL_CASES 는 각 tool contract 를 대표하는 최소 direct-call 샘플이다.
#
# 주의:
# - document_issue_tool 샘플 문서는 "최종 보고서 품질" 검증용이 아니라,
#   1회 호출 시 어떤 구조의 분석 패키지가 오는지와 auto_search 결과를 관찰하기 위한 것이다.
# - law_article_tool 샘플은 maintainer 가 직접 정상 contract 를 설명한 tool 이므로,
#   여기서는 strict success/failure tool 로 취급한다.
TOOL_CASES: list[ToolCase] = [
    # ── 1. legal_qa_tool ─────────────────────────────────────────────────────
    ToolCase(
        label="legal_qa_tool / 연장근로 한도 질문",
        tool=LEGAL_QA_TOOL,
        args={
            "query": "연장근로 한도가 얼마나 되나요? 위반 시 제재는 무엇인가요?",
            "max_results_per_type": 3,
        },
        desc="노동법 도메인 연장근로 한도 질문",
    ),
    ToolCase(
        label="legal_qa_tool / 개인정보보호 CCTV 설치 질문",
        tool=LEGAL_QA_TOOL,
        args={
            "query": "사업장 CCTV 설치 시 개인정보보호법 준수 사항은?",
            "max_results_per_type": 2,
        },
        desc="도메인 미지정 일반 법률 QA",
    ),
    # ── 2. law_article_tool ──────────────────────────────────────────────────
    ToolCase(
        label="law_article_tool / 건축법 제3조제1항제2호다목",
        tool=LAW_ARTICLE_TOOL,
        args={
            "law_name": "건축법",
            "article_number": "3",
            "hang": "1",
            "ho": "2",
            "mok": "다",
        },
        desc="공식 eflawjosub 가이드 샘플 기반 단일 조문/항/호/목 조회",
    ),
    ToolCase(
        label="law_article_tool / 건축법 제3조",
        tool=LAW_ARTICLE_TOOL,
        args={
            "law_name": "건축법",
            "article_number": "3",
        },
        desc="공식 eflawjosub 가이드 샘플 기반 조문 단건 조회",
    ),
    # ── 3. law_comparison_tool ───────────────────────────────────────────────
    ToolCase(
        label="law_comparison_tool / 근로기준법 신구법 비교",
        tool=LAW_COMPARISON_TOOL,
        args={
            "law_name": "근로기준법",
            "compare_type": "신구법",
        },
        desc="근로기준법 개정 전후 조문 비교",
    ),
    ToolCase(
        label="law_comparison_tool / 개인정보보호법 신구법 비교",
        tool=LAW_COMPARISON_TOOL,
        args={
            "law_name": "개인정보보호법",
            "compare_type": "신구법",
        },
        desc="개인정보보호법 최신 개정 신구법 비교",
    ),
    # ── 4. document_issue_tool ───────────────────────────────────────────────
    ToolCase(
        label="document_issue_tool / 프리랜서 계약서 문제 조항 분석",
        tool=DOCUMENT_ISSUE_TOOL,
        args={
            "document_text": FREELANCE_CONTRACT_TEXT,
            "auto_search": True,
            "max_clauses": 4,
            "max_results_per_type": 2,
        },
        desc="독소조항 포함 용역계약서 분석",
    ),
    ToolCase(
        label="document_issue_tool / 임대차 계약서 문제 조항 분석",
        tool=DOCUMENT_ISSUE_TOOL,
        args={
            "document_text": LEASE_CONTRACT_TEXT,
            "auto_search": True,
            "max_clauses": 3,
            "max_results_per_type": 2,
        },
        desc="불공정 관리비·단기 퇴거 요구 포함 임대차 계약서",
    ),
]


# ─────────────────────────────────────────────────────────────
# tool별 판정 함수
#
# 여기의 verdict 는 "direct tool contract" 기준이다.
# 특히 document_issue_tool 은 최종 LLM 보고서 생성기 계약이 아니라,
# direct call 시 어떤 상태를 contract success / enriched success / 비정상으로 볼지
# 분리해서 해석해야 한다.
# ─────────────────────────────────────────────────────────────


def _verdict_legal_qa(result: dict[str, Any]) -> tuple[bool, str]:
    """
    legal_qa_tool 성공 조건 (upstream emitted payload 기준):
      - success == True
      - results 필드 존재 (dict 타입)

    주의: success_search 는 legal_qa_tool 의 emitted payload 에 포함되지 않는다.
    upstream formatter 의 smart_search_tool branch 를 거치지 않고
    default raw return 경로로 반환되기 때문이다.
    따라서 success_search 를 판정 기준으로 사용하면 안 된다.

    no-result 정상 케이스:
      - success == True
      - results 는 dict (내부 값이 비어있어도 무방)
      - has_legal_basis == False + missing_reason == "NO_MATCH" 는 정상 범주
    """
    if result.get("success") is not True:
        return False, f"success={result.get('success')}"
    results = result.get("results")
    if not isinstance(results, dict):
        return (
            False,
            f"results 필드가 없거나 dict 가 아님 (type={type(results).__name__})",
        )
    return True, "ok"


def _verdict_law_article(result: dict[str, Any]) -> tuple[bool, str]:
    """
    law_article_tool 성공 조건:
      - content 필드 존재 + "조문 내용을 찾을 수 없습니다" 문구 없음

    서버 응답 구조 (law_detail.py get_single_article 기준):
      성공: {law_id, article_number, title, content, api_url, ...}
      실패: content="조문 내용을 찾을 수 없습니다." + note + raw_data

    success 필드 자체가 응답에 없으므로 content 필드로만 판정.
    """
    content = str(result.get("content", "") or "").strip()
    note = str(result.get("note", "") or "").strip()
    raw_data = str(result.get("raw_data", "") or "")

    if not content:
        return False, "content 비어있음"
    if "조문 내용을 찾을 수 없습니다" in content:
        if "기본정보" in raw_data and "조문내용" not in raw_data:
            return False, "content recovery 실패 (raw_data=basicInfo-only JSON 추정)"
        if note:
            return False, f"content recovery 실패 (note={note[:80]})"
        return False, "content recovery 실패 (조문 본문 없음)"
    return True, "ok"


def _verdict_law_comparison(result: dict[str, Any]) -> tuple[bool, str]:
    """
    law_comparison_tool 성공 조건:
      - error 필드 없음 (또는 null)
      - law_name 필드 존재
      - comparison 필드 非null + 비어있지 않음
    """
    if result.get("error"):
        return (
            False,
            f"error={result.get('error', '')[:80]}, error_code={result.get('error_code', '')}",
        )
    if not result.get("law_name"):
        return False, "law_name 필드 없음"
    comparison = result.get("comparison")
    if not comparison:
        return False, "comparison 필드가 없거나 비어있음"
    return True, "ok"


def _verdict_document_issue(result: dict[str, Any]) -> tuple[bool, str]:
    """
    document_issue_tool direct verdict:
      1) contract success
         - analysis_success == True
         - document_analysis.detected == True
         - missing_reason 이 API_ERROR_* 가 아니면 정상 범주 가능

      2) enriched success
         - success_search == True
         - has_legal_basis == True
         - missing_reason is None
         - citations non-empty

    direct test 최종 판정 정책:
      - contract success 는 PASS 로 본다
      - enriched success 가 아니면 PASS(reason=contract-only) 로 본다
      - 즉 document_issue_tool 은 "중간 분석 패키지" contract 를 우선 검증하고,
        풍부한 근거 확보 여부는 reason 으로 구분한다

    실패로 보는 경우:
      - analysis_success == True
      - document_analysis.detected == True
      - API_ERROR_* 류 missing_reason
      - document_analysis 자체 부재/미인식
    """
    if result.get("analysis_success") is not True:
        return False, "analysis_success=False — 문서 분석 자체 실패"
    doc_analysis = result.get("document_analysis") or {}
    if not doc_analysis.get("detected"):
        return False, "document_analysis.detected=False — 문서 유형 미인식"
    missing_reason = result.get("missing_reason")
    if isinstance(missing_reason, str) and missing_reason.startswith("API_ERROR"):
        return False, f"missing_reason={missing_reason}"
    if result.get("success_search") is not True:
        return (
            True,
            f"contract-only success (success_search={result.get('success_search')}, missing_reason={missing_reason})",
        )
    if result.get("has_legal_basis") is not True:
        return (
            True,
            f"contract-only success (has_legal_basis={result.get('has_legal_basis')})",
        )
    if missing_reason is not None:
        return True, f"contract-only success (missing_reason={missing_reason})"
    citations = result.get("citations")
    if not citations:
        return True, "contract-only success (citations 비어있음)"
    return True, "enriched success"


# tool → 판정 함수 매핑
_VERDICT_FN = {
    LEGAL_QA_TOOL: _verdict_legal_qa,
    LAW_ARTICLE_TOOL: _verdict_law_article,
    LAW_COMPARISON_TOOL: _verdict_law_comparison,
    DOCUMENT_ISSUE_TOOL: _verdict_document_issue,
}


# ─────────────────────────────────────────────────────────────
# 파일 저장 헬퍼
# ─────────────────────────────────────────────────────────────


def _safe_filename(label: str) -> str:
    """케이스 label → 파일명으로 변환 (특수문자 제거)."""
    name = re.sub(r"[^\w가-힣\-]", "_", label)
    name = re.sub(r"_+", "_", name).strip("_")
    return name


def save_response(
    case: ToolCase,
    result: dict[str, Any] | None,
    raw_blocks: list[str] | None,
    status: str,
    run_ts: str,
) -> Path:
    """케이스 raw 응답을 그대로 텍스트 파일로 저장."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{run_ts}__{_safe_filename(case.label)}.txt"
    out_path = OUTPUT_DIR / filename

    parts: list[str] = []

    def _pretty_json_or_raw(text: str) -> str:
        stripped = text.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                return json.dumps(json.loads(stripped), ensure_ascii=False, indent=2)
            except json.JSONDecodeError:
                return text
        return text

    # 저장 정책:
    # - direct test 의 목적은 "server raw 응답 전체"를 보존하는 것
    # - 따라서 우리 코드가 별도 분석 섹션/파생 결과를 덧붙이지 않는다
    # - 단, raw block 이 JSON 이면 readability 를 위해 pretty-print 만 적용한다
    # - raw block 이 없을 때만 result dict 를 fallback 저장한다
    if raw_blocks:
        parts.extend(_pretty_json_or_raw(block) for block in raw_blocks)
    elif result is not None:
        # raw blocks 없으면 파싱된 JSON을 fallback으로 저장
        parts.append(json.dumps(result, ensure_ascii=False, indent=2))

    out_path.write_text("\n".join(parts), encoding="utf-8-sig")
    return out_path


# ─────────────────────────────────────────────────────────────
# MCP raw 호출 (SDK schema 검증 우회)
# ─────────────────────────────────────────────────────────────


async def _call_raw(
    provider: LexguardProvider, tool_name: str, tool_args: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """send_request() 직접 호출 — _validate_tool_result() schema 검증 완전 우회.

    law_article_tool 처럼 서버 응답 schema가 MCP outputSchema 선언과 불일치하는 경우,
    fastmcp Client 경로의 jsonschema 검증이 RuntimeError를 일으킨다.
    send_request()는 그 경로를 건너뛰어 raw CallToolResult를 반환한다.

    Returns:
        (result_dict, raw_text_blocks)

    raw_text_blocks 정책:
    - MCP content[] 의 text block 을 있는 그대로 수집한다
    - instruction text 와 JSON echo 가 함께 올 수 있으므로 둘 다 저장 대상이다
    - direct test 의 목적은 "무엇이 왔는가" 확인이므로, 여기서 임의 필터링을 최소화한다

    result_dict 정책:
    - verdict 용으로는 JSON block 하나를 dict 로 파싱해 사용한다
    - 여러 text block 이 있을 때는 첫 번째 JSON block 을 대표 결과로 사용한다
    - 즉, 저장(raw)과 판정(parsed)은 의도적으로 분리되어 있다
    """
    import mcp.types as mcp_types

    request = mcp_types.CallToolRequest(
        params=mcp_types.CallToolRequestParams(name=tool_name, arguments=tool_args)
    )
    raw_result = await provider.client.session.send_request(  # type: ignore[arg-type]
        cast(Any, request),
        mcp_types.CallToolResult,  # type: ignore[arg-type]
    )

    blocks = getattr(raw_result, "content", []) or []
    all_texts = [b.text for b in blocks if hasattr(b, "text") and b.text]
    is_error = getattr(raw_result, "isError", False)

    # verdict 용 dict 는 JSON block 우선 파싱
    # (raw 저장은 all_texts 전체를 사용하므로, JSON 이외의 instruction text 는 버리지 않음)
    result_dict: dict[str, Any] | None = None
    for text in all_texts:
        stripped = text.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                result_dict = json.loads(stripped)
                break
            except json.JSONDecodeError:
                pass

    if result_dict is None:
        result_dict = {
            "raw_text": "\n".join(all_texts),
            "success": not is_error if not all_texts else True,
            "_fallback": True,
        }

    return result_dict, all_texts


# ─────────────────────────────────────────────────────────────
# 케이스 실행
# ─────────────────────────────────────────────────────────────


@dataclass
class Summary:
    total: int = 0
    passed: int = 0
    failed: list[str] = field(default_factory=list)
    saved_files: list[Path] = field(default_factory=list)


def _make_config() -> McpServerConfig:
    return McpServerConfig(
        provider_id="lexguard",
        display_name="lexguard-mcp",
        transport="streamable_http",
        base_url=LEXGUARD_URL,
        kind="local",
        origin_type="local",
    )


async def run_case(
    provider: LexguardProvider,
    case: ToolCase,
    summary: Summary,
    run_ts: str,
) -> None:
    summary.total += 1
    result: dict[str, Any] | None = None
    raw_blocks: list[str] = []

    # 항상 _call_raw() 경로를 사용 (schema 검증 우회 + raw blocks 동시 획득)
    try:
        result, raw_blocks = await _call_raw(provider, case.tool, case.args)
    except ToolError as exc:
        out = save_response(case, None, [str(exc)], "FAIL", run_ts)
        summary.saved_files.append(out)
        summary.failed.append(f"{case.label} — ToolError: {str(exc)[:100]}")
        return
    except Exception as exc:  # noqa: BLE001
        msg = f"{type(exc).__name__}: {exc}"
        out = save_response(case, None, None, "FAIL", run_ts)
        summary.saved_files.append(out)
        summary.failed.append(f"{case.label} — {msg[:100]}")
        return

    # tool별 verdict 는 direct-call contract 기준이다.
    # document_issue_tool 은 maintainer 의도상 중간 분석 패키지도 정상일 수 있으므로,
    # contract success 와 enriched success 를 reason 문자열로 구분한다.
    verdict_fn = _VERDICT_FN.get(case.tool)
    if verdict_fn is None:
        # 판정 함수 미등록 tool → 일단 PASS
        out = save_response(case, result, raw_blocks, "PASS", run_ts)
        summary.saved_files.append(out)
        summary.passed += 1
        return

    passed, reason = verdict_fn(result)

    out = save_response(case, result, raw_blocks, "PASS" if passed else "FAIL", run_ts)
    summary.saved_files.append(out)

    if passed:
        summary.passed += 1
    else:
        summary.failed.append(f"{case.label} — {reason}")


# ─────────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────────


async def run_all() -> None:
    run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    config = _make_config()
    summary = Summary()

    # health check
    try:
        async with LexguardProvider.connect_from_config(config) as provider:
            health = await provider.health_check()
            if health.get("status") != "ok":
                print(f"[연결 실패] 서버 상태 이상: {health.get('error')}")
                return
    except Exception as exc:  # noqa: BLE001
        print(f"[연결 실패] {type(exc).__name__}: {exc}")
        return

    # 각 tool 테스트 실행
    async with LexguardProvider.connect_from_config(config) as provider:
        for case in TOOL_CASES:
            await run_case(provider, case, summary, run_ts)

    # 결과 요약 (최종 출력)
    print(f"\n결과: {summary.passed}/{summary.total} 통과")
    if summary.failed:
        print("실패:")
        for item in summary.failed:
            print(f"  - {item}")
    print(f"저장: {OUTPUT_DIR}")


if __name__ == "__main__":
    asyncio.run(run_all())
