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

from ..services.image_processor import process_comparison, load_file, encode_image_to_base64
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


def _build_crop_rect(crop_x, crop_y, crop_w, crop_h):
    """crop 파라미터를 검증 후 dict로 조립한다. 값이 없으면 None 반환."""
    values = [crop_x, crop_y, crop_w, crop_h]
    if not any(value is not None for value in values):
        return None

    if not all(value is not None for value in values):
        raise HTTPException(status_code=400, detail="crop_x, crop_y, crop_w, crop_h는 모두 함께 전달되어야 합니다.")

    if crop_w <= 0 or crop_h <= 0:
        raise HTTPException(status_code=400, detail="crop_w, crop_h는 0보다 커야 합니다.")

    if crop_x < 0 or crop_y < 0 or crop_w > 1 or crop_h > 1:
        raise HTTPException(status_code=400, detail="crop 좌표는 0-1 범위의 정규화 값이어야 합니다.")

    if crop_x + crop_w > 1 or crop_y + crop_h > 1:
        raise HTTPException(status_code=400, detail="crop 영역이 원본 범위를 벗어났습니다.")

    return {'x': crop_x, 'y': crop_y, 'width': crop_w, 'height': crop_h}


@router.post("/process", dependencies=[Depends(verify_token)])
async def compare_images(
    file1: UploadFile = File(...),
    file2: UploadFile = File(...),
    diff_threshold: int = Form(30),
    feature_count: int = Form(4000),
    alignment_algorithm: str = Form("orb"),
    page1: int = Form(0),
    page2: int = Form(0),
    # 품질 설정
    processing_resolution: int = Form(6000),  # 비교 연산용 최대 해상도 (4000-8000)
    output_resolution: int = Form(2000),       # 화면 출력용 최대 해상도 (1000-4000)
    output_quality: int = Form(85),            # JPEG 출력 품질 (50-100)
    pdf_dpi: int = Form(200),                  # PDF 변환 DPI (100-300)
    cad_mode: bool = Form(False),
    cad_line_width: float = Form(0.2),
    # CAD 모드 정렬 설정
    cad_align_tolerance: float = Form(0.22),   # 정렬 허용도 (0.10~0.30)
    cad_quality_threshold: float = Form(0.35), # 품질 기준 (0.20~0.50)
    # Optional crop parameters (정규화 좌표 0-1, 4개 모두 있을 때만 적용)
    crop_x: float = Form(None),
    crop_y: float = Form(None),
    crop_w: float = Form(None),
    crop_h: float = Form(None),
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

    crop_rect = _build_crop_rect(crop_x, crop_y, crop_w, crop_h)
    if crop_rect is not None:
        logger.debug("[req=%s] crop_rect active: %s", request_id, crop_rect)

    logger.debug(
        "[req=%s] /image-compare/process start: file1=%s (%s), file2=%s (%s), "
        "diff_threshold=%s, feature_count=%s, alignment_algorithm=%s, pages=(%s,%s), "
        "processing_resolution=%s, output_resolution=%s, "
        "output_quality=%s, pdf_dpi=%s, cad_mode=%s, cad_line_width=%s",
        request_id,
        file1.filename, file1.content_type,
        file2.filename, file2.content_type,
        diff_threshold, feature_count, alignment_algorithm,
        page1, page2,
        processing_resolution, output_resolution,
        output_quality, pdf_dpi, cad_mode, cad_line_width,
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
                alignment_algorithm,
                page1,
                page2,
                colors,
                processing_resolution=processing_resolution,
                output_resolution=output_resolution,
                output_quality=output_quality,
                pdf_dpi=pdf_dpi,
                cad_mode=cad_mode,
                cad_line_width=cad_line_width,
                cad_align_tolerance=cad_align_tolerance,
                cad_quality_threshold=cad_quality_threshold,
                crop_rect=crop_rect,
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


@router.post("/preview", dependencies=[Depends(verify_token)])
async def preview_file(
    file: UploadFile = File(...),
    page: int = Form(0),
    pdf_dpi: int = Form(150),
    cad_mode: bool = Form(False),
    cad_line_width: float = Form(0.2),
):
    """
    [POST] /image-compare/preview
    단일 파일의 지정 페이지를 저해상도(기본 DPI 150)로 래스터화하여 base64 이미지를 반환합니다.
    CropSelector UI에서 crop 영역 선택 시 미리보기 용도로 사용합니다.

    ⚠️ PDF의 경우 cad_mode/cad_line_width 가 실제 비교와 동일한 렌더링 조건을 적용합니다.
       (Stage1: apply_cad_mode_to_pdf 스트림 편집 → Stage2: fitz 래스터화)
    """
    request_id = uuid.uuid4().hex[:8]

    if file.content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file.content_type}. Allowed: {', '.join(_ALLOWED_CONTENT_TYPES)}"
        )

    async with image_processing_semaphore:
        try:
            file_bytes = await file.read()

            if len(file_bytes) > _MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=413,
                    detail=f"File too large: {len(file_bytes) / 1024 / 1024:.1f}MB (max 30MB)"
                )

            logger.debug(
                "[req=%s] /image-compare/preview: file=%s (%s) page=%s dpi=%s cad_mode=%s",
                request_id, file.filename, file.content_type, page, pdf_dpi, cad_mode,
            )

            loop = asyncio.get_running_loop()
            fn = functools.partial(
                load_file,
                file_bytes,
                file.content_type,
                page,
                pdf_dpi,
                cad_mode,
                cad_line_width,
                None,  # clip_rect=None — 전체 페이지 표시
            )
            img_bgr, total_pages, _ = await loop.run_in_executor(None, fn)

            b64 = encode_image_to_base64(img_bgr, format='PNG')
            h, w = img_bgr.shape[:2]
            logger.info("[req=%s] preview complete: %sx%s pages=%s", request_id, w, h, total_pages)
            return {
                "image_base64": b64,
                "width": w,
                "height": h,
                "pages": total_pages,
            }

        except HTTPException:
            raise
        except ValueError as e:
            logger.warning("[req=%s] preview invalid input: %s", request_id, e)
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error("[req=%s] preview failed: %s: %s", request_id, type(e).__name__, str(e), exc_info=True)
            raise HTTPException(status_code=500, detail=f"Preview failed: {str(e)}")
