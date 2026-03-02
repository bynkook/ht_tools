import React, { useState, memo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism'; // 밝은 테마 추천
import { User, Bot, Copy, Check } from 'lucide-react';

// 코드 블록을 별도 컴포넌트로 분리하여 스트리밍 중 Copy 버튼 상태 초기화 방지
const CodeBlock = memo(({ inline, className, children, ...props }) => {
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
      <div className="rounded-lg overflow-hidden my-3 border border-gray-200 shadow-sm">
        <div className="bg-gray-50 px-3 py-1 text-xs text-gray-500 font-mono border-b border-gray-200 flex justify-between items-center">
          <span>{match[1]}</span>
          <button
            onClick={copyToClipboard}
            className="flex items-center gap-1.5 hover:text-gray-800 transition-colors"
          >
            {copied ? <Check size={14} /> : <Copy size={14} />}
            Copy
          </button>
        </div>
        <SyntaxHighlighter
          {...props}
          style={oneLight}
          language={match[1]}
          PreTag="div"
          customStyle={{ margin: 0, padding: '1rem', background: '#ffffff', fontSize: '12px' }}
        >
          {codeContent}
        </SyntaxHighlighter>
      </div>
    );
  }
  return (
    <code className="bg-gray-100 text-pink-600 px-1.5 py-0.5 rounded text-xs font-mono" {...props}>
      {children}
    </code>
  );
});

const ChatBubble = memo(({ message, isStreaming }) => {
  const isUser = message.role === 'user';

  // System 메시지 (메모리 커맨드 결과 표시용)
  if (message.role === 'system') {
    return (
      <div className="flex justify-center animate-fade-in my-3">
        <div className="text-gray-400 text-xs max-w-[80%] text-center whitespace-pre-wrap">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className={`flex w-full ${isUser ? 'justify-end' : 'justify-start'} animate-fade-in`}>
      <div className={`flex max-w-[90%] md:max-w-[85%] gap-4 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
        
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
                  code(props) {
                    return <CodeBlock {...props} />;
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