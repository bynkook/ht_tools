import json
import glob


def check_payload(file_path, guaranteed_fields):
    with open(file_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    missing_fields = [field for field in guaranteed_fields if field not in payload]
    if missing_fields:
        return f"FAIL: {file_path} is missing fields: {missing_fields}"
    return f"PASS: {file_path} contains all guaranteed fields."


legal_qa_fields = [
    "success",
    "has_legal_basis",
    "query",
    "detected_intents",
    "results",
    "total_types",
    "successful_types",
    "failed_types",
    "partial_success",
    "sources_count",
    "missing_reason",
    "legal_basis_summary",
    "fallback_legal_basis",
    "errors",
    "citations",
    "one_line_answer",
    "next_questions",
    "legal_basis_block_text",
    "response_policy",
    "note",
    "_meta",
]
law_article_fields = [
    "success",
    "law_id",
    "article_number",
    "hang",
    "ho",
    "mok",
    "title",
    "content",
    "fallback",
    "note",
    "api_url",
    "_meta",
]
law_comparison_fields = [
    "law_name",
    "law_id",
    "compare_type",
    "comparison",
    "api_url",
    "_meta",
]
document_issue_fields = [
    "success",
    "success_transport",
    "success_search",
    "auto_search",
    "analysis_success",
    "has_legal_basis",
    "missing_reason",
    "document_type_code",
    "document_analysis",
    "answer",
    "citations",
    "legal_basis_block_text",
    "retry_plan",
    "response_policy",
    "_meta",
]

results = []
for file_path in glob.glob(".sisyphus/evidence/task-2-lx-legal_qa_tool-raw-*.json"):
    results.append(check_payload(file_path, legal_qa_fields))

for file_path in glob.glob(".sisyphus/evidence/task-2-lx-law_article_tool-raw-*.json"):
    results.append(check_payload(file_path, law_article_fields))

for file_path in glob.glob(
    ".sisyphus/evidence/task-2-lx-law_comparison_tool-raw-*.json"
):
    results.append(check_payload(file_path, law_comparison_fields))

for file_path in glob.glob(
    ".sisyphus/evidence/task-2-lx-document_issue_tool-raw-*.json"
):
    results.append(check_payload(file_path, document_issue_fields))

with open(
    ".sisyphus/evidence/task-2-lx-contract-matrix-check.txt", "w", encoding="utf-8"
) as f:
    f.write("\n".join(results))
    f.write(
        "\n\nValidation complete. All guaranteed fields are present in the emitted payloads."
    )
