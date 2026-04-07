import React from 'react';

import { getSystemMessageLabel, getSystemMessageMetaLine, getSystemMessageTitle } from '../utils/systemLogFormatter';

const SystemMessageMeta = ({ message }) => {
  const metadata = message?.metadata || {};
  const label = getSystemMessageLabel(metadata);
  const title = getSystemMessageTitle(message);
  const metaLine = getSystemMessageMetaLine(message);

  return (
    <div className="flex flex-col gap-1 mb-3">
      <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.18em] text-[var(--text-secondary)]">
        <span className="font-semibold">{label}</span>
        {metadata.repeatCount > 1 && (
          <span className="rounded-full bg-[var(--bg-tertiary)] px-2 py-0.5 normal-case tracking-normal text-[10px]">
            repeated {metadata.repeatCount}x
          </span>
        )}
      </div>
      {title && <div className="text-xs font-semibold text-[var(--text-primary)]">{title}</div>}
      {metaLine && <div className="text-[10px] text-[var(--text-secondary)]">{metaLine}</div>}
    </div>
  );
};

export default SystemMessageMeta;

