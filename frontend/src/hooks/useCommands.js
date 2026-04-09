import { useState, useCallback, useRef } from 'react';

import { memoryApi, modelChatApi } from '../api/djangoApi';
import { mcpCommandApi, mcpRagApi } from '../api/fastapiApi';
import { buildSystemMessage } from '../features/chat/utils/systemMessageState';

const DEFAULT_MCP_PROVIDER_ID = 'internal_docs';

// =============================================================================
// @<파일명> mention 파싱 유틸리티 (ChatPage에서 import하여 사용)
// =============================================================================

/**
 * 입력 텍스트에서 @<파일명> 멘션 목록을 파싱한다.
 * 문법:
 *   @파일명.md               — 공백 없는 단순 파일명
 *   @"파일명 공백 있음.md"   — 공백/특수문자 포함 시 큰따옴표 감싸기
 *   @카테고리/파일명.md      — 카테고리 경로 포함
 * @param {string} text
 * @returns {string[]} 파싱된 파일명 목록 (따옴표 제거 후 trim)
 */
export function parseAtMentions(text) {
  const mentions = [];
  const regex = /@"([^"]+)"|@([^\s"@]+)/g;
  let match;
  while ((match = regex.exec(text)) !== null) {
    const raw = (match[1] ?? match[2]).trim();
    if (raw) {
      mentions.push(raw);
    }
  }
  return mentions;
}

/**
 * 텍스트에서 @<파일명> 멘션을 제거하고 정리된 쿼리를 반환한다.
 * @param {string} text
 * @returns {string}
 */
export function stripAtMentions(text) {
  return text.replace(/@"[^"]+"|@[^\s"@]+/g, '').replace(/\s{2,}/g, ' ').trim();
}

/**
 * @mention 파일 목록을 rag-search API로 해석하여 관련 스니펫을 수집한다.
 * BM25 건너뜀 — 지정 파일만 semantic block 스니펫 추출.
 * @param {string[]} mentions  parseAtMentions() 결과
 * @param {string} cleanQuery  stripAtMentions() 결과 (LLM에 전달할 실제 질문)
 * @param {string|null} activeCategory  현재 세션 카테고리
 * @param {string} providerId  현재 MCP provider
 * @returns {Promise<{ resolved: Array<{filename, system_prompt, snippets}>, errors: string[] }>}
 */
export async function resolveAtMentions(mentions, cleanQuery, activeCategory, providerId = DEFAULT_MCP_PROVIDER_ID) {
  const results = await Promise.allSettled(
    mentions.map(async (raw) => {
      let filenameFilter = raw;
      let category;
      const slashIndex = raw.indexOf('/');
      if (slashIndex > 0) {
        category = raw.slice(0, slashIndex);
        filenameFilter = raw.slice(slashIndex + 1);
      } else if (activeCategory) {
        category = activeCategory;
      }
      const response = await mcpRagApi.search({
        query: cleanQuery || raw,
        filename_filter: filenameFilter,
        ...(category ? { category } : {}),
        ...(providerId ? { provider_id: providerId } : {}),
      });
      if (!response.data?.success) {
        throw new Error(`not found: ${raw}`);
      }
      return {
        filename: raw,
        system_prompt: response.data.system_prompt ?? null,
        snippets: response.data.snippets ?? [],
      };
    }),
  );

  const resolved = results
    .filter(result => result.status === 'fulfilled')
    .map(result => result.value);
  const errors = results.flatMap((result, index) =>
    result.status === 'rejected' ? [mentions[index]] : [],
  );
  return { resolved, errors };
}

const getApiErrorMessage = (error, fallback) => {
  return error?.response?.data?.detail
    || error?.response?.data?.content
    || error?.message
    || fallback;
};

export const tokenizeCommand = (command) => {
  const tokens = [];
  const tokenPattern = /"([^"]*)"|'([^']*)'|(\S+)/g;
  let match;

  while ((match = tokenPattern.exec(command.trim())) !== null) {
    const token = match[1] ?? match[2] ?? match[3] ?? '';
    if (token) {
      tokens.push(token);
    }
  }

  return tokens;
};

export const extractProviderOverride = (command) => {
  const rawParts = tokenizeCommand(command);
  const parts = [];
  let providerId = null;
  let missingValue = false;

  for (let index = 0; index < rawParts.length; index += 1) {
    if (rawParts[index] !== '--provider') {
      parts.push(rawParts[index]);
      continue;
    }

    const nextValue = rawParts[index + 1]?.trim();
    if (!nextValue) {
      missingValue = true;
      break;
    }
    providerId = nextValue;
    index += 1;
  }

  return { parts, providerId, missingValue };
};

export const buildLegacyMcpRequest = ({
  action,
  parts,
  activeCategory,
  ragEnabled,
  sessionProviderId,
  commandProviderId,
}) => {
  const params = {
    action,
    provider_id: commandProviderId,
  };

  if (activeCategory) {
    params.session_category = activeCategory;
  }
  if (sessionProviderId) {
    params.session_provider_id = sessionProviderId;
  }
  params.rag_enabled = Boolean(ragEnabled);

  if (action === 'list') {
    const target = parts.slice(2).join(' ').trim() || null;
    if (target) {
      params.target = target;
    }
    return params;
  }

  if (action === 'search') {
    const queryParts = parts.slice(2);
    if (!queryParts.length) {
      throw new Error('검색어를 입력하세요. 예: /mcp search 안전밸브');
    }
    params.query = queryParts.join(' ');
    return params;
  }

  if (action === 'read') {
    const rawTarget = parts.slice(2).join(' ').trim();
    if (!rawTarget) {
      throw new Error('파일명을 입력하세요. 예: /mcp read valve_spec.md');
    }
    if (rawTarget.includes('*') || rawTarget.includes('?')) {
      throw new Error('와일드카드(*, ?)는 허용하지 않습니다.');
    }
    params.target = rawTarget;
    return params;
  }

  throw new Error(`알 수 없는 /mcp 커맨드: "${action}". /mcp help 로 확인하세요.`);
};

/**
 * Chat 커맨드 처리를 위한 커스텀 훅
 * "/" 로 시작하는 커맨드들을 파싱하고 실행한다.
 *
 * 지원 커맨드:
 * - /memory save|load|delete|list|clear "이름"
 * - /mcp list|search|read|set|clear|rag|use|help
 *
 * @param {Object} params
 * @param {Array} params.messages - 현재 메시지 배열
 * @param {Function} params.setMessages - 메시지 상태 setter
 * @param {string} params.currentSessionId - 현재 세션 ID
 * @returns {{ executeCommand: Function, isCommandLoading: boolean }}
 */
export const useCommands = ({
  messages,
  setMessages,
  currentSessionId,
  ensureSession,
}) => {
  const [isCommandLoading, setIsCommandLoading] = useState(false);
  const [activeCategory, setActiveCategory] = useState(null);
  const [activeProvider, setActiveProvider] = useState(DEFAULT_MCP_PROVIDER_ID);
  const [ragEnabled, setRagEnabled] = useState(false);
  const ragCacheRef = useRef(null);

  const resetCommandState = useCallback(() => {
    setActiveCategory(null);
    setActiveProvider(DEFAULT_MCP_PROVIDER_ID);
    setRagEnabled(false);
    ragCacheRef.current = null;
  }, []);

  const appendSystemHistory = useCallback(async (_sessionId, content, metadata = {}) => {
    const message = buildSystemMessage(content, {
      channel: 'command_result',
      phase: 'command',
      raw: null,
      ...metadata,
    });
    const messageMetadata = message.metadata;
    setMessages(prev => [
      ...prev,
      message,
    ]);
    if (_sessionId) {
      await modelChatApi.saveMessage(_sessionId, 'system', content, messageMetadata);
    }
  }, [setMessages]);

  const emitCommandError = useCallback(async (sessionId, message) => {
    await appendSystemHistory(sessionId, `⚠️ ${message}`, {
      level: 'error',
      title: 'Command error',
      phase: 'command_error',
    });
  }, [appendSystemHistory]);

  const handleMemorySave = useCallback(async (sessionId, name) => {
    setIsCommandLoading(true);
    try {
      const snapshotMessages = messages.filter(message => message.role !== 'system');
      if (snapshotMessages.length === 0) {
        await emitCommandError(sessionId, '저장할 대화 내용이 없습니다.');
        return;
      }

      await memoryApi.saveSnapshot(sessionId, name, snapshotMessages);
      const successText = `메모리 저장 완료: "${name}" (${snapshotMessages.length}개 메시지)`;
      await appendSystemHistory(sessionId, `✅ ${successText}`, {
        title: 'Memory saved',
        phase: 'memory',
      });
    } catch (error) {
      if (error.response?.data?.error?.includes('이미 존재')) {
        await emitCommandError(sessionId, `스냅샷 "${name}"이(가) 이미 존재합니다. 다른 이름을 사용해주세요.`);
      } else {
        await emitCommandError(sessionId, `스냅샷 저장에 실패했습니다: ${error.response?.data?.error || error.message || '알 수 없는 오류'}`);
      }
    } finally {
      setIsCommandLoading(false);
    }
  }, [messages, emitCommandError, appendSystemHistory]);

  const handleMemoryLoad = useCallback(async (sessionId, name) => {
    setIsCommandLoading(true);
    try {
      const snapshot = await memoryApi.getSnapshotByName(sessionId, name);
      if (!snapshot) {
        await emitCommandError(sessionId, `스냅샷 "${name}"을(를) 찾을 수 없습니다.`);
        return;
      }

      setMessages(snapshot.messages || []);
      const successText = `메모리 불러오기 완료: "${name}" (${snapshot.messages?.length || 0}개 메시지)`;
      await appendSystemHistory(sessionId, `✅ ${successText}`, {
        title: 'Memory loaded',
        phase: 'memory',
      });
    } catch (error) {
      await emitCommandError(sessionId, `스냅샷 로드에 실패했습니다: ${error.message || '알 수 없는 오류'}`);
    } finally {
      setIsCommandLoading(false);
    }
  }, [appendSystemHistory, emitCommandError, setMessages]);

  const handleMemoryList = useCallback(async (sessionId) => {
    setIsCommandLoading(true);
    try {
      const snapshots = await memoryApi.listSnapshots(sessionId);
      if (!snapshots.length) {
        await appendSystemHistory(sessionId, '저장된 메모리 스냅샷이 없습니다.', {
          title: 'Memory list',
          phase: 'memory',
        });
      } else {
        const rows = snapshots.map(snapshot => `| ${snapshot.name} | ${snapshot.message_count} | ${new Date(snapshot.updated_at).toLocaleString()} |`);
        const content = [
          '## 🧠 저장된 메모리 스냅샷',
          '',
          '| 이름 | 메시지 수 | 수정일 |',
          '|:---|---:|:---|',
          ...rows,
        ].join('\n');
        await appendSystemHistory(sessionId, content, {
          title: 'Memory list',
          phase: 'memory',
        });
      }
    } catch (error) {
      await emitCommandError(sessionId, `스냅샷 목록 조회에 실패했습니다: ${error.message || '알 수 없는 오류'}`);
    } finally {
      setIsCommandLoading(false);
    }
  }, [appendSystemHistory, emitCommandError]);

  const handleMemoryClear = useCallback(async (sessionId) => {
    setIsCommandLoading(true);
    try {
      const result = await memoryApi.clearSnapshots(sessionId);
      const successText = `메모리 초기화 완료: ${result.deleted}개의 스냅샷 삭제`;
      await appendSystemHistory(sessionId, `✅ ${successText}`, {
        title: 'Memory cleared',
        phase: 'memory',
      });
    } catch (error) {
      await emitCommandError(sessionId, `스냅샷 삭제에 실패했습니다: ${error.message || '알 수 없는 오류'}`);
    } finally {
      setIsCommandLoading(false);
    }
  }, [appendSystemHistory, emitCommandError]);

  const handleMemoryDelete = useCallback(async (sessionId, name) => {
    setIsCommandLoading(true);
    try {
      const result = await memoryApi.deleteSnapshotByName(sessionId, name);
      if (!result) {
        await emitCommandError(sessionId, `스냅샷 "${name}"을(를) 찾을 수 없습니다.`);
      } else {
        const successText = `스냅샷 "${name}" 삭제 완료`;
        await appendSystemHistory(sessionId, `✅ ${successText}`, {
          title: 'Memory deleted',
          phase: 'memory',
        });
      }
    } catch (error) {
      await emitCommandError(sessionId, `스냅샷 삭제에 실패했습니다: ${error.message || '알 수 없는 오류'}`);
    } finally {
      setIsCommandLoading(false);
    }
  }, [appendSystemHistory, emitCommandError]);

  const handleMemoryCommand = useCallback(async (sessionId, command) => {
    if (command.startsWith('/memory save ')) {
      const name = command.replace('/memory save ', '').trim().replace(/^["']|["']$/g, '');
      if (!name) {
        await emitCommandError(sessionId, '스냅샷 이름을 입력해주세요. 예: /memory save "이름"');
        return;
      }
      await handleMemorySave(sessionId, name);
      return;
    }

    if (command.startsWith('/memory load ')) {
      const name = command.replace('/memory load ', '').trim().replace(/^["']|["']$/g, '');
      if (!name) {
        await emitCommandError(sessionId, '스냅샷 이름을 입력해주세요. 예: /memory load "이름"');
        return;
      }
      await handleMemoryLoad(sessionId, name);
      return;
    }

    if (command.startsWith('/memory delete ')) {
      const name = command.replace('/memory delete ', '').trim().replace(/^["']|["']$/g, '');
      if (!name) {
        await emitCommandError(sessionId, '스냅샷 이름을 입력해주세요. 예: /memory delete "이름"');
        return;
      }
      await handleMemoryDelete(sessionId, name);
      return;
    }

    if (command === '/memory list') {
      await handleMemoryList(sessionId);
      return;
    }

    if (command === '/memory clear') {
      await handleMemoryClear(sessionId);
      return;
    }

    if (command === '/memory') {
      await emitCommandError(sessionId, '사용법: /memory [save|load|delete|list|clear] "이름"');
      return;
    }

    await emitCommandError(sessionId, '알 수 없는 /memory 커맨드입니다. 사용 가능한 커맨드: save, load, delete, list, clear');
  }, [
    handleMemorySave,
    handleMemoryLoad,
    handleMemoryDelete,
    handleMemoryList,
    handleMemoryClear,
    emitCommandError,
  ]);

  const handleMcpCommand = useCallback(async (sessionId, command) => {
    const { parts, providerId: overrideProviderId, missingValue } = extractProviderOverride(command);
    if (missingValue) {
      await emitCommandError(sessionId, '사용법: /mcp ... --provider <provider_id>');
      return;
    }

    const action = parts[1];
    const providerForState = activeProvider || DEFAULT_MCP_PROVIDER_ID;
    const commandProviderId = overrideProviderId || providerForState;

    if (!action || action === 'help') {
      const categoryStatus = activeCategory
        ? `🗂️ 현재 기본 카테고리: **"${activeCategory}"**`
        : '🗂️ 기본 카테고리: 없음 (전체 문서 검색)';

      const helpContent = [
        '## 📖 MCP 문서 검색 커맨드',
        '',
        '| 커맨드 | 설명 |',
        '|:---|:---|',
        '| `/mcp list` | 카테고리 목록 + 문서 수 조회 |',
        '| `/mcp list <카테고리>` | 해당 카테고리의 파일 목록 + 최종 수정일 조회 |',
        '| `/mcp search <키워드>` | 키워드로 문서 검색 (RAG ON + 카테고리 설정 시 해당 카테고리 우선) |',
        '| `/mcp read <파일명>` | 문서 읽기 (카테고리 설정 시 해당 카테고리 내 탐색, 없으면 전체 탐색) |',
        '| `/mcp read <카테고리/파일명>` | 특정 카테고리의 문서 전체 내용 읽기 |',
        '| `/mcp set <카테고리명>` | 카테고리 설정 + **RAG 자동 활성화** |',
        '| `/mcp clear` | 카테고리 해제 + RAG 자동 비활성화 |',
        '| `/mcp rag off` | RAG 모드 비활성화 (카테고리 유지) |',
        '| `/mcp rag on` | RAG 모드 재활성화 |',
        '| `/mcp rag status` | RAG 모드 상태 + 캐시 정보 확인 |',
        '| `/mcp rag refresh` | RAG 검색 캐시 강제 초기화 |',
        '| `/mcp use <provider_id>` | 기본 MCP provider 전환 |',
        '| `/mcp ... --provider <provider_id>` | 이번 명령만 provider override |',
        '| `/mcp help` | 이 도움말 표시 |',
        '',
        '---',
        '### 📎 @파일명 문법 (특정 파일 직접 지정)',
        '',
        '| 문법 | 설명 |',
        '|:---|:---|',
        '| `@파일명.md 질문` | 해당 파일의 관련 스니펫을 LLM 컨텍스트에 주입 (RAG 대신) |',
        '| `@"파일명 공백.md" 질문` | 공백/특수문자 포함 파일명은 **큰따옴표**로 감싸기 |',
        '| `@카테고리/파일명.md 질문` | 카테고리 경로 포함 지정 |',
        '| `@file1.md @"file 2.md" 질문` | 복수 파일 동시 지정 가능 |',
        '',
        '> `@`는 질문 어느 위치에나 사용 가능. 세션 카테고리 설정 시 경로 없는 파일명은 해당 카테고리 내 탐색.',
        '',
        '---',
        `🔌 현재 기본 provider: **"${providerForState}"**`,
        categoryStatus,
        ragEnabled
          ? '🤖 RAG 모드: **ON** — 일반 질문 입력 시 문서를 자동 검색합니다'
          : '🤖 RAG 모드: **OFF** — `/mcp set <카테고리명>` 으로 활성화',
      ].join('\n');

      await appendSystemHistory(sessionId, helpContent, {
        title: 'MCP help',
        phase: 'command',
        provider: providerForState,
      });
      return;
    }

    if (action === 'use') {
      const nextProvider = parts[2]?.trim();
      if (!nextProvider) {
        await emitCommandError(sessionId, 'provider_id를 입력하세요. 예: /mcp use internal_docs');
        return;
      }

      setActiveProvider(nextProvider);
      setActiveCategory(null);
      setRagEnabled(false);
      ragCacheRef.current = null;
      await appendSystemHistory(sessionId, [
        '## 🔌 MCP provider 변경',
        '',
        `기본 provider가 **"${nextProvider}"** 로 변경되었습니다.`,
        'provider 의미가 섞이지 않도록 기존 카테고리와 RAG 상태는 초기화했습니다.',
        '',
        '> 필요한 경우 `/mcp set <카테고리명>` 으로 다시 카테고리를 설정하세요.',
      ].join('\n'), {
        title: 'MCP provider changed',
        phase: 'command',
        provider: nextProvider,
      });
      return;
    }

    if (action === 'set') {
      const categoryName = parts.slice(2).join(' ').trim();
      if (!categoryName) {
        await emitCommandError(sessionId, '카테고리 이름을 입력하세요. 예: /mcp set safety');
        return;
      }

      const validation = await mcpCommandApi.validateCategory(categoryName, providerForState);
      const validatedCategory = validation.data?.category || categoryName;

      setActiveCategory(validatedCategory);
      setRagEnabled(true);
      ragCacheRef.current = null;
      await appendSystemHistory(sessionId, [
        '## 🗂️ 문서 카테고리 설정',
        '',
        `provider **"${providerForState}"** 에서 카테고리 **"${validatedCategory}"** 이(가) 설정되었습니다.`,
        '📚 **RAG 모드가 자동으로 활성화**되었습니다.',
        '',
        '> 이제 채팅창에서 일반 질문을 입력하면 해당 카테고리 문서를 자동 검색하여 답변에 활용합니다.',
        '> RAG를 끄려면 `/mcp rag off` 를 입력하세요.',
        '> 카테고리를 해제하려면 `/mcp clear` 를 입력하세요.',
      ].join('\n'), {
        title: 'MCP category set',
        phase: 'command',
        provider: providerForState,
      });
      return;
    }

    if (action === 'clear') {
      setActiveCategory(null);
      setRagEnabled(false);
      ragCacheRef.current = null;
      await appendSystemHistory(sessionId, `🗂️ MCP 문서 카테고리가 해제되었습니다. provider는 **"${providerForState}"** 로 유지되며, RAG 모드도 비활성화되었습니다.`, {
        title: 'MCP category cleared',
        phase: 'command',
        provider: providerForState,
      });
      return;
    }

    if (action === 'rag') {
      const sub = parts[2];
      if (!sub || sub === 'status') {
        const cacheAge = ragCacheRef.current
          ? Math.round((Date.now() - ragCacheRef.current.cachedAt) / 1000)
          : null;
        const statusContent = ragEnabled
          ? [
              '## 🤖 RAG 모드: **ON**',
              `🔌 provider: **"${providerForState}"**`,
              `🗂️ 검색 카테고리: ${activeCategory ? `**"${activeCategory}"**` : '전체 (카테고리 미지정)'}`,
              '📊 용량: 문서 최대 10개 × 1,500자 스니펫 (BM25 관련성 랭킹 + 최신 우선)',
              cacheAge !== null ? `🗃️ 캐시: ${cacheAge}초 전 검색 결과 보관 중` : '🗃️ 캐시: 없음 (첫 질문 시 검색)',
            ].join('\n')
          : [
              '🤖 RAG 모드: **OFF**',
              `현재 provider: **"${providerForState}"**`,
              '',
              '`/mcp set <카테고리>` 로 활성화하세요.',
            ].join('\n');
        await appendSystemHistory(sessionId, statusContent, {
          title: 'RAG status',
          phase: 'command',
          provider: providerForState,
        });
      } else if (sub === 'on') {
        setRagEnabled(true);
        ragCacheRef.current = null;
        await appendSystemHistory(sessionId, [
          '## 🤖 RAG 모드 활성화',
          '',
          '이제 일반 질문을 입력하면 **자동으로 문서를 검색**하여 LLM 답변에 활용합니다.',
          '',
          `🔌 provider: **"${providerForState}"**`,
          activeCategory
            ? `🗂️ 검색 대상: **"${activeCategory}"** 카테고리`
            : '🗂️ 검색 대상: 전체 문서 (카테고리 미지정)',
          '📊 검색 규모: 서버의 doc search 설정(문서 수, 스니펫 길이, 핵심 스니펫 조립 상한)을 따릅니다.',
          '',
          '> 카테고리를 지정하려면 `/mcp set <카테고리명>` 을 입력하세요.',
          '> 캐시를 초기화하려면 `/mcp rag refresh` 를 입력하세요.',
          '> RAG를 끄려면 `/mcp rag off` 를 입력하세요.',
        ].join('\n'), {
          title: 'RAG enabled',
          phase: 'command',
          provider: providerForState,
        });
      } else if (sub === 'off') {
        setRagEnabled(false);
        ragCacheRef.current = null;
        await appendSystemHistory(sessionId, `🤖 RAG 모드 **비활성화** — provider **"${providerForState}"** 는 유지되고, LLM이 자체 지식으로 답변합니다.`, {
          title: 'RAG disabled',
          phase: 'command',
          provider: providerForState,
        });
      } else if (sub === 'refresh') {
        ragCacheRef.current = null;
        await appendSystemHistory(sessionId, `🗃️ RAG 캐시 초기화 완료 — provider **"${providerForState}"** 로 다음 질문 시 새로 문서를 검색합니다.`, {
          title: 'RAG cache refreshed',
          phase: 'command',
          provider: providerForState,
        });
      } else {
        await emitCommandError(sessionId, '사용법: /mcp rag on | off | status | refresh');
      }
      return;
    }

    setIsCommandLoading(true);
    try {
      const params = buildLegacyMcpRequest({
        action,
        parts,
        activeCategory,
        ragEnabled,
        sessionProviderId: providerForState,
        commandProviderId,
      });

      const response = await mcpCommandApi.execute(params);
      await appendSystemHistory(sessionId, response.data.content, {
        title: `/mcp ${action}`,
        phase: 'command',
        provider: commandProviderId,
      });
    } catch (error) {
      await emitCommandError(sessionId, `/mcp 커맨드 실패: ${getApiErrorMessage(error, '알 수 없는 오류')}`);
    } finally {
      setIsCommandLoading(false);
    }
  }, [activeCategory, activeProvider, ragEnabled, appendSystemHistory, emitCommandError]);

  const executeCommand = useCallback(async (text, options = {}) => {
    const originalText = options.originalText || text;

    const sessionId = currentSessionId || await ensureSession();
    if (!sessionId) {
      return { handled: true };
    }

    if (text.startsWith('/mcp')) {
      await handleMcpCommand(sessionId, text);
      return { handled: true };
    }

    if (text.startsWith('/memory')) {
      await handleMemoryCommand(sessionId, text);
      return { handled: true };
    }

    await emitCommandError(sessionId, `알 수 없는 커맨드입니다: "${originalText.split(' ')[0]}"`);
    return { handled: true };
  }, [
    currentSessionId,
    emitCommandError,
    ensureSession,
    handleMcpCommand,
    handleMemoryCommand,
  ]);

  return {
    executeCommand,
    isCommandLoading,
    activeCategory,
    activeProvider,
    ragEnabled,
    ragCacheRef,
    resetCommandState,
  };
};
