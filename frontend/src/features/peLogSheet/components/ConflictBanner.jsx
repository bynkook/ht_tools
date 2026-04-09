import React from 'react';
import { AlertTriangle, X } from 'lucide-react';

export default function ConflictBanner({ message, onDismiss }) {
  if (!message) return null;

  return (
    <div className="flex items-center gap-2 bg-orange-50 border border-orange-200 rounded-md px-3 py-2 text-sm text-orange-700">
      <AlertTriangle size={15} className="shrink-0" />
      <span className="flex-1">{message}</span>
      <button
        onClick={onDismiss}
        className="text-orange-400 hover:text-orange-600 transition-colors"
        aria-label="닫기"
      >
        <X size={14} />
      </button>
    </div>
  );
}
