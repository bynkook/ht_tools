import React, { useState, memo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneLight, oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { User, Bot, Copy, Check } from 'lucide-react';

// 코드 블록을 별도 컴포넌트로 분리하여 스트리밍 중 Copy 버튼 상태 초기화 방지
// react-markdown v9: pre 컴포넌트의 renderer로 사용 (블록 코드 전용)
const CodeBlock = memo(({ children, theme }) => {
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
    <div className="relative my-4 rounded-lg overflow-hidden border border-[var(--border-color)]">
      <div className="flex items-center justify-between px-4 py-2 bg-[var(--bg-secondary)] text-[var(--text-secondary)] text-xs">
        <span className="font-mono">{match ? language : ''}</span>
        <button
          onClick={copyToClipboard}
          className="flex items-center gap-1.5 hover:text-[var(--text-primary)] transition-colors"
        >
          {copied ? <Check size={14} /> : <Copy size={14} />}
          Copy
        </button>
      </div>
      <SyntaxHighlighter
        style={theme === 'dark' ? oneDark : oneLight}
        language={language}
        PreTag="div"
        customStyle={{
          margin: 0,
          padding: '1rem',
          backgroundColor: theme === 'dark' ? 'var(--bg-tertiary)' : 'var(--bg-secondary)',
          fontSize: '0.725rem',
        }}
      >
        {codeContent}
      </SyntaxHighlighter>
    </div>
  );
});

/**
 * Chat bubble component for Model Chat (FabriX Chat)
 * Renders user and assistant messages with markdown support
 */
const ChatBubble = memo(({ message, isStreaming }) => {
  const isUser = message.role === 'user';
  const theme = document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';

  // System 메시지 (메모리 커맨드 결과 표시용)
  if (message.role === 'system') {
    return (
      <div className="flex justify-center animate-fade-in-up my-3">
        <div className="text-gray-400 text-xs max-w-[80%] text-center whitespace-pre-wrap">
          {message.content}
        </div>
      </div>
    );
  }

  const renderMarkdown = (content) => {
    return (
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          pre({ children }) {
            return <CodeBlock theme={theme}>{children}</CodeBlock>;
          },
          code({ children, className, node, ...props }) {
            // language- className이 있으면 블록 코드의 내부 <code> → className 보존하여 pre로 전달
            // node는 react-markdown AST 객체 — DOM 요소에 spread 금지
            if (className?.startsWith('language-')) {
              return <code className={className} {...props}>{children}</code>;
            }
            // 인라인 코드
            return (
              <code className="bg-[var(--bg-tertiary)] text-[var(--accent-color)] px-1.5 py-0.5 rounded" {...props}>
                {children}
              </code>
            );
          },
          table({ children }) {
            return (
              <div className="my-4 overflow-x-auto rounded-lg border border-[var(--border-color)]">
                <table className="min-w-full divide-y divide-[var(--border-color)]">{children}</table>
              </div>
            );
          },
          th({ children }) {
            return (
              <th className="px-4 py-2 bg-[var(--bg-secondary)] text-left text-xs font-semibold text-[var(--text-primary)]">
                {children}
              </th>
            );
          },
          td({ children }) {
            return <td className="px-4 py-2 text-xs border-t border-[var(--border-color)]">{children}</td>;
          },
          p({ children }) {
            return <p className="mb-3 last:mb-0 leading-relaxed">{children}</p>;
          },
          ul({ children }) {
            return <ul className="list-disc list-inside mb-3 space-y-1">{children}</ul>;
          },
          ol({ children }) {
            return <ol className="list-decimal list-inside mb-3 space-y-1">{children}</ol>;
          },
          h1({ children }) {
            return <h1 className="text-xs font-semibold mb-3 text-[var(--text-primary)]">{children}</h1>;
          },
          h2({ children }) {
            return <h2 className="text-xs font-semibold mb-3 text-[var(--text-primary)]">{children}</h2>;
          },
          h3({ children }) {
            return <h3 className="text-xs font-semibold mb-2 text-[var(--text-primary)]">{children}</h3>;
          },
          a({ children, href, ...props }) {
            return (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-500 underline hover:text-blue-600"
                {...props}
              >
                {children}
              </a>
            );
          },
        }}
      >
        {content || ''}
      </ReactMarkdown>
    );
  };

  if (isUser) {
    return (
      <div className="flex justify-end items-start gap-3 animate-fade-in-up">
        <div className="max-w-[80%] bg-[var(--user-bubble-bg)] text-[var(--user-bubble-text)] px-4 py-2 rounded-2xl rounded-tr-sm shadow-sm">
          <div className="whitespace-pre-wrap break-words text-xs">{message.content}</div>
        </div>
        <div className="flex-shrink-0 w-9 h-9 rounded-full bg-[var(--user-bubble-bg)] flex items-center justify-center">
          <User size={18} className="text-[var(--user-bubble-text)]" />
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-start gap-3 animate-fade-in-up">
      <div className="flex-shrink-0 w-9 h-9 rounded-full bg-gradient-to-tr from-cyan-500 to-blue-500 flex items-center justify-center shadow-md">
        <Bot size={18} className="text-white" />
      </div>
      <div className="max-w-[85%] flex-1">
        <div className="max-w-none text-xs text-[var(--text-primary)] break-words">
          {renderMarkdown(message.content)}
          {isStreaming && (
            <span className="inline-flex ml-1">
              <span className="w-2 h-2 bg-cyan-500 rounded-full animate-pulse" />
            </span>
          )}
        </div>
      </div>
    </div>
  );
});

export default ChatBubble;
