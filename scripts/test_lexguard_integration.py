"""
lexguard-mcp 통합 테스트: SharedPlannerCore 라우팅 + LexguardProvider 실 호출/응답 수신 검증.

목적:
  - SharedPlannerCore가 각 사용자 입력을 올바른 lexguard tool로 라우팅하는지 확인
  - LexguardProvider를 통해 실제 MCP 서버로부터 응답을 수신하는지 확인

주의:
  - Layer 2는 transport / MCP 응답 수신 여부 중심 검증이다.
  - semantic 성공(예: law_article_tool이 실제 조문 본문을 반환하는지)은 이 파일의 PASS 기준이 아니다.

라우팅 설계:
  - legal_qa_tool    : 모든 일반 법률 질문의 단일 진입점 (priority 100, catch-all)
  - law_article_tool : 법령명 + 제N조 패턴이 모두 있을 때만 진입 (priority 20)
  - law_comparison_tool : 법령명 + 신구법/연혁/3단비교 키워드가 모두 있을 때만 진입 (priority 30)
  - document_issue_tool : 계약서류 + 분석액션 키워드가 모두 있을 때만 진입 (priority 10)

실행:
  powershell -Command "& '.venv\\Scripts\\python.exe' scripts/test_lexguard_integration.py"

원격 서버 사용:
  powershell -Command "$env:LEXGUARD_URL='https://lexguard-mcp.onrender.com/mcp'; & '.venv\\Scripts\\python.exe' scripts/test_lexguard_integration.py"

환경변수:
  LEXGUARD_URL  - MCP 엔드포인트 (기본: http://127.0.0.1:9099/mcp)
  TIMEOUT       - 요청 타임아웃 초 (기본: 30)
"""

import asyncio
import io
import os
import sys
from dataclasses import dataclass, field
from typing import Any

# Windows cp949 터미널 유니코드 출력 방지
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# 프로젝트 루트를 sys.path에 추가
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

LEXGUARD_URL = os.environ.get("LEXGUARD_URL", "http://127.0.0.1:9099/mcp")
TIMEOUT = float(os.environ.get("TIMEOUT", "30"))

SEP = "-" * 72
SEP2 = "=" * 72


def h1(text: str) -> None:
    print(f"\n{SEP2}\n  {text}\n{SEP2}")


def h2(text: str) -> None:
    print(f"\n{SEP}\n  {text}\n{SEP}")


# ─────────────────────────────────────────────────────────────
# Layer 1: SharedPlannerCore 라우팅 검증 (단위 테스트)
# ─────────────────────────────────────────────────────────────


@dataclass
class RoutingCase:
    label: str
    user_input: str
    expected_action: str
    expected_keyword_hint: str  # 매칭 근거 키워드 (디버깅용)
    expected_param_key: str | None = None  # 결과 params에 있어야 할 key
    expected_param_value: Any = None  # 해당 key의 기대값 (None이면 존재 여부만 확인)


ROUTING_CASES: list[RoutingCase] = [
    # ── legal_qa_tool: 일반 법률 질문 (catch-all) ──────────────────────────
    RoutingCase(
        label="legal_qa_tool / 일반 법령 질문",
        user_input="근로기준법 연장근로 한도를 알려줘",
        expected_action="legal_qa_tool",
        expected_keyword_hint="근로기준법",
        expected_param_key="query",
    ),
    RoutingCase(
        label="legal_qa_tool / 판례 포함 일반 질문 (전용툴 미진입 확인)",
        user_input="부당해고 판례 찾아줘",
        expected_action="legal_qa_tool",
        expected_keyword_hint="판례",
        expected_param_key="query",
    ),
    RoutingCase(
        label="legal_qa_tool / 헌법재판소 결정 질문",
        user_input="헌법재판소 표현의 자유 결정 알려줘",
        expected_action="legal_qa_tool",
        expected_keyword_hint="헌법재판소",
        expected_param_key="query",
    ),
    RoutingCase(
        label="legal_qa_tool / 행정심판 질문",
        user_input="행정심판 재결례 찾아줘",
        expected_action="legal_qa_tool",
        expected_keyword_hint="행정심판",
        expected_param_key="query",
    ),
    RoutingCase(
        label="legal_qa_tool / 조례 + 판례 혼합 질문",
        user_input="조례 위반 판례 찾아줘",
        expected_action="legal_qa_tool",
        expected_keyword_hint="조례",
        expected_param_key="query",
    ),
    RoutingCase(
        label="legal_qa_tool / 세금 + 행정심판 혼합 질문",
        user_input="세금 체납 행정심판 어떻게 되나요",
        expected_action="legal_qa_tool",
        expected_keyword_hint="세금",
        expected_param_key="query",
    ),
    # ── law_article_tool: 법령명 + 제N조 패턴 ──────────────────────────────
    RoutingCase(
        label="law_article_tool / 근로기준법 제50조 조문 조회",
        user_input="근로기준법 제50조 내용 알려줘",
        expected_action="law_article_tool",
        expected_keyword_hint="제50조",
        expected_param_key="law_name",
    ),
    RoutingCase(
        label="law_article_tool / 민법 제750조 조회",
        user_input="민법 제750조가 뭐야",
        expected_action="law_article_tool",
        expected_keyword_hint="제750조",
        expected_param_key="law_name",
    ),
    # ── law_comparison_tool: 법령명 + 신구법/연혁/3단비교 ──────────────────
    RoutingCase(
        label="law_comparison_tool / 형법 신구법 비교",
        user_input="형법 신구법 비교해줘",
        expected_action="law_comparison_tool",
        expected_keyword_hint="신구법",
        expected_param_key="law_name",
    ),
    RoutingCase(
        label="law_comparison_tool / 근로기준법 개정연혁",
        user_input="근로기준법 연혁 보여줘",
        expected_action="law_comparison_tool",
        expected_keyword_hint="연혁",
        expected_param_key="law_name",
    ),
    # ── document_issue_tool: 계약서류 + 분석액션 ───────────────────────────
    # document_issue_tool은 result_chaining 전용이므로 라우팅만 확인
    # (실제 plan 실행 시 document_text 없으면 ValueError → Layer 2에서 직접 호출로 검증)
    RoutingCase(
        label="document_issue_tool / 계약서 분석 요청",
        user_input="프리랜서계약 독소조항 분석해줘",
        expected_action="document_issue_tool",
        expected_keyword_hint="계약",
        expected_param_key=None,  # document_text는 result_chaining으로 주입 — params 검증 불가
    ),
]


@dataclass
class RoutingTestResult:
    label: str
    passed: bool
    actual_action: str | None
    expected_action: str
    actual_params: dict | None
    error: str | None = None


def run_routing_tests() -> list[RoutingTestResult]:
    """SharedPlannerCore 라우팅 단위 검증 (네트워크 불필요)."""
    from ai_gateway.services.mcp.providers.lexguard import (
        DEFAULT_LEXGUARD_ACTIVATION_RULE_REF,
    )
    from ai_gateway.services.mcp.shared_planner.catalog import (
        require_activation_catalog,
    )
    from ai_gateway.services.mcp.shared_planner.core import SharedPlannerCore

    catalog = require_activation_catalog(
        DEFAULT_LEXGUARD_ACTIVATION_RULE_REF,
        provider_ids={"lexguard", "internal_docs"},
    )
    planner = SharedPlannerCore(
        default_provider_id="lexguard",
        activation_rule_ref=DEFAULT_LEXGUARD_ACTIVATION_RULE_REF,
        activation_catalog=catalog,
    )

    results: list[RoutingTestResult] = []
    for case in ROUTING_CASES:
        try:
            decision = planner.plan(case.user_input)
        except ValueError as exc:
            # document_issue_tool은 result_chaining 전용이므로 standalone plan() 호출 시
            # _map_tool_params에서 document_text 없음으로 ValueError를 raise한다.
            # 이는 의도된 설계 — rule이 올바르게 document_issue_tool을 선택했다는 증거.
            if case.expected_action == "document_issue_tool" and "document_text" in str(
                exc
            ):
                results.append(
                    RoutingTestResult(
                        label=case.label,
                        passed=True,
                        actual_action="document_issue_tool",
                        expected_action=case.expected_action,
                        actual_params=None,
                        error=f"(설계 의도) result_chaining 필요: {str(exc)[:80]}",
                    )
                )
            else:
                results.append(
                    RoutingTestResult(
                        label=case.label,
                        passed=False,
                        actual_action=None,
                        expected_action=case.expected_action,
                        actual_params=None,
                        error=f"ValueError: {exc}",
                    )
                )
            continue
        except Exception as exc:  # noqa: BLE001
            results.append(
                RoutingTestResult(
                    label=case.label,
                    passed=False,
                    actual_action=None,
                    expected_action=case.expected_action,
                    actual_params=None,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
            continue

        actual_action: str | None = None
        actual_params: dict | None = None

        if decision.plans:
            for plan in decision.plans:
                if plan.action == case.expected_action:
                    actual_action = plan.action
                    actual_params = dict(plan.params)
                    break
            if actual_action is None:
                actual_action = decision.plans[0].action
                actual_params = dict(decision.plans[0].params)

        error: str | None = None
        passed = actual_action == case.expected_action

        if passed and case.expected_param_key and actual_params is not None:
            if case.expected_param_key not in actual_params:
                passed = False
                error = f"params에 '{case.expected_param_key}' 키가 없음. 실제 params: {actual_params}"
            elif case.expected_param_value is not None:
                if actual_params[case.expected_param_key] != case.expected_param_value:
                    passed = False
                    error = (
                        f"params['{case.expected_param_key}'] = "
                        f"{actual_params[case.expected_param_key]!r} "
                        f"(기대: {case.expected_param_value!r})"
                    )

        if not passed and error is None:
            error = (
                f"라우팅 오류: 기대={case.expected_action!r}, 실제={actual_action!r}"
            )

        results.append(
            RoutingTestResult(
                label=case.label,
                passed=passed,
                actual_action=actual_action,
                expected_action=case.expected_action,
                actual_params=actual_params,
                error=error,
            )
        )

    return results


# ─────────────────────────────────────────────────────────────
# Layer 2: LexguardProvider 실 호출 검증 (네트워크 필요)
# ─────────────────────────────────────────────────────────────


@dataclass
class ProviderCallCase:
    label: str
    tool: str
    args: dict
    expect_success: bool  # True=응답 수신 기대 (semantic 성공 의미 아님)


PROVIDER_CASES: list[ProviderCallCase] = [
    # legal_qa_tool — 모든 일반 법률 질문의 단일 진입점
    ProviderCallCase(
        label="legal_qa_tool / 연장근로 질문",
        tool="legal_qa_tool",
        args={"query": "연장근로 한도", "max_results_per_type": 2},
        expect_success=True,
    ),
    ProviderCallCase(
        label="legal_qa_tool / 부당해고 판례 포함 종합 질문",
        tool="legal_qa_tool",
        args={"query": "부당해고 판례", "max_results_per_type": 2},
        expect_success=True,
    ),
    # law_article_tool — 법령명 + 조문번호 정밀 조회 (응답 수신 여부만 확인)
    ProviderCallCase(
        label="law_article_tool / 근로기준법 제50조",
        tool="law_article_tool",
        args={"law_name": "근로기준법", "article_number": "50"},
        expect_success=True,
    ),
    ProviderCallCase(
        label="law_article_tool / 민법 제750조",
        tool="law_article_tool",
        args={"law_name": "민법", "article_number": "750"},
        expect_success=True,
    ),
    # law_comparison_tool — 법령 신구·연혁·3단 비교
    ProviderCallCase(
        label="law_comparison_tool / 형법 신구법 비교",
        tool="law_comparison_tool",
        args={"law_name": "형법", "compare_type": "신구법"},
        expect_success=True,
    ),
    ProviderCallCase(
        label="law_comparison_tool / 근로기준법 연혁",
        tool="law_comparison_tool",
        args={"law_name": "근로기준법", "compare_type": "연혁"},
        expect_success=True,
    ),
    # document_issue_tool — result_chaining 우회 직접 호출 검증
    ProviderCallCase(
        label="document_issue_tool / 프리랜서 계약서 분석",
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
]


@dataclass
class ProviderCallResult:
    label: str
    tool: str
    passed: bool
    response_received: bool
    result_keys: list[str]
    error: str | None = None


async def run_provider_tests(
    server_url: str, timeout: float
) -> list[ProviderCallResult]:
    """LexguardProvider를 통해 실제 MCP 서버 호출 검증."""
    from ai_gateway.services.mcp.config import McpServerConfig
    from ai_gateway.services.mcp.providers.lexguard import (
        LEXGUARD_PROVIDER_ID,
        LEXGUARD_PROVIDER_NAME,
        LEXGUARD_PROVIDER_TRANSPORT,
        LexguardProvider,
    )

    config = McpServerConfig(
        provider_id=LEXGUARD_PROVIDER_ID,
        display_name=LEXGUARD_PROVIDER_NAME,
        transport=LEXGUARD_PROVIDER_TRANSPORT,
        base_url=server_url,
        kind="local",
        enabled=True,
        origin_type="local",
    )

    results: list[ProviderCallResult] = []

    async with LexguardProvider.connect_from_config(config) as provider:
        for case in PROVIDER_CASES:
            try:
                raw = await asyncio.wait_for(
                    provider.call_tool_dict(case.tool, case.args),
                    timeout=timeout,
                )
                response_received = True
                result_keys = list(raw.keys()) if isinstance(raw, dict) else []
                passed = response_received
                error = None
            except TimeoutError:
                response_received = False
                result_keys = []
                passed = False
                error = f"TIMEOUT ({timeout}s)"
            except Exception as exc:  # noqa: BLE001
                exc_type = type(exc).__name__
                exc_msg = str(exc)
                # ToolError means the MCP server responded with isError=true —
                # the transport layer worked correctly. Treat as response received.
                if exc_type == "ToolError":
                    response_received = True
                    result_keys = []
                    passed = True
                    error = f"ToolError (서버 측 에러 응답, 수신 성공): {exc_msg[:120]}"
                else:
                    response_received = False
                    result_keys = []
                    passed = False
                    error = f"{exc_type}: {exc_msg}"

            results.append(
                ProviderCallResult(
                    label=case.label,
                    tool=case.tool,
                    passed=passed,
                    response_received=response_received,
                    result_keys=result_keys,
                    error=error,
                )
            )

    return results


# ─────────────────────────────────────────────────────────────
# 출력 및 결과 집계
# ─────────────────────────────────────────────────────────────


def print_routing_results(results: list[RoutingTestResult]) -> int:
    """라우팅 결과 출력. 실패 수 반환."""
    h1("Layer 1: SharedPlannerCore 라우팅 검증")
    failures = 0
    for r in results:
        status = "✅ PASS" if r.passed else "❌ FAIL"
        print(f"\n  {status} | {r.label}")
        print(
            f"         action   : 기대={r.expected_action!r}, 실제={r.actual_action!r}"
        )
        if r.actual_params:
            print(f"         params   : {r.actual_params}")
        if not r.passed and r.error:
            print(f"         오류     : {r.error}")
        if not r.passed:
            failures += 1
    return failures


def print_provider_results(results: list[ProviderCallResult]) -> int:
    """Provider 호출 결과 출력. 실패 수 반환."""
    h1("Layer 2: LexguardProvider 실 호출 검증")
    failures = 0
    for r in results:
        status = "✅ PASS" if r.passed else "❌ FAIL"
        print(f"\n  {status} | {r.label}")
        print(f"         tool     : {r.tool}")
        print(f"         수신     : {r.response_received}")
        if r.result_keys:
            print(f"         keys     : {r.result_keys}")
        if r.error:
            print(f"         오류     : {r.error}")
        if not r.passed:
            failures += 1
    return failures


# ─────────────────────────────────────────────────────────────
# 실행 진입점
# ─────────────────────────────────────────────────────────────


async def main() -> int:
    h1(f"lexguard-mcp 통합 테스트 (endpoint: {LEXGUARD_URL})")
    print(f"  timeout: {TIMEOUT}s")
    print(f"  Layer 1 routing cases : {len(ROUTING_CASES)}")
    print(f"  Layer 2 provider cases: {len(PROVIDER_CASES)}")

    # Layer 1: 라우팅 (동기, 네트워크 불필요)
    routing_results = run_routing_tests()
    routing_failures = print_routing_results(routing_results)

    # Layer 2: 실 호출 (비동기, 네트워크 필요)
    provider_results = await run_provider_tests(LEXGUARD_URL, TIMEOUT)
    provider_failures = print_provider_results(provider_results)

    total_failures = routing_failures + provider_failures
    total_cases = len(ROUTING_CASES) + len(PROVIDER_CASES)
    total_passed = total_cases - total_failures

    h1("최종 결과 요약")
    print(
        f"  Layer 1 라우팅 : {len(ROUTING_CASES) - routing_failures}/{len(ROUTING_CASES)} 통과"
    )
    print(
        f"  Layer 2 호출   : {len(PROVIDER_CASES) - provider_failures}/{len(PROVIDER_CASES)} 통과"
    )
    print(f"  전체           : {total_passed}/{total_cases} 통과")

    if total_failures == 0:
        print("\n  🎉 모든 테스트 통과!")
        return 0
    else:
        print(f"\n  ⚠️  {total_failures}개 실패. 위 오류 내용을 확인하세요.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
