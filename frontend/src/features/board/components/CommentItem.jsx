import React, { useState } from 'react';
import { Pencil, Trash2 } from 'lucide-react';

import { boardApi } from '../../../api/djangoApi';

const formatDate = (value) => {
  if (!value) return '-';
  return new Date(value).toLocaleDateString('ko-KR', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const CommentItem = ({ comment, onUpdated, onDeleted }) => {
  const [isEditing, setIsEditing] = useState(false);
  const [editBody, setEditBody] = useState(comment.body);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState('');

  const handleSaveEdit = async () => {
    const trimmed = editBody.trim();
    if (!trimmed) { setError('댓글을 입력하세요.'); return; }
    setIsSaving(true);
    setError('');
    try {
      const updated = await boardApi.updateComment(comment.id, trimmed);
      onUpdated(updated);
      setIsEditing(false);
    } catch (err) {
      setError(err.response?.data?.error || '수정하지 못했습니다.');
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    const confirmed = window.confirm('댓글을 삭제하시겠습니까?');
    if (!confirmed) return;
    try {
      await boardApi.deleteComment(comment.id);
      onDeleted(comment.id);
    } catch (err) {
      setError(err.response?.data?.error || '삭제하지 못했습니다.');
    }
  };

  return (
    <div className="group py-4">
      <div className="flex items-start gap-3">
        {/* 아바타 */}
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-zinc-200 text-xs font-semibold text-zinc-600">
          {comment.author_username?.[0]?.toUpperCase() ?? '?'}
        </div>
        <div className="min-w-0 flex-1">
          {/* 메타 */}
          <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-400">
            <span className="font-medium text-zinc-700">{comment.author_username}</span>
            <span>·</span>
            <span>{formatDate(comment.created_at)}</span>
            {comment.updated_at !== comment.created_at && (
              <span className="text-zinc-300">(수정됨)</span>
            )}
          </div>

          {/* 본문 또는 수정 폼 */}
          {isEditing ? (
            <div className="mt-2 space-y-2">
              {error && <p className="text-xs text-red-500">{error}</p>}
              <textarea
                value={editBody}
                onChange={(e) => setEditBody(e.target.value)}
                rows={3}
                className="w-full rounded-xl border border-zinc-200 bg-zinc-50 px-3 py-2 text-sm text-zinc-800 outline-none transition focus:border-orange-400 focus:ring-1 focus:ring-orange-400/20"
              />
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={handleSaveEdit}
                  disabled={isSaving}
                  className="rounded-full bg-orange-500 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-orange-400 disabled:opacity-50"
                >
                  {isSaving ? '저장 중...' : '저장'}
                </button>
                <button
                  type="button"
                  onClick={() => { setIsEditing(false); setEditBody(comment.body); setError(''); }}
                  className="rounded-full border border-zinc-200 px-3 py-1.5 text-xs text-zinc-500 transition hover:bg-zinc-100"
                >
                  취소
                </button>
              </div>
            </div>
          ) : (
            <p className="mt-1 whitespace-pre-wrap text-sm leading-6 text-zinc-700">{comment.body}</p>
          )}

          {/* 액션 버튼 */}
          {!isEditing && (comment.can_edit || comment.can_delete) && (
            <div className="mt-1.5 flex gap-3 opacity-0 transition group-hover:opacity-100">
              {comment.can_edit && (
                <button
                  type="button"
                  onClick={() => { setIsEditing(true); setError(''); }}
                  className="flex items-center gap-1 text-[11px] text-zinc-400 transition hover:text-zinc-700"
                >
                  <Pencil size={11} />
                  수정
                </button>
              )}
              {comment.can_delete && (
                <button
                  type="button"
                  onClick={handleDelete}
                  className="flex items-center gap-1 text-[11px] text-zinc-400 transition hover:text-red-500"
                >
                  <Trash2 size={11} />
                  삭제
                </button>
              )}
            </div>
          )}
          {error && !isEditing && <p className="mt-1 text-xs text-red-500">{error}</p>}
        </div>
      </div>
    </div>
  );
};

export default CommentItem;
