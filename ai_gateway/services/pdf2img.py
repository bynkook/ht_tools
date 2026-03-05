"""
PDF → BGR numpy 배열 변환 라이브러리

PDF 파일을 BGR numpy 배열로 변환하는 범용 모듈.
다른 앱에서도 PDF 파일 읽기에 사용할 수 있다.

공개 API:
    - pdf_to_bgr(file_bytes, page_num, dpi)
        메인 진입점. fitz 직접 렌더링 1차 시도, 실패 시 PyPDF2 폴백.
    - fitz_page_to_bgr(page, dpi)
        fitz page 객체 → BGR numpy 배열. 단순 렌더링 헬퍼.

변환 전략:
    1차: fitz.open(stream=pdf_bytes) — 일반 PDF(비암호화)
    2차: PyPDF2 PdfWriter로 페이지 재기록(암호화 메타 제거) → fitz 렌더

PdfReader는 BytesIO 스트림 대신 임시 파일 경로로 초기화한다.
PyPDF2 3.x에서 BytesIO 스트림으로 암호화 PDF를 읽으면
EOF 탐색 실패가 발생하지만, 파일 경로 방식은 이 문제를 회피한다.
"""

import io
import logging
import os
import tempfile
from typing import Tuple

import cv2
import fitz
import numpy as np
from PyPDF2 import PdfReader, PdfWriter

logger = logging.getLogger(__name__)

_DEFAULT_DPI = 200

# 단일 fitz 픽스맵 허용 상한 (RGB uint8, 3채널 기준).
# 이 값을 초과하면 get_pixmap() 호출 전에 MemoryError를 발생시켜
# C 레벨 OOM 및 프로세스 강제 종료를 방지한다.
_MAX_PIXMAP_BYTES = 400 * 1024 * 1024  # 400 MB


def _single_page_bytes(reader: PdfReader, page_index: int) -> bytes:
    """
    PdfReader의 특정 페이지만 포함하는 PDF bytes 반환.
    PdfWriter를 통해 재기록하면 암호화 메타데이터가 제거된다.
    """
    writer = PdfWriter()
    writer.add_page(reader.pages[page_index])
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _estimate_pixmap_bytes(page, dpi: int) -> int:
    """fitz 렌더 전 예상 픽스맵 바이트 수 산출 (RGB uint8, 3채널 기준)."""
    zoom = dpi / 72
    w = int(page.rect.width * zoom)
    h = int(page.rect.height * zoom)
    return w * h * 3


def fitz_page_to_bgr(page, dpi: int = _DEFAULT_DPI) -> np.ndarray:
    """
    fitz page 객체를 BGR numpy 배열로 변환.

    Args:
        page: fitz.Page 객체
        dpi: 렌더링 해상도 (기본 200)

    Returns:
        BGR numpy 배열
    """
    zoom = dpi / 72
    logger.debug("[pdf2img] fitz_page_to_bgr start: page=%s dpi=%s zoom=%.3f", page.number, dpi, zoom)

    # --- 메모리 사전 체크: C 레벨 OOM → 프로세스 강제 종료 방지 ---
    estimated_bytes = _estimate_pixmap_bytes(page, dpi)
    logger.debug(
        "[pdf2img] fitz_page_to_bgr estimated: %.1fMB (limit %.0fMB)",
        estimated_bytes / 1024 / 1024,
        _MAX_PIXMAP_BYTES / 1024 / 1024,
    )
    if estimated_bytes > _MAX_PIXMAP_BYTES:
        raise MemoryError(
            f"픽스맵 예상 크기 {estimated_bytes / 1024 / 1024:.0f}MB가 "
            f"허용 한도 {_MAX_PIXMAP_BYTES / 1024 / 1024:.0f}MB를 초과합니다 "
            f"(dpi={dpi}). pdf_dpi 또는 처리 해상도를 낮춰 주세요."
        )
    # ---------------------------------------------------------------

    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
    logger.debug(
        "[pdf2img] fitz_page_to_bgr done: size=%sx%s bytes=%.2fMB",
        pix.width,
        pix.height,
        img_bgr.nbytes / 1024 / 1024,
    )
    return img_bgr


def _pypdf2_page_to_bgr(
    file_bytes: bytes,
    page_num: int = 0,
    dpi: int = _DEFAULT_DPI,
) -> Tuple[np.ndarray, int]:
    """
    PyPDF2 경로: 암호화 PDF에서 특정 페이지를 BGR numpy 배열로 변환.

    PdfWriter로 페이지를 재기록하여 암호화 메타데이터를 제거한 뒤
    fitz로 래스터라이즈한다.
    """
    tmp_path = None
    try:
        logger.debug(
            "[pdf2img] PyPDF2 fallback start: page_num=%s dpi=%s input_size=%.2fMB",
            page_num,
            dpi,
            len(file_bytes) / 1024 / 1024,
        )
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        logger.debug("[pdf2img] temp file created: %s", tmp_path)

        try:
            reader = PdfReader(tmp_path, strict=False)
        except Exception as e:
            logger.error(f"[pdf2img] PdfReader 초기화 실패: {type(e).__name__}: {e}")
            raise ValueError(f"PDF 읽기 실패: {e}") from e

        total_pages = len(reader.pages)
        logger.debug("[pdf2img] PdfReader loaded: total_pages=%s", total_pages)
        if total_pages == 0:
            raise ValueError("PDF에 페이지가 없습니다.")

        if page_num >= total_pages:
            page_num = 0
            logger.debug("[pdf2img] page_num out of range, reset to 0")

        page_pdf_bytes = _single_page_bytes(reader, page_num)
        logger.debug("[pdf2img] single-page bytes extracted: page=%s size=%s", page_num, len(page_pdf_bytes))

        with fitz.open(stream=page_pdf_bytes, filetype="pdf") as doc:
            logger.debug("[pdf2img] fallback fitz open success: page_count=%s", doc.page_count)
            img_bgr = fitz_page_to_bgr(doc.load_page(0), dpi)

        return img_bgr, total_pages

    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
                logger.debug("[pdf2img] temp file removed: %s", tmp_path)
            except OSError as e:
                logger.warning("[pdf2img] temp file cleanup failed: %s: %s", type(e).__name__, e)


def pdf_to_bgr(
    file_bytes: bytes,
    page_num: int = 0,
    dpi: int = _DEFAULT_DPI,
) -> Tuple[np.ndarray, int]:
    """
    PDF bytes → BGR numpy 배열 변환 (메인 진입점).

    1차: fitz 직접 렌더링 (일반 PDF)
    2차: PyPDF2 폴백 (암호화 PDF 등 fitz 실패 시)

    Args:
        file_bytes: PDF 파일 바이트
        page_num: 요청 페이지 번호 (0-based, 범위 초과 시 0으로 보정)
        dpi: 렌더링 해상도 (기본 200)

    Returns:
        (BGR numpy 배열, 전체 페이지 수)

    Raises:
        ValueError: 변환 실패 시
    """
    logger.debug(
        "[pdf2img] pdf_to_bgr start: page_num=%s dpi=%s input_size=%.2fMB",
        page_num,
        dpi,
        len(file_bytes) / 1024 / 1024,
    )

    _fallback_dpi = dpi

    # 1차: fitz 직접 렌더링
    try:
        with fitz.open(stream=file_bytes, filetype="pdf") as doc:
            total_pages = doc.page_count
            logger.debug("[pdf2img] fitz direct open success: total_pages=%s", total_pages)

            if page_num >= total_pages:
                page_num = 0
                logger.debug("[pdf2img] fitz direct page_num reset to 0")

            img_bgr = fitz_page_to_bgr(doc[page_num], dpi)

            return img_bgr, total_pages

    except MemoryError as e:
        # 픽스맵 크기 초과: 폴백에서 DPI를 절반으로 줄여 메모리 압박 완화
        _fallback_dpi = max(72, dpi // 2)
        logger.warning(
            "[pdf2img] fitz 렌더 메모리 초과, 폴백 DPI 축소: %s → %s (원인: %s)",
            dpi,
            _fallback_dpi,
            e,
        )
    except Exception as e:
        logger.warning(
            "[pdf2img] fitz 직접 로드 실패, PyPDF2 폴백 시도 (원인: %s: %s)",
            type(e).__name__,
            e,
        )

    # 2차: PyPDF2 폴백 (메모리 초과 시 축소된 DPI 적용)
    try:
        if _fallback_dpi < dpi:
            logger.info("[pdf2img] 폴백 DPI 축소 적용: %s → %s", dpi, _fallback_dpi)
        img_bgr, total_pages = _pypdf2_page_to_bgr(file_bytes, page_num=page_num, dpi=_fallback_dpi)
        logger.info(
            "[pdf2img] PyPDF2 폴백 성공 — 페이지 %s/%s (dpi=%s)",
            page_num + 1,
            total_pages,
            _fallback_dpi,
        )
        return img_bgr, total_pages
    except Exception as fallback_e:
        logger.error("[pdf2img] fitz + PyPDF2 모두 실패: %s: %s", type(fallback_e).__name__, fallback_e)
        raise ValueError(f"PDF 변환 실패: {fallback_e}") from fallback_e
