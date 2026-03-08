import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import { ArrowLeft, BookOpen } from 'lucide-react';

const HelpPage = () => {
  const navigate = useNavigate();
  const [markdownContent, setMarkdownContent] = useState('');
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const defaultHelpContent = `# FabriX 도움말 및 가이드

FabriX에 오신 것을 환영합니다! 이 가이드는 핵심 기능을 안내합니다.

## 🤖 FabriX Chat

FabriX 에서 제공하는 LLM 모델과 자유롭게 대화하며 아이디어를 발전시키세요.

- **모델 선택 (Model Selection)**: 작업 목적에 맞는 다양한 모델을 선택할 수 있습니다.
- **컨텍스트 기억 (Context Memory)**: 현재 세션의 대화 맥락을 기억하여 자연스러운 이어가기가 가능합니다.
  - 질문 시점 이전 5턴 대화를 기억하여 대화를 이어갑니다.
  - /memory [ list | save | load | delete | clear ] 로 중요 시점의 대화 전체를 저장하세요.  이 기능은 어떤 시점 이후 대화를 수정하고 싶을때 되돌아 가는 기능입니다.
    
        /memory list    : 저장된 스냅샷 목록 출력
        /memory save    : 현재 세션 대화 전체 저장
        /memory load    : 저장된 스냅샷 불러오기
        /memory delete  : 저장된 스냅샷 삭제
        /memory clear   : 모든 스냅샷 삭제

            (사용 예) /memory save 2월 주간공정회의록 요약

            --> "2월 주간공정회의록 요약" 스냅샷이 저장됩니다.    

## 🧠 FabriX Agent Chat

FabriX에 미리 설계된 에이전트와 협업하세요.

- **특정 주제 대화**: 주제와 관련 있는 대화만 가능합니다.

    (주의) 현재 Samsung LLM 모델에 기반한 Agent 들은 모두 테넌트에서 off 상태입니다.

## 🖼️ Image Inspector

이미지나 기술 도면을 비교하고 분석합니다.

- **차이점 강조 (Side-by-Side Comparison)**: 두 이미지를 동시에 나란히 띄워놓고 비교합니다.
- **오버레이 (Difference Highlighting)**: 두 이미지 간의 차이점을 자동으로 감지하고 강조 표시합니다.
- **ORB 모드**: 사진이나 질감이 있는 일반 이미지 비교에 적합합니다.
- **CAD 도면용 모드**: PDF 도면이나 선 구조가 복잡한 기술 도면 비교에 적합합니다. 내부적으로 선분, 교차점, 코너 정보를 함께 사용해 정렬합니다.
PDF내부의 선(line) 요소 두께를 일괄 변경 가능합니다.


## 📊 Data Explorer

데이터셋을 대화형으로 시각화하고 분석하여 인사이트를 도출하세요.

- **데이터 업로드 (Data Upload)**: CSV 파일을 업로드하여 즉시 분석을 시작합니다.
- **대용량 데이터셋 로드(Quick Select Dataset)**: 서버에 미리 저장된 데이터를 빠르게 불러옵니다.
- **대화형 차트 (Interactive Charts)**: 드래그 앤 드롭 인터페이스를 사용하여 다양한 차트(막대, 선, 산점도 등)를 생성합니다.
- **사용자 프리셋 (Saved Preset)**: 사용자의 차트를 저장하면 다음 작업시 빠르게 사용할 수 있습니다.
    - 모든 사용자용, 개인용 구분하여 저장
    - 삭제는 처음 등록자만 가능
- **(429) Too Many Requests 경고**: 일정 시간 내 요청이 허용 한도를 초과하면 발생합니다.
    - 컬럼 갯수가 많고 대용량 데이터의 Data 탭에서 모든 컬럼을 로드하여 조회할때 주로 발생
    - 따라서, 대용량 데이터의 경우는 반드시 컬럼 선택 메뉴에서 필요한 컬럼만 선택해서 로드하세요

---

### 🔒 보안 및 개인정보 보호 (Security & Privacy)

- **데이터 격리 (Data Isolation)**: 모든 데이터는 로컬에서 처리되며 외부로 공유되지 않습니다.
- **세션 관리 (Session Management)**: 대화 기록은 안전하게 저장되며 언제든지 삭제할 수 있습니다.
- **프로필 설정 (Profile Settings)**: User Profile 메뉴에서 비밀번호와 복구용 PIN 번호를 안전하게 관리하세요.

    (PIN 생성은 Profile 메뉴에서도 가능합니다)

---

*추가적인 지원이 필요하시면 시스템 관리자에게 문의해 주세요.*`;

    setMarkdownContent(defaultHelpContent);
    setIsLoading(false);
  }, []);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-[var(--bg-primary)] flex items-center justify-center">
        <div className="w-8 h-8 border-4 border-[var(--accent-color)] border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[var(--bg-primary)] p-6 flex justify-center items-start pt-10 pb-20">
      <div className="w-full max-w-4xl bg-[var(--bg-secondary)] rounded-2xl shadow-xl border border-[var(--border-color)] overflow-hidden">
        
        {/* Header */}
        <div className="px-8 py-6 border-b border-[var(--border-color)] flex items-center gap-4">
          <button 
            onClick={() => navigate('/')}
            className="p-2 hover:bg-[var(--bg-tertiary)] rounded-lg text-[var(--text-secondary)] transition-colors"
          >
            <ArrowLeft size={24} />
          </button>
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-50 text-blue-600 rounded-lg">
              <BookOpen size={24} />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-[var(--text-primary)]">도움말 센터</h1>
              <p className="text-sm text-[var(--text-secondary)]">문서 및 가이드</p>
            </div>
          </div>
        </div>

        {/* Content */}
        <div className="p-8">
          <div className="prose prose-slate max-w-none prose-headings:text-[var(--text-primary)] prose-p:text-[var(--text-secondary)] prose-a:text-[var(--accent-color)] prose-strong:text-[var(--text-primary)]">
            <ReactMarkdown
              components={{
                p: ({node, ...props}) => <p className="mb-4 text-[var(--text-secondary)]" {...props} />,
                h1: ({node, ...props}) => <h1 className="mb-6 text-3xl font-bold text-[var(--text-primary)]" {...props} />,
                h2: ({node, ...props}) => <h2 className="mt-8 mb-4 text-2xl font-semibold text-[var(--text-primary)]" {...props} />,
                h3: ({node, ...props}) => <h3 className="mt-6 mb-3 text-xl font-medium text-[var(--text-primary)]" {...props} />,
                ul: ({node, ...props}) => <ul className="mb-4 space-y-2 list-disc pl-6 text-[var(--text-secondary)] [&_ul]:mt-2 [&_ul]:mb-2" {...props} />,
                li: ({node, ...props}) => <li className="text-[var(--text-secondary)]" {...props} />,
                hr: ({node, ...props}) => <hr className="my-8 border-[var(--border-color)]" {...props} />,
              }}
            >
              {markdownContent}
            </ReactMarkdown>
          </div>
        </div>
      </div>
    </div>
  );
};

export default HelpPage;