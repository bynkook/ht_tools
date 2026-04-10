/**
 * Persist policy per system message phase.
 * - 'always'    : always saved to DB (backend-driven events, conversation flow)
 * - 'test_only' : saved only in test mode (command results, memory ops)
 * - 'never'     : UI-only, never saved (transient errors, model-selection warnings)
 *
 * Adding a new command phase: add one line here. No other changes needed.
 *
 * IMPORTANT: Unknown phases fall back to 'always' (saved by default).
 * If a new phase must NOT be saved, explicitly add it with 'never' or 'test_only'.
 */
const PHASE_PERSIST_POLICY = {
  runtime: 'always',
  conversation: 'always',
  persistence: 'always',
  command: 'test_only',
  command_error: 'never',
  memory: 'test_only',
};

/**
 * Resolve whether a system message should be persisted to DB.
 *
 * @param {string} phase - The message phase (key in PHASE_PERSIST_POLICY)
 * @param {boolean|undefined} isTestMode - Whether the current session is in test mode.
 *   If undefined (runtimeConfig not yet loaded), 'test_only' phases return false (safe default).
 * @returns {boolean}
 */
export const resolvePersist = (phase, isTestMode) => {
  const policy = PHASE_PERSIST_POLICY[phase] ?? 'always';
  if (policy === 'never') return false;
  if (policy === 'test_only') return isTestMode === true;
  return true; // 'always'
};

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