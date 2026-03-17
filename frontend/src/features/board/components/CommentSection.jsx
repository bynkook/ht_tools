import React, { useCallback, useEffect, useRef, useState } from 'react';
import { MessageSquare } from 'lucide-react';

import { boardApi } from '../../../api/djangoApi';
import CommentItem from './CommentItem';

const CommentSection = ({ postId }) => {
  const [comments, setComments] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSending, setIsSending] = useState(false);
  const [newBody, setNewBody] = useState('');
  const [error, setError] = useState('');
  const textareaRef = useRef(null);

  const loadComments = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await boardApi.listComments(postId);
      setComments(data);
    } catch (err) {
      setError(err.response?.data?.error || '댓글을 불러오지 못했습니다.');
    } finally {
      setIsLoading(false);
    }
  }, [postId]);

  useEffect(() => {
    void loadComments();
  }, [loadComments]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    const trimmed = newBody.trim();
    if (!trimmed) return;
    setIsSending(true);
    setError('');
    try {
      const created = await boardApi.createComment(postId, trimmed);
      setComments((prev) => [...prev, created]);
      setNewBody('');
    } catch (err) {
      setError(err.response?.data?.error || '댓글을 등록하지 못했습니다.');
    } finally {
      setIsSending(false);
    }
  };

  const handleUpdated = (updated) => {
    setComments((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
  };

  const handleDeleted = (commentId) => {
    setComments((prev) => prev.filter((c) => c.id !== commentId));
  };

  return (
    <section className="mt-10">
      {/* 섹션 헤더 */}
      <div className="flex items-center gap-2 border-b border-zinc-200 pb-3">
        <MessageSquare size={16} className="text-zinc-400" />
        <h3 className="text-sm font-semibold text-zinc-700">
          댓글 {comments.length > 0 ? `(${comments.length})` : ''}
        </h3>
      </div>

      {/* 댓글 작성 폼 */}
      <form onSubmit={handleSubmit} className="mt-5">
        {error && (
          <div className="mb-3 rounded-xl border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-600">
            {error}
          </div>
        )}
        <textarea
          ref={textareaRef}
          value={newBody}
          onChange={(e) => setNewBody(e.target.value)}
          rows={3}
          placeholder="댓글을 작성하세요..."
          className="w-full rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm text-zinc-800 outline-none transition focus:border-orange-400 focus:bg-white focus:ring-1 focus:ring-orange-400/20"
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
              void handleSubmit(e);
            }
          }}
        />
        <div className="mt-2 flex items-center justify-between">
          <p className="text-[11px] text-zinc-400">Ctrl+Enter로 빠른 등록</p>
          <button
            type="submit"
            disabled={isSending || !newBody.trim()}
            className="rounded-full bg-orange-500 px-4 py-2 text-xs font-semibold text-white transition hover:bg-orange-400 disabled:opacity-40"
          >
            {isSending ? '등록 중...' : '댓글 등록'}
          </button>
        </div>
      </form>

      {/* 댓글 목록 */}
      {isLoading ? (
        <div className="mt-6 flex items-center gap-2 text-sm text-zinc-400">
          <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-zinc-300 border-t-zinc-600" />
          댓글을 불러오는 중...
        </div>
      ) : comments.length === 0 ? (
        <p className="mt-6 text-sm text-zinc-400">아직 댓글이 없습니다. 첫 댓글을 남겨보세요.</p>
      ) : (
        <div className="mt-4 divide-y divide-zinc-100">
          {comments.map((comment) => (
            <CommentItem
              key={comment.id}
              comment={comment}
              onUpdated={handleUpdated}
              onDeleted={handleDeleted}
            />
          ))}
        </div>
      )}
    </section>
  );
};

export default CommentSection;
