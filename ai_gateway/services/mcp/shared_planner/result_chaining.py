"""
Result chaining utilities for sequential MCP pipeline execution.

Design principle (from user requirements):
1. Query → no doc search needed → if query is legal-related → call lexguard
2. Query → doc search needed → execute doc search → if ORIGINAL QUERY is legal-related → call lexguard with doc search results as document_text

Key insight: Legal-relatedness is determined by the ORIGINAL USER QUERY, not the doc search results.
Doc search results are passed as data (document_text) to lexguard, but don't determine whether to call lexguard.
"""

import re
from typing import Any

# Legal content detection keywords (extracted from lexguard-mcp SmartSearchService)
LEGAL_KEYWORDS = frozenset(
    [
        # Law-related
        "법령",
        "법",
        "조문",
        "조항",
        "법률",
        "시행령",
        "시행규칙",
        # Precedent-related
        "판례",
        "대법원",
        "판결",
        "선고",
        "사건",
        "재판",
        "법원",
        "헌법재판소",
        "헌재",
        # Labor-related
        "근로자성",
        "해고",
        "부당해고",
        "정리해고",
        "임금",
        "퇴직금",
        "체불",
        "프리랜서",
        "근로기준법",
        "산재",
        "4대보험",
        # Civil-related
        "손해배상",
        "계약위반",
        "위약금",
        "재산분할",
        "상속",
        "양육권",
        "위자료",
        "불법행위",
        # Contract-related (document analysis triggers)
        "계약서",
        "약관",
        "협약서",
        "각서",
        "합의서",
        "근로계약서",
        "임대차계약서",
        "독소조항",
        "불공정",
        "검토",
        "분석",
        # Administrative
        "행정심판",
        "행정소송",
        "위헌",
        "행정처분",
        "과태료",
        # Interpretation
        "법령해석",
        "해석례",
        "법제처",
        # Special domains
        "개인정보",
        "세금",
        "부동산",
        "임대차",
        "전세",
        "소비자",
        "금융",
        "보험",
        "저작권",
        "특허",
    ]
)

# Regex patterns for legal content detection
LEGAL_PATTERNS = [
    re.compile(r"법\s*제?\s*\d+조"),  # 법 제1조, 법제1조
    re.compile(r"\w+법\s*제?\s*\d+조"),  # 근로기준법 제1조
    re.compile(r"대법원\s*\d+"),  # 대법원 판결번호
    re.compile(r"\d{4}[가나다라마바사아자차카타파하도]\d+"),  # 사건번호
    re.compile(r"(?:대법원|고등법원|지방법원)\s*\d{4}"),  # 법원 연도
]


def is_legal_query(query: str) -> bool:
    """Detect if the user query is legal-related.

    This determines WHETHER to call lexguard.
    Uses keyword matching and regex patterns extracted from lexguard-mcp.
    """
    if not query:
        return False

    # Check for keyword matches
    query_lower = query.lower()
    for keyword in LEGAL_KEYWORDS:
        if keyword in query_lower:
            return True

    # Check for pattern matches
    for pattern in LEGAL_PATTERNS:
        if pattern.search(query):
            return True

    return False


def extract_document_text_from_result(result: dict[str, Any]) -> str | None:
    """Extract document text from a doc_search (search_docs_rag) result.

    The raw_result from search_docs_rag contains:
    - files: list of matching files
    - snippets: list of {filename, snippet, start, end, ...}

    Returns concatenated snippet texts, or None if no content found.
    """
    raw_result = result.get("raw_result", {})

    # Try snippets first (most common case)
    snippets = raw_result.get("snippets", [])
    if snippets:
        texts = []
        for snippet in snippets:
            snippet_text = snippet.get("snippet", "")
            if snippet_text:
                texts.append(snippet_text)
        if texts:
            return "\n\n---\n\n".join(texts)

    # Fallback to files if no snippets
    files = raw_result.get("files", [])
    if files:
        texts = []
        for file_info in files:
            content = file_info.get("content", "")
            if content:
                texts.append(content)
        if texts:
            return "\n\n---\n\n".join(texts)

    return None


def should_chain_doc_to_lexguard(
    current_action: str,
    next_action: str,
) -> bool:
    """Determine if result chaining should occur from doc_search to lexguard.

    Chaining conditions:
    1. Current action is doc_search (search_docs_rag)
    2. Next action requires document_text (document_issue_tool)

    Note: Legal-relatedness is NOT checked here. That's determined by the
    original user query at planning time, not at execution time.
    """
    if current_action != "search_docs_rag":
        return False

    if next_action != "document_issue_tool":
        return False

    return True


def chain_document_text(
    next_plan_params: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    """Inject document_text from doc_search result into next plan's params.

    Returns a new params dict with document_text populated from the result.
    """
    document_text = extract_document_text_from_result(result)
    if document_text is None:
        return next_plan_params

    updated_params = dict(next_plan_params)
    updated_params["document_text"] = document_text
    return updated_params


__all__ = [
    "chain_document_text",
    "extract_document_text_from_result",
    "is_legal_query",
    "should_chain_doc_to_lexguard",
]
