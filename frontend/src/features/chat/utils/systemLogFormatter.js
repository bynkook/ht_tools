export const getSystemMessageLabel = (metadata = {}) => {
  const level = (metadata.level || '').toLowerCase();
  if (level === 'error') return 'ERROR';
  if (level === 'warn') return 'WARNING';
  if ((metadata.channel || '').toLowerCase() === 'mcp_test') return 'MCP-TEST';
  if (metadata.kind === 'system_log') return 'SYSTEM';
  return 'SYSTEM';
};

export const getSystemMessageTitle = (message) => {
  const metadata = message?.metadata || {};
  return metadata.title || null;
};

export const getSystemMessageMetaLine = (message) => {
  const metadata = message?.metadata || {};
  const parts = [
    metadata.phase,
    metadata.provider,
    metadata.tool,
    metadata.requestId,
    metadata.suppressedCount > 0 ? `suppressed ${metadata.suppressedCount}` : null,
    metadata.rawSuppressed ? 'raw suppressed' : null,
  ].filter(Boolean);
  return parts.join(' · ');
};

