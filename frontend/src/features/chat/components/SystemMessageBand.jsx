import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import SystemMessageMeta from './SystemMessageMeta';
import SystemMessageRaw from './SystemMessageRaw';

const SystemMessageBand = ({ message }) => {
  const metadata = message?.metadata || {};

  return (
    <div className="animate-fade-in-up">
      <div className="border-y border-[var(--border-color)] bg-[var(--bg-secondary)]/55 px-5 py-2.5">
        <SystemMessageMeta message={message} />
        <div className="max-w-none text-xs leading-relaxed text-[var(--text-primary)]">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              table({ children }) {
                return (
                  <div className="my-2 overflow-x-auto rounded-lg border border-[var(--border-color)]">
                    <table className="min-w-full divide-y divide-[var(--border-color)]">{children}</table>
                  </div>
                );
              },
              th({ children }) {
                return (
                  <th className="px-3 py-1.5 bg-[var(--bg-tertiary)] text-left text-xs font-semibold text-[var(--text-primary)]">
                    {children}
                  </th>
                );
              },
              td({ children }) {
                return <td className="px-3 py-1.5 text-xs border-t border-[var(--border-color)]">{children}</td>;
              },
              pre({ children }) {
                return (
                  <pre className="my-2 overflow-x-auto rounded-lg bg-[var(--bg-tertiary)] px-3 py-2 text-[11px]">
                    {children}
                  </pre>
                );
              },
              code({ children }) {
                return (
                  <code className="rounded bg-[var(--bg-tertiary)] px-1.5 py-0.5 text-[11px]">
                    {children}
                  </code>
                );
              },
              p({ children }) {
                return <p className="mb-2.5 last:mb-0">{children}</p>;
              },
            }}
          >
            {message?.content || ''}
          </ReactMarkdown>
        </div>
        <SystemMessageRaw raw={metadata.raw} />
      </div>
    </div>
  );
};

export default SystemMessageBand;

