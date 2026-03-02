"""
Image Inspector - 이미지/PDF 비교 처리 모듈
image_inspector.py의 핵심 로직을 FastAPI용으로 포팅
"""

import cv2
import numpy as np
from PIL import Image
import base64
import io
from typing import Tuple, Optional
import logging

from .pdf2img import pdf_to_bgr

logger = logging.getLogger(__name__)


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
        logger.error(f"TIFF 변환 실패: {str(e)}")
        raise ValueError(f"TIFF 변환 실패: {str(e)}")


def load_file(file_bytes: bytes, content_type: str, page_num: int = 0) -> Tuple[np.ndarray, int, str]:
    """
    파일 로드 (이미지 또는 PDF)
    
    Args:
        file_bytes: 파일 바이트 데이터
        content_type: MIME 타입
        page_num: PDF 페이지 번호
    
    Returns:
        (이미지 BGR 배열, 총 페이지 수, 파일 타입)
    """
    try:
        if "pdf" in content_type.lower():
            img_bgr, total_pages = pdf_to_bgr(file_bytes, page_num=page_num)
            return img_bgr, total_pages, "pdf"
        elif "tiff" in content_type.lower() or "tif" in content_type.lower():
            img_bgr, total_pages = tiff_to_image(file_bytes, page_num=page_num)
            return img_bgr, total_pages, "tiff"
        else:
            arr = np.frombuffer(file_bytes, np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            
            if img is None:
                raise ValueError("이미지 디코딩 실패")
            
            return img, 1, "image"
    except Exception as e:
        logger.error(f"파일 로드 실패: {str(e)}")
        raise ValueError(f"파일 로드 실패: {str(e)}")


def downsample_if_needed(img: np.ndarray, max_dimension: int = 4000) -> np.ndarray:
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
    
    if max_size > max_dimension:
        scale = max_dimension / max_size
        new_w = int(w * scale)
        new_h = int(h * scale)
        img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
        logger.info(f"이미지 다운샘플링: {w}x{h} -> {new_w}x{new_h}")
    
    return img


def align_images(A_bgr: np.ndarray, B_bgr: np.ndarray, nfeatures: int = 4000) -> Tuple[np.ndarray, Optional[np.ndarray], Optional[np.ndarray], float]:
    """
    ORB 특징점 매칭을 이용한 이미지 정렬
    
    Args:
        A_bgr: 기준 이미지
        B_bgr: 정렬할 이미지
        nfeatures: ORB 특징점 개수
    
    Returns:
        (기준 이미지, 정렬된 이미지, 호모그래피 행렬, 매칭 품질)
    """
    A_gray = cv2.cvtColor(A_bgr, cv2.COLOR_BGR2GRAY)
    B_gray = cv2.cvtColor(B_bgr, cv2.COLOR_BGR2GRAY)

    orb = cv2.ORB_create(nfeatures=nfeatures)
    kp1, des1 = orb.detectAndCompute(A_gray, None)
    kp2, des2 = orb.detectAndCompute(B_gray, None)

    if des1 is None or des2 is None or len(kp1) < 4 or len(kp2) < 4:
        logger.warning("특징점 부족, 정렬 실패")
        return A_bgr, None, None, 0

    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
    try:
        matches = bf.knnMatch(des1, des2, k=2)
    except Exception:
        logger.warning("특징점 매칭 실패")
        return A_bgr, None, None, 0

    good_matches = []
    for match_pair in matches:
        if len(match_pair) == 2:
            m, n = match_pair
            if m.distance < 0.75 * n.distance:
                good_matches.append(m)

    min_matches = 10
    if len(good_matches) < min_matches:
        logger.warning(f"충분한 매칭 부족: {len(good_matches)}/{min_matches}")
        return A_bgr, None, None, len(good_matches) / min_matches

    src_pts = np.float32([kp1[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
    dst_pts = np.float32([kp2[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

    H, mask = cv2.findHomography(dst_pts, src_pts, cv2.RANSAC, 5.0)
    
    if H is None:
        logger.warning("호모그래피 계산 실패")
        return A_bgr, None, None, 0

    inliers = np.sum(mask)
    match_quality = inliers / len(good_matches) if len(good_matches) > 0 else 0

    hA, wA = A_bgr.shape[:2]
    warped_B = cv2.warpPerspective(B_bgr, H, (wA, hA),
                                   flags=cv2.INTER_LINEAR,
                                   borderMode=cv2.BORDER_CONSTANT,
                                   borderValue=(255, 255, 255))

    logger.info(f"정렬 성공: 매칭 품질 {match_quality:.2f}")
    return A_bgr, warped_B, H, match_quality


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

def compare_images(
    A_bgr: np.ndarray, 
    B_aligned_bgr: np.ndarray, 
    diff_thresh: int = 30, 
    bin_thresh: int = 200,
    colors: dict = None
) -> np.ndarray:
    """
    두 이미지 비교 (차이점 강조)
    
    Args:
        colors: {
            'diff_file1': '#RRGGBB', 
            'diff_file2': '#RRGGBB', 
            'diff_common': '#RRGGBB'
        }
    """
    # Default colors if not provided
    if colors is None:
        colors = {}
    
    c_file1 = hex_to_bgr(colors.get('diff_file1', '#0000FF')) # Blue default
    c_file2 = hex_to_bgr(colors.get('diff_file2', '#FF0000')) # Red default
    c_common = hex_to_bgr(colors.get('diff_common', '#000000')) # Black default

    h, w = A_bgr.shape[:2]
    
    A_gray = cv2.cvtColor(A_bgr, cv2.COLOR_BGR2GRAY)
    B_gray = cv2.cvtColor(B_aligned_bgr, cv2.COLOR_BGR2GRAY)
    
    _, A_bin = cv2.threshold(A_gray, bin_thresh, 255, cv2.THRESH_BINARY_INV)
    _, B_bin = cv2.threshold(B_gray, bin_thresh, 255, cv2.THRESH_BINARY_INV)
    
    diff = cv2.absdiff(A_gray, B_gray)
    _, diff_mask = cv2.threshold(diff, diff_thresh, 255, cv2.THRESH_BINARY)
    
    only_A = np.logical_and(A_bin > 0, B_bin == 0).astype(np.uint8) * 255
    only_B = np.logical_and(B_bin > 0, A_bin == 0).astype(np.uint8) * 255
    both = np.logical_and(A_bin > 0, B_bin > 0).astype(np.uint8) * 255
    
    diff_common = np.logical_and(diff_mask > 0, both > 0)
    darker_in_A = np.logical_and(diff_common, A_gray < B_gray)
    darker_in_B = np.logical_and(diff_common, B_gray < A_gray)
    
    only_A = np.logical_or(only_A > 0, darker_in_A)
    only_B = np.logical_or(only_B > 0, darker_in_B)
    both = np.logical_and(both > 0, ~diff_mask.astype(bool))
    
    result = np.full((h, w, 3), 255, dtype=np.uint8)
    result[both] = c_common
    result[only_A] = c_file1
    result[only_B] = c_file2
    
    return result


def compare_images_overlay(
    A_bgr: np.ndarray, 
    B_aligned_bgr: np.ndarray, 
    bin_thresh: int = 200,
    colors: dict = None
) -> np.ndarray:
    """
    두 이미지 오버레이 (겹치기)
    
    Args:
        colors: {
            'overlay_file1': '#RRGGBB',
            'overlay_file2': '#RRGGBB'
        }
    """
    # Default colors
    if colors is None:
        colors = {}
        
    c_file1 = hex_to_bgr(colors.get('overlay_file1', '#FFA500')) # Orange default
    c_file2 = hex_to_bgr(colors.get('overlay_file2', '#00FF00')) # Green default

    h, w = A_bgr.shape[:2]
    
    A_gray = cv2.cvtColor(A_bgr, cv2.COLOR_BGR2GRAY)
    B_gray = cv2.cvtColor(B_aligned_bgr, cv2.COLOR_BGR2GRAY)
    
    _, A_bin = cv2.threshold(A_gray, bin_thresh, 255, cv2.THRESH_BINARY_INV)
    _, B_bin = cv2.threshold(B_gray, bin_thresh, 255, cv2.THRESH_BINARY_INV)
    
    result = np.full((h, w, 3), 255, dtype=np.uint8)
    
    result[A_bin > 0] = c_file1
    result[B_bin > 0] = c_file2
    
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
    if format.upper() == 'JPEG':
        encode_param = [cv2.IMWRITE_JPEG_QUALITY, quality]
        _, buffer = cv2.imencode('.jpg', img, encode_param)
        mime_type = 'image/jpeg'
    else:  # PNG
        _, buffer = cv2.imencode('.png', img)
        mime_type = 'image/png'
    
    base64_str = base64.b64encode(buffer).decode('utf-8')
    return f"data:{mime_type};base64,{base64_str}"


def generate_highlighted_images(
    A_bgr: np.ndarray, 
    B_aligned_bgr: np.ndarray, 
    diff_thresh: int = 30, 
    bin_thresh: int = 200,
    colors: dict = None
) -> Tuple[np.ndarray, np.ndarray]:
    """
    각 이미지에 차이점 강조 (Side-by-Side 뷰용)
    A에는 A만의 특징(삭제됨)을, B에는 B만의 특징(추가됨)을 강조
    
    Args:
        colors: {
            'diff_file1': '#RRGGBB', 
            'diff_file2': '#RRGGBB',
            'diff_common': '#RRGGBB'
        }
    """
    if colors is None:
        colors = {}
        
    c_file1 = hex_to_bgr(colors.get('diff_file1', '#0000FF')) # Blue default
    c_file2 = hex_to_bgr(colors.get('diff_file2', '#FF0000')) # Red default
    c_common = hex_to_bgr(colors.get('diff_common', '#000000')) # Black default

    h, w = A_bgr.shape[:2]
    
    A_gray = cv2.cvtColor(A_bgr, cv2.COLOR_BGR2GRAY)
    B_gray = cv2.cvtColor(B_aligned_bgr, cv2.COLOR_BGR2GRAY)
    
    _, A_bin = cv2.threshold(A_gray, bin_thresh, 255, cv2.THRESH_BINARY_INV)
    _, B_bin = cv2.threshold(B_gray, bin_thresh, 255, cv2.THRESH_BINARY_INV)
    
    diff = cv2.absdiff(A_gray, B_gray)
    _, diff_mask = cv2.threshold(diff, diff_thresh, 255, cv2.THRESH_BINARY)
    
    # Masks
    only_A = np.logical_and(A_bin > 0, B_bin == 0).astype(np.uint8) * 255
    only_B = np.logical_and(B_bin > 0, A_bin == 0).astype(np.uint8) * 255
    both = np.logical_and(A_bin > 0, B_bin > 0).astype(np.uint8) * 255
    
    # 엣지 노이즈 보정 (Common diff)
    diff_common = np.logical_and(diff_mask > 0, both > 0)
    darker_in_A = np.logical_and(diff_common, A_gray < B_gray)
    darker_in_B = np.logical_and(diff_common, B_gray < A_gray)
    
    only_A = np.logical_or(only_A > 0, darker_in_A)
    only_B = np.logical_or(only_B > 0, darker_in_B)
    # 공통 영역 (차이가 없는 부분)
    both_no_diff = np.logical_and(both > 0, ~diff_mask.astype(bool))

    # Image A Highlighted
    imgA_out = np.full((h, w, 3), 255, dtype=np.uint8) # 배경을 흰색으로 초기화 (원본 유지보다 색상 지정이 정확함)
    imgA_out[both_no_diff] = c_common
    imgA_out[only_A] = c_file1 
    
    # Image B Highlighted
    imgB_out = np.full((h, w, 3), 255, dtype=np.uint8)
    imgB_out[both_no_diff] = c_common
    imgB_out[only_B] = c_file2
    
    return imgA_out, imgB_out

def process_comparison(
    file1_bytes: bytes,
    file1_type: str,
    file2_bytes: bytes,
    file2_type: str,
    mode: str = "difference",
    diff_threshold: int = 30,
    feature_count: int = 4000,
    page1: int = 0,
    page2: int = 0,
    bin_threshold: int = 200,
    colors: dict = None
) -> dict:
    """
    이미지 비교 전체 파이프라인
    
    Args:
        ...
        colors: 색상 설정 딕셔너리
    """
    try:
        # 1. 파일 로드
        logger.info("파일 로드 중...")
        img1, pages1, type1 = load_file(file1_bytes, file1_type, page1)
        img2, pages2, type2 = load_file(file2_bytes, file2_type, page2)
        
        # 2. 다운샘플링
        img1 = downsample_if_needed(img1, max_dimension=4000)
        img2 = downsample_if_needed(img2, max_dimension=4000)
        
        # 3. 이미지 정렬
        logger.info("이미지 정렬 중...")
        _, aligned_img2, H, quality = align_images(img1, img2, nfeatures=feature_count)
        
        alignment_failed = False
        # 폴백: 정렬 실패 시
        if aligned_img2 is None or quality < 0.3:
            logger.warning("ORB 정렬 실패, 폴백 정렬 사용")
            aligned_img2 = fallback_align(img1, img2)
            alignment_failed = True
        
        # 4. 비교
        logger.info(f"비교 모드: {mode}")
        
        file1_result = img1
        file2_result = aligned_img2

        if mode == "overlay":
            result = compare_images_overlay(img1, aligned_img2, bin_thresh=bin_threshold, colors=colors)
            # Overlay 모드에서는 원본(정렬된) 그냥 반환
        else:  # difference
            result = compare_images(img1, aligned_img2, diff_thresh=diff_threshold, bin_thresh=bin_threshold, colors=colors)
            # Difference 모드에서는 하이라이트된 개별 이미지 생성
            file1_result, file2_result = generate_highlighted_images(
                img1, aligned_img2, diff_thresh=diff_threshold, bin_thresh=bin_threshold, colors=colors
            )
        
        # 5. 인코딩
        logger.info("이미지 인코딩 중...")
        result_base64 = encode_image_to_base64(result, format='JPEG', quality=85)
        file1_base64 = encode_image_to_base64(file1_result, format='JPEG', quality=85)
        file2_base64 = encode_image_to_base64(file2_result, format='JPEG', quality=85)
        
        download_base64 = encode_image_to_base64(result, format='PNG')
        
        return {
            "result_base64": result_base64,
            "file1_base64": file1_base64,
            "file2_base64": file2_base64,
            "download_base64": download_base64,
            "metadata": {
                "mode": mode,
                "file1_pages": pages1,
                "file2_pages": pages2,
                "match_quality": quality,
                "alignment_failed": alignment_failed,
                "result_size": f"{result.shape[1]}x{result.shape[0]}"
            }
        }
    
    except Exception as e:
        logger.error(f"비교 처리 실패: {str(e)}")
        raise