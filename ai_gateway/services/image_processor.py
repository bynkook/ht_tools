"""
Image Inspector - 이미지/PDF 비교 처리 모듈
image_inspector.py의 핵심 로직을 FastAPI용으로 포팅
"""

import base64
from dataclasses import dataclass
import io
import logging
from typing import Any, Optional, Tuple

import cv2
import numpy as np
from PIL import Image

from .pdf2img import pdf_to_bgr

logger = logging.getLogger(__name__)

# 이진화 임계값: 흰 배경(~255) vs 선/잉크(~0-80) 이진화에 사용.
# CAD/공학 도면 전용 고정 상수로, 사용자 조정 불필요.
_BIN_THRESHOLD = 200

_SUPPORTED_ALIGNMENT_METHODS = frozenset({"orb", "drawing_hybrid"})
_DRAWING_METHOD_ALIASES = frozenset({"cad", "hybrid", "drawing"})
_DRAWING_ANALYSIS_MAX_DIMENSION = 2200
_DRAWING_MAX_LINES = 96
_DRAWING_MAX_INTERSECTIONS = 144
_DRAWING_MAX_CORNERS = 720
_DRAWING_MAX_SPARSE_SUPPORT = 240


@dataclass
class AlignmentCandidate:
    method: str
    transform_model: str
    src_points: Optional[np.ndarray]
    dst_points: Optional[np.ndarray]
    matched_points: int
    raw_metrics: dict[str, float]
    diagnostics: dict[str, Any]
    transform_matrix: Optional[np.ndarray] = None
    inlier_mask: Optional[np.ndarray] = None
    aligned_bgr: Optional[np.ndarray] = None
    reprojection_error_mean: Optional[float] = None


@dataclass
class ScoreResult:
    method: str
    transform_model: str
    normalized_quality: float
    acceptance_threshold: float
    accepted: bool
    inlier_count: int
    inlier_ratio: float
    spatial_coverage: float
    geometry_score: float
    reprojection_error_mean: Optional[float]
    raw_metrics: dict[str, float]
    fallback_reason: Optional[str]
    diagnostics: dict[str, Any]


@dataclass
class AlignmentResult:
    method: str
    transform_model: str
    aligned_bgr: Optional[np.ndarray]
    transform_matrix: Optional[np.ndarray]
    normalized_quality: float
    accepted: bool
    used_fallback: bool
    fallback_reason: Optional[str]
    metrics: dict[str, float]
    diagnostics: dict[str, Any]


def _img_debug_info(img: np.ndarray) -> str:
    """로그용 이미지 메타정보 문자열 생성."""
    if img is None:
        return "shape=None dtype=None size=0.00MB"
    return (
        f"shape={img.shape} dtype={img.dtype} "
        f"size={img.nbytes / 1024 / 1024:.2f}MB"
    )


def tiff_to_image(tiff_bytes: bytes, page_num: int = 0) -> Tuple[np.ndarray, int]:
    """
    Multi-page TIFF를 이미지로 변환
    
    Args:
        tiff_bytes: TIFF 파일의 바이트 데이터
        page_num: 변환할 페이지 번호 (0-based)
    
    Returns:
        (이미지 BGR 배열, 전체 페이지 수)
    """
    try:
        # PIL로 TIFF 열기
        tiff_image = Image.open(io.BytesIO(tiff_bytes))
        
        # 전체 페이지 수 확인 (n_frames 속성 사용)
        total_pages = getattr(tiff_image, 'n_frames', 1)
        
        # 요청한 페이지로 이동
        if page_num >= total_pages:
            page_num = 0
            
        tiff_image.seek(page_num)
        
        # RGB로 변환 후 numpy 배열로
        if tiff_image.mode != 'RGB':
            tiff_image = tiff_image.convert('RGB')
        
        img_array = np.array(tiff_image)
        # PIL은 RGB, OpenCV는 BGR 사용하므로 변환
        img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
        
        return img_bgr, total_pages
        
    except Exception as e:
        logger.error("TIFF 변환 실패: %s", e)
        raise ValueError(f"TIFF 변환 실패: {str(e)}")


def _apply_clip_rect(img_bgr: np.ndarray, clip_rect: Optional[dict]) -> np.ndarray:
    """정규화 clip_rect를 이미지 픽셀 좌표로 변환해 crop 적용."""
    if clip_rect is None:
        return img_bgr

    height, width = img_bgr.shape[:2]
    x1 = max(0, min(width - 1, int(width * clip_rect['x'])))
    y1 = max(0, min(height - 1, int(height * clip_rect['y'])))
    x2 = max(1, min(width, int(width * (clip_rect['x'] + clip_rect['width']))))
    y2 = max(1, min(height, int(height * (clip_rect['y'] + clip_rect['height']))))

    if x2 <= x1 or y2 <= y1:
        raise ValueError("유효하지 않은 crop 영역입니다.")

    cropped = img_bgr[y1:y2, x1:x2]
    logger.debug(
        "clip_rect applied: src=%sx%s rect=(%s,%s)-(%s,%s) dst=%sx%s",
        width,
        height,
        x1,
        y1,
        x2,
        y2,
        cropped.shape[1],
        cropped.shape[0],
    )
    return cropped


def load_file(
    file_bytes: bytes,
    content_type: str,
    page_num: int = 0,
    dpi: int = 200,
    cad_mode: bool = False,
    cad_line_width: float = 0.2,
    apply_line_width: bool = True,
    hide_hatch_transparency: bool = False,
    request_id: str = "-",
    source_label: Optional[str] = None,
    clip_rect: Optional[dict] = None,
) -> Tuple[np.ndarray, int, str]:
    """
    파일 로드 (이미지 또는 PDF)
    
    Args:
        file_bytes: 파일 바이트 데이터
        content_type: MIME 타입
        page_num: PDF 페이지 번호
        dpi: PDF 변환 해상도 (PDF 파일에만 적용)
        clip_rect: 선택적 crop 영역. {'x', 'y', 'width', 'height'} 정규화 좌표(0-1).
    
    Returns:
        (이미지 BGR 배열, 총 페이지 수, 파일 타입)
    """
    try:
        logger.debug(
            "load_file start: content_type=%s page_num=%s dpi=%s cad_mode=%s clip=%s size=%.2fMB",
            content_type,
            page_num,
            dpi,
            cad_mode,
            clip_rect is not None,
            len(file_bytes) / 1024 / 1024,
        )

        if "pdf" in content_type.lower():
            img_bgr, total_pages = pdf_to_bgr(
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
            logger.debug("load_file complete (pdf): pages=%s %s", total_pages, _img_debug_info(img_bgr))
            return img_bgr, total_pages, "pdf"
        elif "tiff" in content_type.lower() or "tif" in content_type.lower():
            img_bgr, total_pages = tiff_to_image(file_bytes, page_num=page_num)
            img_bgr = _apply_clip_rect(img_bgr, clip_rect)
            logger.debug("load_file complete (tiff): pages=%s %s", total_pages, _img_debug_info(img_bgr))
            return img_bgr, total_pages, "tiff"
        else:
            arr = np.frombuffer(file_bytes, np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            
            if img is None:
                raise ValueError("이미지 디코딩 실패")

            img = _apply_clip_rect(img, clip_rect)

            logger.debug("load_file complete (image): pages=1 %s", _img_debug_info(img))
            
            return img, 1, "image"
    except MemoryError:
        raise  # → process_comparison의 except MemoryError에서 처리
    except ValueError:
        raise  # 하위 함수가 이미 적절한 메시지를 포함
    except Exception as e:
        logger.error("파일 로드 실패: %s: %s", type(e).__name__, str(e))
        raise ValueError(f"파일 로드 실패: {str(e)}")


def downsample_if_needed(img: np.ndarray, max_dimension: int = 6000) -> np.ndarray:
    """
    이미지가 너무 크면 다운샘플링
    
    Args:
        img: 입력 이미지
        max_dimension: 최대 크기 (픽셀)
    
    Returns:
        다운샘플링된 이미지
    """
    h, w = img.shape[:2]
    max_size = max(h, w)
    logger.debug(
        "downsample_if_needed start: max_dimension=%s current=%sx%s",
        max_dimension,
        w,
        h,
    )
    
    if max_size > max_dimension:
        scale = max_dimension / max_size
        new_w = int(w * scale)
        new_h = int(h * scale)
        img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
        logger.info("이미지 다운샘플링: %sx%s -> %sx%s", w, h, new_w, new_h)
        logger.debug(
            "downsample_if_needed resized: scale=%.4f %s",
            scale,
            _img_debug_info(img),
        )
    else:
        logger.debug("downsample_if_needed skipped: %s", _img_debug_info(img))
    
    return img


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _normalize_count(value: float, target: float) -> float:
    if target <= 0:
        return 0.0
    return _clamp01(value / target)


def _ensure_point_array(points: list[tuple[float, float]]) -> Optional[np.ndarray]:
    if len(points) < 4:
        return None
    return np.float32(points).reshape(-1, 1, 2)


def _compute_spatial_coverage(points: Optional[np.ndarray], image_shape: tuple[int, int]) -> float:
    if points is None or len(points) < 2:
        return 0.0

    height, width = image_shape[:2]
    flat_points = points.reshape(-1, 2)
    min_xy = flat_points.min(axis=0)
    max_xy = flat_points.max(axis=0)
    bbox_area = max(0.0, (max_xy[0] - min_xy[0]) * (max_xy[1] - min_xy[1]))
    image_area = float(max(width * height, 1))
    return _clamp01(bbox_area / image_area)


def _compute_reprojection_error(
    src_points: Optional[np.ndarray],
    dst_points: Optional[np.ndarray],
    transform_matrix: Optional[np.ndarray],
    transform_model: str,
    inlier_mask: Optional[np.ndarray],
) -> Optional[float]:
    if (
        src_points is None
        or dst_points is None
        or transform_matrix is None
        or len(src_points) == 0
    ):
        return None

    if inlier_mask is not None:
        mask = inlier_mask.ravel().astype(bool)
        src = src_points.reshape(-1, 2)[mask]
        dst = dst_points.reshape(-1, 2)[mask]
    else:
        src = src_points.reshape(-1, 2)
        dst = dst_points.reshape(-1, 2)

    if len(src) == 0 or len(dst) == 0:
        return None

    dst_reshaped = dst.reshape(-1, 1, 2)
    if transform_model == "homography":
        projected = cv2.perspectiveTransform(dst_reshaped, transform_matrix)
    else:
        projected = cv2.transform(dst_reshaped, transform_matrix)

    errors = np.linalg.norm(projected.reshape(-1, 2) - src, axis=1)
    if len(errors) == 0:
        return None
    return float(np.mean(errors))


def _build_alignment_candidate(
    method: str,
    transform_model: str,
    src_points: Optional[np.ndarray],
    dst_points: Optional[np.ndarray],
    raw_metrics: Optional[dict[str, float]] = None,
    diagnostics: Optional[dict[str, Any]] = None,
) -> AlignmentCandidate:
    return AlignmentCandidate(
        method=method,
        transform_model=transform_model,
        src_points=src_points,
        dst_points=dst_points,
        matched_points=0 if src_points is None else int(len(src_points)),
        raw_metrics=raw_metrics or {},
        diagnostics=diagnostics or {},
    )


def _distribution_score(points: Optional[np.ndarray], image_shape: tuple[int, int], grid_size: int = 3) -> float:
    if points is None or len(points) == 0:
        return 0.0

    height, width = image_shape[:2]
    cells = np.zeros((grid_size, grid_size), dtype=np.uint8)
    flat_points = points.reshape(-1, 2)
    for x, y in flat_points:
        grid_x = min(grid_size - 1, max(0, int((x / max(width, 1)) * grid_size)))
        grid_y = min(grid_size - 1, max(0, int((y / max(height, 1)) * grid_size)))
        cells[grid_y, grid_x] = 1
    return float(cells.sum()) / float(grid_size * grid_size)


def _descriptor_stability(distances: list[float]) -> float:
    if not distances:
        return 0.0
    distance_array = np.asarray(distances, dtype=np.float32)
    mean_distance = float(np.mean(distance_array))
    std_distance = float(np.std(distance_array))
    if mean_distance <= 0:
        return 1.0
    return _clamp01(1.0 - (std_distance / (mean_distance + 1e-6)))


def _angle_consistency(src_points: Optional[np.ndarray], dst_points: Optional[np.ndarray]) -> float:
    if src_points is None or dst_points is None or len(src_points) < 4:
        return 0.0

    src = src_points.reshape(-1, 2)
    dst = dst_points.reshape(-1, 2)
    delta = src - dst
    angles = np.arctan2(delta[:, 1], delta[:, 0])
    if len(angles) == 0:
        return 0.0
    return _clamp01(1.0 - (float(np.std(angles)) / np.pi))


def _angle_diversity(angles_deg: list[float], bins: int = 6) -> float:
    if not angles_deg:
        return 0.0
    normalized = np.mod(np.asarray(angles_deg, dtype=np.float32), 180.0)
    hist, _ = np.histogram(normalized, bins=bins, range=(0.0, 180.0))
    occupied_bins = int(np.count_nonzero(hist))
    return float(occupied_bins) / float(bins)


def _line_length_balance(lengths: list[float]) -> float:
    if not lengths:
        return 0.0
    arr = np.asarray(lengths, dtype=np.float32)
    mean_length = float(np.mean(arr))
    max_length = float(np.max(arr))
    if max_length <= 0:
        return 0.0
    return _clamp01(mean_length / max_length)


def _reprojection_quality(reprojection_error_mean: Optional[float], image_shape: tuple[int, int]) -> float:
    if reprojection_error_mean is None:
        return 0.0
    height, width = image_shape[:2]
    diagonal = max((width ** 2 + height ** 2) ** 0.5, 1.0)
    relative_error = reprojection_error_mean / diagonal * 1000.0
    if relative_error <= 1.5:
        return 1.0
    if relative_error >= 4.0:
        return 0.0
    return _clamp01(1.0 - ((relative_error - 1.5) / 2.5))


def _mask_points(points: Optional[np.ndarray], mask: Optional[np.ndarray]) -> Optional[np.ndarray]:
    if points is None:
        return None
    if mask is None:
        return points
    flat_mask = mask.ravel().astype(bool)
    return points.reshape(-1, 2)[flat_mask].reshape(-1, 1, 2)


def _pair_points_by_proximity(
    points_a: np.ndarray,
    points_b: np.ndarray,
    shape_a: tuple[int, int],
    shape_b: tuple[int, int],
    max_distance: float = 0.18,
) -> tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    if len(points_a) < 4 or len(points_b) < 4:
        return None, None

    norm_a = points_a / np.array([max(shape_a[1], 1), max(shape_a[0], 1)], dtype=np.float32)
    norm_b = points_b / np.array([max(shape_b[1], 1), max(shape_b[0], 1)], dtype=np.float32)
    translation_hint = np.median(norm_a, axis=0) - np.median(norm_b, axis=0)
    norm_b = norm_b + translation_hint

    distances = np.linalg.norm(norm_a[:, None, :] - norm_b[None, :, :], axis=2)
    pairs = []
    for i in range(distances.shape[0]):
        for j in range(distances.shape[1]):
            if distances[i, j] <= max_distance:
                pairs.append((float(distances[i, j]), i, j))
    pairs.sort(key=lambda item: item[0])

    used_a = set()
    used_b = set()
    matched_a = []
    matched_b = []
    for _, idx_a, idx_b in pairs:
        if idx_a in used_a or idx_b in used_b:
            continue
        used_a.add(idx_a)
        used_b.add(idx_b)
        matched_a.append(tuple(points_a[idx_a]))
        matched_b.append(tuple(points_b[idx_b]))

    return _ensure_point_array(matched_a), _ensure_point_array(matched_b)


def _line_intersection(
    line_a: tuple[int, int, int, int],
    line_b: tuple[int, int, int, int],
) -> Optional[tuple[float, float]]:
    # cv2 HoughLinesP 결과는 np.int32가 섞일 수 있어 곱셈 시 overflow 경고가 발생한다.
    # 교차점 계산은 float64로 승격해 안전하게 수행한다.
    x1, y1, x2, y2 = (float(v) for v in line_a)
    x3, y3, x4, y4 = (float(v) for v in line_b)
    denominator = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denominator) < 1e-6:
        return None

    det_a = x1 * y2 - y1 * x2
    det_b = x3 * y4 - y3 * x4
    px = (det_a * (x3 - x4) - (x1 - x2) * det_b) / denominator
    py = (det_a * (y3 - y4) - (y1 - y2) * det_b) / denominator
    return float(px), float(py)


def _extract_lines(gray: np.ndarray) -> tuple[list[tuple[int, int, int, int]], list[float], list[float]]:
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    raw_lines = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 180,
        threshold=80,
        minLineLength=max(20, min(gray.shape[:2]) // 12),
        maxLineGap=12,
    )
    if raw_lines is None:
        return [], [], []

    lines = []
    angles = []
    lengths = []
    for line in raw_lines[:_DRAWING_MAX_LINES]:
        x1, y1, x2, y2 = line[0]
        length = float(np.hypot(x2 - x1, y2 - y1))
        if length < 20:
            continue
        angle = float(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
        lines.append((x1, y1, x2, y2))
        angles.append(angle)
        lengths.append(length)
    return lines, angles, lengths


def _collect_intersections(gray: np.ndarray, lines: list[tuple[int, int, int, int]]) -> np.ndarray:
    points = []
    height, width = gray.shape[:2]
    for idx, line_a in enumerate(lines):
        for line_b in lines[idx + 1:]:
            angle_a = np.degrees(np.arctan2(line_a[3] - line_a[1], line_a[2] - line_a[0]))
            angle_b = np.degrees(np.arctan2(line_b[3] - line_b[1], line_b[2] - line_b[0]))
            if abs(((angle_a - angle_b + 90) % 180) - 90) < 15:
                continue
            point = _line_intersection(line_a, line_b)
            if point is None:
                continue
            px, py = point
            if 0 <= px < width and 0 <= py < height:
                points.append((px, py))
            if len(points) >= _DRAWING_MAX_INTERSECTIONS:
                break
        if len(points) >= _DRAWING_MAX_INTERSECTIONS:
            break
    if not points:
        return np.empty((0, 2), dtype=np.float32)
    unique_points = np.unique(np.asarray(points, dtype=np.int32), axis=0)
    return unique_points.astype(np.float32)


def _normalize_alignment_method(method: Optional[str]) -> str:
    normalized = (method or "orb").strip().lower()
    if normalized == "orb":
        return "orb"
    if normalized in _DRAWING_METHOD_ALIASES or normalized == "drawing_hybrid":
        return "drawing_hybrid"
    return "orb"


def _resize_for_analysis(gray: np.ndarray, max_dimension: int = _DRAWING_ANALYSIS_MAX_DIMENSION) -> tuple[np.ndarray, float]:
    height, width = gray.shape[:2]
    max_size = max(height, width)
    if max_size <= max_dimension:
        return gray, 1.0

    scale = max_dimension / float(max_size)
    resized = cv2.resize(
        gray,
        (max(1, int(width * scale)), max(1, int(height * scale))),
        interpolation=cv2.INTER_AREA,
    )
    return resized, scale


def _rescale_point_array(points: Optional[np.ndarray], scale: float) -> Optional[np.ndarray]:
    if points is None or scale == 1.0:
        return points
    return (points.astype(np.float32) / scale).reshape(-1, 1, 2)


def _detect_corners(gray: np.ndarray, max_corners: int = _DRAWING_MAX_CORNERS) -> np.ndarray:
    corners = cv2.goodFeaturesToTrack(
        gray,
        maxCorners=max_corners,
        qualityLevel=0.01,
        minDistance=max(8, min(gray.shape[:2]) // 120),
    )
    if corners is None:
        return np.empty((0, 1, 2), dtype=np.float32)
    return corners.astype(np.float32)


def _extract_sparse_support_points(gray: np.ndarray, max_points: int = _DRAWING_MAX_SPARSE_SUPPORT) -> np.ndarray:
    orb = cv2.ORB_create(nfeatures=max_points)
    keypoints = orb.detect(gray, None)
    if not keypoints:
        return np.empty((0, 1, 2), dtype=np.float32)
    limited = keypoints[:max_points]
    points = np.float32([keypoint.pt for keypoint in limited]).reshape(-1, 1, 2)
    return points


def prepare_drawing_views(A_bgr: np.ndarray, B_bgr: np.ndarray) -> dict[str, Any]:
    A_gray = cv2.cvtColor(A_bgr, cv2.COLOR_BGR2GRAY)
    B_gray = cv2.cvtColor(B_bgr, cv2.COLOR_BGR2GRAY)
    A_analysis_gray, A_scale = _resize_for_analysis(A_gray)
    B_analysis_gray, B_scale = _resize_for_analysis(B_gray)
    _, A_binary = cv2.threshold(A_analysis_gray, _BIN_THRESHOLD, 255, cv2.THRESH_BINARY_INV)
    _, B_binary = cv2.threshold(B_analysis_gray, _BIN_THRESHOLD, 255, cv2.THRESH_BINARY_INV)

    return {
        "A_gray": A_gray,
        "B_gray": B_gray,
        "A_analysis_gray": A_analysis_gray,
        "B_analysis_gray": B_analysis_gray,
        "A_binary": A_binary,
        "B_binary": B_binary,
        "A_scale": A_scale,
        "B_scale": B_scale,
    }


def extract_drawing_primitives(views: dict[str, Any], nfeatures: int) -> dict[str, Any]:
    A_analysis_gray = views["A_analysis_gray"]
    B_analysis_gray = views["B_analysis_gray"]
    A_scale = views["A_scale"]
    B_scale = views["B_scale"]
    max_corners = min(_DRAWING_MAX_CORNERS, max(320, nfeatures // 5))

    lines_a, angles_a, lengths_a = _extract_lines(A_analysis_gray)
    lines_b, angles_b, lengths_b = _extract_lines(B_analysis_gray)
    intersections_a = _collect_intersections(A_analysis_gray, lines_a)
    intersections_b = _collect_intersections(B_analysis_gray, lines_b)
    corners_a = _detect_corners(A_analysis_gray, max_corners=max_corners)
    corners_b = _detect_corners(B_analysis_gray, max_corners=max_corners)
    support_a = _extract_sparse_support_points(A_analysis_gray)
    support_b = _extract_sparse_support_points(B_analysis_gray)

    return {
        "lines_a": lines_a,
        "lines_b": lines_b,
        "angles_a": angles_a,
        "angles_b": angles_b,
        "lengths_a": lengths_a,
        "lengths_b": lengths_b,
        "intersections_a": intersections_a,
        "intersections_b": intersections_b,
        "corners_a": corners_a,
        "corners_b": corners_b,
        "support_a": support_a,
        "support_b": support_b,
        "intersections_a_full": np.empty((0, 1, 2), dtype=np.float32) if len(intersections_a) == 0 else _rescale_point_array(intersections_a.reshape(-1, 1, 2), A_scale),
        "intersections_b_full": np.empty((0, 1, 2), dtype=np.float32) if len(intersections_b) == 0 else _rescale_point_array(intersections_b.reshape(-1, 1, 2), B_scale),
        "corners_a_full": _rescale_point_array(corners_a, A_scale),
        "corners_b_full": _rescale_point_array(corners_b, B_scale),
        "support_a_full": _rescale_point_array(support_a, A_scale),
        "support_b_full": _rescale_point_array(support_b, B_scale),
    }


def build_line_candidate(
    primitives: dict[str, Any],
    image_shape_a: tuple[int, int],
    image_shape_b: tuple[int, int],
    max_distance: float = 0.22,
) -> AlignmentCandidate:
    intersections_a = primitives["intersections_a_full"]
    intersections_b = primitives["intersections_b_full"]
    diagnostics: dict[str, Any] = {
        "candidate_source": "line",
        "detected_lines_a": len(primitives["lines_a"]),
        "detected_lines_b": len(primitives["lines_b"]),
        "valid_intersections_a": int(len(primitives["intersections_a"])),
        "valid_intersections_b": int(len(primitives["intersections_b"])),
    }

    if len(intersections_a) < 4 or len(intersections_b) < 4:
        diagnostics["reason"] = "insufficient_intersections"
        return _build_alignment_candidate("line", "partial_affine", None, None, diagnostics=diagnostics)

    src_points, dst_points = _pair_points_by_proximity(
        intersections_a.reshape(-1, 2),
        intersections_b.reshape(-1, 2),
        image_shape_a,
        image_shape_b,
        max_distance=max_distance,
    )
    if src_points is None or dst_points is None:
        diagnostics["reason"] = "insufficient_intersection_pairs"
        return _build_alignment_candidate("line", "partial_affine", None, None, diagnostics=diagnostics)

    coverage = _compute_spatial_coverage(src_points, image_shape_a)
    angle_diversity_score = min(_angle_diversity(primitives["angles_a"]), _angle_diversity(primitives["angles_b"]))
    line_length_balance_score = min(_line_length_balance(primitives["lengths_a"]), _line_length_balance(primitives["lengths_b"]))
    intersection_quality = min(
        _normalize_count(len(primitives["intersections_a"]), 20),
        _normalize_count(len(primitives["intersections_b"]), 20),
        coverage,
    )
    diagnostics["evaluated_pairs"] = int(len(primitives["intersections_a"]) * len(primitives["intersections_b"]))
    diagnostics["matched_intersections"] = int(len(src_points))
    return _build_alignment_candidate(
        "line",
        "partial_affine",
        src_points,
        dst_points,
        {
            "angle_diversity_score": angle_diversity_score,
            "line_length_balance_score": line_length_balance_score,
            "intersection_quality": intersection_quality,
        },
        diagnostics,
    )


def build_corner_candidate(primitives: dict[str, Any], views: dict[str, Any], max_corners: int, max_distance: float = 0.22) -> AlignmentCandidate:
    corners_a = primitives["corners_a"]
    corners_b = primitives["corners_b"]
    diagnostics: dict[str, Any] = {
        "candidate_source": "corner",
        "detected_corners_a": int(len(corners_a)),
        "detected_corners_b": int(len(corners_b)),
    }
    if len(corners_a) < 4 or len(corners_b) < 4:
        diagnostics["reason"] = "insufficient_corners"
        return _build_alignment_candidate("corner", "partial_affine", None, None, diagnostics=diagnostics)

    orb = cv2.ORB_create(nfeatures=max_corners)
    keypoints_a = [cv2.KeyPoint(float(pt[0][0]), float(pt[0][1]), 16) for pt in corners_a]
    keypoints_b = [cv2.KeyPoint(float(pt[0][0]), float(pt[0][1]), 16) for pt in corners_b]
    keypoints_a, descriptors_a = orb.compute(views["A_analysis_gray"], keypoints_a)
    keypoints_b, descriptors_b = orb.compute(views["B_analysis_gray"], keypoints_b)

    if descriptors_a is None or descriptors_b is None or len(keypoints_a) < 4 or len(keypoints_b) < 4:
        diagnostics["reason"] = "insufficient_corner_descriptors"
        return _build_alignment_candidate("corner", "partial_affine", None, None, diagnostics=diagnostics)

    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
    matches = bf.knnMatch(descriptors_a, descriptors_b, k=2)
    good_matches = []
    for pair in matches:
        if len(pair) != 2:
            continue
        first, second = pair
        if first.distance < 0.78 * second.distance:
            good_matches.append(first)

    diagnostics["good_matches"] = len(good_matches)
    if len(good_matches) < 4:
        diagnostics["reason"] = "insufficient_corner_matches"
        return _build_alignment_candidate("corner", "partial_affine", None, None, diagnostics=diagnostics)

    src_points = np.float32([keypoints_a[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
    dst_points = np.float32([keypoints_b[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)
    src_points = _rescale_point_array(src_points, views["A_scale"])
    dst_points = _rescale_point_array(dst_points, views["B_scale"])
    return _build_alignment_candidate(
        "corner",
        "partial_affine",
        src_points,
        dst_points,
        {
            "corner_distribution_score": _distribution_score(src_points, views["A_gray"].shape),
            "angle_consistency": _angle_consistency(src_points, dst_points),
        },
        diagnostics,
    )


def fuse_candidate_points(candidate_list: list[AlignmentCandidate]) -> AlignmentCandidate:
    fused_src: list[tuple[float, float]] = []
    fused_dst: list[tuple[float, float]] = []
    seen_pairs: set[tuple[int, int, int, int]] = set()
    diagnostics: dict[str, Any] = {"candidate_source": "hybrid"}
    raw_metrics: dict[str, float] = {}
    support_counts = []

    for candidate in candidate_list:
        if candidate.src_points is None or candidate.dst_points is None:
            continue
        support_counts.append(candidate.matched_points)
        raw_metrics.update(candidate.raw_metrics)
        diagnostics.update(candidate.diagnostics)
        src_flat = candidate.src_points.reshape(-1, 2)
        dst_flat = candidate.dst_points.reshape(-1, 2)
        for src_point, dst_point in zip(src_flat, dst_flat):
            key = (
                int(round(src_point[0] / 4.0)),
                int(round(src_point[1] / 4.0)),
                int(round(dst_point[0] / 4.0)),
                int(round(dst_point[1] / 4.0)),
            )
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            fused_src.append((float(src_point[0]), float(src_point[1])))
            fused_dst.append((float(dst_point[0]), float(dst_point[1])))

    if not fused_src or not fused_dst:
        diagnostics["reason"] = "insufficient_hybrid_support"
        return _build_alignment_candidate("drawing_hybrid", "partial_affine", None, None, diagnostics=diagnostics)

    if support_counts:
        raw_metrics["support_balance_score"] = _clamp01(min(support_counts) / max(max(support_counts), 1))
    diagnostics["fused_points"] = len(fused_src)
    return _build_alignment_candidate(
        "drawing_hybrid",
        "partial_affine",
        _ensure_point_array(fused_src),
        _ensure_point_array(fused_dst),
        raw_metrics,
        diagnostics,
    )


def build_hybrid_candidate(
    primitives: dict[str, Any],
    line_candidate: AlignmentCandidate,
    corner_candidate: AlignmentCandidate,
    image_shape_a: tuple[int, int],
    image_shape_b: tuple[int, int],
    max_distance: float = 0.22,
) -> AlignmentCandidate:
    eligible_candidates = [candidate for candidate in (line_candidate, corner_candidate) if candidate.src_points is not None and candidate.dst_points is not None]
    # 최소 1개의 유효 candidate가 있고 충분한 점이 있으면 진행
    total_points = sum(c.matched_points for c in eligible_candidates)
    if len(eligible_candidates) < 1 or total_points < 4:
        diagnostics = {
            "candidate_source": "hybrid",
            "reason": "insufficient_hybrid_support",
            "eligible_count": len(eligible_candidates),
            "total_points": total_points,
        }
        return _build_alignment_candidate("drawing_hybrid", "partial_affine", None, None, diagnostics=diagnostics)

    hybrid_candidate = fuse_candidate_points(eligible_candidates)
    if hybrid_candidate.src_points is None or hybrid_candidate.dst_points is None:
        return hybrid_candidate

    support_a = primitives["support_a_full"]
    support_b = primitives["support_b_full"]
    if len(support_a) >= 4 and len(support_b) >= 4:
        sparse_src, sparse_dst = _pair_points_by_proximity(
            support_a.reshape(-1, 2),
            support_b.reshape(-1, 2),
            image_shape_a,
            image_shape_b,
            max_distance=max_distance,
        )
        if sparse_src is not None and sparse_dst is not None:
            hybrid_candidate = fuse_candidate_points(
                [
                    hybrid_candidate,
                    _build_alignment_candidate(
                        "drawing_hybrid",
                        "partial_affine",
                        sparse_src,
                        sparse_dst,
                        {"support_balance_score": hybrid_candidate.raw_metrics.get("support_balance_score", 0.0)},
                        {"candidate_source": "hybrid_sparse_support"},
                    ),
                ]
            )
    hybrid_candidate.diagnostics["candidate_source"] = "hybrid"
    return hybrid_candidate


def score_hybrid_alignment(candidate: AlignmentCandidate, image_shape: tuple[int, int]) -> ScoreResult:
    mask = candidate.inlier_mask
    matched_points = candidate.matched_points
    inlier_count = int(mask.sum()) if mask is not None else 0
    inlier_ratio = inlier_count / max(matched_points, 1)
    src_inliers = _mask_points(candidate.src_points, mask)
    spatial_coverage = _compute_spatial_coverage(src_inliers, image_shape)
    reprojection_quality = _reprojection_quality(candidate.reprojection_error_mean, image_shape)
    angle_diversity_score = candidate.raw_metrics.get("angle_diversity_score", 0.0)
    corner_distribution_score = candidate.raw_metrics.get("corner_distribution_score", 0.0)
    support_balance_score = candidate.raw_metrics.get("support_balance_score", 0.0)
    diversity = max(angle_diversity_score, corner_distribution_score)
    geometry_score = (
        0.40 * reprojection_quality
        + 0.30 * diversity
        + 0.20 * max(angle_diversity_score, corner_distribution_score)
        + 0.10 * support_balance_score
    )
    raw_metrics = dict(candidate.raw_metrics)
    raw_metrics["matched_points"] = float(matched_points)
    return _finalize_score(
        candidate.method,
        candidate.transform_model,
        inlier_count,
        inlier_ratio,
        spatial_coverage,
        geometry_score,
        candidate.reprojection_error_mean,
        raw_metrics,
        dict(candidate.diagnostics),
        (0.25, 0.20, 0.15, 0.40),
        6,
    )


def try_candidate_transforms(
    candidate: AlignmentCandidate,
    transform_models: list[str],
    score_fn,
    A_bgr: np.ndarray,
    B_bgr: np.ndarray,
    request_id: str,
    result_method: str = "drawing_hybrid",
    quality_threshold: Optional[float] = None,
) -> AlignmentResult:
    """Transform 모델들을 순차 시도하여 최적 결과 반환.
    
    Args:
        quality_threshold: 사용자 지정 품질 기준 (None이면 기본값 사용)
    """
    candidate_source = candidate.diagnostics.get("candidate_source", candidate.method)
    if candidate.src_points is None or candidate.dst_points is None or candidate.matched_points < 4:
        fallback_reason = candidate.diagnostics.get("reason", "insufficient_points")
        diagnostics = dict(candidate.diagnostics)
        diagnostics["transform_trials"] = 0
        return AlignmentResult(
            method=result_method,
            transform_model=candidate.transform_model,
            aligned_bgr=None,
            transform_matrix=None,
            normalized_quality=0.0,
            accepted=False,
            used_fallback=False,
            fallback_reason=fallback_reason,
            metrics={
                "matched_points": float(candidate.matched_points),
                "inlier_count": 0.0,
                "inlier_ratio": 0.0,
                "spatial_coverage": 0.0,
                "geometry_score": 0.0,
            },
            diagnostics=diagnostics,
        )

    accepted_results: list[tuple[ScoreResult, np.ndarray, np.ndarray]] = []
    last_score: Optional[ScoreResult] = None
    transform_trials = 0
    for transform_model in transform_models:
        transform_trials += 1
        matrix, mask, reprojection_error_mean = estimate_transform_from_matches(
            candidate.src_points,
            candidate.dst_points,
            transform_model=transform_model,
        )
        logger.debug(
            "[req=%s] transform trial: source=%s transform=%s matrix=%s",
            request_id,
            candidate_source,
            transform_model,
            matrix is not None,
        )
        if matrix is None:
            last_score = ScoreResult(
                method=candidate.method,
                transform_model=transform_model,
                normalized_quality=0.0,
                acceptance_threshold=0.55 if transform_model == "homography" else 0.45,
                accepted=False,
                inlier_count=0,
                inlier_ratio=0.0,
                spatial_coverage=0.0,
                geometry_score=0.0,
                reprojection_error_mean=None,
                raw_metrics={**candidate.raw_metrics, "matched_points": float(candidate.matched_points)},
                fallback_reason="transform_estimation_failed",
                diagnostics={**candidate.diagnostics, "transform_model": transform_model, "transform_trials": transform_trials},
            )
            continue

        active_candidate = AlignmentCandidate(
            method=candidate.method,
            transform_model=transform_model,
            src_points=candidate.src_points,
            dst_points=candidate.dst_points,
            matched_points=candidate.matched_points,
            raw_metrics=dict(candidate.raw_metrics),
            diagnostics=dict(candidate.diagnostics),
            transform_matrix=matrix,
            inlier_mask=mask,
            reprojection_error_mean=reprojection_error_mean,
        )
        raw_score = score_fn(active_candidate, A_bgr.shape[:2])
        # 사용자 지정 품질 기준이 있으면 적용
        if quality_threshold is not None:
            raw_score.acceptance_threshold = quality_threshold
        score = evaluate_alignment_acceptance(raw_score)
        score.diagnostics["transform_trials"] = transform_trials
        score.diagnostics["candidate_source"] = candidate_source
        logger.debug(
            "[req=%s] score: source=%s transform=%s quality=%.4f accepted=%s reason=%s",
            request_id,
            candidate_source,
            transform_model,
            score.normalized_quality,
            score.accepted,
            score.fallback_reason,
        )
        last_score = score
        if score.accepted:
            aligned_bgr = warp_aligned_image(B_bgr, matrix, transform_model, (A_bgr.shape[1], A_bgr.shape[0]))
            accepted_results.append((score, matrix, aligned_bgr))

    # 모든 모델 중 최고 품질 결과 선택
    if accepted_results:
        best_score, best_matrix, best_aligned = max(accepted_results, key=lambda x: x[0].normalized_quality)
        logger.debug(
            "[req=%s] selected best: transform=%s quality=%.4f (from %d accepted)",
            request_id,
            best_score.transform_model,
            best_score.normalized_quality,
            len(accepted_results),
        )
        metrics = dict(best_score.raw_metrics)
        metrics["reprojection_error_mean"] = 0.0 if best_score.reprojection_error_mean is None else float(best_score.reprojection_error_mean)
        return AlignmentResult(
            method=result_method,
            transform_model=best_score.transform_model,
            aligned_bgr=best_aligned,
            transform_matrix=best_matrix,
            normalized_quality=best_score.normalized_quality,
            accepted=True,
            used_fallback=False,
            fallback_reason=None,
            metrics=metrics,
            diagnostics=dict(best_score.diagnostics),
        )

    fallback_reason = "alignment_rejected"
    metrics = {
        "matched_points": float(candidate.matched_points),
        "inlier_count": 0.0,
        "inlier_ratio": 0.0,
        "spatial_coverage": 0.0,
        "geometry_score": 0.0,
    }
    diagnostics = dict(candidate.diagnostics)
    transform_model = candidate.transform_model
    quality = 0.0
    if last_score is not None:
        fallback_reason = last_score.fallback_reason or fallback_reason
        metrics = dict(last_score.raw_metrics)
        transform_model = last_score.transform_model
        quality = last_score.normalized_quality
        diagnostics = dict(last_score.diagnostics)
    diagnostics["candidate_source"] = candidate_source
    diagnostics["transform_trials"] = transform_trials
    return AlignmentResult(
        method=result_method,
        transform_model=transform_model,
        aligned_bgr=None,
        transform_matrix=None,
        normalized_quality=quality,
        accepted=False,
        used_fallback=False,
        fallback_reason=fallback_reason,
        metrics=metrics,
        diagnostics=diagnostics,
    )


def drawing_hybrid_path(
    A_bgr: np.ndarray,
    B_bgr: np.ndarray,
    nfeatures: int = 4000,
    request_id: str = "-",
    align_tolerance: float = 0.22,
    quality_threshold: float = 0.35,
) -> AlignmentResult:
    """CAD 도면용 hybrid 정렬 경로 (line 교점 + corner + sparse ORB 융합).
    
    Args:
        align_tolerance: 점 매칭 최대 허용 거리 (정규화 좌표, 0.10~0.30)
        quality_threshold: 품질 점수 통과 기준 (0.20~0.50)
    """
    views = prepare_drawing_views(A_bgr, B_bgr)
    primitives = extract_drawing_primitives(views, nfeatures=nfeatures)

    # line/corner candidate 추출 (hybrid 입력용)
    line_candidate = build_line_candidate(primitives, A_bgr.shape[:2], B_bgr.shape[:2], max_distance=align_tolerance)
    corner_candidate = build_corner_candidate(
        primitives,
        views,
        max_corners=min(_DRAWING_MAX_CORNERS, max(320, nfeatures // 5)),
        max_distance=align_tolerance,
    )

    # 디버그: line/corner candidate 상태 로깅
    logger.debug(
        "[req=%s] CAD candidates: line(pts=%s reason=%s) corner(pts=%s reason=%s)",
        request_id,
        line_candidate.matched_points if line_candidate.src_points is not None else 0,
        line_candidate.diagnostics.get("reason", "ok"),
        corner_candidate.matched_points if corner_candidate.src_points is not None else 0,
        corner_candidate.diagnostics.get("reason", "ok"),
    )

    # hybrid candidate 생성 (line + corner + sparse support 융합)
    hybrid_candidate = build_hybrid_candidate(
        primitives, line_candidate, corner_candidate, A_bgr.shape[:2], B_bgr.shape[:2],
        max_distance=align_tolerance,
    )

    # hybrid candidate가 유효하지 않으면 빈 결과 반환
    if hybrid_candidate.src_points is None or hybrid_candidate.dst_points is None:
        return AlignmentResult(
            method="drawing_hybrid",
            transform_model="partial_affine",
            aligned_bgr=None,
            transform_matrix=None,
            normalized_quality=0.0,
            accepted=False,
            used_fallback=False,
            fallback_reason="insufficient_hybrid_points",
            metrics={"matched_points": 0.0},
            diagnostics=hybrid_candidate.diagnostics,
        )

    # hybrid candidate에 대해 transform 시도 (partial_affine → affine → homography)
    result = try_candidate_transforms(
        hybrid_candidate,
        ["partial_affine", "affine", "homography"],
        score_hybrid_alignment,
        A_bgr,
        B_bgr,
        request_id,
        quality_threshold=quality_threshold,
    )
    result.diagnostics["candidate_source"] = "hybrid"
    return result


def orb_feature_align(A_gray: np.ndarray, B_gray: np.ndarray, nfeatures: int = 4000) -> AlignmentCandidate:
    orb = cv2.ORB_create(nfeatures=nfeatures)
    kp1, des1 = orb.detectAndCompute(A_gray, None)
    kp2, des2 = orb.detectAndCompute(B_gray, None)
    logger.debug("orb_feature_align keypoints: kp1=%s kp2=%s", len(kp1), len(kp2))

    diagnostics: dict[str, Any] = {
        "keypoints_a": len(kp1),
        "keypoints_b": len(kp2),
    }
    if des1 is None or des2 is None or len(kp1) < 4 or len(kp2) < 4:
        diagnostics["reason"] = "insufficient_keypoints"
        return _build_alignment_candidate("orb", "homography", None, None, diagnostics=diagnostics)

    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
    matches = bf.knnMatch(des1, des2, k=2)
    good_matches = []
    distances = []
    for pair in matches:
        if len(pair) != 2:
            continue
        first, second = pair
        if first.distance < 0.75 * second.distance:
            good_matches.append(first)
            distances.append(float(first.distance))

    logger.debug("orb_feature_align matches: total=%s good=%s", len(matches), len(good_matches))
    if len(good_matches) < 4:
        diagnostics["reason"] = "insufficient_matches"
        diagnostics["good_matches"] = len(good_matches)
        return _build_alignment_candidate("orb", "homography", None, None, diagnostics=diagnostics)

    src_points = np.float32([kp1[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
    dst_points = np.float32([kp2[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)
    raw_metrics = {
        "good_match_ratio": len(good_matches) / max(len(matches), 1),
        "lowe_ratio_pass_rate": len(good_matches) / max(len(matches), 1),
        "descriptor_stability": _descriptor_stability(distances),
    }
    diagnostics["good_matches"] = len(good_matches)
    return _build_alignment_candidate("orb", "homography", src_points, dst_points, raw_metrics, diagnostics)


def estimate_transform_from_matches(
    src_points: np.ndarray,
    dst_points: np.ndarray,
    transform_model: str = "homography",
) -> tuple[Optional[np.ndarray], Optional[np.ndarray], Optional[float]]:
    matrix = None
    mask = None
    if transform_model == "homography":
        matrix, mask = cv2.findHomography(dst_points, src_points, cv2.RANSAC, 5.0)
    elif transform_model == "affine":
        matrix, mask = cv2.estimateAffine2D(dst_points, src_points, method=cv2.RANSAC, ransacReprojThreshold=5.0)
    else:
        matrix, mask = cv2.estimateAffinePartial2D(dst_points, src_points, method=cv2.RANSAC, ransacReprojThreshold=5.0)

    reprojection_error_mean = _compute_reprojection_error(src_points, dst_points, matrix, transform_model, mask)
    return matrix, mask, reprojection_error_mean


def _finalize_score(
    method: str,
    transform_model: str,
    inlier_count: int,
    inlier_ratio: float,
    spatial_coverage: float,
    geometry_score: float,
    reprojection_error_mean: Optional[float],
    raw_metrics: dict[str, float],
    diagnostics: dict[str, Any],
    weights: tuple[float, float, float, float],
    target_inliers: float,
) -> ScoreResult:
    coverage_weight, ratio_weight, count_weight, geometry_weight = weights
    # drawing_hybrid: 교점/코너가 적은 단순 도형도 처리 → 낮은 coverage 기준
    coverage_norm = 0.15 if method == "drawing_hybrid" else 0.35
    coverage_score = _clamp01(spatial_coverage / coverage_norm)
    quality = (
        coverage_score * coverage_weight
        + _clamp01(inlier_ratio) * ratio_weight
        + _normalize_count(inlier_count, target_inliers) * count_weight
        + _clamp01(geometry_score) * geometry_weight
    )

    merged_metrics = dict(raw_metrics)
    merged_metrics.update({
        "inlier_count": float(inlier_count),
        "inlier_ratio": float(inlier_ratio),
        "spatial_coverage": float(spatial_coverage),
        "geometry_score": float(geometry_score),
        "matched_points": float(merged_metrics.get("matched_points", 0.0)),
    })

    # drawing_hybrid는 낮은 수용 임계값 적용 (단순 도형 허용)
    if method == "drawing_hybrid":
        _threshold = 0.45 if transform_model == "homography" else 0.35
    else:
        _threshold = 0.55 if transform_model == "homography" else 0.45
    return ScoreResult(
        method=method,
        transform_model=transform_model,
        normalized_quality=_clamp01(quality),
        acceptance_threshold=_threshold,
        accepted=False,
        inlier_count=inlier_count,
        inlier_ratio=float(inlier_ratio),
        spatial_coverage=float(spatial_coverage),
        geometry_score=float(geometry_score),
        reprojection_error_mean=reprojection_error_mean,
        raw_metrics=merged_metrics,
        fallback_reason=None,
        diagnostics=diagnostics,
    )


def score_orb_alignment(candidate: AlignmentCandidate, image_shape: tuple[int, int]) -> ScoreResult:
    mask = candidate.inlier_mask
    matched_points = candidate.matched_points
    inlier_count = int(mask.sum()) if mask is not None else 0
    inlier_ratio = inlier_count / max(matched_points, 1)
    src_inliers = _mask_points(candidate.src_points, mask)
    spatial_coverage = _compute_spatial_coverage(src_inliers, image_shape)
    reprojection_quality = _reprojection_quality(candidate.reprojection_error_mean, image_shape)
    geometry_score = (
        0.5 * candidate.raw_metrics.get("lowe_ratio_pass_rate", 0.0)
        + 0.3 * reprojection_quality
        + 0.2 * candidate.raw_metrics.get("descriptor_stability", 0.0)
    )
    raw_metrics = dict(candidate.raw_metrics)
    raw_metrics["matched_points"] = float(matched_points)
    return _finalize_score(
        candidate.method,
        candidate.transform_model,
        inlier_count,
        inlier_ratio,
        spatial_coverage,
        geometry_score,
        candidate.reprojection_error_mean,
        raw_metrics,
        dict(candidate.diagnostics),
        (0.25, 0.30, 0.20, 0.25),
        40,
    )


def evaluate_alignment_acceptance(score_result: ScoreResult) -> ScoreResult:
    """정렬 품질 평가 후 수락 여부 결정."""
    reason = None
    # drawing_hybrid: 단순 도형(교점 4개 등)도 허용 → 낮은 coverage 기준
    coverage_floor = 0.03 if score_result.method == "drawing_hybrid" else 0.10
    if score_result.normalized_quality < score_result.acceptance_threshold:
        reason = "score_below_threshold"
    elif score_result.spatial_coverage < coverage_floor:
        reason = "low_coverage"
    elif score_result.method == "orb" and score_result.inlier_count < 12:
        reason = "insufficient_inliers"
    elif score_result.method == "drawing_hybrid" and score_result.inlier_count < 4:
        reason = "insufficient_hybrid_inliers"

    score_result.accepted = reason is None
    score_result.fallback_reason = reason
    return score_result


def warp_aligned_image(
    B_bgr: np.ndarray,
    transform_matrix: np.ndarray,
    transform_model: str,
    output_size: tuple[int, int],
) -> np.ndarray:
    width, height = output_size
    if transform_model == "homography":
        return cv2.warpPerspective(
            B_bgr,
            transform_matrix,
            (width, height),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(255, 255, 255),
        )
    return cv2.warpAffine(
        B_bgr,
        transform_matrix,
        (width, height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )


def alignment_result_to_metadata(result: AlignmentResult) -> dict[str, Any]:
    metadata = {
        "match_quality": result.normalized_quality,
        "algorithm_used": result.method,
        "transform_model": result.transform_model,
        "alignment_failed": not result.accepted,
        "used_fallback": result.used_fallback,
        "fallback_reason": result.fallback_reason,
        "matched_points": int(result.metrics.get("matched_points", 0)),
        "inlier_count": int(result.metrics.get("inlier_count", 0)),
        "inlier_ratio": float(result.metrics.get("inlier_ratio", 0.0)),
        "spatial_coverage": float(result.metrics.get("spatial_coverage", 0.0)),
        "geometry_score": float(result.metrics.get("geometry_score", 0.0)),
    }
    if "reprojection_error_mean" in result.metrics:
        metadata["reprojection_error_mean"] = float(result.metrics["reprojection_error_mean"])
    for key in ("corner_distribution_score", "angle_diversity_score", "intersection_quality"):
        if key in result.diagnostics:
            metadata[key] = result.diagnostics[key]
        elif key in result.metrics:
            metadata[key] = float(result.metrics[key])
    for key in ("candidate_source", "candidate_count", "early_exit_stage", "transform_trials", "evaluated_pairs", "refinement_used"):
        if key in result.diagnostics:
            metadata[key] = result.diagnostics[key]
    return metadata


def estimate_alignment(
    A_bgr: np.ndarray,
    B_bgr: np.ndarray,
    method: str = "orb",
    nfeatures: int = 4000,
    request_id: str = "-",
    cad_align_tolerance: float = 0.22,
    cad_quality_threshold: float = 0.35,
) -> AlignmentResult:
    """이미지 정렬 추정.
    
    Args:
        cad_align_tolerance: CAD 모드 점 매칭 최대 허용 거리 (0.10~0.30)
        cad_quality_threshold: CAD 모드 품질 점수 통과 기준 (0.20~0.50)
    """
    requested_method = (method or "orb").lower()
    method = _normalize_alignment_method(method)
    if method not in _SUPPORTED_ALIGNMENT_METHODS:
        logger.warning("[req=%s] unsupported alignment method '%s', fallback to orb", request_id, requested_method)
        method = "orb"

    if method == "drawing_hybrid":
        logger.debug(
            "[req=%s] estimate_alignment start: requested=%s normalized=%s A=%s B=%s tolerance=%.2f threshold=%.2f",
            request_id,
            requested_method,
            method,
            _img_debug_info(A_bgr),
            _img_debug_info(B_bgr),
            cad_align_tolerance,
            cad_quality_threshold,
        )
        return drawing_hybrid_path(
            A_bgr, B_bgr, nfeatures=nfeatures, request_id=request_id,
            align_tolerance=cad_align_tolerance, quality_threshold=cad_quality_threshold,
        )

    A_gray = cv2.cvtColor(A_bgr, cv2.COLOR_BGR2GRAY)
    B_gray = cv2.cvtColor(B_bgr, cv2.COLOR_BGR2GRAY)
    transform_priority = {
        "orb": ["homography", "partial_affine"],
    }
    logger.debug(
        "[req=%s] estimate_alignment start: method=%s A=%s B=%s transforms=%s",
        request_id,
        method,
        _img_debug_info(A_bgr),
        _img_debug_info(B_bgr),
        transform_priority[method],
    )

    candidate = orb_feature_align(A_gray, B_gray, nfeatures=nfeatures)

    if candidate.src_points is None or candidate.dst_points is None or candidate.matched_points < 4:
        fallback_reason = candidate.diagnostics.get("reason", "insufficient_points")
        logger.warning("[req=%s] alignment candidate rejected early: method=%s reason=%s", request_id, method, fallback_reason)
        return AlignmentResult(
            method=method,
            transform_model=candidate.transform_model,
            aligned_bgr=None,
            transform_matrix=None,
            normalized_quality=0.0,
            accepted=False,
            used_fallback=False,
            fallback_reason=fallback_reason,
            metrics={
                "matched_points": float(candidate.matched_points),
                "inlier_count": 0.0,
                "inlier_ratio": 0.0,
                "spatial_coverage": 0.0,
                "geometry_score": 0.0,
            },
            diagnostics=dict(candidate.diagnostics),
        )

    score_fn = {
        "orb": score_orb_alignment,
    }[method]

    last_score: Optional[ScoreResult] = None
    for transform_model in transform_priority[method]:
        matrix, mask, reprojection_error_mean = estimate_transform_from_matches(
            candidate.src_points,
            candidate.dst_points,
            transform_model=transform_model,
        )
        logger.debug(
            "[req=%s] transform trial: method=%s transform=%s matrix=%s",
            request_id,
            method,
            transform_model,
            matrix is not None,
        )
        if matrix is None:
            last_score = ScoreResult(
                method=method,
                transform_model=transform_model,
                normalized_quality=0.0,
                acceptance_threshold=0.55 if transform_model == "homography" else 0.45,
                accepted=False,
                inlier_count=0,
                inlier_ratio=0.0,
                spatial_coverage=0.0,
                geometry_score=0.0,
                reprojection_error_mean=None,
                raw_metrics={**candidate.raw_metrics, "matched_points": float(candidate.matched_points)},
                fallback_reason="transform_estimation_failed",
                diagnostics={**candidate.diagnostics, "transform_model": transform_model},
            )
            continue

        active_candidate = AlignmentCandidate(
            method=method,
            transform_model=transform_model,
            src_points=candidate.src_points,
            dst_points=candidate.dst_points,
            matched_points=candidate.matched_points,
            raw_metrics=dict(candidate.raw_metrics),
            diagnostics=dict(candidate.diagnostics),
            transform_matrix=matrix,
            inlier_mask=mask,
            reprojection_error_mean=reprojection_error_mean,
        )
        score = evaluate_alignment_acceptance(score_fn(active_candidate, A_gray.shape))
        logger.debug(
            "[req=%s] score: method=%s transform=%s quality=%.4f accepted=%s reason=%s",
            request_id,
            method,
            transform_model,
            score.normalized_quality,
            score.accepted,
            score.fallback_reason,
        )
        last_score = score
        if not score.accepted:
            continue

        aligned_bgr = warp_aligned_image(B_bgr, matrix, transform_model, (A_bgr.shape[1], A_bgr.shape[0]))
        metrics = dict(score.raw_metrics)
        metrics["reprojection_error_mean"] = 0.0 if score.reprojection_error_mean is None else float(score.reprojection_error_mean)
        return AlignmentResult(
            method=method,
            transform_model=transform_model,
            aligned_bgr=aligned_bgr,
            transform_matrix=matrix,
            normalized_quality=score.normalized_quality,
            accepted=True,
            used_fallback=False,
            fallback_reason=None,
            metrics=metrics,
            diagnostics=dict(score.diagnostics),
        )

    fallback_reason = "alignment_rejected"
    metrics = {
        "matched_points": float(candidate.matched_points),
        "inlier_count": 0.0,
        "inlier_ratio": 0.0,
        "spatial_coverage": 0.0,
        "geometry_score": 0.0,
    }
    diagnostics = dict(candidate.diagnostics)
    transform_model = candidate.transform_model
    quality = 0.0
    if last_score is not None:
        fallback_reason = last_score.fallback_reason or fallback_reason
        metrics = dict(last_score.raw_metrics)
        transform_model = last_score.transform_model
        quality = last_score.normalized_quality
        diagnostics = dict(last_score.diagnostics)

    logger.warning(
        "[req=%s] alignment rejected: method=%s transform=%s reason=%s quality=%.4f",
        request_id,
        method,
        transform_model,
        fallback_reason,
        quality,
    )
    return AlignmentResult(
        method=method,
        transform_model=transform_model,
        aligned_bgr=None,
        transform_matrix=None,
        normalized_quality=quality,
        accepted=False,
        used_fallback=False,
        fallback_reason=fallback_reason,
        metrics=metrics,
        diagnostics=diagnostics,
    )


def align_images(A_bgr: np.ndarray, B_bgr: np.ndarray, nfeatures: int = 4000) -> Tuple[np.ndarray, Optional[np.ndarray], Optional[np.ndarray], float]:
    """기존 ORB 호출 경로 호환용 래퍼."""
    result = estimate_alignment(A_bgr, B_bgr, method="orb", nfeatures=nfeatures)
    return A_bgr, result.aligned_bgr, result.transform_matrix, result.normalized_quality


def fallback_align(A_bgr: np.ndarray, B_bgr: np.ndarray) -> np.ndarray:
    """
    간단한 리사이즈 기반 정렬 (폴백)
    
    Args:
        A_bgr: 기준 이미지
        B_bgr: 정렬할 이미지
    
    Returns:
        정렬된 이미지
    """
    hA, wA = A_bgr.shape[:2]
    hB, wB = B_bgr.shape[:2]

    scale = min(wA / wB, hA / hB)
    new_w = int(wB * scale)
    new_h = int(hB * scale)
    B_resized = cv2.resize(B_bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)

    canvas = np.full((hA, wA, 3), 255, dtype=np.uint8)
    x_off = (wA - new_w) // 2
    y_off = (hA - new_h) // 2
    canvas[y_off:y_off+new_h, x_off:x_off+new_w] = B_resized
    
    logger.info("폴백 정렬 사용 (리사이즈 기반)")
    return canvas


def hex_to_bgr(hex_color: str) -> Tuple[int, int, int]:
    """Hex 색상 코드를 BGR 튜플로 변환"""
    hex_color = hex_color.lstrip('#')
    rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    return (rgb[2], rgb[1], rgb[0])  # Convert RGB to BGR


def compare_images_overlay(
    A_bgr: np.ndarray,
    B_aligned_bgr: np.ndarray,
    bin_thresh: int = 200,
    colors: dict = None,
    use_dilation: bool = False,
) -> np.ndarray:
    """
    두 이미지 오버레이 (겹치기) — diff 3색 공통 사용

    Args:
        colors: {
            'diff_file1': '#RRGGBB',  File 1 전용 영역
            'diff_file2': '#RRGGBB',  File 2 전용 영역
            'diff_common': '#RRGGBB'  공통 영역
        }
        use_dilation: CAD 도면 모드용 — dilation으로 warp 보간 아티팩트 허용
    """
    if colors is None:
        colors = {}

    c_file1  = hex_to_bgr(colors.get('diff_file1',  '#0000FF'))
    c_file2  = hex_to_bgr(colors.get('diff_file2',  '#FF0000'))
    c_common = hex_to_bgr(colors.get('diff_common', '#000000'))

    h, w = A_bgr.shape[:2]

    A_gray = cv2.cvtColor(A_bgr, cv2.COLOR_BGR2GRAY)
    B_gray = cv2.cvtColor(B_aligned_bgr, cv2.COLOR_BGR2GRAY)

    _, A_bin = cv2.threshold(A_gray, bin_thresh, 255, cv2.THRESH_BINARY_INV)
    _, B_bin = cv2.threshold(B_gray, bin_thresh, 255, cv2.THRESH_BINARY_INV)

    if use_dilation:
        # CAD 도면: ±1~2px warp 오차 허용 — 양쪽 dilation 후 근접 선은 공통으로 판정
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        A_bin_d = cv2.dilate(A_bin, kernel, iterations=1)
        B_bin_d = cv2.dilate(B_bin, kernel, iterations=1)
        both   = np.logical_or(
            np.logical_and(A_bin > 0, B_bin_d > 0),
            np.logical_and(B_bin > 0, A_bin_d > 0),
        )
        only_A = np.logical_and(A_bin > 0, B_bin_d == 0)
        only_B = np.logical_and(B_bin > 0, A_bin_d == 0)
    else:
        only_A = np.logical_and(A_bin > 0, B_bin == 0)
        only_B = np.logical_and(B_bin > 0, A_bin == 0)
        both   = np.logical_and(A_bin > 0, B_bin > 0)

    result = np.full((h, w, 3), 255, dtype=np.uint8)
    result[both]   = c_common
    result[only_A] = c_file1
    result[only_B] = c_file2

    return result


def encode_image_to_base64(img: np.ndarray, format: str = 'JPEG', quality: int = 85) -> str:
    """
    이미지를 base64 문자열로 인코딩
    
    Args:
        img: 입력 이미지 (BGR)
        format: 'JPEG' 또는 'PNG'
        quality: JPEG 품질 (1-100)
    
    Returns:
        base64 인코딩된 data URI
    """
    logger.debug(
        "encode_image_to_base64 start: format=%s quality=%s %s",
        format,
        quality,
        _img_debug_info(img),
    )

    if format.upper() == 'JPEG':
        encode_param = [cv2.IMWRITE_JPEG_QUALITY, quality]
        _, buffer = cv2.imencode('.jpg', img, encode_param)
        mime_type = 'image/jpeg'
    else:  # PNG
        _, buffer = cv2.imencode('.png', img)
        mime_type = 'image/png'
    
    base64_str = base64.b64encode(buffer).decode('utf-8')
    logger.debug(
        "encode_image_to_base64 done: mime=%s encoded_bytes=%s base64_chars=%s",
        mime_type,
        len(buffer),
        len(base64_str),
    )
    return f"data:{mime_type};base64,{base64_str}"


def generate_highlighted_images(
    A_bgr: np.ndarray,
    B_aligned_bgr: np.ndarray,
    diff_thresh: int = 30,
    bin_thresh: int = 200,
    colors: dict = None,
    use_dilation: bool = False,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    각 이미지에 차이점 강조 (Side-by-Side 뷰용)
    File1 뷰: File1 전용 영역(c_file1) + 공통 영역(c_common)
    File2 뷰: File2 전용 영역(c_file2) + 공통 영역(c_common)

    Args:
        colors: {
            'diff_file1': '#RRGGBB',
            'diff_file2': '#RRGGBB',
            'diff_common': '#RRGGBB'
        }
        use_dilation: CAD 도면 모드용 — dilation으로 warp 보간 아티팩트 허용
    """
    if colors is None:
        colors = {}

    c_file1  = hex_to_bgr(colors.get('diff_file1',  '#0000FF'))
    c_file2  = hex_to_bgr(colors.get('diff_file2',  '#FF0000'))
    c_common = hex_to_bgr(colors.get('diff_common', '#000000'))

    h, w = A_bgr.shape[:2]

    A_gray = cv2.cvtColor(A_bgr, cv2.COLOR_BGR2GRAY)
    B_gray = cv2.cvtColor(B_aligned_bgr, cv2.COLOR_BGR2GRAY)

    _, A_bin = cv2.threshold(A_gray, bin_thresh, 255, cv2.THRESH_BINARY_INV)
    _, B_bin = cv2.threshold(B_gray, bin_thresh, 255, cv2.THRESH_BINARY_INV)

    if use_dilation:
        # CAD 도면 모드: ±1~2px warp 오차 허용 — 근접 선은 공통으로 판정
        # diff_common/darker 로직 제거 — binary 선 존재 여부만 기준
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        A_bin_d = cv2.dilate(A_bin, kernel, iterations=1)
        B_bin_d = cv2.dilate(B_bin, kernel, iterations=1)
        both_mask   = np.logical_or(
            np.logical_and(A_bin > 0, B_bin_d > 0),
            np.logical_and(B_bin > 0, A_bin_d > 0),
        )
        only_A_mask = np.logical_and(A_bin > 0, B_bin_d == 0)
        only_B_mask = np.logical_and(B_bin > 0, A_bin_d == 0)
    else:
        # ORB 사진 모드: pixel-diff 기반 — 공통 영역 중 밝기 차이가 있으면 각각에 귀속
        diff = cv2.absdiff(A_gray, B_gray)
        _, diff_mask = cv2.threshold(diff, diff_thresh, 255, cv2.THRESH_BINARY)
        only_A_raw = np.logical_and(A_bin > 0, B_bin == 0)
        only_B_raw = np.logical_and(B_bin > 0, A_bin == 0)
        both_raw   = np.logical_and(A_bin > 0, B_bin > 0)
        diff_common = np.logical_and(diff_mask > 0, both_raw)
        only_A_mask = np.logical_or(only_A_raw, np.logical_and(diff_common, A_gray < B_gray))
        only_B_mask = np.logical_or(only_B_raw, np.logical_and(diff_common, B_gray < A_gray))
        both_mask   = np.logical_and(both_raw, ~diff_mask.astype(bool))

    # File 1 뷰: A 전용(c_file1) + 공통(c_common)
    imgA_out = np.full((h, w, 3), 255, dtype=np.uint8)
    imgA_out[both_mask]   = c_common
    imgA_out[only_A_mask] = c_file1

    # File 2 뷰: B 전용(c_file2) + 공통(c_common)
    imgB_out = np.full((h, w, 3), 255, dtype=np.uint8)
    imgB_out[both_mask]   = c_common
    imgB_out[only_B_mask] = c_file2

    return imgA_out, imgB_out

def process_comparison(
    file1_bytes: bytes,
    file1_type: str,
    file2_bytes: bytes,
    file2_type: str,
    file1_name: str = "file1",
    file2_name: str = "file2",
    diff_threshold: int = 30,
    feature_count: int = 4000,
    alignment_algorithm: str = "orb",
    page1: int = 0,
    page2: int = 0,
    colors: dict = None,
    # 품질 설정
    processing_resolution: int = 6000,  # 비교 연산용 최대 해상도 (4000-8000)
    output_resolution: int = 2000,      # 화면 출력용 최대 해상도 (1000-4000)
    output_quality: int = 85,           # JPEG 출력 품질 (50-100)
    pdf_dpi: int = 300,                 # PDF 변환 DPI (100-600)
    cad_mode: bool = False,
    cad_line_width: float = 0.2,
    apply_line_width: bool = True,
    hide_hatch_transparency: bool = False,
    cad_align_tolerance: float = 0.22,  # CAD 정렬 허용도 (0.10~0.30)
    cad_quality_threshold: float = 0.35,  # CAD 품질 기준 (0.20~0.50)
    crop_rect: dict = None,
    request_id: str = "-",
) -> dict:
    """
    이미지 비교 전체 파이프라인 (2단계)

    Stage 1 — 고해상도 비교 연산:
        PDF 파일은 pdf_dpi 해상도로 변환하고, processing_resolution 범위 내에서
        비교 연산(정렬 + 차이 계산)을 수행한다. 원본 해상도가 높을수록 미세한
        차이를 더 정확하게 감지할 수 있다.

    Stage 2 — 출력용 다운샘플:
        브라우저 전송 전에 output_resolution으로 다운샘플하고 output_quality로
        PNG 인코딩한다.

    Args:
        colors: 색상 설정 딕셔너리
        processing_resolution: 비교 연산에 사용할 최대 해상도 (px). 원본이 이보다
            크면 다운샘플 후 연산한다.
        output_resolution: 브라우저 출력용 최대 해상도 (px). 연산 완료 후 다운샘플.
        output_quality: JPEG 인코딩 품질 (50-100).
        pdf_dpi: PDF → 이미지 변환 해상도.
    """
    # 입력값 범위 보정 (clamp)
    processing_resolution = max(4000, min(8000, processing_resolution))
    output_resolution = max(1000, min(4000, output_resolution))
    output_quality = max(50, min(100, output_quality))
    pdf_dpi = max(100, min(600, pdf_dpi))

    logger.debug(
        "[req=%s] process_comparison start: file1_type=%s file2_type=%s "
        "diff_threshold=%s feature_count=%s alignment_algorithm=%s pages=(%s,%s) "
        "processing_resolution=%s output_resolution=%s output_quality=%s pdf_dpi=%s cad_mode=%s cad_line_width=%s",
        request_id,
        file1_type,
        file2_type,
        diff_threshold,
        feature_count,
        alignment_algorithm,
        page1,
        page2,
        processing_resolution,
        output_resolution,
        output_quality,
        pdf_dpi,
        cad_mode,
        cad_line_width,
    )

    try:
        # Stage 1-A. 파일 로드 (PDF는 사용자 지정 DPI 적용, crop_rect 있을 때만 clip 적용)
        logger.info("[req=%s] 파일 로드 중... (pdf_dpi=%s, cad_mode=%s, crop=%s)", request_id, pdf_dpi, cad_mode, crop_rect is not None)
        img1, pages1, type1 = load_file(
            file1_bytes,
            file1_type,
            page1,
            dpi=pdf_dpi,
            cad_mode=cad_mode,
            cad_line_width=cad_line_width,
            apply_line_width=apply_line_width,
            hide_hatch_transparency=hide_hatch_transparency,
            request_id=request_id,
            source_label=file1_name,
            clip_rect=crop_rect,
        )
        img2, pages2, type2 = load_file(
            file2_bytes,
            file2_type,
            page2,
            dpi=pdf_dpi,
            cad_mode=cad_mode,
            cad_line_width=cad_line_width,
            apply_line_width=apply_line_width,
            hide_hatch_transparency=hide_hatch_transparency,
            request_id=request_id,
            source_label=file2_name,
            clip_rect=crop_rect,
        )
        logger.debug(
            "[req=%s] Stage1-A load complete: file1(type=%s,pages=%s,%s) file2(type=%s,pages=%s,%s)",
            request_id,
            type1,
            pages1,
            _img_debug_info(img1),
            type2,
            pages2,
            _img_debug_info(img2),
        )

        # Stage 1-B. 비교 연산용 다운샘플 (processing_resolution 기준)
        img1 = downsample_if_needed(img1, max_dimension=processing_resolution)
        img2 = downsample_if_needed(img2, max_dimension=processing_resolution)
        logger.info(
            "[req=%s] 연산 해상도 적용: max=%spx, img1=%sx%s, img2=%sx%s",
            request_id, processing_resolution,
            img1.shape[1], img1.shape[0], img2.shape[1], img2.shape[0],
        )

        # Stage 1-C. 이미지 정렬 (고해상도 기준)
        logger.info("[req=%s] 이미지 정렬 중... algorithm=%s", request_id, alignment_algorithm)
        alignment_result = estimate_alignment(
            img1,
            img2,
            method=alignment_algorithm,
            nfeatures=feature_count,
            request_id=request_id,
            cad_align_tolerance=cad_align_tolerance,
            cad_quality_threshold=cad_quality_threshold,
        )
        aligned_img2 = alignment_result.aligned_bgr
        logger.debug(
            "[req=%s] Stage1-C align result: method=%s transform=%s accepted=%s quality=%.4f",
            request_id,
            alignment_result.method,
            alignment_result.transform_model,
            alignment_result.accepted,
            alignment_result.normalized_quality,
        )

        if aligned_img2 is None or not alignment_result.accepted:
            logger.warning(
                "[req=%s] 정렬 실패, 폴백 정렬 사용 (method=%s quality=%.4f reason=%s)",
                request_id,
                alignment_result.method,
                alignment_result.normalized_quality,
                alignment_result.fallback_reason,
            )
            aligned_img2 = fallback_align(img1, img2)
            alignment_result = AlignmentResult(
                method=alignment_result.method,
                transform_model=alignment_result.transform_model,
                aligned_bgr=aligned_img2,
                transform_matrix=alignment_result.transform_matrix,
                normalized_quality=alignment_result.normalized_quality,
                accepted=False,
                used_fallback=True,
                fallback_reason=alignment_result.fallback_reason,
                metrics=dict(alignment_result.metrics),
                diagnostics=dict(alignment_result.diagnostics),
            )
            logger.debug("[req=%s] Stage1-C fallback aligned: %s", request_id, _img_debug_info(aligned_img2))

        # Stage 1-D. 비교 연산 (고해상도에서 수행 → 미세 차이 정확 감지)

        # CAD 도면 모드: dilation으로 warp 보간 아티팩트 허용 / ORB 사진 모드: pixel-diff 기반
        _use_dilation = _normalize_alignment_method(alignment_algorithm) == "drawing_hybrid"
        # 모든 모드에서 필요한 3개 이미지 생성: file1_highlighted, file2_highlighted, overlay
        file1_result, file2_result = generate_highlighted_images(
            img1, aligned_img2, diff_thresh=diff_threshold, bin_thresh=_BIN_THRESHOLD, colors=colors,
            use_dilation=_use_dilation,
        )
        overlay_result = compare_images_overlay(
            img1, aligned_img2, bin_thresh=_BIN_THRESHOLD, colors=colors, use_dilation=_use_dilation,
        )
        logger.debug("[req=%s] Stage1-D compare done: overlay=%s", request_id, _img_debug_info(overlay_result))

        # Stage 2. 출력용 다운샘플 + 인코딩
        overlay_out = downsample_if_needed(overlay_result, max_dimension=output_resolution)
        file1_out = downsample_if_needed(file1_result, max_dimension=output_resolution)
        file2_out = downsample_if_needed(file2_result, max_dimension=output_resolution)
        logger.info(
            "[req=%s] 출력 해상도 적용: max=%spx, overlay=%sx%s",
            request_id, output_resolution, overlay_out.shape[1], overlay_out.shape[0],
        )

        overlay_base64 = encode_image_to_base64(overlay_out, format='PNG')
        file1_base64 = encode_image_to_base64(file1_out, format='PNG')
        file2_base64 = encode_image_to_base64(file2_out, format='PNG')

        logger.debug(
            "[req=%s] Stage2 payload chars: overlay=%s file1=%s file2=%s",
            request_id, len(overlay_base64), len(file1_base64), len(file2_base64),
        )

        return {
            "file1_base64": file1_base64,
            "file2_base64": file2_base64,
            "overlay_base64": overlay_base64,
            "metadata": {
                "file1_pages": pages1,
                "file2_pages": pages2,
                "processing_size": f"{overlay_result.shape[1]}x{overlay_result.shape[0]}",
                "result_size": f"{overlay_out.shape[1]}x{overlay_out.shape[0]}",
                **alignment_result_to_metadata(alignment_result),
            }
        }

    except MemoryError as e:
        msg = (
            f"메모리 부족으로 처리가 중단됐습니다 — "
            f"pdf_dpi({pdf_dpi}) 또는 processing_resolution({processing_resolution}px)을 낮춰 주세요. "
            f"(상세: {e})"
        )
        logger.error("[req=%s] MemoryError: %s", request_id, msg)
        raise ValueError(msg)  # → 라우터에서 HTTP 400으로 변환
    except Exception as e:
        logger.error("[req=%s] 비교 처리 실패: %s: %s", request_id, type(e).__name__, str(e), exc_info=True)
        raise
