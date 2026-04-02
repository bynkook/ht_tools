import React, { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import JobQueueTable from './components/JobQueueTable';
import FileUploadArea from './components/FileUploadArea';
import CategoryManager from './components/CategoryManager';

export default function DocUploaderPage() {
  const navigate = useNavigate();
  const [selectedCategory, setSelectedCategory] = useState(null);
  // 업로드 완료 시 JobQueueTable과 CategoryManager를 강제 새로고침
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  const handleUploadComplete = useCallback(() => {
    setRefreshTrigger((n) => n + 1);
  }, []);

  const handleCategorySelect = (name) => {
    setSelectedCategory(name === selectedCategory ? null : name);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-white to-violet-50 flex flex-col">
      {/* 상단 헤더 */}
      <div className="bg-white border-b border-gray-200 px-4 py-3 flex items-center gap-3 shadow-sm">
        <button
          onClick={() => navigate('/')}
          className="text-gray-400 hover:text-gray-600 transition-colors"
          title="홈으로"
        >
          <ArrowLeft size={18} />
        </button>
        <div>
          <h1 className="text-base font-bold text-gray-900">Doc Uploader</h1>
          <p className="text-xs text-gray-500">
            문서를 업로드하면 자동으로 Markdown으로 변환되어 선택한 카테고리의 RAG 검색에 활용됩니다.
          </p>
        </div>
      </div>

      {/* 본문: 사이드바(카테고리) + 메인(큐 + 업로드) */}
      <div className="flex flex-1 gap-4 p-4 overflow-hidden">
        {/* 왼쪽: 카테고리 패널 */}
        <div className="w-56 shrink-0 flex flex-col" style={{ minHeight: 0 }}>
          <CategoryManager
            selectedCategory={selectedCategory}
            onSelect={handleCategorySelect}
            refreshTrigger={refreshTrigger}
          />
        </div>

        {/* 오른쪽: 작업 현황 + 업로드 */}
        <div className="flex-1 flex flex-col gap-4 min-w-0">
          {/* 작업 대기열 */}
          <JobQueueTable refreshTrigger={refreshTrigger} />

          {/* 파일 업로드 영역 */}
          <FileUploadArea
            selectedCategory={selectedCategory}
            onUploadComplete={handleUploadComplete}
          />
        </div>
      </div>
    </div>
  );
}
