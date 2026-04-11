export const getSystemMessageLabel = (metadata = {}) => {
  const level = (metadata.level || '').toLowerCase();
  if (level === 'error') return 'ERROR';
  if (level === 'warn') return 'WARNING';
  const channel = (metadata.channel || '').toLowerCase();
  if (channel === 'mcp_test') return 'MCP-TEST';
  if (channel === 'mcp') return 'MCP';
  if (metadata.kind === 'system_log') return 'SYSTEM';
  return 'SYSTEM';
};

export const getSystemMessageTitle = (message) => {
  const metadata = message?.metadata || {};
  return metadata.title || null;
};

export const getSystemMessageMetaLine = (message) => {
  const metadata = message?.metadata || {};
  const providerLabel = metadata.providerDisplayName || metadata.providerId || metadata.provider;
  const candidateCount = Array.isArray(metadata.candidateSummary) ? metadata.candidateSummary.length : 0;
  const parts = [
    metadata.phase,
    providerLabel,
    metadata.tool,
    metadata.selectionRank > 1 ? `rank ${metadata.selectionRank}` : null,
    candidateCount > 1 ? `candidates ${candidateCount}` : null,
    metadata.partialFailure ? 'partial failure' : null,
    metadata.requestId,
    metadata.suppressedCount > 0 ? `suppressed ${metadata.suppressedCount}` : null,
    metadata.rawSuppressed ? 'raw suppressed' : null,
  ].filter(Boolean);
  return parts.join(' · ');
};