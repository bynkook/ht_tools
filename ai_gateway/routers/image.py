"""
FastAPI Router: Image Compare
이미지/PDF/TIFF 비교 엔드포인트
"""

import asyncio
import functools
import logging
import time
import uuid

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends

from ..services.image_processor import process_comparison
from ..dependencies import verify_token

router = APIRouter()
logger = logging.getLogger(__name__)

# Semaphore: 동시 처리 제한 (최대 5개)
image_processing_semaphore = asyncio.Semaphore(5)

_MAX_FILE_SIZE = 30 * 1024 * 1024  # 30 MB
_ALLOWED_CONTENT_TYPES = frozenset([
    'image/jpeg', 'image/png', 'image/gif',
    'application/pdf', 'image/tiff', 'image/tif',
])


@router.post("/process", dependencies=[Depends(verify_token)])
async def compare_images(
    file1: UploadFile = File(...),
    file2: UploadFile = File(...),
    diff_threshold: int = Form(30),
    feature_count: int = Form(4000),
    page1: int = Form(0),
    page2: int = Form(0),
    bin_threshold: int = Form(200),
    # 품질 설정
    processing_resolution: int = Form(6000),  # 비교 연산용 최대 해상도 (4000-8000)
    output_resolution: int = Form(2000),       # 화면 출력용 최대 해상도 (1000-4000)
    output_quality: int = Form(85),            # JPEG 출력 품질 (50-100)
    pdf_dpi: int = Form(200),                  # PDF 변환 DPI (100-300)
    # Optional color parameters (모든 모드에서 diff 3색 공통 사용)
    color_diff_file1: str = Form(None),
    color_diff_file2: str = Form(None),
    color_diff_common: str = Form(None),
):
    """
    [POST] /image-compare/process
    두 이미지/PDF/TIFF를 비교하여 차이점을 시각화합니다.
    """
    request_id = uuid.uuid4().hex[:8]

    # MIME 타입 검증
    if file1.content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type for file1: {file1.content_type}. Allowed: {', '.join(_ALLOWED_CONTENT_TYPES)}"
        )
    if file2.content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type for file2: {file2.content_type}. Allowed: {', '.join(_ALLOWED_CONTENT_TYPES)}"
        )

    colors = {}
    if color_diff_file1:  colors['diff_file1']  = color_diff_file1
    if color_diff_file2:  colors['diff_file2']  = color_diff_file2
    if color_diff_common: colors['diff_common'] = color_diff_common

    logger.debug(
        "[req=%s] /image-compare/process start: file1=%s (%s), file2=%s (%s), "
        "diff_threshold=%s, feature_count=%s, pages=(%s,%s), "
        "bin_threshold=%s, processing_resolution=%s, output_resolution=%s, "
        "output_quality=%s, pdf_dpi=%s",
        request_id,
        file1.filename, file1.content_type,
        file2.filename, file2.content_type,
        diff_threshold, feature_count,
        page1, page2,
        bin_threshold, processing_resolution, output_resolution,
        output_quality, pdf_dpi,
    )

    # Semaphore로 동시 처리 제한
    async with image_processing_semaphore:
        try:
            logger.info("[req=%s] Image comparison started: %s vs %s", request_id, file1.filename, file2.filename)

            # 파일 읽기 + 크기 검증
            file1_bytes = await file1.read()
            file2_bytes = await file2.read()
            logger.debug(
                "[req=%s] Read upload bytes: file1=%.2fMB, file2=%.2fMB",
                request_id,
                len(file1_bytes) / 1024 / 1024,
                len(file2_bytes) / 1024 / 1024,
            )

            if len(file1_bytes) > _MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=413,
                    detail=f"File1 too large: {len(file1_bytes) / 1024 / 1024:.1f}MB (max 30MB)"
                )
            if len(file2_bytes) > _MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=413,
                    detail=f"File2 too large: {len(file2_bytes) / 1024 / 1024:.1f}MB (max 30MB)"
                )
            
            # CPU-bound 작업을 별도 스레드에서 실행 (이벤트 루프 블록 방지)
            loop = asyncio.get_running_loop()
            fn = functools.partial(
                process_comparison,
                file1_bytes,
                file1.content_type,
                file2_bytes,
                file2.content_type,
                diff_threshold,
                feature_count,
                page1,
                page2,
                bin_threshold,
                colors,
                processing_resolution=processing_resolution,
                output_resolution=output_resolution,
                output_quality=output_quality,
                pdf_dpi=pdf_dpi,
                request_id=request_id,
            )

            executor_start = time.perf_counter()
            logger.debug("[req=%s] run_in_executor submit", request_id)
            result = await loop.run_in_executor(None, fn)
            elapsed_ms = (time.perf_counter() - executor_start) * 1000
            logger.debug(
                "[req=%s] run_in_executor returned in %.1fms",
                request_id,
                elapsed_ms,
            )

            logger.info(
                "[req=%s] Image comparison completed: processing=%s, output=%s",
                request_id,
                result['metadata']['processing_size'],
                result['metadata']['result_size'],
            )
            return result
        
        except ValueError as e:
            # 사용자 입력 오류 (파일 형식, 페이지 번호 등)
            logger.warning("[req=%s] Invalid input: %s: %s", request_id, type(e).__name__, str(e))
            raise HTTPException(status_code=400, detail=str(e))
        
        except Exception as e:
            # 서버 내부 오류
            logger.error("[req=%s] Image comparison failed: %s: %s", request_id, type(e).__name__, str(e), exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Image processing failed: {str(e)}"
            )
