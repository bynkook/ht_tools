import React, { useState, useEffect } from 'react';
import { X, Pencil } from 'lucide-react';

/**
 * Modal for renaming an existing preset.
 * Only the owner can rename — this is enforced in both UI and backend.
 */
const PresetRenameModal = ({ isOpen, onClose, onConfirm, currentName }) => {
  const [name, setName] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    if (isOpen) {
      setName(currentName || '');
      setError('');
    }
  }, [isOpen, currentName]);

  const handleSubmit = (e) => {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return setError('이름을 입력해주세요.');
    if (trimmed.length > 200) return setError('이름은 200자를 초과할 수 없습니다.');
    if (trimmed === currentName) return onClose(); // no-op if unchanged
    onConfirm(trimmed);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />

      {/* Modal */}
      <div className="relative bg-white rounded-xl shadow-2xl w-full max-w-sm mx-4 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b bg-gray-50">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-yellow-100 rounded-lg">
              <Pencil className="text-yellow-600" size={20} />
            </div>
            <h2 className="text-lg font-semibold text-gray-800">이름 변경</h2>
          </div>
          <button
            onClick={onClose}
            className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <X size={20} />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">
              새 이름 <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => { setName(e.target.value); setError(''); }}
              placeholder="프리셋 이름 입력"
              className="w-full px-4 py-2.5 border border-gray-300 rounded-lg hover:border-gray-500 focus:outline-none focus:border-gray-500 focus:ring-0 transition-colors"
              autoFocus
              maxLength={200}
            />
          </div>

          {error && (
            <div className="text-sm text-red-600 bg-red-50 px-3 py-2 rounded-lg">{error}</div>
          )}

          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-2.5 text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg font-medium transition-colors"
            >
              취소
            </button>
            <button
              type="submit"
              className="flex-1 px-4 py-2.5 text-white bg-yellow-500 hover:bg-yellow-600 rounded-lg font-medium transition-colors flex items-center justify-center gap-2"
            >
              <Pencil size={16} />
              변경
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default PresetRenameModal;
