import json
import urllib.request


def call_mcp(tool_name, arguments, output_file):
    url = "http://127.0.0.1:9099/mcp"
    data = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
    )
    try:
        with urllib.request.urlopen(req) as response:
            result = response.read().decode("utf-8")
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(result)
            print(f"Success: {output_file}")
    except Exception as e:
        print(f"Error calling {tool_name}: {e}")


call_mcp(
    "legal_qa_tool",
    {"query": "연장근로 한도 위반 시 처벌 규정"},
    ".sisyphus/evidence/task-2-lx-legal_qa_tool-raw-1.json",
)
call_mcp(
    "legal_qa_tool",
    {"query": "개인정보보호법 CCTV 설치 동의 요건"},
    ".sisyphus/evidence/task-2-lx-legal_qa_tool-raw-2.json",
)

call_mcp(
    "law_article_tool",
    {"law_name": "건축법", "article_number": "3"},
    ".sisyphus/evidence/task-2-lx-law_article_tool-raw-1.json",
)
call_mcp(
    "law_article_tool",
    {"law_name": "건축법", "article_number": "3", "hang": "1", "ho": "2", "mok": "다"},
    ".sisyphus/evidence/task-2-lx-law_article_tool-raw-2.json",
)

call_mcp(
    "law_comparison_tool",
    {"law_name": "근로기준법", "compare_type": "신구법"},
    ".sisyphus/evidence/task-2-lx-law_comparison_tool-raw-1.json",
)
call_mcp(
    "law_comparison_tool",
    {"law_name": "개인정보보호법", "compare_type": "신구법"},
    ".sisyphus/evidence/task-2-lx-law_comparison_tool-raw-2.json",
)

call_mcp(
    "document_issue_tool",
    {
        "document_text": "제1조(목적) 본 계약은 프리랜서 용역 제공에 관한 사항을 정한다.\n제2조(보수) 월 200만원을 지급한다.\n제3조(지식재산권) 작업 결과물의 저작권은 갑에게 귀속된다.",
        "auto_search": False,
    },
    ".sisyphus/evidence/task-2-lx-document_issue_tool-raw-1.json",
)
call_mcp(
    "document_issue_tool",
    {
        "document_text": "제1조(임대차 목적물) 서울시 강남구 소재 아파트 101호\n제2조(임대차 기간) 2024년 1월 1일부터 2025년 12월 31일까지\n제3조(보증금) 보증금 3억원, 월세 없음\n제4조(특약) 임차인은 임대인 동의 없이 전대할 수 없다.",
        "auto_search": False,
    },
    ".sisyphus/evidence/task-2-lx-document_issue_tool-raw-2.json",
)
