import React from 'react';
import { Home, HelpCircle, RefreshCw, Users } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import SyncStatusBadge from './SyncStatusBadge';

export default function SheetHeader({
  syncStatus,
  revision,
  onHelpOpen,
  onResetFromSource,
}) {
  const navigate = useNavigate();

  return (
    <header className="flex items-center gap-3 px-4 py-2.5 bg-white border-b border-gray-200 shadow-sm shrink-0">
      <button
        onClick={() => navigate('/')}
        className="p-1.5 rounded-md text-gray-500 hover:text-gray-800 hover:bg-gray-100 transition-colors"
        title="홈으로"
      >
        <Home size={16} />
      </button>

      <div className="w-px h-5 bg-gray-200" />

      <span className="font-semibold text-gray-700 text-sm select-none">
        PE Log Sheet
      </span>

      <div className="flex-1" />

      <SyncStatusBadge status={syncStatus} revision={revision} />

      <div className="w-px h-5 bg-gray-200" />

      <button
        onClick={onHelpOpen}
        className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-teal-600 transition-colors px-2 py-1 rounded-md hover:bg-teal-50"
        title="유형 분류 기준"
      >
        <HelpCircle size={14} />
        <span>유형 안내</span>
      </button>

      <button
        onClick={onResetFromSource}
        className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-orange-600 transition-colors px-2 py-1 rounded-md hover:bg-orange-50"
        title="CSV 원본으로 재초기화"
      >
        <RefreshCw size={14} />
        <span>원본 복원</span>
      </button>
    </header>
  );
}
