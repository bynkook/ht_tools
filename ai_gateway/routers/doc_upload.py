"""
doc_upload.py — 문서 업로드 엔드포인트

POST /doc-converter/upload
  - .pdf, .docx, .pptx, .doc, .xlsx, .xls → 변환 큐에 추가 (BackgroundTask)
  - .txt, .md → 즉시 DOCS_DIR에 저장 (변환 없음)
"""

import logging
import pathlib
import uuid
from typing import Annotated

import toml
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from ..dependencies import verify_token
from ..services.doc_converter import (
    DJANGO_BASE_URL,
    process_conversion_job,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# ── 설정 로드 ──────────────────────────────────────────────────────────────────
_BASE_DIR = pathlib.Path(__file__).resolve().parent.parent.parent
_SECRETS_PATH = _BASE_DIR / "secrets.toml"


def _load_doc_config() -> dict:
    with open(_SECRETS_PATH, "r", encoding="utf-8") as f:
        secrets = toml.load(f)
    cfg = secrets.get("doc_converter", {})
    return {
        "dev_marker_dir": pathlib.Path(cfg.get("dev_marker_dir", "")),
        "doc_data_dir": pathlib.Path(
            cfg.get("doc_data_dir", str(pathlib.Path.home() / "doc_data"))
        ),
        "force_ocr": bool(cfg.get("force_ocr", False)),
        "internal_secret": str(cfg.get("internal_secret", "")),
    }


_DOC_CFG = _load_doc_config()

# 업로드 임시 저장 디렉토리 (변환 완료 후 자동 삭제)
_TEMP_DIR: pathlib.Path = _BASE_DIR / "media" / "doc_uploader_temp"
_TEMP_DIR.mkdir(parents=True, exist_ok=True)

# ── 지원 확장자 ────────────────────────────────────────────────────────────────
_SUPPORTED_EXT = {
    ".pdf",
    ".doc", ".docx",
    ".ppt", ".pptx",
    ".xls", ".xlsx",
    ".txt", ".md",
}
# 변환 없이 바로 저장 가능한 텍스트 형식
_PLAIN_EXT = {".txt", ".md"}
# subprocess 변환이 필요한 Word/Excel/PPT 형식
_WORD_EXT = {".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"}

_MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


async def _create_django_job(
    http_client,
    original_filename: str,
    category_name: str,
    initial_status: str,
) -> dict:
    """Django 내부 엔드포인트로 ConversionJob 레코드 생성."""
    try:
        resp = await http_client.post(
            f"{DJANGO_BASE_URL}/api/doc-uploader/jobs/internal/",
            json={
                "original_filename": original_filename,
                "category_name": category_name,
                "status": initial_status,
            },
            headers={"X-Internal-Secret": _DOC_CFG["internal_secret"]},
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.error("Django job creation failed: %s", exc)
        return {}


@router.post("/upload")
async def upload_document(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    category: str = Form(...),
    token: str = Depends(verify_token),
):
    """
    문서 파일을 업로드하고 변환 작업을 대기열에 추가합니다.

    지원 형식: PDF, Word(docx/doc), PowerPoint(pptx/ppt), Excel(xlsx/xls), TXT, MD
    - .txt / .md  → 즉시 DOCS_DIR/<category>/<stem>.md 로 저장 (변환 없음)
    - 나머지       → BackgroundTask로 변환 후 저장
    """
    filename = file.filename or "unknown"
    ext = pathlib.Path(filename).suffix.lower()
    stem = pathlib.Path(filename).stem

    # ── 입력 검증 ──────────────────────────────────────────────────────────────
    if ext not in _SUPPORTED_EXT:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 파일 형식입니다: '{ext}'. "
                   f"지원 형식: {', '.join(sorted(_SUPPORTED_EXT))}",
        )

    # category 경로 조작 방지
    category = category.strip()
    if not category or "/" in category or "\\" in category or ".." in category:
        raise HTTPException(status_code=400, detail="유효하지 않은 카테고리명입니다.")

    content = await file.read()

    if len(content) > _MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"파일 크기가 허용 한도({_MAX_FILE_SIZE_BYTES // 1024 // 1024}MB)를 초과합니다.",
        )

    output_dir: pathlib.Path = _DOC_CFG["doc_data_dir"] / category
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── .txt / .md: 즉시 저장 ──────────────────────────────────────────────────
    if ext in _PLAIN_EXT:
        dest_file = output_dir / f"{stem}.md"
        text = content.decode("utf-8", errors="replace")
        dest_file.write_text(text, encoding="utf-8")
        logger.info("Direct save: %s → %s", filename, dest_file)

        job_data = await _create_django_job(
            request.app.state.http_client,
            original_filename=filename,
            category_name=category,
            initial_status="completed",
        )
        return JSONResponse({
            "job_id": job_data.get("id"),
            "status": "completed",
            "message": f"'{filename}'이(가) 저장되었습니다.",
        })

    # ── PDF / Office: 변환 큐 등록 ────────────────────────────────────────────
    # 임시 파일 저장 (고유 이름으로 충돌 방지)
    temp_name = f"{uuid.uuid4().hex}_{filename}"
    temp_file = _TEMP_DIR / temp_name
    temp_file.write_bytes(content)

    # Django job 생성
    job_data = await _create_django_job(
        request.app.state.http_client,
        original_filename=filename,
        category_name=category,
        initial_status="waiting",
    )
    callback_token = job_data.get("callback_token")

    if not callback_token:
        temp_file.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="변환 작업 생성에 실패했습니다. 잠시 후 다시 시도하세요.")

    # BackgroundTask 등록
    background_tasks.add_task(
        process_conversion_job,
        http_client=request.app.state.http_client,
        callback_token=callback_token,
        temp_file=temp_file,
        category=category,
        original_filename=filename,
        dev_marker_dir=_DOC_CFG["dev_marker_dir"],
        doc_data_dir=_DOC_CFG["doc_data_dir"],
        internal_secret=_DOC_CFG["internal_secret"],
        force_ocr=_DOC_CFG["force_ocr"],
    )

    logger.info("Queued conversion job: %s → category '%s'", filename, category)
    return JSONResponse({
        "job_id": job_data.get("id"),
        "status": "waiting",
        "message": f"'{filename}' 변환 작업이 대기열에 추가되었습니다.",
    })
