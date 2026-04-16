"""
PDF → BGR numpy 배열 변환 라이브러리

PDF 파일을 BGR numpy 배열로 변환하는 범용 모듈.
다른 앱에서도 PDF 파일 읽기에 사용할 수 있다.

공개 API:
    - pdf_to_bgr(file_bytes, page_num, dpi)
        메인 진입점. 모든 PDF를 공통 2-step 파이프라인으로 처리한다.

변환 전략:
    1차: pypdf PdfWriter로 단일 페이지 재기록(메타데이터 정리)
    2차: fitz로 최종 래스터 렌더링

PdfReader는 BytesIO 스트림 대신 임시 파일 경로로 초기화한다.
pypdf에서 BytesIO 스트림으로 암호화 PDF를 읽으면
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
from pypdf import PdfReader, PdfWriter

logger = logging.getLogger(__name__)

_DEFAULT_DPI = 200

# 단일 fitz 픽스맵 허용 상한 (RGB uint8, 3채널 기준).
# 이 값을 초과하면 get_pixmap() 호출 전에 MemoryError를 발생시켜
# C 레벨 OOM 및 프로세스 강제 종료를 방지한다.
_MAX_PIXMAP_BYTES = 400 * 1024 * 1024  # 400 MB

_PDF_OPERATOR_BOUNDARY = rb"[\x00\t\n\f\r ]"
_BT_OPERATOR_PATTERN = re.compile(
    rb"(?:^|" + _PDF_OPERATOR_BOUNDARY + rb")BT(?=" + _PDF_OPERATOR_BOUNDARY + rb")"
)
_ET_OPERATOR_PATTERN = re.compile(
    rb"(?:^|" + _PDF_OPERATOR_BOUNDARY + rb")ET(?=" + _PDF_OPERATOR_BOUNDARY + rb")"
)

# small polygon hatch 전용 설정
# 현재 기본값은 기존 동작과 동일하게 유지하되, blob 계열과 독립 튜닝할 수 있게 분리한다.
_HATCH_POLYGON_MAX_DIM = 6.0
_HATCH_POLYGON_MIN_LINE_OPS = 2
_HATCH_POLYGON_LOOKBACK_BYTES = 180
_HATCH_POLYGON_STATE_LOOKBACK_BYTES = 1024

# large clip-path blob / rect hatch 전용 설정
# 현재 기본값은 기존 동작과 동일하게 유지하되, polygon 계열과 독립 튜닝할 수 있게 분리한다.
_HATCH_RECT_MAX_DIM = 6.0
_HATCH_RECT_LOOKBACK_BYTES = 80
_HATCH_BLOB_MIN_DIM = 100.0
_HATCH_BLOB_STATE_LOOKBACK_BYTES = 2048
_HATCH_BLOB_RECENT_PATH_LOOKBACK_BYTES = 1024
_HATCH_BLOB_PATH_LOOKBACK_BYTES = 16384
_PDF_TOKEN_FOLLOW_BOUNDARY = rb"[\x00\t\n\f\r /]"
_RE_OPERATOR_PATTERN = re.compile(
    rb"(?:^|" + _PDF_OPERATOR_BOUNDARY + rb")re(?=" + _PDF_TOKEN_FOLLOW_BOUNDARY + rb")"
)
_M_OPERATOR_PATTERN = re.compile(
    rb"(?:^|" + _PDF_OPERATOR_BOUNDARY + rb")m(?=" + _PDF_TOKEN_FOLLOW_BOUNDARY + rb")"
)
_L_OPERATOR_PATTERN = re.compile(
    rb"(?:^|" + _PDF_OPERATOR_BOUNDARY + rb")l(?=" + _PDF_TOKEN_FOLLOW_BOUNDARY + rb")"
)
_GS_OPERATOR_PATTERN = re.compile(
    rb"(?:^|" + _PDF_OPERATOR_BOUNDARY + rb")gs(?=" + _PDF_TOKEN_FOLLOW_BOUNDARY + rb")"
)
_CM_OPERATOR_PATTERN = re.compile(
    rb"(?:^|" + _PDF_OPERATOR_BOUNDARY + rb")cm(?=" + _PDF_TOKEN_FOLLOW_BOUNDARY + rb")"
)
_Q_OPERATOR_PATTERN = re.compile(
    rb"(?:^|" + _PDF_OPERATOR_BOUNDARY + rb")q(?=" + _PDF_TOKEN_FOLLOW_BOUNDARY + rb")"
)
_H_OPERATOR_PATTERN = re.compile(
    rb"(?:^|" + _PDF_OPERATOR_BOUNDARY + rb")h(?=" + _PDF_TOKEN_FOLLOW_BOUNDARY + rb")"
)
_SCN_OPERATOR_PATTERN = re.compile(
    rb"(?:^|"
    + _PDF_OPERATOR_BOUNDARY
    + rb")(?:scn|sc)(?="
    + _PDF_TOKEN_FOLLOW_BOUNDARY
    + rb")"
)
_CLIP_RECT_SEQUENCE_PATTERN = re.compile(rb"re\s+W\*?\s+n")


# ----------------------------------------------------------------------
# CAD-mode 전용 PDF 스트림 편집 함수
# ----------------------------------------------------------------------


def _object_cache_key(pdf_obj) -> tuple:
    """pikepdf 객체의 방문 추적용 키를 반환한다."""
    objgen = getattr(pdf_obj, "objgen", None)
    if objgen is not None:
        return tuple(objgen)
    return (id(pdf_obj), 0)


def _ensure_hatch_alpha_extgstate(
    pdf, resource_owner, alpha_value: float = 0.0, base_name: str = "FxHatchHide"
):
    resources = resource_owner.get("/Resources")
    if resources is None:
        resources = pikepdf.Dictionary()
        resource_owner["/Resources"] = resources

    extgstate = resources.get("/ExtGState")
    if extgstate is None:
        extgstate = pikepdf.Dictionary()
        resources["/ExtGState"] = extgstate

    # 기존 동일 alpha ExtGState 재사용
    for key in list(extgstate.keys()):
        gs_obj = extgstate[key]
        try:
            if float(gs_obj.get("/ca", -1)) == float(alpha_value):
                return key
        except Exception:
            continue

    index = 0
    while True:
        suffix = "" if index == 0 else str(index)
        gs_name = pikepdf.Name(f"/{base_name}{suffix}")
        if gs_name not in extgstate:
            break
        index += 1

    gs_dict = pikepdf.Dictionary(
        {
            "/Type": pikepdf.Name("/ExtGState"),
            "/ca": float(alpha_value),
            "/CA": float(alpha_value),
        }
    )
    extgstate[gs_name] = pdf.make_indirect(gs_dict)
    return gs_name


def _read_resource_bytes(resource_owner) -> bytes:
    if "/Contents" in resource_owner:
        contents = resource_owner["/Contents"]
        if isinstance(contents, pikepdf.Array):
            raise TypeError(
                "페이지 /Contents 배열은 개별 스트림 단위로 처리해야 합니다"
            )
        return contents.read_bytes()
    return resource_owner.read_bytes()


def _write_resource_bytes(pdf, resource_owner, raw_bytes: bytes) -> None:
    is_page_like = (
        resource_owner.get("/Type") == pikepdf.Name("/Page")
        or "/Contents" in resource_owner
    )
    if is_page_like:
        contents = resource_owner.get("/Contents")
        if isinstance(contents, pikepdf.Array):
            raise TypeError(
                "페이지 /Contents 배열은 단일 스트림으로 재조립할 수 없습니다"
            )
        if contents is not None:
            contents.write(raw_bytes)
            return
        resource_owner.Contents = pdf.make_stream(raw_bytes)
        return
    resource_owner.write(raw_bytes)


def _edit_single_stream_object(
    pdf,
    stream_obj,
    location: str,
    *,
    hide_hatch_transparency: bool,
    apply_line_width: bool,
    line_width: float,
) -> tuple[int, int]:
    try:
        raw_bytes = stream_obj.read_bytes()
    except Exception as e:
        logger.warning("[cad_mode] %s 스트림 읽기 실패: %s", location, e)
        return 0, 0

    if not raw_bytes:
        return 0, 0

    new_bytes, hatch_count, line_count = _edit_content_stream_preserving_text(
        stream_obj,
        raw_bytes,
        location,
        hide_hatch_transparency=hide_hatch_transparency,
        apply_line_width=apply_line_width,
        line_width=line_width,
    )

    if hatch_count == 0 and line_count == 0:
        return 0, 0

    try:
        stream_obj.write(new_bytes)
    except Exception as e:
        logger.warning("[cad_mode] %s 스트림 write 실패: %s", location, e)
        return 0, 0

    logger.debug(
        "[cad_mode] %s 스트림 편집 완료: hatch=%d line_width=%d",
        location,
        hatch_count,
        line_count,
    )
    return hatch_count, line_count


def _may_contain_text_objects(raw_bytes: bytes) -> bool:
    """BT/ET 기반 text object가 없으면 content stream 파싱을 건너뛴다."""
    if b"BT" not in raw_bytes or b"ET" not in raw_bytes:
        return False
    return bool(
        _BT_OPERATOR_PATTERN.search(raw_bytes)
        and _ET_OPERATOR_PATTERN.search(raw_bytes)
    )


def _find_text_object_ranges(raw_bytes: bytes) -> list[tuple[int, int]]:
    """원본 바이트 스트림에서 BT/ET text object 범위를 찾는다."""
    ranges: list[tuple[int, int]] = []
    search_pos = 0

    while True:
        bt_match = _BT_OPERATOR_PATTERN.search(raw_bytes, search_pos)
        if not bt_match:
            break

        bt_start = bt_match.start()
        et_match = _ET_OPERATOR_PATTERN.search(raw_bytes, bt_match.end())
        if not et_match:
            break

        ranges.append((bt_start, et_match.end()))
        search_pos = et_match.end()

    return ranges


def _mask_text_object_ranges(raw_bytes: bytes) -> bytes:
    """
    BT/ET text object를 동일 길이 공백으로 마스킹한다.

    해치 검출은 전체 스트림 문맥을 유지해야 하므로, 텍스트를 분리된 청크로 잘라내지 않고
    원본 위치를 보존한 채 비가시화한 바이트 사본에서 수행한다.
    """
    text_ranges = _find_text_object_ranges(raw_bytes)
    if not text_ranges:
        return raw_bytes

    masked = bytearray(raw_bytes)
    for start, end in text_ranges:
        for index in range(start, end):
            byte = masked[index]
            if byte not in (0x0A, 0x0D):
                masked[index] = 0x20
    return bytes(masked)


def _find_hatch_fill_ranges(
    raw_bytes: bytes,
) -> tuple[list[tuple[int, int]], dict[str, int]]:
    """해치로 판단된 fill 연산자의 원본 바이트 범위와 진단 통계를 반환한다."""
    matches = list(_FILL_BYTE_PATTERN.finditer(raw_bytes))
    stats = {
        "total_fills": len(matches),
        "rect_candidates": 0,
        "polygon_candidates": 0,
        "accepted": 0,
        "skipped_text_context": 0,
        "skipped_text_nearby": 0,
        "skipped_rect_parse": 0,
        "skipped_rect_large": 0,
        "accepted_large_blob": 0,
        "skipped_polygon_state": 0,
        "skipped_polygon_shape": 0,
        "skipped_polygon_scale": 0,
        "skipped_other_shape": 0,
    }

    if not matches:
        return [], stats

    fill_ranges: list[tuple[int, int]] = []

    def _scan_large_blob_context(fill_start: int) -> tuple[int, int, int, bool]:
        blob_ctx_start = max(0, fill_start - _HATCH_BLOB_PATH_LOOKBACK_BYTES)
        blob_context = raw_bytes[blob_ctx_start:fill_start]
        return (
            len(_L_OPERATOR_PATTERN.findall(blob_context)),
            len(_M_OPERATOR_PATTERN.findall(blob_context)),
            len(_H_OPERATOR_PATTERN.findall(blob_context)),
            bool(_CLIP_RECT_SEQUENCE_PATTERN.search(blob_context)),
        )

    for m in matches:
        fill_start = m.start() + 1
        fill_end = m.end()

        shape_ctx_start = max(
            0,
            fill_start - max(_HATCH_RECT_LOOKBACK_BYTES, _HATCH_POLYGON_LOOKBACK_BYTES),
        )
        context = raw_bytes[shape_ctx_start:fill_start]
        polygon_state_context = raw_bytes[
            max(0, fill_start - _HATCH_POLYGON_STATE_LOOKBACK_BYTES) : fill_start
        ]
        blob_state_context = raw_bytes[
            max(0, fill_start - _HATCH_BLOB_STATE_LOOKBACK_BYTES) : fill_start
        ]

        last_bt = context.rfind(b"\nBT\n")
        if last_bt == -1:
            last_bt = context.rfind(b" BT\n")
        last_et = context.rfind(b"\nET\n")
        if last_et == -1:
            last_et = context.rfind(b" ET\n")
        if last_bt > last_et:
            stats["skipped_text_context"] += 1
            continue

        near_context = context[-50:] if len(context) >= 50 else context
        if (
            b" Tj\n" in near_context
            or b" TJ\n" in near_context
            or b" Tf\n" in near_context
        ):
            stats["skipped_text_nearby"] += 1
            continue

        polygon_has_gs = bool(_GS_OPERATOR_PATTERN.search(polygon_state_context))
        polygon_has_q = bool(_Q_OPERATOR_PATTERN.search(polygon_state_context))
        polygon_has_cm = bool(_CM_OPERATOR_PATTERN.search(polygon_state_context))
        polygon_has_clip = (
            b" W\n" in polygon_state_context
            or b" W*\n" in polygon_state_context
            or b" n\n" in polygon_state_context
        )
        polygon_has_nonstroke_color = (
            bool(_SCN_OPERATOR_PATTERN.search(polygon_state_context))
            or b" g" in polygon_state_context
            or b" rg" in polygon_state_context
        )
        polygon_has_state_hint = (
            polygon_has_gs or polygon_has_q or polygon_has_cm or polygon_has_clip
        )

        blob_has_clip = (
            b" W\n" in blob_state_context
            or b" W*\n" in blob_state_context
            or b" n\n" in blob_state_context
        )

        rect_context = (
            context[-_HATCH_RECT_LOOKBACK_BYTES:]
            if len(context) >= _HATCH_RECT_LOOKBACK_BYTES
            else context
        )
        polygon_context = (
            context[-_HATCH_POLYGON_LOOKBACK_BYTES:]
            if len(context) >= _HATCH_POLYGON_LOOKBACK_BYTES
            else context
        )
        is_rect = bool(_RE_OPERATOR_PATTERN.search(rect_context))
        is_polygon = bool(
            _L_OPERATOR_PATTERN.search(polygon_context)
            and _M_OPERATOR_PATTERN.search(polygon_context)
        )

        if is_rect:
            stats["rect_candidates"] += 1
            re_matches = list(_RE_OPERATOR_PATTERN.finditer(context))
            if not re_matches:
                stats["skipped_rect_parse"] += 1
                continue
            re_idx = re_matches[-1].start()
            before_re = context[:re_idx]
            nums = _NUM_BYTE_PATTERN.findall(before_re)
            if len(nums) < 2:
                stats["skipped_rect_parse"] += 1
                continue
            try:
                width = abs(float(nums[-2]))
                height = abs(float(nums[-1]))
                if max(width, height) > _HATCH_RECT_MAX_DIM:
                    recent_path_context = (
                        context[-_HATCH_BLOB_RECENT_PATH_LOOKBACK_BYTES:]
                        if len(context) >= _HATCH_BLOB_RECENT_PATH_LOOKBACK_BYTES
                        else context
                    )
                    line_ops = len(_L_OPERATOR_PATTERN.findall(recent_path_context))
                    move_ops = len(_M_OPERATOR_PATTERN.findall(recent_path_context))
                    close_ops = len(_H_OPERATOR_PATTERN.findall(recent_path_context))
                    has_clip_rect_sequence = bool(
                        _CLIP_RECT_SEQUENCE_PATTERN.search(recent_path_context)
                    )

                    if max(width, height) >= _HATCH_BLOB_MIN_DIM and (
                        line_ops < 2
                        or move_ops < 1
                        or close_ops < 1
                        or not has_clip_rect_sequence
                    ):
                        line_ops, move_ops, close_ops, has_clip_rect_sequence = (
                            _scan_large_blob_context(fill_start)
                        )

                    has_large_blob_hatch = (
                        max(width, height) >= _HATCH_BLOB_MIN_DIM
                        and blob_has_clip
                        and move_ops >= 1
                        and line_ops >= 2
                        and close_ops >= 1
                        and has_clip_rect_sequence
                    )
                    if has_large_blob_hatch:
                        stats["accepted_large_blob"] += 1
                    else:
                        stats["skipped_rect_large"] += 1
                        continue
            except Exception:
                stats["skipped_rect_parse"] += 1
                continue
        elif is_polygon:
            stats["polygon_candidates"] += 1
            if not polygon_has_state_hint:
                stats["skipped_polygon_state"] += 1
                continue

            polygon_context = (
                context[-_HATCH_POLYGON_LOOKBACK_BYTES:]
                if len(context) >= _HATCH_POLYGON_LOOKBACK_BYTES
                else context
            )
            line_ops = len(_L_OPERATOR_PATTERN.findall(polygon_context))
            move_ops = len(_M_OPERATOR_PATTERN.findall(polygon_context))
            recent_fill_ops = len(_FILL_BYTE_PATTERN.findall(polygon_context))
            has_repeated_fill_chain = polygon_has_cm and recent_fill_ops >= 1
            has_polygon_hatch_context = (
                (polygon_has_gs and polygon_has_cm and polygon_has_nonstroke_color)
                or polygon_has_clip
                or polygon_has_q
                or has_repeated_fill_chain
            )
            if (
                line_ops < _HATCH_POLYGON_MIN_LINE_OPS
                or move_ops < 1
                or not has_polygon_hatch_context
            ):
                stats["skipped_polygon_shape"] += 1
                continue

            cm_matches = list(_CM_OPERATOR_PATTERN.finditer(context))
            if cm_matches:
                after_cm = context[cm_matches[-1].start() :]
                nums = _NUM_BYTE_PATTERN.findall(after_cm)
                if nums:
                    try:
                        vals = [abs(float(n)) for n in nums[:8]]
                        if not any(v <= _HATCH_POLYGON_MAX_DIM for v in vals):
                            stats["skipped_polygon_scale"] += 1
                            continue
                    except Exception:
                        stats["skipped_polygon_scale"] += 1
                        continue
            else:
                stats["skipped_polygon_scale"] += 1
                continue
        else:
            stats["skipped_other_shape"] += 1
            continue

        fill_ranges.append((fill_start, fill_end))
        stats["accepted"] += 1

    return fill_ranges, stats


def _inject_hatch_hide_ops(
    raw_bytes: bytes, fill_ranges: list[tuple[int, int]]
) -> tuple[bytes, int]:
    if not fill_ranges:
        return raw_bytes, 0

    gs_prefix = b"q\n/FxHatchHide gs\n"
    gs_suffix = b"Q\n"
    parts = []
    prev_end = 0

    for fill_start, fill_end in fill_ranges:
        parts.append(raw_bytes[prev_end:fill_start])
        parts.append(gs_prefix)
        parts.append(raw_bytes[fill_start:fill_end])
        parts.append(gs_suffix)
        prev_end = fill_end

    parts.append(raw_bytes[prev_end:])
    return b"".join(parts), len(fill_ranges)


def _replace_line_width_outside_text_objects(
    raw_bytes: bytes, line_width: float
) -> tuple[bytes, int]:
    text_ranges = _find_text_object_ranges(raw_bytes)
    if not text_ranges:
        return _byte_level_line_width_replace(raw_bytes, line_width)

    replacement = f"{line_width:g} w".encode("ascii")
    parts = []
    total_count = 0
    prev_end = 0

    for start, end in text_ranges:
        non_text_chunk = raw_bytes[prev_end:start]
        replaced_chunk, chunk_count = _LINE_WIDTH_BYTE_PATTERN.subn(
            replacement, non_text_chunk
        )
        parts.append(replaced_chunk)
        parts.append(raw_bytes[start:end])
        total_count += chunk_count
        prev_end = end

    tail_chunk, tail_count = _LINE_WIDTH_BYTE_PATTERN.subn(
        replacement, raw_bytes[prev_end:]
    )
    parts.append(tail_chunk)
    total_count += tail_count
    return b"".join(parts), total_count


def _edit_content_stream_preserving_text(
    resource_owner,
    raw_bytes: bytes,
    location: str,
    *,
    hide_hatch_transparency: bool,
    apply_line_width: bool,
    line_width: float,
) -> tuple[bytes, int, int]:
    """
    텍스트/그래픽 순서를 유지한 채 원본 스트림 위치에서 CAD 편집을 적용한다.

    BT/ET 텍스트는 해치 검출 시에만 동일 길이 공백으로 마스킹해 문맥을 보존한다.
    실제 출력 바이트에서는 텍스트를 분리하거나 재조립하지 않는다.
    """
    del resource_owner

    edit_target = raw_bytes
    has_text_objects = _may_contain_text_objects(raw_bytes)

    if hide_hatch_transparency and has_text_objects:
        edit_target = _mask_text_object_ranges(raw_bytes)

    new_bytes = raw_bytes
    hatch_count = 0
    line_count = 0

    if hide_hatch_transparency:
        fill_ranges, hatch_stats = _find_hatch_fill_ranges(edit_target)
        new_bytes, hatch_count = _inject_hatch_hide_ops(new_bytes, fill_ranges)
        logger.debug(
            "[cad_mode] %s hatch scan: fills=%d accepted=%d rect=%d polygon=%d large_blob=%d skipped_text=%d skipped_rect_large=%d skipped_polygon_state=%d skipped_polygon_shape=%d skipped_polygon_scale=%d",
            location,
            hatch_stats["total_fills"],
            hatch_stats["accepted"],
            hatch_stats["rect_candidates"],
            hatch_stats["polygon_candidates"],
            hatch_stats["accepted_large_blob"],
            hatch_stats["skipped_text_context"] + hatch_stats["skipped_text_nearby"],
            hatch_stats["skipped_rect_large"],
            hatch_stats["skipped_polygon_state"],
            hatch_stats["skipped_polygon_shape"],
            hatch_stats["skipped_polygon_scale"],
        )

    if apply_line_width:
        new_bytes, line_count = _replace_line_width_outside_text_objects(
            new_bytes, line_width
        )

    if has_text_objects and hatch_count > 0:
        logger.debug("[cad_mode] %s 텍스트 위치 보존 상태로 해치 편집 적용", location)

    return new_bytes, hatch_count, line_count


def _apply_cad_edits_to_resource(
    pdf,
    resource_owner,
    location: str,
    *,
    hide_hatch_transparency: bool,
    apply_line_width: bool,
    line_width: float,
) -> tuple[int, int]:
    if "/Contents" in resource_owner:
        contents = resource_owner["/Contents"]
        stream_list = (
            list(contents) if isinstance(contents, pikepdf.Array) else [contents]
        )

        total_hatch = 0
        total_line = 0
        for index, stream_obj in enumerate(stream_list):
            hatch_count, line_count = _edit_single_stream_object(
                pdf,
                stream_obj,
                f"{location} Contents[{index}]",
                hide_hatch_transparency=hide_hatch_transparency,
                apply_line_width=apply_line_width,
                line_width=line_width,
            )
            total_hatch += hatch_count
            total_line += line_count

        if total_hatch > 0:
            _ensure_hatch_alpha_extgstate(pdf, resource_owner, alpha_value=0.0)

        return total_hatch, total_line

    try:
        raw_bytes = _read_resource_bytes(resource_owner)
    except Exception as e:
        logger.warning("[cad_mode] %s 바이트 읽기 실패: %s", location, e)
        return 0, 0

    if not raw_bytes:
        return 0, 0

    new_bytes, hatch_count, line_count = _edit_content_stream_preserving_text(
        resource_owner,
        raw_bytes,
        location,
        hide_hatch_transparency=hide_hatch_transparency,
        apply_line_width=apply_line_width,
        line_width=line_width,
    )

    if hatch_count == 0 and line_count == 0:
        return 0, 0

    if hatch_count > 0:
        _ensure_hatch_alpha_extgstate(pdf, resource_owner, alpha_value=0.0)

    try:
        _write_resource_bytes(pdf, resource_owner, new_bytes)
    except Exception as e:
        logger.warning("[cad_mode] %s content write 실패: %s", location, e)
        return 0, 0

    logger.debug(
        "[cad_mode] %s 스트림 편집 완료: hatch=%d line_width=%d",
        location,
        hatch_count,
        line_count,
    )
    return hatch_count, line_count


def _apply_cad_edits_to_form_xobjects(
    pdf,
    resource_owner,
    location: str,
    *,
    hide_hatch_transparency: bool,
    apply_line_width: bool,
    line_width: float,
    visited: Set[tuple],
) -> tuple[int, int]:
    if (
        "/Resources" not in resource_owner
        or "/XObject" not in resource_owner["/Resources"]
    ):
        return 0, 0

    total_hatch = 0
    total_line = 0
    xobjects = resource_owner["/Resources"]["/XObject"]
    for name in list(xobjects.keys()):
        xobj = xobjects[name]
        subtype = xobj.get("/Subtype")
        if subtype != pikepdf.Name.Form:
            continue

        cache_key = _object_cache_key(xobj)
        if cache_key in visited:
            continue
        visited.add(cache_key)

        child_location = f"{location} XObject/{name}"
        hatch_count, line_count = _apply_cad_edits_to_resource(
            pdf,
            xobj,
            child_location,
            hide_hatch_transparency=hide_hatch_transparency,
            apply_line_width=apply_line_width,
            line_width=line_width,
        )
        total_hatch += hatch_count
        total_line += line_count

        child_hatch, child_line = _apply_cad_edits_to_form_xobjects(
            pdf,
            xobj,
            child_location,
            hide_hatch_transparency=hide_hatch_transparency,
            apply_line_width=apply_line_width,
            line_width=line_width,
            visited=visited,
        )
        total_hatch += child_hatch
        total_line += child_line

    return total_hatch, total_line


# ── 바이트 레벨 해치 검출용 패턴 (성능 최적화) ──
_FILL_BYTE_PATTERN = re.compile(rb"[\n ](f|f\*|F)\n")
_NUM_BYTE_PATTERN = re.compile(rb"[-]?(?:\d+\.?\d*|\.\d+)")
# line width 패턴: 정수/소수 + w 연산자 (1.8x 최적화, 3.3s → 1.8s)
_LINE_WIDTH_BYTE_PATTERN = re.compile(rb"[-+]?(?:\d+(?:\.\d*)?|\.\d+)\s+w\b")


def _byte_level_hatch_detection(raw_bytes: bytes) -> tuple[bytes, int]:
    """
    바이트 레벨에서 해치 fill을 검출하고 gs를 삽입한다.
    현재 주 경로는 텍스트 마스킹 기반 편집이며, 이 함수는 동일한 fill-range/
    주입 로직을 재사용하는 저수준 유틸리티다.

    Args:
        raw_bytes: PDF content stream 바이트

    Returns:
        (수정된 바이트, 삽입 횟수)
    """
    fill_ranges, _stats = _find_hatch_fill_ranges(raw_bytes)
    return _inject_hatch_hide_ops(raw_bytes, fill_ranges)


def _byte_level_line_width_replace(
    raw_bytes: bytes, line_width: float
) -> tuple[bytes, int]:
    """
    바이트 레벨에서 line-width 연산자를 치환한다.

    Args:
        raw_bytes: PDF content stream 바이트
        line_width: 목표 선 굵기 (pt)

    Returns:
        (수정된 바이트, 치환 횟수)
    """
    replacement = f"{line_width:g} w".encode("ascii")
    new_bytes, count = _LINE_WIDTH_BYTE_PATTERN.subn(replacement, raw_bytes)
    return new_bytes, count


def apply_cad_mode_to_pdf(
    pdf_bytes: bytes,
    line_width: float = 0.2,
    apply_line_width: bool = True,
    hide_hatch_transparency: bool = False,
    request_id: str = "-",
) -> bytes:
    """
    CAD 모드 PDF 전처리.
    선두께 변경과 해치 투명화는 개별 옵션으로 독립 적용한다.
    해치 검출은 원본 스트림 위치를 유지한 상태에서 BT/ET 텍스트만 마스킹해 수행한다.

    Args:
        pdf_bytes: 원본 PDF 바이트
        line_width: 목표 선 굵기 (pt)
        apply_line_width: True이면 선두께 변경 적용
        hide_hatch_transparency: True이면 해치 투명화 적용
    """
    total_hatch = 0
    total_line_subs = 0

    with pikepdf.open(io.BytesIO(pdf_bytes)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            page_hatch, page_line = _apply_cad_edits_to_resource(
                pdf,
                page,
                f"페이지 {page_number}",
                hide_hatch_transparency=hide_hatch_transparency,
                apply_line_width=apply_line_width,
                line_width=line_width,
            )
            total_hatch += page_hatch
            total_line_subs += page_line

            visited_forms: Set[tuple] = set()
            form_hatch, form_line = _apply_cad_edits_to_form_xobjects(
                pdf,
                page,
                f"페이지 {page_number}",
                hide_hatch_transparency=hide_hatch_transparency,
                apply_line_width=apply_line_width,
                line_width=line_width,
                visited=visited_forms,
            )
            total_hatch += form_hatch
            total_line_subs += form_line

        out_io = io.BytesIO()
        pdf.save(out_io)
        result_bytes = out_io.getvalue()

    logger.info(
        "[cad_mode] CAD 처리 완료 - hatch=%d, line_width=%d",
        total_hatch,
        total_line_subs,
    )

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
        w = int((clip_rect["width"] * pr.width) * zoom)
        h = int((clip_rect["height"] * pr.height) * zoom)
    else:
        w = int(page.rect.width * zoom)
        h = int(page.rect.height * zoom)
    return w * h * 3


def _fitz_page_to_bgr(
    page, dpi: int = _DEFAULT_DPI, clip_rect: dict = None
) -> np.ndarray:
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
            clip_rect["x"] * pr.width,
            clip_rect["y"] * pr.height,
            (clip_rect["x"] + clip_rect["width"]) * pr.width,
            (clip_rect["y"] + clip_rect["height"]) * pr.height,
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

    img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
        pix.height, pix.width, 3
    )
    img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
    logger.debug(
        "[pdf2img] render done: size=%sx%s bytes=%.2fMB",
        pix.width,
        pix.height,
        img_bgr.nbytes / 1024 / 1024,
    )
    return img_bgr


def _pypdf_page_to_bgr(
    file_bytes: bytes,
    page_num: int = 0,
    dpi: int = _DEFAULT_DPI,
    cad_mode: bool = False,
    cad_line_width: float = 0.2,
    apply_line_width: bool = True,
    hide_hatch_transparency: bool = False,
    request_id: str = "-",
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
        logger.debug(
            "[pdf2img] single-page bytes extracted: page=%s size=%s",
            page_num,
            len(page_pdf_bytes),
        )

        # ────────────────────────────────────────────────────────────────
        # CAD‑mode: pypdf로 단일 페이지를 추출한 뒤 line-width 스트림 편집을 적용한다.
        #  - cad_pdf_bytes 를 먼저 page_pdf_bytes 로 초기화하여,
        #    CAD 변환 실패 시에도 원본 바이트로 안전하게 fallback 된다.
        # ────────────────────────────────────────────────────────────────
        cad_pdf_bytes = page_pdf_bytes  # CAD 변환 실패 시 원본 단일 페이지 바이트 유지
        if cad_mode:
            try:
                cad_pdf_bytes = apply_cad_mode_to_pdf(
                    page_pdf_bytes,
                    line_width=cad_line_width,
                    apply_line_width=apply_line_width,
                    hide_hatch_transparency=hide_hatch_transparency,
                    request_id=request_id,
                )
                logger.info("[pdf2img] CAD-mode 스트림 편집 성공")
            except Exception as e:
                logger.warning(
                    "[pdf2img] CAD-mode 스트림 편집 실패 - 원본 바이트로 fallback (%s)",
                    e,
                )

        with fitz.open(stream=cad_pdf_bytes, filetype="pdf") as doc:
            logger.debug(
                "[pdf2img] render fitz open success: page_count=%s", doc.page_count
            )
            img_bgr = _fitz_page_to_bgr(doc.load_page(0), dpi=dpi, clip_rect=clip_rect)

        return img_bgr, total_pages

    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
                logger.debug("[pdf2img] temp file removed: %s", tmp_path)
            except OSError as e:
                logger.warning(
                    "[pdf2img] temp file cleanup failed: %s: %s", type(e).__name__, e
                )


def pdf_to_bgr(
    file_bytes: bytes,
    page_num: int = 0,
    dpi: int = _DEFAULT_DPI,
    cad_mode: bool = False,
    cad_line_width: float = 0.2,
    apply_line_width: bool = True,
    hide_hatch_transparency: bool = False,
    request_id: str = "-",
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
        img_bgr, total_pages = _pypdf_page_to_bgr(
            file_bytes,
            page_num=page_num,
            dpi=dpi,
            cad_mode=cad_mode,
            cad_line_width=cad_line_width,
            apply_line_width=apply_line_width,
            hide_hatch_transparency=hide_hatch_transparency,
            request_id=request_id,
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
