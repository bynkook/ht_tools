"""
PDF → BGR numpy 배열 변환 라이브러리

PDF 파일을 BGR numpy 배열로 변환하는 범용 모듈.
다른 앱에서도 PDF 파일 읽기에 사용할 수 있다.

공개 API:
    - pdf_to_bgr(file_bytes, page_num, dpi)
        메인 진입점. 모든 PDF를 공통 2-step 파이프라인으로 처리한다.

변환 전략:
    1차: PyPDF2 PdfWriter로 단일 페이지 재기록(메타데이터 정리)
    2차: fitz로 최종 래스터 렌더링

PdfReader는 BytesIO 스트림 대신 임시 파일 경로로 초기화한다.
PyPDF2 3.x에서 BytesIO 스트림으로 암호화 PDF를 읽으면
EOF 탐색 실패가 발생하지만, 파일 경로 방식은 이 문제를 회피한다.
"""

import io
import logging
import os
import re
import tempfile
from typing import Set, Tuple

import cv2
import fitz
import numpy as np
import pikepdf
from PyPDF2 import PdfReader, PdfWriter

logger = logging.getLogger(__name__)

_DEFAULT_DPI = 200

# 단일 fitz 픽스맵 허용 상한 (RGB uint8, 3채널 기준).
# 이 값을 초과하면 get_pixmap() 호출 전에 MemoryError를 발생시켜
# C 레벨 OOM 및 프로세스 강제 종료를 방지한다.
_MAX_PIXMAP_BYTES = 400 * 1024 * 1024  # 400 MB


# ----------------------------------------------------------------------
# 2️⃣ CAD‑mode 전용 PDF 스트림 편집 함수
# ----------------------------------------------------------------------
def _replace_line_width_in_stream(
    stream_obj,
    pattern: re.Pattern,
    replacement: bytes,
    location: str,
) -> int:
    """
    단일 스트림 객체 내 line-width 연산자를 교체한다.

    Returns: 교체된 연산자 개수
    """
    try:
        raw = stream_obj.read_bytes()
    except Exception as e:
        logger.warning("[cad_mode] %s 스트림 읽기 실패: %s", location, e)
        return 0

    replaced, n_subs = pattern.subn(replacement, raw)
    if n_subs > 0:
        stream_obj.write(replaced)
        logger.debug("[cad_mode] %s: line-width %d개 교체", location, n_subs)
    return n_subs


def _object_cache_key(pdf_obj) -> tuple:
    """pikepdf 객체의 방문 추적용 키를 반환한다."""
    objgen = getattr(pdf_obj, "objgen", None)
    if objgen is not None:
        return tuple(objgen)
    return (id(pdf_obj), 0)


def _replace_line_width_in_form_xobjects(
    resource_owner,
    pattern: re.Pattern,
    replacement: bytes,
    location: str,
    visited: Set[tuple],
) -> int:
    """현재 리소스 소유자 아래의 Form XObject를 재귀 순회하며 line-width를 교체한다."""
    if "/Resources" not in resource_owner or "/XObject" not in resource_owner["/Resources"]:
        return 0

    total_subs = 0
    xobjects = resource_owner["/Resources"]["/XObject"]
    for name in list(xobjects.keys()):
        xobj = xobjects[name]
        subtype = xobj.get("/Subtype")
        if subtype != pikepdf.Name.Form:
            continue

        cache_key = _object_cache_key(xobj)
        if cache_key in visited:
            logger.debug("[cad_mode] %s XObject/%s 재방문 스킵", location, name)
            continue
        visited.add(cache_key)

        child_location = f"{location} XObject/{name}"
        total_subs += _replace_line_width_in_stream(
            xobj,
            pattern,
            replacement,
            child_location,
        )
        total_subs += _replace_line_width_in_form_xobjects(
            xobj,
            pattern,
            replacement,
            child_location,
            visited,
        )

    return total_subs


def apply_cad_mode_to_pdf(pdf_bytes: bytes, line_width: float = 0.2) -> bytes:
    """
    PDF 바이트 스트림을 읽어 모든 라인 굵기 연산자(`w`) 를 지정한 값으로 교체한다.
    페이지 Contents 및 Form XObject 내부 스트림 모두 처리한다.

    Parameters
    ----------
    pdf_bytes : bytes
        원본 PDF 파일 전체 바이트.
    line_width : float, default 0.2
        라인 굵기로 강제 지정할 값 (PDF 단위는 point, 1 pt ≈ 0.352 mm).
        CAD 도면용 thin line은 0.1~0.3 권장.

    Returns
    -------
    bytes
        라인 굵기가 교체된 새로운 PDF 바이트 스트림.
    """
    logger.debug("[cad_mode] PDF 스트림 편집 시작 - 목표 라인 굵기: %s pt", line_width)

    # `w` 연산자(setlinewidth): <숫자> w 형식, `wi` 등 다른 연산자와 혼동 방지를 위해
    # `\b` word boundary로 토큰 끝을 확인한다.
    pattern = re.compile(rb"(?:[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s+w\b")
    replacement = f"{line_width:g} w".encode("ascii")

    total_contents_subs = 0
    total_xobject_subs = 0

    with pikepdf.open(io.BytesIO(pdf_bytes)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            # ─────────────────────────────────────────────────────────────
            # 1) 페이지 /Contents 스트림 수정
            # ─────────────────────────────────────────────────────────────
            if "/Contents" in page:
                contents = page["/Contents"]
                stream_list = list(contents) if isinstance(contents, pikepdf.Array) else [contents]
                for i, stream_obj in enumerate(stream_list):
                    location = f"페이지 {page_number} Contents[{i}]"
                    total_contents_subs += _replace_line_width_in_stream(
                        stream_obj, pattern, replacement, location
                    )

            # ─────────────────────────────────────────────────────────────
            # 2) Form XObject 내부 스트림 수정 (CAD PDF의 실제 도면이 여기 있음)
            # ─────────────────────────────────────────────────────────────
            visited_forms: Set[tuple] = set()
            total_xobject_subs += _replace_line_width_in_form_xobjects(
                page,
                pattern,
                replacement,
                f"페이지 {page_number}",
                visited_forms,
            )

        # 3) 수정된 PDF를 메모리 바이트로 반환
        out_io = io.BytesIO()
        pdf.save(out_io)
        logger.info(
            "[cad_mode] PDF 라인 굵기 교체 완료 - 페이지: %d, Contents: %d개, Form XObject(재귀): %d개",
            len(pdf.pages),
            total_contents_subs,
            total_xobject_subs,
        )
        result_bytes = out_io.getvalue()

    return result_bytes


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


def _estimate_pixmap_bytes(page, dpi: int, clip_rect: dict = None) -> int:
    """fitz 렌더 전 예상 픽스맵 바이트 수 산출 (RGB uint8, 3채널 기준)."""
    zoom = dpi / 72
    if clip_rect is not None:
        pr = page.rect
        w = int((clip_rect['width'] * pr.width) * zoom)
        h = int((clip_rect['height'] * pr.height) * zoom)
    else:
        w = int(page.rect.width * zoom)
        h = int(page.rect.height * zoom)
    return w * h * 3


def _fitz_page_to_bgr(page, dpi: int = _DEFAULT_DPI, clip_rect: dict = None) -> np.ndarray:
    """공통 PDF 파이프라인 내부에서 fitz page 객체를 BGR numpy 배열로 렌더링한다."""
    zoom = dpi / 72
    logger.debug(
        "[pdf2img] render start: page=%s dpi=%s zoom=%.3f clip=%s",
        page.number,
        dpi,
        zoom,
        clip_rect is not None,
    )

    estimated_bytes = _estimate_pixmap_bytes(page, dpi, clip_rect=clip_rect)
    logger.debug(
        "[pdf2img] render estimated: %.1fMB (limit %.0fMB)",
        estimated_bytes / 1024 / 1024,
        _MAX_PIXMAP_BYTES / 1024 / 1024,
    )
    if estimated_bytes > _MAX_PIXMAP_BYTES:
        raise MemoryError(
            f"픽스맵 예상 크기 {estimated_bytes / 1024 / 1024:.0f}MB가 "
            f"허용 한도 {_MAX_PIXMAP_BYTES / 1024 / 1024:.0f}MB를 초과합니다 "
            f"(dpi={dpi}). pdf_dpi 또는 처리 해상도를 낮춰 주세요."
        )

    matrix = fitz.Matrix(zoom, zoom)
    if clip_rect is not None:
        pr = page.rect
        fitz_clip = fitz.Rect(
            clip_rect['x'] * pr.width,
            clip_rect['y'] * pr.height,
            (clip_rect['x'] + clip_rect['width']) * pr.width,
            (clip_rect['y'] + clip_rect['height']) * pr.height,
        )
        pix = page.get_pixmap(matrix=matrix, alpha=False, clip=fitz_clip)
        logger.debug(
            "[pdf2img] render clip applied: pdf_rect=(%.1f,%.1f,%.1f,%.1f)",
            fitz_clip.x0,
            fitz_clip.y0,
            fitz_clip.x1,
            fitz_clip.y1,
        )
    else:
        pix = page.get_pixmap(matrix=matrix, alpha=False)

    img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
    logger.debug(
        "[pdf2img] render done: size=%sx%s bytes=%.2fMB",
        pix.width,
        pix.height,
        img_bgr.nbytes / 1024 / 1024,
    )
    return img_bgr


def _pypdf2_page_to_bgr(
    file_bytes: bytes,
    page_num: int = 0,
    dpi: int = _DEFAULT_DPI,
    cad_mode: bool = False,
    cad_line_width: float = 0.2,
    clip_rect: dict = None,
) -> Tuple[np.ndarray, int]:
    """
    공통 PDF 파이프라인: 특정 페이지를 BGR numpy 배열로 변환.

    PdfWriter로 단일 페이지를 재기록한 뒤 fitz로 최종 렌더링한다.
    """
    tmp_path = None
    try:
        logger.debug(
            "[pdf2img] PDF pipeline start: page_num=%s dpi=%s input_size=%.2fMB",
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

        # ────────────────────────────────────────────────────────────────
        # CAD‑mode: PyPDF2로 단일 페이지를 추출한 뒤 line-width 스트림 편집을 적용한다.
        #  - cad_pdf_bytes 를 먼저 page_pdf_bytes 로 초기화하여,
        #    CAD 변환 실패 시에도 원본 바이트로 안전하게 fallback 된다.
        # ────────────────────────────────────────────────────────────────
        cad_pdf_bytes = page_pdf_bytes  # CAD 변환 실패 시 원본 단일 페이지 바이트 유지
        if cad_mode:
            try:
                cad_pdf_bytes = apply_cad_mode_to_pdf(page_pdf_bytes, line_width=cad_line_width)
                logger.info("[pdf2img] CAD-mode 스트림 편집 성공")
            except Exception as e:
                logger.warning("[pdf2img] CAD-mode 스트림 편집 실패 - 원본 바이트로 fallback (%s)", e)

        with fitz.open(stream=cad_pdf_bytes, filetype="pdf") as doc:
            logger.debug("[pdf2img] render fitz open success: page_count=%s", doc.page_count)
            img_bgr = _fitz_page_to_bgr(doc.load_page(0), dpi=dpi, clip_rect=clip_rect)

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
    cad_mode: bool = False,
    cad_line_width: float = 0.2,
    clip_rect: dict = None,
) -> Tuple[np.ndarray, int]:
    """
    PDF bytes → BGR numpy 배열 변환 (메인 진입점).

    모든 PDF를 공통 2-step 파이프라인으로 처리한다.

    Args:
        file_bytes: PDF 파일 바이트
        page_num: 요청 페이지 번호 (0-based, 범위 초과 시 0으로 보정)
        dpi: 렌더링 해상도 (기본 200)
        clip_rect: 선택적 crop 영역. {'x', 'y', 'width', 'height'} 정규화 좌표(0-1).
                   None이면 전체 페이지 렌더링.

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

    try:
        img_bgr, total_pages = _pypdf2_page_to_bgr(
            file_bytes,
            page_num=page_num,
            dpi=dpi,
            cad_mode=cad_mode,
            cad_line_width=cad_line_width,
            clip_rect=clip_rect,
        )
        logger.info(
            "[pdf2img] PDF pipeline success — total_pages=%s (dpi=%s)",
            total_pages,
            dpi,
        )
        return img_bgr, total_pages
    except Exception as e:
        logger.error("[pdf2img] PDF pipeline failed: %s: %s", type(e).__name__, e)
        raise ValueError(f"PDF 변환 실패: {e}") from e
