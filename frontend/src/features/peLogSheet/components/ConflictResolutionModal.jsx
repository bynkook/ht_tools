import React from 'react';
import { AlertTriangle, RefreshCcw, X } from 'lucide-react';

export default function ConflictResolutionModal({
  conflictState,
  onClose,
  onKeepServer,
  onRetryClientValue,
}) {
  if (!conflictState) return null;

  const conflicts = conflictState.conflicts ?? [];
  const visibleConflicts = conflicts.slice(0, 10);
  const remainingCount = Math.max(conflicts.length - visibleConflicts.length, 0);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 px-4">
      <div className="w-full max-w-3xl rounded-xl bg-white shadow-2xl border border-gray-200 overflow-hidden">
        <div className="flex items-center gap-3 px-5 py-4 border-b border-gray-200 bg-orange-50">
          <AlertTriangle size={18} className="text-orange-600 shrink-0" />
          <div className="min-w-0 flex-1">
            <h2 className="text-sm font-semibold text-gray-900">동시 편집 충돌</h2>
            <p className="text-xs text-gray-600 mt-0.5">
              {conflictState.isPasteConflict
                ? `붙여넣기 범위에서 ${conflicts.length}개 셀이 다른 사용자 변경과 충돌했습니다.`
                : `${conflicts.length}개 셀이 다른 사용자 변경과 충돌했습니다.`}
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition-colors"
            aria-label="닫기"
          >
            <X size={18} />
          </button>
        </div>

        <div className="max-h-[55vh] overflow-y-auto px-5 py-4">
          <div className="space-y-3">
            {visibleConflicts.map((conflict) => (
              <div key={`${conflict.sheet_id}-${conflict.row}-${conflict.column}`} className="rounded-lg border border-gray-200 p-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-sm font-medium text-gray-800">{conflict.cell_address}</div>
                  <div className="text-xs text-gray-500">
                    {conflict.server_editor ? `${conflict.server_editor} 사용자가 먼저 저장함` : `다른 사용자가 먼저 저장함`}
                  </div>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
                  <div className="rounded-md bg-gray-50 border border-gray-200 p-2">
                    <div className="text-[11px] font-medium text-gray-500 mb-1">서버 값</div>
                    <div className="text-sm text-gray-800 break-words whitespace-pre-wrap">{conflict.server_value || <span className="text-gray-400">(빈 값)</span>}</div>
                  </div>
                  <div className="rounded-md bg-blue-50 border border-blue-200 p-2">
                    <div className="text-[11px] font-medium text-blue-600 mb-1">내 값</div>
                    <div className="text-sm text-blue-900 break-words whitespace-pre-wrap">{conflict.client_value || <span className="text-blue-300">(빈 값)</span>}</div>
                  </div>
                </div>
              </div>
            ))}
            {remainingCount > 0 && (
              <div className="text-xs text-gray-500">
                그 외 {remainingCount}개 충돌 셀이 더 있습니다.
              </div>
            )}
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 px-5 py-4 border-t border-gray-200 bg-gray-50">
          <button
            onClick={onKeepServer}
            className="px-3 py-2 rounded-md text-sm bg-white border border-gray-300 text-gray-700 hover:bg-gray-100 transition-colors"
          >
            최신 값 유지
          </button>
          <button
            onClick={onRetryClientValue}
            disabled={!conflictState.canRetry}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-md text-sm bg-blue-600 text-white hover:bg-blue-700 transition-colors disabled:bg-blue-300 disabled:cursor-not-allowed"
          >
            <RefreshCcw size={14} />
            내 값으로 다시 적용
          </button>
        </div>
      </div>
    </div>
  );
}
