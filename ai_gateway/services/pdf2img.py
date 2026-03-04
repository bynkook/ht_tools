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
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    return cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)


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
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        try:
            reader = PdfReader(tmp_path, strict=False)
        except Exception as e:
            logger.error(f"[pdf2img] PdfReader 초기화 실패: {e}")
            raise ValueError(f"PDF 읽기 실패: {e}") from e

        total_pages = len(reader.pages)
        if total_pages == 0:
            raise ValueError("PDF에 페이지가 없습니다.")

        if page_num >= total_pages:
            page_num = 0

        page_pdf_bytes = _single_page_bytes(reader, page_num)

        with fitz.open(stream=page_pdf_bytes, filetype="pdf") as doc:
            img_bgr = fitz_page_to_bgr(doc.load_page(0), dpi)

        return img_bgr, total_pages

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


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
    # 1차: fitz 직접 렌더링
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        total_pages = doc.page_count

        if page_num >= total_pages:
            page_num = 0

        img_bgr = fitz_page_to_bgr(doc[page_num], dpi)
        doc.close()

        return img_bgr, total_pages

    except Exception as e:
        logger.warning(f"[pdf2img] fitz 직접 로드 실패, PyPDF2 폴백 시도 (원인: {e})")

    # 2차: PyPDF2 폴백
    try:
        img_bgr, total_pages = _pypdf2_page_to_bgr(file_bytes, page_num=page_num, dpi=dpi)
        logger.info(f"[pdf2img] PyPDF2 폴백 성공 — 페이지 {page_num + 1}/{total_pages}")
        return img_bgr, total_pages
    except Exception as fallback_e:
        logger.error(f"[pdf2img] fitz + PyPDF2 모두 실패: {fallback_e}")
        raise ValueError(f"PDF 변환 실패: {fallback_e}") from fallback_e
