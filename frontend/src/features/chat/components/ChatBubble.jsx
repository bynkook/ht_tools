import React, { useState, memo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneLight, oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { User, Bot, Copy, Check } from 'lucide-react';

// 코드 블록을 별도 컴포넌트로 분리하여 스트리밍 중 Copy 버튼 상태 초기화 방지
const CodeBlock = memo(({ inline, className, children, theme, ...props }) => {
  const [copied, setCopied] = useState(false);
  const match = /language-(\w+)/.exec(className || '');
  const codeContent = String(children).replace(/\n$/, '');

  const copyToClipboard = async () => {
    await navigator.clipboard.writeText(codeContent);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (!inline && match) {
    return (
      <div className="relative my-4 rounded-lg overflow-hidden border border-[var(--border-color)]">
        <div className="flex items-center justify-between px-4 py-2 bg-[var(--bg-secondary)] text-[var(--text-secondary)] text-xs">
          <span className="font-mono">{match[1]}</span>
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
          language={match[1]}
          PreTag="div"
          customStyle={{
            margin: 0,
            padding: '1rem',
            backgroundColor: theme === 'dark' ? 'var(--bg-tertiary)' : 'var(--bg-secondary)',
            fontSize: '0.725rem',
          }}
          {...props}
        >
          {codeContent}
        </SyntaxHighlighter>
      </div>
    );
  }
  return (
    <code className="bg-[var(--bg-tertiary)] text-[var(--accent-color)] px-1.5 py-0.5 rounded" {...props}>
      {children}
    </code>
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
          code(props) {
            return <CodeBlock theme={theme} {...props} />;
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
