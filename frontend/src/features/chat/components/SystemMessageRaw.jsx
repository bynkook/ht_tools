import React, { useState } from 'react';

const SystemMessageRaw = ({ raw }) => {
  const [open, setOpen] = useState(false);

  if (!raw) {
    return null;
  }

  const rawText = typeof raw === 'string' ? raw : JSON.stringify(raw, null, 2);

  return (
    <div className="mt-2 border-t border-[var(--border-color)] pt-2">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="text-[10px] font-medium uppercase tracking-[0.14em] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
      >
        {open ? 'Hide raw' : 'Show raw'}
      </button>
      {open && (
        <pre className="mt-3 overflow-x-auto rounded-lg bg-[var(--bg-secondary)] px-3 py-3 text-[11px] text-[var(--text-secondary)] whitespace-pre-wrap break-all">
          {rawText}
        </pre>
      )}
    </div>
  );
};

export default SystemMessageRaw;

