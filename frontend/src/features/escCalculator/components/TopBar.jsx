import React, { useState } from 'react';
import { RefreshCw, Save, PlusCircle, Trash2 } from 'lucide-react';

export default function TopBar({
  projects, selectedId, onLoad, onSave, onDelete, onRecalc, onNew, onResetCache, loading,
}) {
  const [saveName, setSaveName] = useState('');
  const [showSaveInput, setShowSaveInput] = useState(false);

  const handleSaveClick = () => {
    const current = projects.find(p => p.id === selectedId);
    if (current) {
      // 기존 프로젝트 덮어쓰기
      onSave(current.name, selectedId);
    } else {
      setShowSaveInput(true);
    }
  };

  const handleSaveConfirm = () => {
    if (!saveName.trim()) return;
    onSave(saveName.trim(), null);
    setSaveName('');
    setShowSaveInput(false);
  };

  return (
    <div className="bg-white border-b border-gray-200 px-4 py-2 flex flex-wrap items-center gap-3 sticky top-0 z-10 shadow-sm">
      {/* 프로젝트 선택 */}
      <div className="flex items-center gap-2">
        <label className="text-sm text-gray-600 shrink-0">프로젝트</label>
        <select
          className="border border-gray-300 rounded px-2 py-1 text-sm min-w-[200px]"
          value={selectedId ?? ''}
          onChange={e => onLoad(e.target.value ? Number(e.target.value) : null)}
        >
          <option value="">-- 선택 --</option>
          {projects.map(p => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
      </div>

      {/* 버튼들 */}
      <div className="flex items-center gap-2 ml-auto">
        {/* 저장 이름 입력 */}
        {showSaveInput && (
          <div className="flex items-center gap-1">
            <input
              autoFocus
              type="text"
              placeholder="프로젝트 이름 입력"
              className="border border-gray-300 rounded px-2 py-1 text-sm w-44"
              value={saveName}
              onChange={e => setSaveName(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') handleSaveConfirm(); if (e.key === 'Escape') setShowSaveInput(false); }}
            />
            <button onClick={handleSaveConfirm}
              className="text-xs bg-blue-500 text-white rounded px-2 py-1 hover:bg-blue-600">확인</button>
            <button onClick={() => setShowSaveInput(false)}
              className="text-xs bg-gray-200 text-gray-600 rounded px-2 py-1 hover:bg-gray-300">취소</button>
          </div>
        )}

        <button
          onClick={handleSaveClick}
          disabled={loading}
          className="flex items-center gap-1 text-sm bg-blue-500 text-white rounded px-3 py-1.5 hover:bg-blue-600 disabled:opacity-50"
        >
          <Save size={14} /> 저장
        </button>

        <button
          onClick={() => onDelete?.(selectedId)}
          disabled={loading || !selectedId}
          className="flex items-center gap-1 text-sm bg-red-500 text-white rounded px-3 py-1.5 hover:bg-red-600 disabled:opacity-50"
        >
          <Trash2 size={14} /> 삭제
        </button>

        <button
          onClick={onRecalc}
          disabled={loading}
          className="flex items-center gap-1 text-sm bg-green-500 text-white rounded px-3 py-1.5 hover:bg-green-600 disabled:opacity-50"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> 계산실행
        </button>

        <button
          onClick={onNew}
          className="flex items-center gap-1 text-sm bg-gray-500 text-white rounded px-3 py-1.5 hover:bg-gray-600"
        >
          <PlusCircle size={14} /> 새로만들기
        </button>

        <button
          onClick={() => onResetCache?.()}
          disabled={loading}
          className="flex items-center gap-1 text-sm bg-amber-600 text-white rounded px-3 py-1.5 hover:bg-amber-700 disabled:opacity-50"
        >
          <RefreshCw size={14} /> 데이터캐시초기화
        </button>
      </div>
    </div>
  );
}
