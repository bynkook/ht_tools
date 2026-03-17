import React, { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  LayoutList,
  MessageSquare,
  MoreVertical,
  Pencil,
  Plus,
  Trash2,
} from 'lucide-react';

import { boardApi } from '../../api/djangoApi';
import { lazy, Suspense } from 'react';

const EditorModal = lazy(() =>
  import('./BoardPage').then((mod) => ({ default: mod.__EditorModal }))
);

// EditorModal을 BoardPage에서 직접 import 불가이므로 인라인 재구현이 필요한 경우를 대비해
// BoardPage 전체를 dynamic import 하지 않고, EditorModal을 별도 파일로 분리한 뒤 둘 다 import.
// 현재는 BoardPage에 EditorModal이 내부 컴포넌트로 존재하므로, 이 파일에서는
// 독립적인 간이 에디터 모달을 직접 포함하거나, BoardPage에서 EditorModal을 named export 해야 한다.
// → BoardPage의 EditorModal을 별도 BoardEditorModal.jsx로 추출하기 전까지
//   이 컴포넌트는 자체 간이 text 폼만 제공한다.
// (아래는 실제 구현 — BoardPage와 동일한 EditorModal 로직을 이 파일에서 독립 구현)

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const MAX_IMAGES = 6;
const BoardMarkdownEditorLazy = lazy(() => import('./BoardMarkdownEditor'));

const DEFAULT_MARKDOWN_TEMPLATE = `# 제목 1
## 제목 2

**굵게** *이탤릭*

\`코드\`

- 항목 1
- 항목 2
`;

const formatDate = (value) => {
  if (!value) return '-';
  return new Date(value).toLocaleDateString('ko-KR', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
};

// ─────────────────────────────────────────────────────────────────────────────
// EditorModal (BoardPage의 것과 동일한 내부 구현 — 공유를 위해 나중에 분리 가능)
// ─────────────────────────────────────────────────────────────────────────────
const EditorModalLocal = ({ board, post, isSaving, onClose, onSave }) => {
  const [title, setTitle] = useState(post?.title ?? '');
  const [bodyMarkdown, setBodyMarkdown] = useState(post?.body_markdown ?? DEFAULT_MARKDOWN_TEMPLATE);
  const [existingImages, setExistingImages] = useState(post?.images ?? []);
  const [newFiles, setNewFiles] = useState([]);
  const [error, setError] = useState('');
  const [newFilePreviews, setNewFilePreviews] = useState([]);
  const fileInputRef = useRef(null);

  React.useEffect(() => {
    const previews = newFiles.map((file) => ({
      id: `${file.name}-${file.size}-${file.lastModified}`,
      name: file.name,
      url: URL.createObjectURL(file),
    }));
    setNewFilePreviews(previews);
    return () => previews.forEach((p) => URL.revokeObjectURL(p.url));
  }, [newFiles]);

  React.useEffect(() => {
    setTitle(post?.title ?? '');
    setBodyMarkdown(post?.body_markdown ?? DEFAULT_MARKDOWN_TEMPLATE);
    setExistingImages(post?.images ?? []);
    setNewFiles([]);
    setError('');
  }, [post]);

  const totalImageCount = existingImages.length + newFiles.length;
  const isEditMode = Boolean(post?.id);

  const handleFileChange = (event) => {
    const selectedFiles = Array.from(event.target.files || []);
    if (!selectedFiles.length) return;
    try {
      if (totalImageCount + selectedFiles.length > MAX_IMAGES) {
        throw new Error(`이미지는 최대 ${MAX_IMAGES}개까지 업로드할 수 있습니다.`);
      }
      setNewFiles((prev) => [...prev, ...selectedFiles]);
    } catch (err) {
      setError(err.message);
    }
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const removeExistingImage = (imageId) =>
    setExistingImages((prev) => prev.filter((img) => img.id !== imageId));

  const removeNewFile = (fileId) =>
    setNewFiles((prev) => prev.filter((f) => `${f.name}-${f.size}-${f.lastModified}` !== fileId));

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError('');
    const trimmedTitle = title.trim();
    if (!trimmedTitle) { setError('제목을 입력하세요.'); return; }
    if (!bodyMarkdown.trim()) { setError('본문을 입력하세요.'); return; }

    const formData = new FormData();
    formData.append('title', trimmedTitle);
    formData.append('body_markdown', bodyMarkdown);
    if (isEditMode) {
      formData.append('retained_image_ids', JSON.stringify(existingImages.map((img) => img.id)));
    }
    newFiles.forEach((file) => formData.append('images', file));

    try {
      await onSave(formData, isEditMode ? post.id : null);
    } catch (saveError) {
      setError(saveError.message || '저장하지 못했습니다.');
    }
  };

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-black/70 px-4 py-6 backdrop-blur-sm">
      <div className="mx-auto flex max-h-[calc(100vh-3rem)] w-full max-w-3xl flex-col overflow-hidden rounded-[28px] border border-white/10 bg-zinc-950 text-white shadow-2xl">
        <div className="flex shrink-0 items-center justify-between border-b border-white/8 px-6 py-4">
          <h2 className="text-base font-semibold">
            {isEditMode ? '게시글 수정' : `${board?.title_display || 'Board'}에 글쓰기`}
          </h2>
          <button type="button" onClick={onClose} className="rounded-full p-1.5 text-zinc-400 transition hover:bg-white/8 hover:text-white">
            ✕
          </button>
        </div>
        <form onSubmit={handleSubmit} className="flex flex-1 flex-col overflow-y-auto">
          <div className="space-y-5 px-6 py-5">
            {error && (
              <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
                {error}
              </div>
            )}
            <div>
              <label className="mb-1.5 block text-xs font-medium uppercase tracking-[0.12em] text-zinc-400">제목</label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                maxLength={200}
                placeholder="제목을 입력하세요"
                className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white placeholder-zinc-500 outline-none transition focus:border-emerald-400/60 focus:bg-white/8"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium uppercase tracking-[0.12em] text-zinc-400">본문 (Markdown)</label>
              <Suspense fallback={<div className="h-[280px] animate-pulse rounded-xl bg-white/5" />}>
                <BoardMarkdownEditorLazy value={bodyMarkdown} onChange={setBodyMarkdown} />
              </Suspense>
            </div>
            <div>
              <div className="mb-2 flex items-center justify-between">
                <label className="text-xs font-medium uppercase tracking-[0.12em] text-zinc-400">
                  이미지 ({totalImageCount}/{MAX_IMAGES})
                </label>
                {totalImageCount < MAX_IMAGES && (
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    className="flex items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-zinc-300 transition hover:bg-white/10"
                  >
                    <Plus size={12} />
                    이미지 추가
                  </button>
                )}
              </div>
              <input ref={fileInputRef} type="file" multiple accept="image/*" className="hidden" onChange={handleFileChange} />
              {(existingImages.length > 0 || newFilePreviews.length > 0) && (
                <div className="flex flex-wrap gap-2">
                  {existingImages.map((img) => (
                    <div key={img.id} className="group relative h-20 w-20 overflow-hidden rounded-xl border border-white/10">
                      <img src={img.image_url} alt={img.alt_text || ''} className="h-full w-full object-cover" />
                      <button
                        type="button"
                        onClick={() => removeExistingImage(img.id)}
                        className="absolute inset-0 flex items-center justify-center bg-black/60 opacity-0 transition group-hover:opacity-100"
                      >
                        <span className="text-xs text-white">삭제</span>
                      </button>
                    </div>
                  ))}
                  {newFilePreviews.map((preview) => (
                    <div key={preview.id} className="group relative h-20 w-20 overflow-hidden rounded-xl border border-white/10">
                      <img src={preview.url} alt={preview.name} className="h-full w-full object-cover" />
                      <button
                        type="button"
                        onClick={() => removeNewFile(preview.id)}
                        className="absolute inset-0 flex items-center justify-center bg-black/60 opacity-0 transition group-hover:opacity-100"
                      >
                        <span className="text-xs text-white">삭제</span>
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
          <div className="flex shrink-0 justify-end gap-3 border-t border-white/8 px-6 py-4">
            <button type="button" onClick={onClose} className="rounded-full border border-white/10 px-4 py-2 text-sm text-zinc-300 transition hover:bg-white/5">
              취소
            </button>
            <button
              type="submit"
              disabled={isSaving}
              className="rounded-full bg-emerald-500 px-5 py-2 text-sm font-semibold text-white transition hover:bg-emerald-400 disabled:opacity-50"
            >
              {isSaving ? '저장 중...' : isEditMode ? '수정 완료' : '등록'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// RedditBoardView — 메인 컴포넌트
// ─────────────────────────────────────────────────────────────────────────────
const RedditBoardView = ({ board, posts, permissions, error: externalError, isSaving: externalIsSaving, onRefresh }) => {
  const navigate = useNavigate();
  const menuRef = useRef(null);

  const [editingPost, setEditingPost] = useState(null);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState('');
  const [openMenuId, setOpenMenuId] = useState(null);

  const canCreate = Boolean(permissions?.can_create);
  const boardHeaderStyle = board?.header_image_url
    ? {
        backgroundImage: `linear-gradient(135deg, rgba(9, 9, 11, 0.78), rgba(24, 24, 27, 0.4)), url(${board.header_image_url})`,
        backgroundSize: 'cover',
        backgroundPosition: 'center',
      }
    : undefined;

  const combinedError = externalError || error;

  React.useEffect(() => {
    const handleOutsideClick = (event) => {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setOpenMenuId(null);
      }
    };
    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, []);

  const handleSavePost = async (formData, postId) => {
    setIsSaving(true);
    try {
      if (postId) {
        await boardApi.updatePost(postId, formData);
      } else {
        await boardApi.createPost(board.slug, formData);
      }
      setEditingPost(null);
      onRefresh?.();
    } catch (saveError) {
      throw new Error(saveError.response?.data?.error || '게시글을 저장하지 못했습니다.');
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async (postId) => {
    const confirmed = window.confirm('이 게시글을 삭제하시겠습니까?');
    if (!confirmed) return;
    try {
      await boardApi.deletePost(postId);
      setOpenMenuId(null);
      onRefresh?.();
    } catch (deleteError) {
      setError(deleteError.response?.data?.error || '게시글을 삭제하지 못했습니다.');
    }
  };

  const handleEditPost = async (post) => {
    setError('');
    setOpenMenuId(null);
    try {
      const detail = await boardApi.getPost(post.id);
      setEditingPost(detail);
    } catch (loadError) {
      setError(loadError.response?.data?.error || '게시글 편집 정보를 불러오지 못했습니다.');
    }
  };

  return (
    <div className="min-h-screen bg-[#f6f7f8] text-zinc-950">
      {/* 헤더 */}
      <div
        className="bg-gradient-to-br from-zinc-950 via-zinc-900 to-zinc-800 text-white shadow-[0_24px_80px_rgba(0,0,0,0.18)]"
        style={boardHeaderStyle}
      >
        <div className="mx-auto max-w-4xl px-5 py-6 md:px-8 md:py-8">
          <div className="flex flex-col gap-6 md:flex-row md:items-start md:justify-between">
            <div className="max-w-2xl">
              <button
                type="button"
                onClick={() => navigate('/')}
                className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs uppercase tracking-[0.25em] text-zinc-300 transition hover:border-white/20 hover:text-white"
              >
                <ArrowLeft size={14} />
                Home
              </button>
              <div className="mt-6 flex items-center gap-2">
                <LayoutList size={16} className="text-orange-400" />
                <p className="text-[11px] uppercase tracking-[0.45em] text-zinc-500">Reddit Style Board</p>
              </div>
              <h1
                className="mt-3 text-4xl font-semibold tracking-[-0.04em] md:text-5xl"
                style={{ fontFamily: 'Georgia, Times New Roman, serif' }}
              >
                {board?.title_display || 'Board'}
              </h1>
              <p className="mt-3 max-w-xl text-sm leading-7 text-zinc-300">
                {board?.description || ''}
              </p>
            </div>

            {canCreate && (
              <button
                type="button"
                onClick={() => { setError(''); setEditingPost({}); }}
                className="self-start rounded-full border border-orange-300/30 bg-orange-300/10 px-4 py-2 text-xs font-semibold uppercase tracking-[0.25em] text-orange-200 transition hover:border-orange-200/50 hover:bg-orange-300/20 hover:text-white"
              >
                <span className="inline-flex items-center gap-2">
                  <Plus size={14} />
                  Write
                </span>
              </button>
            )}
          </div>
        </div>
      </div>

      {/* 게시글 목록 */}
      <div className="mx-auto max-w-4xl px-4 py-6 md:px-8">
        {combinedError && (
          <div className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
            {combinedError}
          </div>
        )}

        {posts.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-zinc-300 bg-white px-6 py-16 text-center shadow-sm">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-zinc-900 text-white">
              <LayoutList size={20} />
            </div>
            <h2 className="mt-5 text-xl font-semibold text-zinc-900">첫 게시글을 기다리는 중입니다</h2>
            <p className="mx-auto mt-2 max-w-sm text-sm text-zinc-500">
              moderator 권한이 있는 사용자는 Write 버튼으로 글을 등록할 수 있습니다.
            </p>
          </div>
        ) : (
          <div className="overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-sm">
            {posts.map((post, index) => (
              <article
                key={post.id}
                className={`group flex items-start gap-4 px-5 py-4 transition hover:bg-zinc-50 ${
                  index < posts.length - 1 ? 'border-b border-zinc-100' : ''
                }`}
              >
                {/* 왼쪽: 통계 컬럼 */}
                <div className="hidden w-10 shrink-0 flex-col items-center gap-1 pt-0.5 text-[11px] text-zinc-400 sm:flex">
                  <MessageSquare size={15} className="text-zinc-300" />
                  <span>{post.comment_count ?? 0}</span>
                </div>

                {/* 메인 콘텐츠 */}
                <div className="min-w-0 flex-1">
                  <button
                    type="button"
                    onClick={() => navigate(`/${board.slug}/post/${post.id}`)}
                    className="text-left"
                  >
                    <h2 className="text-base font-semibold text-zinc-900 transition group-hover:text-orange-600">
                      {post.title}
                    </h2>
                    {post.excerpt && (
                      <p className="mt-1 line-clamp-2 text-sm leading-6 text-zinc-500">
                        {post.excerpt}
                      </p>
                    )}
                  </button>
                  <div className="mt-2 flex flex-wrap items-center gap-3 text-[11px] text-zinc-400">
                    <span>
                      by <span className="font-medium text-zinc-600">{post.author_username}</span>
                    </span>
                    <span>{formatDate(post.created_at)}</span>
                    <span className="flex items-center gap-1 sm:hidden">
                      <MessageSquare size={11} />
                      {post.comment_count ?? 0}
                    </span>
                  </div>
                </div>

                {/* 우측: 관리 메뉴 */}
                {(post.can_edit || post.can_delete) && (
                  <div className="relative shrink-0" ref={openMenuId === post.id ? menuRef : null}>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setOpenMenuId((cur) => (cur === post.id ? null : post.id));
                      }}
                      className="rounded-full p-1.5 text-zinc-300 opacity-0 transition group-hover:opacity-100 hover:bg-zinc-100 hover:text-zinc-600"
                    >
                      <MoreVertical size={16} />
                    </button>
                    {openMenuId === post.id && (
                      <div className="absolute right-0 z-10 mt-1 min-w-[130px] overflow-hidden rounded-xl border border-zinc-200 bg-white py-1 shadow-xl">
                        {post.can_edit && (
                          <button
                            type="button"
                            onClick={(e) => { e.stopPropagation(); void handleEditPost(post); }}
                            className="flex w-full items-center gap-2 px-4 py-2.5 text-sm text-zinc-700 transition hover:bg-zinc-100"
                          >
                            <Pencil size={13} />
                            수정
                          </button>
                        )}
                        {post.can_delete && (
                          <button
                            type="button"
                            onClick={(e) => { e.stopPropagation(); void handleDelete(post.id); }}
                            className="flex w-full items-center gap-2 px-4 py-2.5 text-sm text-red-600 transition hover:bg-red-50"
                          >
                            <Trash2 size={13} />
                            삭제
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </article>
            ))}
          </div>
        )}
      </div>

      {/* 게시글 에디터 모달 */}
      {editingPost !== null && board && (
        <Suspense fallback={null}>
          <EditorModalLocal
            board={board}
            post={editingPost.id ? editingPost : null}
            isSaving={isSaving || externalIsSaving}
            onClose={() => setEditingPost(null)}
            onSave={handleSavePost}
          />
        </Suspense>
      )}
    </div>
  );
};

export default RedditBoardView;
