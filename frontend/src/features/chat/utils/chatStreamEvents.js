import { normalizeSseEvent } from './sseEventNormalizer';
import { buildSystemMessage } from './systemMessageState';

const FILTER_PASS_RESULT_CODE = 'FR-200';
const FILTER_PASS_MARKERS = ['passed', 'allowed'];

const isAllowedFilterMessage = (message) => FILTER_PASS_MARKERS.some((marker) => message.includes(marker));

export const buildRuntimeSystemMessage = (content, metadata = {}) => buildSystemMessage(content, {
  phase: 'runtime',
  persist: true, // runtime phase is always persisted (see PHASE_PERSIST_POLICY in systemMessageState.js)
  ...metadata,
});

export const interpretChatStreamEvent = (parsed) => {
  const normalizedEvent = normalizeSseEvent(parsed);
  if (normalizedEvent.kind !== 'upstream') {
    return normalizedEvent;
  }

  if (parsed.error) {
    return {
      kind: 'system_log',
      message: buildRuntimeSystemMessage(`⚠️ API Error: ${parsed.error}`, {
        level: 'error',
        title: 'Runtime error',
      }),
    };
  }

  const filterBlockReason = parsed.filter_block_reason ?? parsed.filterBlockReason;
  if (filterBlockReason) {
    const resultCode = filterBlockReason.result_code || filterBlockReason.resultCode || '';
    const message = String(filterBlockReason.message || '').toLowerCase();
    const isFilterPassed = resultCode === FILTER_PASS_RESULT_CODE || isAllowedFilterMessage(message);

    if (!isFilterPassed) {
      const blockReason = filterBlockReason.ko || filterBlockReason.en || filterBlockReason.message;
      if (blockReason) {
        return {
          kind: 'system_log',
          message: buildRuntimeSystemMessage(`⚠️ 응답이 필터링되었습니다: ${blockReason}`, {
            level: 'warn',
            title: 'Filtered response',
          }),
        };
      }
    }
  }

  const eventStatus = parsed.event_status ?? parsed.eventStatus;
  if (eventStatus === 'CHUNK') {
    const content = parsed.content;
    if (content !== null && content !== undefined) {
      const contentStr = String(content);
      if (contentStr) {
        return {
          kind: 'assistant_delta',
          content: contentStr,
        };
      }
    }
  }

  return { kind: 'ignore' };
};

export const removeEmptyAssistantPlaceholder = (messages) => {
  if (messages.length === 0) {
    return messages;
  }

  const nextMessages = [...messages];
  const lastAssistantIndex = nextMessages.map((message) => message.role).lastIndexOf('assistant');
  if (lastAssistantIndex >= 0 && !nextMessages[lastAssistantIndex].content) {
    nextMessages.splice(lastAssistantIndex, 1);
  }
  return nextMessages;
};
