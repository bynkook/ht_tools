import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  ExternalLink,
  FilePlus2,
  ImagePlus,
  LayoutGrid,
  MoreVertical,
  Pencil,
  Plus,
  Trash2,
  X,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import { boardApi } from '../../api/djangoApi';


const MAX_IMAGES = 6;

const formatDate = (value) => {
  if (!value) {
    return '-';
  }
  return new Date(value).toLocaleDateString('ko-KR', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
};

const EditorModal = ({ board, post, isSaving, onClose, onSave }) => {
  const [title, setTitle] = useState(post?.title ?? '');
  const [bodyMarkdown, setBodyMarkdown] = useState(post?.body_markdown ?? '');
  const [existingImages, setExistingImages] = useState(post?.images ?? []);
  const [newFiles, setNewFiles] = useState([]);
  const [error, setError] = useState('');
  const [newFilePreviews, setNewFilePreviews] = useState([]);
  const fileInputRef = useRef(null);

  useEffect(() => {
    const previews = newFiles.map((file) => ({
      id: `${file.name}-${file.size}-${file.lastModified}`,
      name: file.name,
      url: URL.createObjectURL(file),
    }));
    setNewFilePreviews(previews);

    return () => {
      previews.forEach((preview) => URL.revokeObjectURL(preview.url));
    };
  }, [newFiles]);

  const totalImageCount = existingImages.length + newFiles.length;
  const isEditMode = Boolean(post?.id);

  const handleFileChange = (event) => {
    const selectedFiles = Array.from(event.target.files ?? []);
    if (selectedFiles.length === 0) {
      return;
    }

    if (totalImageCount + selectedFiles.length > MAX_IMAGES) {
      setError(`이미지는 최대 ${MAX_IMAGES}개까지 업로드할 수 있습니다.`);
      event.target.value = '';
      return;
    }

    setError('');
    setNewFiles((prev) => [...prev, ...selectedFiles]);
    event.target.value = '';
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!title.trim()) {
      setError('제목을 입력하세요.');
      return;
    }
    if (!bodyMarkdown.trim()) {
      setError('본문을 입력하세요.');
      return;
    }

    setError('');
    const formData = new FormData();
    formData.append('title', title.trim());
    formData.append('body_markdown', bodyMarkdown);
    formData.append('retained_image_ids', JSON.stringify(existingImages.map((image) => image.id)));
    newFiles.forEach((file) => {
      formData.append('images', file);
    });

    try {
      await onSave(formData, post?.id ?? null);
    } catch (saveError) {
      setError(saveError.message || '게시글을 저장하지 못했습니다.');
    }
  };

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-black/70 px-4 py-6 backdrop-blur-sm">
      <div className="flex min-h-full items-start justify-center">
        <div className="flex max-h-[calc(100vh-3rem)] w-full max-w-5xl flex-col overflow-hidden rounded-[28px] border border-white/10 bg-zinc-950 text-white shadow-2xl">
          <div className="flex items-center justify-between border-b border-white/10 px-6 py-5">
            <div>
              <p className="text-[11px] uppercase tracking-[0.35em] text-zinc-500">{board?.title_display}</p>
              <h2 className="mt-2 text-2xl font-semibold text-white">
                {isEditMode ? 'Edit Post' : 'New Post'}
              </h2>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="rounded-full border border-white/10 p-2 text-zinc-400 transition hover:border-white/20 hover:text-white"
              aria-label="닫기"
            >
              <X size={18} />
            </button>
          </div>

          <form onSubmit={handleSubmit} className="board-dark-scrollbar space-y-6 overflow-y-auto bg-zinc-950 px-6 py-6">
          {error && (
            <div className="rounded-2xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-200">
              {error}
            </div>
          )}

          <div className="space-y-2">
            <label className="text-xs uppercase tracking-[0.3em] text-zinc-500">Title</label>
            <input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-base text-white outline-none transition focus:border-emerald-400/60"
              placeholder="게시글 제목"
              maxLength={200}
            />
          </div>

          <div className="space-y-2">
            <label className="text-xs uppercase tracking-[0.3em] text-zinc-500">Markdown Content</label>
            <div className="rounded-2xl border border-white/10 bg-white/5 p-1">
              <textarea
                value={bodyMarkdown}
                onChange={(event) => setBodyMarkdown(event.target.value)}
                className="h-[220px] w-full resize-y rounded-[20px] bg-transparent px-3 py-3 text-sm leading-7 text-zinc-100 outline-none md:h-[280px]"
                placeholder="Markdown 본문을 입력하세요."
              />
            </div>
          </div>

          <div className="space-y-4 rounded-[24px] border border-white/10 bg-white/[0.03] p-4">
            <div className="flex flex-col gap-3">
              <div>
                <p className="text-xs uppercase tracking-[0.3em] text-zinc-500">Images</p>
                <p className="mt-2 text-sm text-zinc-300">첫 번째 이미지는 타일 preview로 사용됩니다.</p>
              </div>
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="inline-flex w-full items-center justify-center gap-2 rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm font-medium text-white transition hover:border-emerald-400/50 hover:bg-emerald-400/10"
              >
                <ImagePlus size={16} />
                Add Image
              </button>
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/png,image/jpeg,image/jpg,image/gif,image/webp"
              multiple
              hidden
              onChange={handleFileChange}
            />
            <p className="text-xs text-zinc-500">총 {totalImageCount}/{MAX_IMAGES}</p>

            {existingImages.length > 0 && (
              <div className="space-y-3">
                <p className="text-xs uppercase tracking-[0.3em] text-zinc-500">Current</p>
                <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
                  {existingImages.map((image) => (
                    <div key={image.id} className="overflow-hidden rounded-[22px] border border-white/10 bg-white/[0.04]">
                      <div className="aspect-square overflow-hidden bg-zinc-900">
                        <img src={image.image_url} alt={image.alt_text || title} className="h-full w-full object-cover" />
                      </div>
                      <button
                        type="button"
                        onClick={() => setExistingImages((prev) => prev.filter((item) => item.id !== image.id))}
                        className="flex w-full items-center justify-center gap-2 border-t border-white/10 px-3 py-2 text-xs text-zinc-300 transition hover:bg-red-500/10 hover:text-red-200"
                      >
                        <Trash2 size={12} />
                        Remove
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {newFilePreviews.length > 0 && (
              <div className="space-y-3">
                <p className="text-xs uppercase tracking-[0.3em] text-zinc-500">New</p>
                <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
                  {newFilePreviews.map((preview, index) => (
                    <div key={preview.id} className="overflow-hidden rounded-[22px] border border-white/10 bg-white/[0.04]">
                      <div className="aspect-square overflow-hidden bg-zinc-900">
                        <img src={preview.url} alt={preview.name} className="h-full w-full object-cover" />
                      </div>
                      <button
                        type="button"
                        onClick={() => setNewFiles((prev) => prev.filter((_, fileIndex) => fileIndex !== index))}
                        className="flex w-full items-center justify-center gap-2 border-t border-white/10 px-3 py-2 text-xs text-zinc-300 transition hover:bg-red-500/10 hover:text-red-200"
                      >
                        <Trash2 size={12} />
                        Remove
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {existingImages.length === 0 && newFilePreviews.length === 0 && (
              <div className="rounded-[24px] border border-dashed border-white/10 bg-white/[0.03] px-5 py-10 text-center text-sm text-zinc-500">
                미리보기 이미지를 추가하면 이 영역에 표시됩니다.
              </div>
            )}
          </div>

          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-full border border-white/10 px-5 py-2.5 text-sm text-zinc-300 transition hover:border-white/20 hover:text-white"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSaving}
              className="inline-flex items-center gap-2 rounded-full bg-emerald-400 px-5 py-2.5 text-sm font-semibold text-zinc-950 transition hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isEditMode ? <Pencil size={14} /> : <FilePlus2 size={14} />}
              {isSaving ? 'Saving...' : isEditMode ? 'Update Post' : 'Publish Post'}
            </button>
          </div>
          </form>
        </div>
      </div>
    </div>
  );
};

const ReadModal = ({ post, boardTitle, onClose }) => (
  <div className="fixed inset-0 z-40 overflow-y-auto bg-black/70 px-4 py-6 backdrop-blur-sm">
    <div className="flex min-h-full items-start justify-center">
      <div className="flex max-h-[calc(100vh-3rem)] w-full max-w-4xl flex-col overflow-hidden rounded-[30px] border border-zinc-200 bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-zinc-200 px-6 py-5">
          <div>
            <p className="text-[11px] uppercase tracking-[0.35em] text-zinc-400">{boardTitle}</p>
            <h2 className="mt-2 text-2xl font-semibold text-zinc-950">{post.title}</h2>
            <p className="mt-2 text-sm text-zinc-500">@{post.author_username} · {formatDate(post.updated_at)}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex items-center gap-2 rounded-full border border-zinc-200 px-4 py-2 text-sm font-medium text-zinc-700 transition hover:border-zinc-900 hover:text-zinc-950"
          >
            <X size={16} />
            닫기
          </button>
        </div>

        <div className="custom-scrollbar max-h-full space-y-6 overflow-y-auto px-6 py-6">
        {post.images?.length > 0 && (
          <div className="grid gap-3 md:grid-cols-2">
            {post.images.map((image) => (
              <div key={image.id} className="overflow-hidden rounded-[26px] bg-zinc-100">
                <img src={image.image_url} alt={image.alt_text || post.title} className="max-h-[420px] w-full object-cover" />
              </div>
            ))}
          </div>
        )}

        <article className="markdown-body prose prose-zinc max-w-none text-zinc-800">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            skipHtml
            components={{
              a: ({ href, children, ...props }) => (
                <a
                  {...props}
                  href={href}
                  target="_blank"
                  rel="noreferrer"
                  onClick={(event) => {
                    event.preventDefault();
                    onClose();
                    if (href) {
                      window.open(href, '_blank', 'noopener,noreferrer');
                    }
                  }}
                  className="inline-flex items-center gap-1 text-blue-600 underline underline-offset-4"
                >
                  {children}
                  <ExternalLink size={14} />
                </a>
              ),
            }}
          >
            {post.body_markdown}
          </ReactMarkdown>
        </article>
        </div>
      </div>
    </div>
  </div>
);

const BoardPage = () => {
  const navigate = useNavigate();
  const { boardSlug } = useParams();
  const [board, setBoard] = useState(null);
  const [posts, setPosts] = useState([]);
  const [selectedPost, setSelectedPost] = useState(null);
  const [editingPost, setEditingPost] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState('');
  const [openMenuId, setOpenMenuId] = useState(null);
  const menuRef = useRef(null);

  const loadBoard = async () => {
    if (!boardSlug) {
      setError('게시판 주소가 올바르지 않습니다.');
      setIsLoading(false);
      return;
    }

    try {
      setIsLoading(true);
      setError('');
      const data = await boardApi.getBoard(boardSlug);
      setBoard(data.board);
      setPosts(data.posts);
    } catch (loadError) {
      setError(loadError.response?.data?.error || '게시판을 불러오지 못했습니다.');
      setBoard(null);
      setPosts([]);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void loadBoard();
  }, [boardSlug]);

  useEffect(() => {
    const handleOutsideClick = (event) => {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setOpenMenuId(null);
      }
    };
    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, []);

  const boardTitle = board?.title_display || 'Board';
  const permissions = board?.permissions ?? {};
  const canCreate = Boolean(permissions.can_create);
  const boardHeaderStyle = board?.header_image_url
    ? {
        backgroundImage: `linear-gradient(135deg, rgba(9, 9, 11, 0.78), rgba(24, 24, 27, 0.4)), url(${board.header_image_url})`,
        backgroundSize: 'cover',
        backgroundPosition: 'center',
      }
    : undefined;

  const sortedPosts = useMemo(() => posts, [posts]);

  const handleDelete = async (postId) => {
    const confirmed = window.confirm('이 게시글을 삭제하시겠습니까?');
    if (!confirmed) {
      return;
    }

    try {
      await boardApi.deletePost(postId);
      setOpenMenuId(null);
      if (selectedPost?.id === postId) {
        setSelectedPost(null);
      }
      await loadBoard();
    } catch (deleteError) {
      setError(deleteError.response?.data?.error || '게시글을 삭제하지 못했습니다.');
    }
  };

  const handleSavePost = async (formData, postId) => {
    setIsSaving(true);
    try {
      if (postId) {
        await boardApi.updatePost(postId, formData);
      } else {
        await boardApi.createPost(board.slug, formData);
      }
      setEditingPost(null);
      await loadBoard();
    } catch (saveError) {
      throw new Error(saveError.response?.data?.error || '게시글을 저장하지 못했습니다.');
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#f5f5f3]">
        <div className="flex items-center gap-3 rounded-full border border-zinc-200 bg-white px-5 py-3 text-sm text-zinc-600 shadow-sm">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-300 border-t-zinc-900" />
          게시판을 불러오는 중입니다.
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#f3f3ef] text-zinc-950">
      <div
        className="bg-gradient-to-br from-zinc-950 via-zinc-900 to-zinc-800 text-white shadow-[0_24px_80px_rgba(0,0,0,0.18)]"
        style={boardHeaderStyle}
      >
        <div className="mx-auto max-w-7xl px-5 py-6 md:px-8 md:py-8">
          <div className="flex flex-col gap-6 md:flex-row md:items-start md:justify-between">
            <div className="max-w-3xl">
              <button
                type="button"
                onClick={() => navigate('/')}
                className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs uppercase tracking-[0.25em] text-zinc-300 transition hover:border-white/20 hover:text-white"
              >
                <ArrowLeft size={14} />
                Home
              </button>
              <p className="mt-8 text-[11px] uppercase tracking-[0.45em] text-zinc-500">Board</p>
              <h1 className="mt-3 text-4xl font-semibold tracking-[-0.04em] md:text-6xl" style={{ fontFamily: 'Georgia, Times New Roman, serif' }}>
                {boardTitle}
              </h1>
              <p className="mt-4 max-w-2xl text-sm leading-7 text-zinc-300 md:text-base">
                {board?.description || '대시보드 관련 게시글을 시각적 타일 목록으로 빠르게 탐색할 수 있는 보드입니다.'}
              </p>
            </div>

            {canCreate && (
              <button
                type="button"
                onClick={() => setEditingPost({})}
                className="self-start rounded-full border border-emerald-300/20 bg-emerald-300/10 px-4 py-2 text-xs font-semibold uppercase tracking-[0.25em] text-emerald-200 transition hover:border-emerald-200/40 hover:bg-emerald-300/20 hover:text-white"
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

      <div className="mx-auto max-w-7xl px-5 pb-6 pt-8 md:px-8 md:pb-8">
        <div className="space-y-6">
          {error && (
            <div className="rounded-[22px] border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-600 shadow-sm">
              {error}
            </div>
          )}

          {board && sortedPosts.length === 0 && (
            <div className="rounded-[28px] border border-dashed border-zinc-300 bg-white/70 px-6 py-16 text-center shadow-sm">
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-zinc-950 text-white shadow-lg">
                <LayoutGrid size={24} />
              </div>
              <h2 className="mt-6 text-2xl font-semibold text-zinc-950">첫 게시글을 기다리는 중입니다</h2>
              <p className="mx-auto mt-3 max-w-xl text-sm leading-7 text-zinc-500">
                moderator 권한이 있는 사용자는 우측 상단의 버튼으로 글을 등록할 수 있습니다.
              </p>
            </div>
          )}

          {sortedPosts.length > 0 && (
            <div
              className="grid justify-start gap-5"
              style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 232px))' }}
            >
              {sortedPosts.map((post) => (
                <article
                  key={post.id}
                  className="group relative w-full overflow-hidden rounded-[28px] border border-black/5 bg-white shadow-[0_12px_36px_rgba(0,0,0,0.08)] transition hover:-translate-y-1 hover:shadow-[0_18px_48px_rgba(0,0,0,0.12)]"
                >
                  {(post.can_edit || post.can_delete) && (
                    <div className="absolute right-4 top-4 z-10" ref={openMenuId === post.id ? menuRef : null}>
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          setOpenMenuId((current) => current === post.id ? null : post.id);
                        }}
                        className="rounded-full border border-white/50 bg-white/85 p-2 text-zinc-600 opacity-0 shadow-sm backdrop-blur transition group-hover:opacity-100 hover:text-zinc-950"
                        aria-label="옵션"
                      >
                        <MoreVertical size={16} />
                      </button>
                      {openMenuId === post.id && (
                        <div className="absolute right-0 mt-2 min-w-[140px] overflow-hidden rounded-2xl border border-zinc-200 bg-white py-1.5 shadow-xl">
                          {post.can_edit && (
                            <button
                              type="button"
                              onClick={(event) => {
                                event.stopPropagation();
                                setOpenMenuId(null);
                                setEditingPost(post);
                              }}
                              className="flex w-full items-center gap-2 px-4 py-2.5 text-sm text-zinc-700 transition hover:bg-zinc-100"
                            >
                              <Pencil size={14} />
                              수정
                            </button>
                          )}
                          {post.can_delete && (
                            <button
                              type="button"
                              onClick={(event) => {
                                event.stopPropagation();
                                void handleDelete(post.id);
                              }}
                              className="flex w-full items-center gap-2 px-4 py-2.5 text-sm text-red-600 transition hover:bg-red-50"
                            >
                              <Trash2 size={14} />
                              삭제
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                  )}

                  <button
                    type="button"
                    onClick={() => setSelectedPost(post)}
                    className="flex h-full w-full flex-col text-left"
                  >
                    <div className="relative aspect-[1.08/1] overflow-hidden rounded-t-[28px] bg-zinc-100">
                      {post.preview_image_url ? (
                        <img
                          src={post.preview_image_url}
                          alt={post.title}
                          className="h-full w-full object-cover transition duration-500 group-hover:scale-[1.03]"
                        />
                      ) : (
                        <div className="flex h-full w-full items-center justify-center rounded-t-[28px] bg-gradient-to-br from-zinc-200 via-zinc-100 to-white text-zinc-400">
                          <LayoutGrid size={34} />
                        </div>
                      )}
                      <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 via-black/30 to-transparent px-4 pb-4 pt-14 text-white">
                        <h2 className="line-clamp-2 text-xl font-semibold tracking-[-0.03em]">{post.title}</h2>
                      </div>
                    </div>
                    <div className="flex flex-1 flex-col px-4 pb-3 pt-2.5">
                      <div className="flex items-center justify-between gap-3 text-[11px] text-zinc-400">
                        <span>{formatDate(post.updated_at)}</span>
                        <span>{post.image_count || 0} image</span>
                      </div>
                    </div>
                  </button>
                </article>
              ))}
            </div>
          )}
        </div>
      </div>

      {selectedPost && (
        <ReadModal
          post={selectedPost}
          boardTitle={boardTitle}
          onClose={() => setSelectedPost(null)}
        />
      )}

      {editingPost !== null && board && (
        <EditorModal
          board={board}
          post={editingPost.id ? editingPost : null}
          isSaving={isSaving}
          onClose={() => setEditingPost(null)}
          onSave={handleSavePost}
        />
      )}
    </div>
  );
};

export default BoardPage;
