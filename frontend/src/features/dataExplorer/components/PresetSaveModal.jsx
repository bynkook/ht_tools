import React, { useState, useEffect } from 'react';
import { X, Save, FileText, Globe, User } from 'lucide-react';

/**
 * Modal for saving a new preset.
 * Captures preset name, optional description, and visibility from user.
 */
const PresetSaveModal = ({ isOpen, onClose, onSave, currentFilename }) => {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [isPublic, setIsPublic] = useState(false);
  const [error, setError] = useState('');

  // Reset form when modal opens/closes
  useEffect(() => {
    if (isOpen) {
      // Default name based on filename
      const defaultName = currentFilename 
        ? `${currentFilename.replace(/\.[^/.]+$/, '')} 차트`
        : '새 프리셋';
      setName(defaultName);
      setDescription('');
      setIsPublic(false);
      setError('');
    }
  }, [isOpen, currentFilename]);

  const handleSubmit = (e) => {
    e.preventDefault();
    
    const trimmedName = name.trim();
    if (!trimmedName) {
      setError('프리셋 이름을 입력해주세요.');
      return;
    }
    
    if (trimmedName.length > 200) {
      setError('이름은 200자를 초과할 수 없습니다.');
      return;
    }
    
    onSave({
      name: trimmedName,
      description: description.trim(),
      is_public: isPublic,
    });
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div 
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />
      
      {/* Modal */}
      <div className="relative bg-white rounded-xl shadow-2xl w-full max-w-md mx-4 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b bg-gray-50">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-100 rounded-lg">
              <Save className="text-blue-600" size={20} />
            </div>
            <h2 className="text-lg font-semibold text-gray-800">프리셋 저장</h2>
          </div>
          <button
            onClick={onClose}
            className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <X size={20} />
          </button>
        </div>

        {/* Content */}
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {/* Current file info */}
          <div className="flex items-center gap-2 text-sm text-gray-500 bg-gray-50 p-3 rounded-lg">
            <FileText size={16} />
            <span>데이터: <span className="font-medium text-gray-700">{currentFilename}</span></span>
          </div>

          {/* Name input */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">
              프리셋 이름 <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                setError('');
              }}
              placeholder="차트 이름 입력"
              className="w-full px-4 py-2.5 border border-gray-300 rounded-lg hover:border-gray-500 focus:outline-none focus:border-gray-500 focus:ring-0 focus:ring-gray-300 transition-colors"
              autoFocus
              maxLength={200}
            />
          </div>

          {/* Description input */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">
              설명 <span className="text-gray-400 font-normal">(선택)</span>
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Preset에 대한 설명 메모"
              rows={3}
              className="w-full px-4 py-2.5 border border-gray-300 rounded-lg hover:border-gray-500 focus:outline-none focus:border-gray-500 focus:ring-0 focus:ring-gray-300 transition-colors resize-none"
            />
          </div>

          {/* Visibility toggle */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              공유 범위
            </label>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setIsPublic(false)}
                className={`flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg border-2 transition-all ${
                  !isPublic
                    ? 'border-blue-500 bg-blue-50 text-blue-700'
                    : 'border-gray-200 bg-white text-gray-600 hover:border-gray-300'
                }`}
              >
                <User size={16} />
                <span className="text-sm font-medium">나만 보기</span>
              </button>
              <button
                type="button"
                onClick={() => setIsPublic(true)}
                className={`flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg border-2 transition-all ${
                  isPublic
                    ? 'border-green-500 bg-green-50 text-green-700'
                    : 'border-gray-200 bg-white text-gray-600 hover:border-gray-300'
                }`}
              >
                <Globe size={16} />
                <span className="text-sm font-medium">모든 사용자</span>
              </button>
            </div>
            <p className="mt-1.5 text-xs text-gray-500">
              {isPublic 
                ? '모든 사용자가 이 프리셋을 볼 수 있습니다.'
                : '나만 이 프리셋을 볼 수 있습니다.'}
            </p>
          </div>

          {/* Error message */}
          {error && (
            <div className="text-sm text-red-600 bg-red-50 px-3 py-2 rounded-lg">
              {error}
            </div>
          )}

          {/* Actions */}
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
              className="flex-1 px-4 py-2.5 text-white bg-blue-600 hover:bg-blue-700 rounded-lg font-medium transition-colors flex items-center justify-center gap-2"
            >
              <Save size={18} />
              저장
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default PresetSaveModal;
