import React, { useState, useRef, useCallback, useEffect } from 'react';
import { X, Check, Crop } from 'lucide-react';

/**
 * CropSelector
 *
 * 전체화면 모달로 previewImage를 표시하고 마우스 드래그로 crop 영역을 선택한다.
 * 선택 완료 후 "적용" 버튼을 누르면 onApply({ x, y, width, height }) 를 0-1 정규화 좌표로 호출한다.
 *
 * Props:
 *   previewImage  - base64 이미지 문자열 (data URI 또는 raw base64)
 *   onApply(rect) - crop 적용 콜백. rect = { x, y, width, height } (0-1 정규화)
 *   onCancel()    - 취소 콜백
 */
export default function CropSelector({ previewImage, onApply, onCancel }) {
  const imgRef = useRef(null);
  const [selection, setSelection] = useState(null);   // { x, y, w, h } in px (screen coords)
  const [dragging, setDragging] = useState(false);
  const startRef = useRef(null);                       // 드래그 시작점 { x, y } (screen px, image-relative)

  // base64 raw 문자열에 data URI prefix 붙이기
  const imgSrc = previewImage?.startsWith('data:')
    ? previewImage
    : `data:image/png;base64,${previewImage}`;

  // 마우스 좌표 → 이미지 렌더 영역 기준 상대 좌표(px) 변환
  // object-fit:contain 이므로 letterbox 보정 필요
  const getImageRelativePos = useCallback((clientX, clientY) => {
    const img = imgRef.current;
    if (!img) return null;
    const rect = img.getBoundingClientRect();

    // 렌더된 이미지의 실제 크기 (letterbox 제거)
    const naturalRatio = img.naturalWidth / img.naturalHeight;
    const containerRatio = rect.width / rect.height;

    let renderW, renderH, offsetX, offsetY;
    if (naturalRatio > containerRatio) {
      // 좌우가 꽉 참, 위아래 letterbox
      renderW = rect.width;
      renderH = rect.width / naturalRatio;
      offsetX = 0;
      offsetY = (rect.height - renderH) / 2;
    } else {
      // 위아래가 꽉 참, 좌우 letterbox
      renderH = rect.height;
      renderW = rect.height * naturalRatio;
      offsetX = (rect.width - renderW) / 2;
      offsetY = 0;
    }

    const x = clientX - rect.left - offsetX;
    const y = clientY - rect.top - offsetY;

    return {
      x: Math.max(0, Math.min(renderW, x)),
      y: Math.max(0, Math.min(renderH, y)),
      renderW,
      renderH,
    };
  }, []);

  const handleMouseDown = useCallback((e) => {
    e.preventDefault();
    const pos = getImageRelativePos(e.clientX, e.clientY);
    if (!pos) return;
    startRef.current = pos;
    setDragging(true);
    setSelection({ x: pos.x, y: pos.y, w: 0, h: 0, renderW: pos.renderW, renderH: pos.renderH });
  }, [getImageRelativePos]);

  const handleMouseMove = useCallback((e) => {
    if (!dragging || !startRef.current) return;
    const pos = getImageRelativePos(e.clientX, e.clientY);
    if (!pos) return;
    const sx = startRef.current.x;
    const sy = startRef.current.y;
    setSelection({
      x: Math.min(sx, pos.x),
      y: Math.min(sy, pos.y),
      w: Math.abs(pos.x - sx),
      h: Math.abs(pos.y - sy),
      renderW: pos.renderW,
      renderH: pos.renderH,
    });
  }, [dragging, getImageRelativePos]);

  const handleMouseUp = useCallback(() => {
    setDragging(false);
  }, []);

  // 터치 이벤트 지원 (태블릿 대응)
  const handleTouchStart = useCallback((e) => {
    const t = e.touches[0];
    handleMouseDown({ preventDefault: () => {}, clientX: t.clientX, clientY: t.clientY });
  }, [handleMouseDown]);

  const handleTouchMove = useCallback((e) => {
    const t = e.touches[0];
    handleMouseMove({ clientX: t.clientX, clientY: t.clientY });
  }, [handleMouseMove]);

  const handleTouchEnd = useCallback(() => handleMouseUp(), [handleMouseUp]);

  // global mouseup 처리 (드래그 중 이미지 밖으로 나갔다 돌아왔을 때도 종료)
  useEffect(() => {
    if (dragging) {
      window.addEventListener('mouseup', handleMouseUp);
      return () => window.removeEventListener('mouseup', handleMouseUp);
    }
  }, [dragging, handleMouseUp]);

  const hasValidSelection = selection && selection.w > 5 && selection.h > 5;

  const handleApply = useCallback(() => {
    if (!hasValidSelection) return;
    const { x, y, w, h, renderW, renderH } = selection;
    onApply({
      x: x / renderW,
      y: y / renderH,
      width:  w / renderW,
      height: h / renderH,
    });
  }, [hasValidSelection, selection, onApply]);

  // 백드롭 클릭으로는 닫지 않음 (실수 방지)
  return (
    <div
      className="fixed inset-0 z-50 flex flex-col bg-black/85"
      style={{ userSelect: 'none' }}
    >
      {/* 상단 헤더 */}
      <div className="flex items-center justify-between px-4 py-3 bg-gray-900 text-white shrink-0">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <Crop size={16} className="text-indigo-400" />
          <span>비교 영역 선택 — 마우스로 드래그하여 분석할 영역을 선택하세요</span>
        </div>
        <div className="flex items-center gap-2">
          {/* 선택 크기 표시 */}
          {hasValidSelection && (
            <span className="text-xs text-gray-400 mr-2">
              {Math.round(selection.w / selection.renderW * 100)}% × {Math.round(selection.h / selection.renderH * 100)}%
            </span>
          )}
          <button
            onClick={handleApply}
            disabled={!hasValidSelection}
            className={`flex items-center gap-1 px-3 py-1.5 rounded text-xs font-semibold transition-colors
              ${hasValidSelection
                ? 'bg-indigo-600 hover:bg-indigo-500 text-white'
                : 'bg-gray-700 text-gray-500 cursor-not-allowed'}`}
          >
            <Check size={14} />
            적용
          </button>
          <button
            onClick={onCancel}
            className="flex items-center gap-1 px-3 py-1.5 rounded text-xs font-semibold bg-gray-700 hover:bg-gray-600 text-gray-200 transition-colors"
          >
            <X size={14} />
            취소
          </button>
        </div>
      </div>

      {/* 이미지 + 선택 오버레이 영역 */}
      <div
        className="relative flex-1 flex items-center justify-center overflow-hidden"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
        style={{ cursor: dragging ? 'crosshair' : 'crosshair' }}
      >
        <img
          ref={imgRef}
          src={imgSrc}
          alt="crop preview"
          draggable={false}
          className="max-w-full max-h-full object-contain"
          style={{ display: 'block' }}
        />

        {/* 선택 영역 오버레이 */}
        {hasValidSelection && (() => {
          // 이미지 실제 렌더 rect 계산 (오버레이 absoluteposition 기준)
          const img = imgRef.current;
          if (!img) return null;
          const rect = img.getBoundingClientRect();
          const containerRect = img.parentElement?.getBoundingClientRect();
          if (!containerRect) return null;

          const naturalRatio = img.naturalWidth / img.naturalHeight;
          const containerRatio = rect.width / rect.height;
          let renderW, renderH, offsetX, offsetY;
          if (naturalRatio > containerRatio) {
            renderW = rect.width;
            renderH = rect.width / naturalRatio;
            offsetX = 0;
            offsetY = (rect.height - renderH) / 2;
          } else {
            renderH = rect.height;
            renderW = rect.height * naturalRatio;
            offsetX = (rect.width - renderW) / 2;
            offsetY = 0;
          }

          // 컨테이너 기준 top-left
          const imgLeft = rect.left - containerRect.left + offsetX;
          const imgTop  = rect.top  - containerRect.top  + offsetY;

          return (
            <div
              className="absolute pointer-events-none"
              style={{
                left:   imgLeft + selection.x,
                top:    imgTop  + selection.y,
                width:  selection.w,
                height: selection.h,
                border: '2px solid #6366f1',
                background: 'rgba(99,102,241,0.15)',
                boxShadow: '0 0 0 9999px rgba(0,0,0,0.35)',
              }}
            />
          );
        })()}
      </div>

      {/* 하단 안내 */}
      <div className="px-4 py-2 bg-gray-900 text-gray-400 text-xs text-center shrink-0">
        선택 영역 외부는 분석에서 제외됩니다. 원본 파일은 변경되지 않습니다.
      </div>
    </div>
  );
}
