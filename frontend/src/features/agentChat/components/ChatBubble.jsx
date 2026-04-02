import React, { useState, memo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism'; // 밝은 테마 추천
import { User, Bot, Copy, Check } from 'lucide-react';

// 코드 블록을 별도 컴포넌트로 분리하여 스트리밍 중 Copy 버튼 상태 초기화 방지
// react-markdown v9: pre 컴포넌트의 renderer로 사용 (블록 코드 전용)
const CodeBlock = memo(({ children }) => {
  const [copied, setCopied] = useState(false);

  // pre의 children으로 전달된 <code> React element에서 언어 및 코드 내용 추출
  const codeChild = React.Children.toArray(children).find(React.isValidElement);
  const className = codeChild?.props?.className || '';
  const codeContent = String(codeChild?.props?.children || '').replace(/\n$/, '');
  const match = /language-(\w+)/.exec(className);
  const language = match ? match[1] : 'text';

  const copyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(codeContent);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // fallback: navigator.clipboard 미지원 환경(HTTP via IP) 대응
      // 향후 서비스가 HTTPS로 전환되면 fallback 블록 전체를 제거한다
      try {
        const ta = document.createElement('textarea');
        ta.value = codeContent;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        // eslint-disable-next-line deprecation/deprecation -- navigator.clipboard 미지원 환경(HTTP via IP) fallback
        document.execCommand('copy');
        document.body.removeChild(ta);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      } catch (err) {
        console.error('클립보드 복사 실패:', err);
      }
    }
  };

  return (
    <div className="rounded-lg overflow-hidden my-3 border border-gray-200 shadow-sm">
      <div className="bg-gray-50 px-3 py-1 text-xs text-gray-500 font-mono border-b border-gray-200 flex justify-between items-center">
        <span>{match ? language : ''}</span>
        <button
          onClick={copyToClipboard}
          className="flex items-center gap-1.5 hover:text-gray-800 transition-colors"
        >
          {copied ? <Check size={14} /> : <Copy size={14} />}
          Copy
        </button>
      </div>
      <SyntaxHighlighter
        style={oneLight}
        language={language}
        PreTag="div"
        customStyle={{ margin: 0, padding: '1rem', background: '#ffffff', fontSize: '12px' }}
      >
        {codeContent}
      </SyntaxHighlighter>
    </div>
  );
});

const ChatBubble = memo(({ message, isStreaming }) => {
  const isUser = message.role === 'user';

  // System 메시지 (메모리 커맨드 결과 표시용)
  if (message.role === 'system') {
    return (
      <div className="flex justify-center animate-fade-in my-3">
        <div className="text-gray-400 text-xs max-w-[85%] text-center whitespace-pre-wrap">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className={`flex w-full ${isUser ? 'justify-end' : 'justify-start'} animate-fade-in`}>
      <div className={`flex max-w-[85%] gap-4 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
        
        {/* Avatar */}
        <div className={`
          flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center shadow-sm mt-1
          ${isUser ? 'bg-[var(--user-bubble-bg)]' : 'bg-white border border-gray-200'}
        `}>
          {isUser ? <User size={18} className="text-[var(--user-bubble-text)]" /> : <Bot size={18} className="text-[var(--accent-color)]" />}
        </div>

        {/* Content */}
        <div className={`
          relative px-5 py-2 rounded-2xl shadow-sm text-[var(--text-primary)] overflow-hidden
          ${isUser 
            ? 'bg-[var(--user-bubble-bg)] text-[var(--user-bubble-text)] rounded-tr-sm' 
            : 'bg-white border border-[var(--border-color)] rounded-tl-sm'}
        `}>
          {isUser ? (
            <div className="whitespace-pre-wrap leading-relaxed text-xs">
              {message.content}
            </div>
          ) : (
            <div className={`markdown-body text-xs ${isStreaming ? 'cursor-blink' : ''}`}>
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  pre({ children }) {
                    return <CodeBlock>{children}</CodeBlock>;
                  },
                  code({ children, className, node, ...props }) {
                    // language- className이 있으면 블록 코드의 내부 <code> → className 보존하여 pre로 전달
                    // node는 react-markdown AST 객체 — DOM 요소에 spread 금지
                    if (className?.startsWith('language-')) {
                      return <code className={className} {...props}>{children}</code>;
                    }
                    // 인라인 코드
                    return (
                      <code className="bg-gray-100 text-pink-600 px-1.5 py-0.5 rounded text-xs font-mono" {...props}>
                        {children}
                      </code>
                    );
                  }
                }}
              >
                {message.content || ""}
              </ReactMarkdown>
            </div>
          )}
        </div>
      </div>
    </div>
  );
});

export default ChatBubble;