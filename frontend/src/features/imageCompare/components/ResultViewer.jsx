import React, { useRef } from 'react';
import { Download, ZoomIn, ZoomOut, Maximize2 } from 'lucide-react';
import { TransformWrapper, TransformComponent, useControls } from 'react-zoom-pan-pinch';

// ─── Constants ──────────────────────────────────────────────────────────────

const COLORS = {
  diff_file1: '#3B82F6', diff_file2: '#DC2626', diff_common: '#000000',
  overlay_file1: '#F97316', overlay_file2: '#22C55E',
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

const ColorLegend = ({ mode, colors }) => {
  const items = mode === 'overlay'
    ? [['overlay_file1', 'File 1'], ['overlay_file2', 'File 2']]
    : [['diff_file1', 'File 1'], ['diff_file2', 'File 2'], ['diff_common', '공통']];
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
  const ref1 = useRef(null), ref2 = useRef(null);
  const isSyncing = useRef(false);

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

  const { result_base64, file1_base64, file2_base64, download_base64, metadata } = resultData;
  const isDiffMode = metadata.mode === 'difference';

  // Sync handler for split view
  const makeSyncHandler = (targetRef) => (_ref, state) => {
    if (isSyncing.current) return;
    isSyncing.current = true;
    targetRef.current?.setTransform(state.positionX, state.positionY, state.scale, 0);
    isSyncing.current = false;
  };

  // Reset both panes to fit (scale=1 is fit state now)
  const resetBoth = () => {
    ref1.current?.resetTransform(200, 'easeOut');
    ref2.current?.resetTransform(200, 'easeOut');
  };

  return (
    <div className="flex flex-col h-full overflow-hidden bg-white mx-4 mb-4">
      {/* Header */}
      <div className="flex-shrink-0 px-4 py-3 bg-white flex items-center justify-between gap-4">
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-bold text-[var(--text-primary)]">
            {isDiffMode ? "비교 결과 (차이점 강조)" : "비교 결과 (오버레이)"}
          </h3>
          <p className="text-xs text-gray-400 mt-0.5">
            {metadata.result_size} • 매칭 품질: {(metadata.match_quality * 100).toFixed(0)}%
          </p>
        </div>
        <ColorLegend mode={metadata.mode} colors={activeColors} />
        <button
          onClick={() => onDownload(download_base64, metadata)}
          className="flex-shrink-0 flex items-center gap-2 px-3 py-2 bg-blue-600 text-white text-sm font-bold rounded-lg hover:bg-blue-700 transition-colors shadow-sm"
        >
          <Download size={16} />
          PNG 다운로드
        </button>
      </div>

      {/* Viewer Body */}
      <div className="flex-1 relative overflow-hidden bg-gray-50 flex">
        {isDiffMode && file1_base64 && file2_base64 ? (
          // Split View — Difference Mode
          <div className="flex w-full h-full">
            <div className="flex-1 relative overflow-hidden">
              <ZoomPane
                src={file1_base64} alt="File 1" tRef={ref1}
                onTransformed={makeSyncHandler(ref2)}
                onResetAll={resetBoth}
              />
            </div>
            <div className="flex-1 relative overflow-hidden border-l border-gray-100">
              <ZoomPane
                src={file2_base64} alt="File 2" tRef={ref2}
                onTransformed={makeSyncHandler(ref1)}
                onResetAll={resetBoth}
              />
            </div>
          </div>
        ) : (
          // Single View — Overlay Mode
          <div className="w-full h-full relative">
            <ZoomPane src={result_base64} alt="Comparison Result" />
          </div>
        )}
      </div>
    </div>
  );
};

export default ResultViewer;
