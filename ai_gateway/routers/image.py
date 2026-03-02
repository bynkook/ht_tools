"""
FastAPI Router: Image Compare
이미지/PDF/TIFF 비교 엔드포인트
"""

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
import asyncio
import logging

from ..services.image_processor import process_comparison
from ..dependencies import verify_token

router = APIRouter()
logger = logging.getLogger(__name__)

# Semaphore: 동시 처리 제한 (최대 5개)
image_processing_semaphore = asyncio.Semaphore(5)


@router.post("/process", dependencies=[Depends(verify_token)])
async def compare_images(
    file1: UploadFile = File(...),
    file2: UploadFile = File(...),
    mode: str = Form("difference"),
    diff_threshold: int = Form(30),
    feature_count: int = Form(4000),
    page1: int = Form(0),
    page2: int = Form(0),
    bin_threshold: int = Form(200),
    # Optional color parameters
    color_diff_file1: str = Form(None),
    color_diff_file2: str = Form(None),
    color_diff_common: str = Form(None),
    color_overlay_file1: str = Form(None),
    color_overlay_file2: str = Form(None),
):
    """
    [POST] /image-compare/process
    두 이미지/PDF/TIFF를 비교하여 차이점을 시각화합니다.
    """
    # Construct colors dictionary
    colors = {}
    if color_diff_file1: colors['diff_file1'] = color_diff_file1
    if color_diff_file2: colors['diff_file2'] = color_diff_file2
    if color_diff_common: colors['diff_common'] = color_diff_common
    if color_overlay_file1: colors['overlay_file1'] = color_overlay_file1
    if color_overlay_file2: colors['overlay_file2'] = color_overlay_file2

    # 파일 크기 제한 (30MB)
    MAX_FILE_SIZE = 30 * 1024 * 1024
    
    # MIME 타입 검증
    ALLOWED_TYPES = [
        'image/jpeg', 
        'image/png', 
        'image/gif', 
        'application/pdf',
        'image/tiff',
        'image/tif'
    ]
    
    if file1.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type for file1: {file1.content_type}. Allowed: {', '.join(ALLOWED_TYPES)}"
        )
    
    if file2.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type for file2: {file2.content_type}. Allowed: {', '.join(ALLOWED_TYPES)}"
        )
    
    # Semaphore로 동시 처리 제한
    async with image_processing_semaphore:
        try:
            logger.info(f"Image comparison started: {file1.filename} vs {file2.filename}")
            
            # 파일 읽기
            file1_bytes = await file1.read()
            file2_bytes = await file2.read()
            
            # 크기 검증
            if len(file1_bytes) > MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=413,
                    detail=f"File1 too large: {len(file1_bytes) / 1024 / 1024:.1f}MB (max 30MB)"
                )
            
            if len(file2_bytes) > MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=413,
                    detail=f"File2 too large: {len(file2_bytes) / 1024 / 1024:.1f}MB (max 30MB)"
                )
            
            # CPU-bound 작업을 별도 스레드에서 실행 (이벤트 루프 블록 방지)
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,  # ThreadPoolExecutor 사용
                process_comparison,
                file1_bytes,
                file1.content_type,
                file2_bytes,
                file2.content_type,
                mode,
                diff_threshold,
                feature_count,
                page1,
                page2,
                bin_threshold,
                colors # Pass colors dict
            )
            
            logger.info(f"Image comparison completed: {result['metadata']['result_size']}")
            return result
        
        except ValueError as e:
            # 사용자 입력 오류 (파일 형식, 페이지 번호 등)
            logger.warning(f"Invalid input: {str(e)}")
            raise HTTPException(status_code=400, detail=str(e))
        
        except Exception as e:
            # 서버 내부 오류
            logger.error(f"Image comparison failed: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Image processing failed: {str(e)}"
            )
