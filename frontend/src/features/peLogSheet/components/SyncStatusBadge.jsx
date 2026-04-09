import React from 'react';
import { RefreshCw, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';

const STATUS_CONFIG = {
  idle: { icon: CheckCircle, label: '동기화됨', color: 'text-green-600' },
  saving: { icon: Loader2, label: '저장 중…', color: 'text-blue-500' },
  conflict: { icon: AlertCircle, label: '충돌 복원됨', color: 'text-orange-500' },
  error: { icon: AlertCircle, label: '저장 오류', color: 'text-red-600' },
};

export default function SyncStatusBadge({ status, revision }) {
  const cfg = STATUS_CONFIG[status] ?? STATUS_CONFIG.idle;
  const Icon = cfg.icon;

  return (
    <div className={`flex items-center gap-1.5 text-xs font-medium ${cfg.color}`}>
      <Icon size={13} className={status === 'saving' ? 'animate-spin' : ''} />
      <span>{cfg.label}</span>
      {revision > 0 && (
        <span className="text-gray-400 font-normal">r{revision}</span>
      )}
    </div>
  );
}
