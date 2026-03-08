import React, { useRef, useEffect } from 'react';
import { Download, ZoomIn, ZoomOut, Maximize2, AlertTriangle } from 'lucide-react';
import { TransformWrapper, TransformComponent, useControls } from 'react-zoom-pan-pinch';

// ─── Constants ──────────────────────────────────────────────────────────────

const COLORS = {
  diff_file1: '#3B82F6', diff_file2: '#DC2626', diff_common: '#000000',
};

const ALGORITHM_LABELS = {
  orb: 'ORB',
  corner: 'CAD 도면용',
  line: 'CAD 도면용',
  drawing_hybrid: 'CAD 도면용',
};

// ─── Zoom Controls (inside TransformWrapper) ────────────────────────────────

const ZoomControls = ({ onReset }) => {
  const { zoomIn, zoomOut, resetTransform } = useControls();
  const btn = "p-1.5 hover:bg-gray-100 rounded transition-colors";
  return (
    <div className="absolute bottom-3 right-3 z-10 flex flex-col gap-0.5 bg-white/85 backdrop-blur-sm rounded-lg shadow-md border border-gray-100 p-1">
      <button onClick={() => zoomIn(0.5)} className={btn} title="확대"><ZoomIn size={14} /></button>
      <button onClick={() => zoomOut(0.5)} className={btn} title="축소"><ZoomOut size={14} /></button>
      <div className="border-t border-gray-100 my-0.5" />
      <button onClick={() => onReset ? onReset() : resetTransform(200, 'easeOut')} className={btn} title="화면 맞춤">
        <Maximize2 size={14} />
      </button>
    </div>
  );
};

// ─── Color Legend ───────────────────────────────────────────────────────────

// 모든 모드에서 동일한 diff 3색 표시
const ColorLegend = ({ colors }) => {
  const items = [['diff_file1', 'File 1'], ['diff_file2', 'File 2'], ['diff_common', '공통']];
  return (
    <div className="flex items-center gap-3 text-xs text-gray-500">
      {items.map(([key, label]) => (
        <span key={key} className="flex items-center gap-1">
          <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: colors[key] }} />
          {label}
        </span>
      ))}
    </div>
  );
};

// ─── Zoomable Image Pane ────────────────────────────────────────────────────
// Image uses CSS to fit container. Scale=1 means "fit to container".
// This makes resetTransform() restore the fit state naturally.

const ZoomPane = ({ src, alt, tRef = null, onTransformed, onResetAll }) => {
  return (
    <TransformWrapper
      ref={tRef || undefined}
      initialScale={1}
      minScale={0.5}
      maxScale={10}
      centerOnInit={true}
      limitToBounds={false}
      onTransformed={onTransformed}
    >
      <TransformComponent
        wrapperStyle={{ width: '100%', height: '100%' }}
        contentStyle={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
      >
        <img 
          src={src} 
          alt={alt} 
          style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }}
        />
      </TransformComponent>
      <ZoomControls onReset={onResetAll} />
    </TransformWrapper>
  );
};

// ─── Main Component ─────────────────────────────────────────────────────────

const ResultViewer = ({ resultData, onDownload, colors }) => {
  const activeColors = { ...COLORS, ...colors };

  // Refs for split view (sync control)
  const ref1 = useRef(null), ref2 = useRef(null), ref3 = useRef(null);
  const isSyncing = useRef(false);
  const isResetting = useRef(false);
  // Workaround: onTransformed는 centerOnInit으로 인해 마운트 직후에도 발화된다.
  // 이 초기 발화를 동기화에 포함하면 패널 크기 차이로 역산이 잘못되어
  // 이미지가 화면 밖으로 이동하는 버그가 발생한다.
  // 라이브러리가 onInit 완료 후 첫 transform 건너뛰기 옵션을 제공하지 않으므로,
  // 패널별로 첫 발화를 기록해 두고 그 이후부터만 동기화를 수행한다.
  const initializedPanels = useRef(new Set());

  // resultData 가 바뀌면(새 비교 결과) 패널이 재마운트되어 init 발화가 다시 일어난다.
  // 이때 Set 에 ID 가 남아 있으면 init 건너뛰기가 동작하지 않으므로 클리어한다.
  useEffect(() => {
    initializedPanels.current.clear();
  }, [resultData]);

  if (!resultData) {
    return (
      <div className="h-full flex items-center justify-center rounded-xl bg-gray-50/50 m-4">
        <div className="text-center">
          <Maximize2 className="mx-auto mb-3 text-gray-300" size={48} />
          <p className="text-gray-400 font-medium mb-1">비교 결과가 여기에 표시됩니다</p>
          <p className="text-sm text-gray-400">두 파일을 업로드하고 "비교 시작" 버튼을 클릭하세요</p>
        </div>
      </div>
    );
  }

  const { 
    file1_base64, 
    file2_base64, 
    overlay_base64,
    metadata,
    _currentMode 
  } = resultData;

  // 현재 모드 결정: _currentMode (프론트 설정)
  const currentMode = _currentMode || 'difference';
  const isDiffMode = currentMode === 'difference';
  const isSplitOverlayMode = currentMode === 'split-overlay';

  // object-fit: contain으로 렌더링된 이미지의 실제 크기와 오프셋 계산
  const getRenderedImageRect = (wrapperEl) => {
    const imgEl = wrapperEl?.querySelector('img');
    if (!imgEl) return null;
    const { naturalWidth: nw, naturalHeight: nh, clientWidth: cw, clientHeight: ch } = imgEl;
    if (!nw || !nh || !cw || !ch) return null;
    // object-fit: contain은 aspect ratio를 유지하며 컨테이너에 맞춤
    const fitScale = Math.min(cw / nw, ch / nh);
    const w = nw * fitScale, h = nh * fitScale;
    // 컨테이너 내 중앙 정렬 오프셋
    return { w, h, ox: (cw - w) / 2, oy: (ch - h) / 2 };
  };

  // Sync handler: panelId(1|2|3) + targetRefs 배열로 복수 패널에 전파
  // 핵심: 이미지의 "정규화된 위치(0~1)"를 계산하여 패널 크기와 무관하게 동기화.
  // object-fit: contain 으로 인해 각 패널에서 이미지 렌더링 크기가 다르므로,
  // 단순 positionX/Y 복사나 컨테이너 비율 계산으로는 줌 포인트가 일치하지 않음.
  const makeSyncHandler = (panelId, targetRefs) => (_ref, state) => {
    // 라이브러리 초기화 시 첫 발화는 건너뛴다.
    if (!initializedPanels.current.has(panelId)) {
      initializedPanels.current.add(panelId);
      return;
    }
    // Reset 중에는 동기화 건너뛰기 (각 패널이 독립적으로 fit 상태로 리셋)
    if (isResetting.current) return;
    if (isSyncing.current) return;
    isSyncing.current = true;

    const srcEl = _ref?.instance?.wrapperComponent;
    const srcW = srcEl?.clientWidth ?? 0;
    const srcH = srcEl?.clientHeight ?? 0;
    const srcImg = getRenderedImageRect(srcEl);

    const targets = Array.isArray(targetRefs) ? targetRefs : [targetRefs];
    targets.forEach(tRef => {
      if (!tRef.current) return;
      const dstEl = tRef.current.instance?.wrapperComponent;
      const dstW = dstEl?.clientWidth ?? 0;
      const dstH = dstEl?.clientHeight ?? 0;
      const dstImg = getRenderedImageRect(dstEl);

      if (srcImg && dstImg && srcW > 0 && dstW > 0) {
        // 소스 패널에서 이미지 렌더링 영역의 컨테이너 내 위치 (scale 적용)
        const srcImgLeft = state.positionX + srcImg.ox * state.scale;
        const srcImgTop = state.positionY + srcImg.oy * state.scale;
        const srcImgW = srcImg.w * state.scale;
        const srcImgH = srcImg.h * state.scale;
        // 뷰포트 중심이 이미지의 정규화된 위치 (0~1)
        const normX = (srcW / 2 - srcImgLeft) / srcImgW;
        const normY = (srcH / 2 - srcImgTop) / srcImgH;
        // 타겟 패널에서 역산
        const dstImgW = dstImg.w * state.scale;
        const dstImgH = dstImg.h * state.scale;
        const dstImgLeft = dstW / 2 - normX * dstImgW;
        const dstImgTop = dstH / 2 - normY * dstImgH;
        const dstPosX = dstImgLeft - dstImg.ox * state.scale;
        const dstPosY = dstImgTop - dstImg.oy * state.scale;
        tRef.current.setTransform(dstPosX, dstPosY, state.scale, 0);
      } else {
        // fallback: 이미지 정보를 얻지 못한 경우 기존 방식
        tRef.current.setTransform(state.positionX, state.positionY, state.scale, 0);
      }
    });

    isSyncing.current = false;
  };

  // Reset all panes to fit (동기화 없이 각자 독립 리셋)
  // Workaround: 라이브러리가 reset 완료 콜백을 제공하지 않으므로,
  // 애니메이션 시간(200ms) + 버퍼 후에 flag를 해제한다.
  const resetAll = () => {
    isResetting.current = true;
    ref1.current?.resetTransform(200, 'easeOut');
    ref2.current?.resetTransform(200, 'easeOut');
    ref3.current?.resetTransform(200, 'easeOut');
    setTimeout(() => { isResetting.current = false; }, 250);
  };

  return (
    <div className="flex flex-col h-full overflow-hidden bg-white mx-4 mb-4">
      {/* Header */}
      <div className="flex-shrink-0 px-4 py-3 bg-white flex items-center justify-between gap-4">
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-bold text-[var(--text-primary)]">
            {isDiffMode ? "비교 결과 (차이점 강조)" : isSplitOverlayMode ? "비교 결과 (차이점+오버레이)" : "비교 결과 (오버레이)"}
          </h3>
          <p className="text-xs text-gray-400 mt-0.5">
            {metadata.result_size} • 알고리즘: {ALGORITHM_LABELS[metadata.algorithm_used] || metadata.algorithm_used || 'ORB'} • 매칭 품질: {(metadata.match_quality * 100).toFixed(0)}%
          </p>
        </div>
        <ColorLegend colors={activeColors} />
        <button
          onClick={() => onDownload(overlay_base64, metadata)}
          className="flex-shrink-0 flex items-center gap-2 px-3 py-2 bg-blue-600 text-white text-sm font-bold rounded-lg hover:bg-blue-700 transition-colors shadow-sm"
        >
          <Download size={16} />
          PNG 다운로드
        </button>
      </div>

      {/* Page count mismatch warning */}
      {metadata.file1_pages !== metadata.file2_pages && (
        <div className="flex-shrink-0 flex items-center gap-2 px-4 py-2 bg-amber-50 border-b border-amber-200 text-amber-800 text-xs">
          <AlertTriangle size={14} className="flex-shrink-0 text-amber-500" />
          두 파일의 페이지 수가 다릅니다 (File 1: {metadata.file1_pages}페이지, File 2: {metadata.file2_pages}페이지). 첫 번째 페이지를 기준으로 비교되었습니다.
        </div>
      )}

      {/* Viewer Body */}
      <div className="flex-1 relative overflow-hidden bg-gray-50 flex">
        {isDiffMode && file1_base64 && file2_base64 ? (
          // Split View — Difference Mode
          <div className="flex w-full h-full">
            <div className="flex-1 relative overflow-hidden">
              <ZoomPane
                src={file1_base64} alt="File 1" tRef={ref1}
                onTransformed={makeSyncHandler(1, ref2)}
                onResetAll={resetAll}
              />
            </div>
            <div className="flex-1 relative overflow-hidden border-l border-gray-100">
              <ZoomPane
                src={file2_base64} alt="File 2" tRef={ref2}
                onTransformed={makeSyncHandler(2, ref1)}
                onResetAll={resetAll}
              />
            </div>
          </div>
        ) : isSplitOverlayMode && file1_base64 && file2_base64 && overlay_base64 ? (
          // 3-Panel View — Split-Overlay Mode
          // Left 1/3: File1(top) + File2(bottom) with diff highlight
          // Right 2/3: Overlay result
          <div className="flex w-full h-full">
            <div className="w-1/3 flex flex-col border-r border-gray-200">
              <div className="flex-1 relative overflow-hidden border-b border-gray-200">
                <div className="absolute top-1.5 left-2 z-10 text-[10px] font-medium text-gray-400 bg-white/70 px-1 rounded">
                  File 1
                </div>
                <ZoomPane
                  src={file1_base64} alt="File 1" tRef={ref1}
                  onTransformed={makeSyncHandler(1, [ref2, ref3])}
                  onResetAll={resetAll}
                />
              </div>
              <div className="flex-1 relative overflow-hidden">
                <div className="absolute top-1.5 left-2 z-10 text-[10px] font-medium text-gray-400 bg-white/70 px-1 rounded">
                  File 2
                </div>
                <ZoomPane
                  src={file2_base64} alt="File 2" tRef={ref2}
                  onTransformed={makeSyncHandler(2, [ref1, ref3])}
                  onResetAll={resetAll}
                />
              </div>
            </div>
            <div className="w-2/3 relative overflow-hidden">
              <div className="absolute top-1.5 left-2 z-10 text-[10px] font-medium text-gray-400 bg-white/70 px-1 rounded">
                Overlay
              </div>
              <ZoomPane
                src={overlay_base64} alt="Overlay Result" tRef={ref3}
                onTransformed={makeSyncHandler(3, [ref1, ref2])}
                onResetAll={resetAll}
              />
            </div>
          </div>
        ) : (
          // Single View — Overlay Mode
          <div className="w-full h-full relative">
            <ZoomPane src={overlay_base64} alt="Comparison Result" />
          </div>
        )}
      </div>
    </div>
  );
};

export default ResultViewer;
