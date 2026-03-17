import React, { Suspense, lazy, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  Calendar,
  ImageIcon,
  MoreVertical,
  Pencil,
  Trash2,
  User,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import { boardApi } from '../../api/djangoApi';
import CommentSection from './components/CommentSection';

const BoardMarkdownEditorLazy = lazy(() => import('./BoardMarkdownEditor'));

const MAX_IMAGES = 6;
const DEFAULT_MARKDOWN_TEMPLATE = `# 제목 1\n## 제목 2\n\n**굵게** *이탤릭*\n\n\`코드\`\n\n- 항목 1\n- 항목 2\n`;

const formatDate = (value) => {
  if (!value) return '-';
  return new Date(value).toLocaleDateString('ko-KR', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
};

// ─────────────────────────────────────────────────────────────────────────────
// EditorModal (인라인 — 향후 별도 파일로 분리 가능)
// ─────────────────────────────────────────────────────────────────────────────
const EditorModal = ({ board, post, isSaving, onClose, onSave }) => {
  const [title, setTitle] = useState(post?.title ?? '');
  const [bodyMarkdown, setBodyMarkdown] = useState(post?.body_markdown ?? DEFAULT_MARKDOWN_TEMPLATE);
  const [existingImages, setExistingImages] = useState(post?.images ?? []);
  const [newFiles, setNewFiles] = useState([]);
  const [newFilePreviews, setNewFilePreviews] = useState([]);
  const [error, setError] = useState('');
  const fileInputRef = useRef(null);
  const isEditMode = Boolean(post?.id);

  useEffect(() => {
    const previews = newFiles.map((f) => ({
      id: `${f.name}-${f.size}-${f.lastModified}`,
      name: f.name,
      url: URL.createObjectURL(f),
    }));
    setNewFilePreviews(previews);
    return () => previews.forEach((p) => URL.revokeObjectURL(p.url));
  }, [newFiles]);

  useEffect(() => {
    setTitle(post?.title ?? '');
    setBodyMarkdown(post?.body_markdown ?? DEFAULT_MARKDOWN_TEMPLATE);
    setExistingImages(post?.images ?? []);
    setNewFiles([]);
    setError('');
  }, [post]);

  const totalImageCount = existingImages.length + newFiles.length;

  const handleFileChange = (e) => {
    const selected = Array.from(e.target.files || []);
    if (!selected.length) return;
    if (totalImageCount + selected.length > MAX_IMAGES) {
      setError(`이미지는 최대 ${MAX_IMAGES}개까지 업로드할 수 있습니다.`);
      return;
    }
    setNewFiles((prev) => [...prev, ...selected]);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
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
          <h2 className="text-base font-semibold">{isEditMode ? '게시글 수정' : '새 글쓰기'}</h2>
          <button type="button" onClick={onClose} className="rounded-full p-1.5 text-zinc-400 hover:bg-white/8 hover:text-white">✕</button>
        </div>
        <form onSubmit={handleSubmit} className="flex flex-1 flex-col overflow-y-auto">
          <div className="space-y-5 px-6 py-5">
            {error && (
              <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{error}</div>
            )}
            <div>
              <label className="mb-1.5 block text-xs font-medium uppercase tracking-[0.12em] text-zinc-400">제목</label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                maxLength={200}
                placeholder="제목을 입력하세요"
                className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white placeholder-zinc-500 outline-none transition focus:border-emerald-400/60"
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
                    className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-zinc-300 hover:bg-white/10"
                  >이미지 추가</button>
                )}
              </div>
              <input ref={fileInputRef} type="file" multiple accept="image/*" className="hidden" onChange={handleFileChange} />
              {(existingImages.length > 0 || newFilePreviews.length > 0) && (
                <div className="flex flex-wrap gap-2">
                  {existingImages.map((img) => (
                    <div key={img.id} className="group relative h-20 w-20 overflow-hidden rounded-xl border border-white/10">
                      <img src={img.image_url} alt={img.alt_text || ''} className="h-full w-full object-cover" />
                      <button type="button" onClick={() => setExistingImages((p) => p.filter((i) => i.id !== img.id))}
                        className="absolute inset-0 flex items-center justify-center bg-black/60 opacity-0 group-hover:opacity-100">
                        <span className="text-xs text-white">삭제</span>
                      </button>
                    </div>
                  ))}
                  {newFilePreviews.map((preview) => (
                    <div key={preview.id} className="group relative h-20 w-20 overflow-hidden rounded-xl border border-white/10">
                      <img src={preview.url} alt={preview.name} className="h-full w-full object-cover" />
                      <button type="button"
                        onClick={() => setNewFiles((p) => p.filter((f) => `${f.name}-${f.size}-${f.lastModified}` !== preview.id))}
                        className="absolute inset-0 flex items-center justify-center bg-black/60 opacity-0 group-hover:opacity-100">
                        <span className="text-xs text-white">삭제</span>
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
          <div className="flex shrink-0 justify-end gap-3 border-t border-white/8 px-6 py-4">
            <button type="button" onClick={onClose} className="rounded-full border border-white/10 px-4 py-2 text-sm text-zinc-300 hover:bg-white/5">취소</button>
            <button type="submit" disabled={isSaving}
              className="rounded-full bg-emerald-500 px-5 py-2 text-sm font-semibold text-white hover:bg-emerald-400 disabled:opacity-50">
              {isSaving ? '저장 중...' : isEditMode ? '수정 완료' : '등록'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// RedditPostDetailPage — 메인 컴포넌트
// ─────────────────────────────────────────────────────────────────────────────
const RedditPostDetailPage = () => {
  const { boardSlug, postId } = useParams();
  const navigate = useNavigate();
  const menuRef = useRef(null);

  const [post, setPost] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isEditingPost, setIsEditingPost] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState('');
  const [menuOpen, setMenuOpen] = useState(false);

  const loadPost = async () => {
    if (!postId) return;
    setIsLoading(true);
    setError('');
    try {
      const data = await boardApi.getPost(Number(postId));
      setPost(data);
    } catch (err) {
      setError(err.response?.data?.error || '게시글을 불러오지 못했습니다.');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void loadPost();
  }, [postId]);

  useEffect(() => {
    const handleOutsideClick = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, []);

  const handleSaveEdit = async (formData, editPostId) => {
    setIsSaving(true);
    try {
      const updated = await boardApi.updatePost(editPostId, formData);
      setPost(updated);
      setIsEditingPost(false);
    } catch (saveError) {
      throw new Error(saveError.response?.data?.error || '게시글을 수정하지 못했습니다.');
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    const confirmed = window.confirm('이 게시글을 삭제하시겠습니까?');
    if (!confirmed) return;
    try {
      await boardApi.deletePost(post.id);
      navigate(`/${boardSlug}`);
    } catch (deleteError) {
      setError(deleteError.response?.data?.error || '게시글을 삭제하지 못했습니다.');
    }
  };

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#f6f7f8]">
        <div className="flex items-center gap-3 rounded-full border border-zinc-200 bg-white px-5 py-3 text-sm text-zinc-500 shadow-sm">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-300 border-t-zinc-700" />
          게시글을 불러오는 중입니다.
        </div>
      </div>
    );
  }

  if (error && !post) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-[#f6f7f8]">
        <div className="rounded-2xl border border-red-200 bg-red-50 px-6 py-4 text-sm text-red-600">{error}</div>
        <button
          type="button"
          onClick={() => navigate(`/${boardSlug}`)}
          className="flex items-center gap-2 rounded-full border border-zinc-200 bg-white px-4 py-2 text-sm text-zinc-600 shadow-sm hover:bg-zinc-50"
        >
          <ArrowLeft size={14} />
          게시판으로 돌아가기
        </button>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#f6f7f8]">
      {/* 상단 네비게이션 바 */}
      <div className="sticky top-0 z-10 border-b border-zinc-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-4 py-3 md:px-8">
          <button
            type="button"
            onClick={() => navigate(`/${boardSlug}`)}
            className="flex items-center gap-2 rounded-full border border-zinc-200 bg-white px-3 py-1.5 text-xs text-zinc-600 shadow-sm transition hover:bg-zinc-50"
          >
            <ArrowLeft size={13} />
            <span className="hidden sm:inline">{boardSlug}</span>
            <span className="sm:hidden">목록</span>
          </button>

          {/* 수정/삭제 메뉴 */}
          {post && (post.can_edit || post.can_delete) && (
            <div className="relative" ref={menuRef}>
              <button
                type="button"
                onClick={() => setMenuOpen((v) => !v)}
                className="rounded-full border border-zinc-200 p-2 text-zinc-500 transition hover:bg-zinc-100"
              >
                <MoreVertical size={16} />
              </button>
              {menuOpen && (
                <div className="absolute right-0 mt-2 min-w-[130px] overflow-hidden rounded-xl border border-zinc-200 bg-white py-1 shadow-xl">
                  {post.can_edit && (
                    <button
                      type="button"
                      onClick={() => { setMenuOpen(false); setIsEditingPost(true); }}
                      className="flex w-full items-center gap-2 px-4 py-2.5 text-sm text-zinc-700 hover:bg-zinc-100"
                    >
                      <Pencil size={13} />
                      수정
                    </button>
                  )}
                  {post.can_delete && (
                    <button
                      type="button"
                      onClick={() => { setMenuOpen(false); void handleDelete(); }}
                      className="flex w-full items-center gap-2 px-4 py-2.5 text-sm text-red-600 hover:bg-red-50"
                    >
                      <Trash2 size={13} />
                      삭제
                    </button>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* 본문 */}
      <div className="mx-auto max-w-4xl px-4 py-8 md:px-8">
        {error && (
          <div className="mb-6 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">{error}</div>
        )}

        {post && (
          <article className="rounded-2xl border border-zinc-200 bg-white shadow-sm">
            {/* 게시글 헤더 */}
            <div className="border-b border-zinc-100 px-6 py-5 md:px-8">
              <h1 className="text-2xl font-bold leading-tight text-zinc-900 md:text-3xl">{post.title}</h1>
              <div className="mt-3 flex flex-wrap items-center gap-4 text-xs text-zinc-400">
                <span className="flex items-center gap-1.5">
                  <User size={12} />
                  <span className="font-medium text-zinc-600">{post.author_username}</span>
                </span>
                <span className="flex items-center gap-1.5">
                  <Calendar size={12} />
                  {formatDate(post.created_at)}
                </span>
                {post.image_count > 0 && (
                  <span className="flex items-center gap-1.5">
                    <ImageIcon size={12} />
                    이미지 {post.image_count}개
                  </span>
                )}
              </div>
            </div>

            {/* 이미지 갤러리 */}
            {post.images && post.images.length > 0 && (
              <div className="border-b border-zinc-100 px-6 py-4 md:px-8">
                <div className="flex flex-wrap gap-3">
                  {post.images.map((img) => (
                    <a
                      key={img.id}
                      href={img.image_url}
                      target="_blank"
                      rel="noreferrer"
                      className="block"
                    >
                      <img
                        src={img.image_url}
                        alt={img.alt_text || post.title}
                        className="h-40 w-auto max-w-[240px] rounded-xl object-cover shadow-sm transition hover:opacity-90"
                      />
                    </a>
                  ))}
                </div>
              </div>
            )}

            {/* Markdown 본문 */}
            <div className="prose prose-zinc max-w-none px-6 py-6 md:px-8">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                skipHtml
                components={{
                  h1: ({ children }) => <h1 className="mb-4 mt-6 text-2xl font-bold text-zinc-900">{children}</h1>,
                  h2: ({ children }) => <h2 className="mb-3 mt-5 text-xl font-semibold text-zinc-800">{children}</h2>,
                  h3: ({ children }) => <h3 className="mb-2 mt-4 text-lg font-semibold text-zinc-700">{children}</h3>,
                  p: ({ children }) => <p className="mb-4 whitespace-pre-wrap leading-7 text-zinc-700">{children}</p>,
                  ul: ({ children }) => <ul className="mb-4 list-disc pl-6 text-zinc-700">{children}</ul>,
                  ol: ({ children }) => <ol className="mb-4 list-decimal pl-6 text-zinc-700">{children}</ol>,
                  li: ({ children }) => <li className="mb-1 leading-7">{children}</li>,
                  blockquote: ({ children }) => (
                    <blockquote className="mb-4 border-l-4 border-orange-300 pl-4 italic text-zinc-500">
                      {children}
                    </blockquote>
                  ),
                  code: ({ className, children }) => {
                    if (className?.startsWith('language-')) {
                      return <code className={`${className} block rounded-xl bg-zinc-100 px-4 py-3 font-mono text-sm`}>{children}</code>;
                    }
                    return <code className="rounded bg-zinc-100 px-1.5 py-0.5 font-mono text-sm text-pink-600">{children}</code>;
                  },
                  pre: ({ children }) => <pre className="mb-4 overflow-x-auto rounded-xl bg-zinc-100 px-4 py-3">{children}</pre>,
                  a: ({ href, children }) => (
                    <a href={href} target="_blank" rel="noreferrer" className="text-orange-600 underline hover:text-orange-500">
                      {children}
                    </a>
                  ),
                  table: ({ children }) => (
                    <div className="mb-4 w-full overflow-x-auto">
                      <table className="w-max min-w-full border-collapse text-sm">{children}</table>
                    </div>
                  ),
                  th: ({ children }) => <th className="border border-zinc-200 bg-zinc-50 px-3 py-2 text-left font-semibold text-zinc-700">{children}</th>,
                  td: ({ children }) => <td className="border border-zinc-200 px-3 py-2 text-zinc-700">{children}</td>,
                  hr: () => <hr className="my-6 border-zinc-200" />,
                  strong: ({ children }) => <strong className="font-semibold text-zinc-900">{children}</strong>,
                }}
              >
                {post.body_markdown}
              </ReactMarkdown>
            </div>
          </article>
        )}

        {/* 댓글 섹션 */}
        {post && (
          <div className="mt-6 rounded-2xl border border-zinc-200 bg-white px-6 py-6 shadow-sm md:px-8">
            <CommentSection postId={post.id} />
          </div>
        )}
      </div>

      {/* 수정 모달 */}
      {isEditingPost && post && (
        <EditorModal
          board={{ slug: boardSlug }}
          post={post}
          isSaving={isSaving}
          onClose={() => setIsEditingPost(false)}
          onSave={handleSaveEdit}
        />
      )}
    </div>
  );
};

export default RedditPostDetailPage;
