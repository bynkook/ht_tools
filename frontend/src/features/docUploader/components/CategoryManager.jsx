import React, { useState, useEffect, useCallback } from 'react';
import {
  FolderOpen,
  FolderPlus,
  Pencil,
  Check,
  X,
  AlertCircle,
  Loader2,
} from 'lucide-react';
import { docUploaderApi } from '../../../api/djangoApi';

export default function CategoryManager({ selectedCategory, onSelect, refreshTrigger }) {
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // 새 폴더 생성 상태
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState('');
  const [createError, setCreateError] = useState('');

  // 이름 변경 상태
  const [renamingName, setRenamingName] = useState(null);
  const [renameValue, setRenameValue] = useState('');
  const [renameError, setRenameError] = useState('');

  const fetchCategories = useCallback(async () => {
    try {
      const data = await docUploaderApi.listCategories();
      setCategories(data);
      setError(null);
    } catch {
      setError('카테고리 목록을 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCategories();
  }, [fetchCategories, refreshTrigger]);

  // ── 카테고리 생성 ──────────────────────────────────────────────────────────
  const handleCreateSubmit = async (e) => {
    e.preventDefault();
    const name = newName.trim();
    if (!name) return;
    setCreateError('');
    try {
      const created = await docUploaderApi.createCategory(name);
      setCategories((prev) => [...prev, created].sort((a, b) => a.name.localeCompare(b.name)));
      setNewName('');
      setCreating(false);
      onSelect(created.name);
    } catch (err) {
      setCreateError(err?.response?.data?.error || '폴더 생성 실패');
    }
  };

  // ── 이름 변경 ──────────────────────────────────────────────────────────────
  const startRename = (name) => {
    setRenamingName(name);
    setRenameValue(name);
    setRenameError('');
  };

  const handleRenameSubmit = async (e, oldName) => {
    e.preventDefault();
    const newN = renameValue.trim();
    if (!newN || newN === oldName) {
      setRenamingName(null);
      return;
    }
    setRenameError('');
    try {
      const updated = await docUploaderApi.renameCategory(oldName, newN);
      setCategories((prev) =>
        prev
          .map((c) => (c.name === oldName ? updated : c))
          .sort((a, b) => a.name.localeCompare(b.name))
      );
      if (selectedCategory === oldName) onSelect(updated.name);
      setRenamingName(null);
    } catch (err) {
      setRenameError(err?.response?.data?.error || '이름 변경 실패');
    }
  };

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 flex flex-col h-full">
      {/* 헤더 */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 bg-gray-50 shrink-0">
        <h2 className="text-sm font-semibold text-gray-700">카테고리</h2>
        <button
          onClick={() => {
            setCreating(true);
            setNewName('');
            setCreateError('');
          }}
          className="text-gray-400 hover:text-blue-500 transition-colors"
          title="새 카테고리"
        >
          <FolderPlus size={16} />
        </button>
      </div>

      {/* 에러 */}
      {error && (
        <div className="px-4 py-2 bg-red-50 text-red-600 text-xs flex items-center gap-1">
          <AlertCircle size={12} />
          {error}
        </div>
      )}

      {/* 목록 */}
      <div className="overflow-y-auto flex-1">
        {loading ? (
          <div className="py-6 text-center text-gray-400 text-xs">
            <Loader2 size={16} className="animate-spin mx-auto mb-1" />
            불러오는 중...
          </div>
        ) : categories.length === 0 && !creating ? (
          <div className="py-6 text-center text-gray-400 text-xs">
            카테고리가 없습니다.
            <br />+ 버튼으로 새 폴더를 만드세요.
          </div>
        ) : (
          <ul className="py-1">
            {categories.map((cat) => (
              <li key={cat.name}>
                {renamingName === cat.name ? (
                  <form
                    onSubmit={(e) => handleRenameSubmit(e, cat.name)}
                    className="flex items-center gap-1 px-3 py-1.5"
                  >
                    <input
                      autoFocus
                      value={renameValue}
                      onChange={(e) => setRenameValue(e.target.value)}
                      className="flex-1 text-xs border border-blue-300 rounded px-2 py-1 outline-none"
                    />
                    <button type="submit" className="text-green-500 hover:text-green-600">
                      <Check size={14} />
                    </button>
                    <button
                      type="button"
                      onClick={() => setRenamingName(null)}
                      className="text-gray-400 hover:text-gray-500"
                    >
                      <X size={14} />
                    </button>
                    {renameError && (
                      <span className="text-red-500 text-xs ml-1">{renameError}</span>
                    )}
                  </form>
                ) : (
                  <button
                    onClick={() => onSelect(cat.name)}
                    className={`w-full flex items-center justify-between px-3 py-2 text-left text-xs
                      hover:bg-blue-50 transition-colors group
                      ${selectedCategory === cat.name ? 'bg-blue-50 text-blue-700 font-medium' : 'text-gray-700'}
                    `}
                  >
                    <span className="flex items-center gap-1.5 min-w-0">
                      <FolderOpen
                        size={13}
                        className={selectedCategory === cat.name ? 'text-blue-500' : 'text-gray-400'}
                      />
                      <span className="truncate">{cat.name}</span>
                    </span>
                    <span className="flex items-center gap-1 shrink-0 ml-1">
                      <span className="text-gray-400">{cat.file_count}</span>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          startRename(cat.name);
                        }}
                        className="opacity-0 group-hover:opacity-100 text-gray-400 hover:text-blue-500 transition-opacity"
                        title="이름 변경"
                      >
                        <Pencil size={11} />
                      </button>
                    </span>
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}

        {/* 새 폴더 입력 */}
        {creating && (
          <form
            onSubmit={handleCreateSubmit}
            className="flex items-center gap-1 px-3 py-2 border-t border-gray-100"
          >
            <FolderOpen size={13} className="text-blue-400 shrink-0" />
            <input
              autoFocus
              value={newName}
              onChange={(e) => {
                setNewName(e.target.value);
                setCreateError('');
              }}
              placeholder="폴더 이름..."
              className="flex-1 text-xs border border-blue-300 rounded px-2 py-1 outline-none"
            />
            <button type="submit" className="text-green-500 hover:text-green-600">
              <Check size={14} />
            </button>
            <button
              type="button"
              onClick={() => setCreating(false)}
              className="text-gray-400 hover:text-gray-500"
            >
              <X size={14} />
            </button>
          </form>
        )}
        {createError && (
          <p className="px-4 py-1 text-red-500 text-xs">{createError}</p>
        )}
      </div>
    </div>
  );
}
