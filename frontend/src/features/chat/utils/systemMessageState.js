export const buildSystemMetadata = (metadata = {}) => ({
  kind: 'system_log',
  level: 'info',
  channel: 'system',
  title: null,
  phase: 'runtime',
  provider: null,
  providerId: null,
  providerDisplayName: null,
  tool: null,
  selectionReason: null,
  selectionRank: null,
  candidateSummary: null,
  partialFailure: null,
  requestId: null,
  fingerprint: null,
  timestamp: null,
  repeatCount: 1,
  suppressedCount: 0,
  persist: true,
  raw: null,
  rawSuppressed: false,
  rawSuppressedCount: 0,
  ...metadata,
});

export const buildSystemMessage = (content, metadata = {}) => ({
  role: 'system',
  content,
  metadata: buildSystemMetadata(metadata),
});

export const appendMessageBeforeAssistantPlaceholder = (messages, message) => {
  const next = [...messages];
  const last = next[next.length - 1];
  if (last?.role === 'assistant' && !last.content) {
    next.splice(next.length - 1, 0, message);
    return next;
  }
  next.push(message);
  return next;
};

export const getPendingTurnSystemMessages = (messages) => {
  const lastAssistantIndex = messages.map((message) => message.role).lastIndexOf('assistant');
  if (lastAssistantIndex <= 0) {
    return [];
  }

  const pendingMessages = [];
  for (let index = lastAssistantIndex - 1; index >= 0; index -= 1) {
    const currentMessage = messages[index];
    if (currentMessage?.role !== 'system') {
      break;
    }
    pendingMessages.unshift(currentMessage);
  }
  return pendingMessages;
};