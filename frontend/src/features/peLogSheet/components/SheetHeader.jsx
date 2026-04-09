import React, { useRef } from 'react';
import { Download, HelpCircle, Home, Upload } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import SyncStatusBadge from './SyncStatusBadge';

export default function SheetHeader({
  syncStatus,
  revision,
  onHelpOpen,
  onCsvUpload,
  onCsvDownload,
}) {
  const navigate = useNavigate();
  const inputRef = useRef(null);

  const handleUploadClick = () => {
    inputRef.current?.click();
  };

  const handleFileChange = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) {
      return;
    }
    try {
      await onCsvUpload(file);
    } catch (error) {
      console.error('[peLogSheet] CSV upload failed', error);
    }
  };

  return (
    <header className="flex items-center gap-3 px-4 py-2.5 bg-white border-b border-gray-200 shadow-sm shrink-0">
      <input
        ref={inputRef}
        type="file"
        accept=".csv,text/csv"
        className="hidden"
        onChange={handleFileChange}
      />

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
        onClick={handleUploadClick}
        className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-blue-600 transition-colors px-2 py-1 rounded-md hover:bg-blue-50"
        title="CSV 업로드"
      >
        <Upload size={14} />
        <span>CSV 업로드</span>
      </button>

      <button
        onClick={onCsvDownload}
        className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-emerald-600 transition-colors px-2 py-1 rounded-md hover:bg-emerald-50"
        title="CSV 다운로드"
      >
        <Download size={14} />
        <span>CSV 다운로드</span>
      </button>
    </header>
  );
}
