import { useState, useCallback, useRef } from 'react';

import { memoryApi, modelChatApi } from '../api/djangoApi';
import { mcpCommandApi, mcpRagApi } from '../api/fastapiApi';
import { buildSystemMessage } from '../features/chat/utils/systemMessageState';

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
 * @returns {Promise<{ resolved: Array<{filename, system_prompt, snippets}>, errors: string[] }>}
 */
export async function resolveAtMentions(mentions, cleanQuery, activeCategory) {
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

/**
 * Chat 커맨드 처리를 위한 커스텀 훅
 * "/" 로 시작하는 커맨드들을 파싱하고 실행한다.
 *
 * 지원 커맨드:
 * - /memory save|load|delete|list|clear "이름"
 * - /mcp list|search|read|category|help
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
  const [ragEnabled, setRagEnabled] = useState(false);
  const ragCacheRef = useRef(null);

  const resetCommandState = useCallback(() => {
    setActiveCategory(null);
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

      const restoredMessages = snapshot.snapshot_data?.messages || [];
      if (restoredMessages.length === 0) {
        await emitCommandError(sessionId, `스냅샷 "${name}"에 저장된 메시지가 없습니다.`);
        return;
      }

      const successText = `메모리 로드 완료: "${name}" (${restoredMessages.length}개 메시지, ${new Date(snapshot.created_at).toLocaleString('ko-KR')})`;
      const message = buildSystemMessage(`✅ ${successText}`, {
        channel: 'command_result',
        title: 'Memory loaded',
        phase: 'memory',
      });
      const messageMetadata = message.metadata;
      setMessages([
        ...restoredMessages,
        message,
      ]);
      if (sessionId) {
        await modelChatApi.saveMessage(sessionId, 'system', `✅ ${successText}`, messageMetadata);
      }
    } catch (error) {
      await emitCommandError(sessionId, `스냅샷 로드에 실패했습니다: ${error.message || '알 수 없는 오류'}`);
    } finally {
      setIsCommandLoading(false);
    }
  }, [emitCommandError, setMessages]);

  const handleMemoryList = useCallback(async (sessionId) => {
    setIsCommandLoading(true);
    try {
      const snapshots = await memoryApi.listSnapshots(sessionId);
      if (snapshots.length === 0) {
        await appendSystemHistory(sessionId, '저장된 스냅샷이 없습니다.', {
          title: 'Memory list',
          phase: 'memory',
        });
      } else {
        const listText = snapshots.map((snapshot, index) =>
          `${index + 1}. "${snapshot.name}" (${new Date(snapshot.created_at).toLocaleString('ko-KR')})`,
        ).join('\n');
        await appendSystemHistory(sessionId, `저장된 스냅샷 (${snapshots.length}개):\n${listText}`, {
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
    const parts = command.trim().split(/\s+/);
    const action = parts[1];

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
        '| `/mcp search <키워드>` | 키워드로 문서 검색 (기본 카테고리 자동 적용) |',
        '| `/mcp read <파일명>` | 문서 읽기 (카테고리 설정 시 해당 카테고리 내 탐색, 없으면 전체 탐색) |',
        '| `/mcp read <카테고리/파일명>` | 특정 카테고리의 문서 전체 내용 읽기 |',
        '| `/mcp set <카테고리명>` | 카테고리 설정 + **RAG 자동 활성화** |',
        '| `/mcp clear` | 카테고리 해제 + RAG 자동 비활성화 |',
        '| `/mcp rag off` | RAG 모드 비활성화 (카테고리 유지) |',
        '| `/mcp rag on` | RAG 모드 재활성화 |',
        '| `/mcp rag status` | RAG 모드 상태 + 캐시 정보 확인 |',
        '| `/mcp rag refresh` | RAG 검색 캐시 강제 초기화 |',
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
        categoryStatus,
        ragEnabled
          ? '🤖 RAG 모드: **ON** — 일반 질문 입력 시 문서를 자동 검색합니다'
          : '🤖 RAG 모드: **OFF** — `/mcp set <카테고리명>` 으로 활성화',
      ].join('\n');

      await appendSystemHistory(sessionId, helpContent, {
        title: 'MCP help',
        phase: 'command',
        provider: 'internal_docs',
      });
      return;
    }

    if (action === 'set') {
      const categoryName = parts.slice(2).join(' ').trim();
      if (!categoryName) {
        await emitCommandError(sessionId, '카테고리 이름을 입력하세요. 예: /mcp set safety');
        return;
      }

      const validation = await mcpCommandApi.validateCategory(categoryName);
      const validatedCategory = validation.data?.category || categoryName;

      setActiveCategory(validatedCategory);
      setRagEnabled(true);
      ragCacheRef.current = null;
      await appendSystemHistory(sessionId, [
        '## 🗂️ 문서 카테고리 설정',
        '',
        `카테고리 **"${validatedCategory}"** 이(가) 설정되었습니다.`,
        '📚 **RAG 모드가 자동으로 활성화**되었습니다.',
        '',
        '> 이제 채팅창에서 일반 질문을 입력하면 해당 카테고리 문서를 자동 검색하여 답변에 활용합니다.',
        '> RAG를 끄려면 `/mcp rag off` 를 입력하세요.',
        '> 카테고리를 해제하려면 `/mcp clear` 를 입력하세요.',
      ].join('\n'), {
        title: 'MCP category set',
        phase: 'command',
        provider: 'internal_docs',
      });
      return;
    }

    if (action === 'clear') {
      setActiveCategory(null);
      setRagEnabled(false);
      ragCacheRef.current = null;
      await appendSystemHistory(sessionId, '🗂️ MCP 문서 카테고리가 해제되었습니다. RAG 모드도 비활성화되었습니다.', {
        title: 'MCP category cleared',
        phase: 'command',
        provider: 'internal_docs',
      });
      return;
    }

    if (action === 'rag') {
      const sub = parts[2];
      if (!sub || sub === 'status') {
        const cacheAge = ragCacheRef.current
          ? Math.round((Date.now() - ragCacheRef.current.cachedAt) / 1000)
          : null;
        await appendSystemHistory(
          sessionId,
          ragEnabled
            ? [
                '## 🤖 RAG 모드: **ON**',
                `🗂️ 검색 카테고리: ${activeCategory ? `**"${activeCategory}"**` : '전체 (카테고리 미지정)'}`,
                '📊 용량: 문서 최대 10개 × 1,500자 스니펫 (BM25 관련성 랭킹 + 최신 우선)',
                cacheAge !== null ? `🗃️ 캐시: ${cacheAge}초 전 검색 결과 보관 중` : '🗃️ 캐시: 없음 (첫 질문 시 검색)',
              ].join('\n')
            : '🤖 RAG 모드: **OFF**\n`/mcp set <카테고리>` 로 활성화하세요.',
          {
            title: 'RAG status',
            phase: 'command',
            provider: 'internal_docs',
          },
        );
      } else if (sub === 'on') {
        setRagEnabled(true);
        ragCacheRef.current = null;
        await appendSystemHistory(sessionId, [
          '## 🤖 RAG 모드 활성화',
          '',
          '이제 일반 질문을 입력하면 **자동으로 문서를 검색**하여 LLM 답변에 활용합니다.',
          '',
          activeCategory
            ? `🗂️ 검색 대상: **"${activeCategory}"** 카테고리`
            : '🗂️ 검색 대상: 전체 문서 (카테고리 미지정)',
          '📊 검색 규모: 문서 **최대 10개** × 스니펫 **1,500자** (BM25 관련성 랭킹 + 최신 우선)',
          '',
          '> 카테고리를 지정하려면 `/mcp set <카테고리명>` 을 입력하세요.',
          '> 캐시를 초기화하려면 `/mcp rag refresh` 를 입력하세요.',
          '> RAG를 끄려면 `/mcp rag off` 를 입력하세요.',
        ].join('\n'), {
          title: 'RAG enabled',
          phase: 'command',
          provider: 'internal_docs',
        });
      } else if (sub === 'off') {
        setRagEnabled(false);
        ragCacheRef.current = null;
        await appendSystemHistory(sessionId, '🤖 RAG 모드 **비활성화** — LLM이 자체 지식으로 답변합니다.', {
          title: 'RAG disabled',
          phase: 'command',
          provider: 'internal_docs',
        });
      } else if (sub === 'refresh') {
        ragCacheRef.current = null;
        await appendSystemHistory(sessionId, '🗃️ RAG 캐시 초기화 완료 — 다음 질문 시 새로 문서를 검색합니다.', {
          title: 'RAG cache refreshed',
          phase: 'command',
          provider: 'internal_docs',
        });
      } else {
        await emitCommandError(sessionId, '사용법: /mcp rag on | off | status | refresh');
      }
      return;
    }

    setIsCommandLoading(true);
    try {
      const params = { action };

      if (action === 'list') {
        const category = parts.slice(2).join(' ').trim() || null;
        if (category) {
          params.category = category;
        }
      } else if (action === 'search') {
        const queryParts = parts.slice(2);
        if (!queryParts.length) {
          await emitCommandError(sessionId, '검색어를 입력하세요. 예: /mcp search 안전밸브');
          return;
        }
        params.query = queryParts.join(' ');
        if (activeCategory) {
          params.category = activeCategory;
        }
      } else if (action === 'read') {
        const rawTarget = parts.slice(2).join(' ').trim();
        if (!rawTarget) {
          await emitCommandError(sessionId, '파일명을 입력하세요. 예: /mcp read valve_spec.md');
          return;
        }
        if (rawTarget.includes('*') || rawTarget.includes('?')) {
          await emitCommandError(sessionId, '와일드카드(*, ?)는 허용하지 않습니다.');
          return;
        }

        const pathMatch = rawTarget.match(/^([^/\\]+)[/\\](.+)$/);
        if (pathMatch) {
          params.category = pathMatch[1].trim();
          params.filename = pathMatch[2].trim();
        } else {
          params.filename = rawTarget;
        }

        if (!pathMatch && !rawTarget.includes('/') && !rawTarget.includes('\\') && activeCategory) {
          params.category = activeCategory;
        }
      } else {
        await emitCommandError(sessionId, `알 수 없는 /mcp 커맨드: "${action}". /mcp help 로 확인하세요.`);
        return;
      }

      const response = await mcpCommandApi.execute(params);
      await appendSystemHistory(sessionId, response.data.content, {
        title: `/mcp ${action}`,
        phase: 'command',
        provider: 'internal_docs',
      });
    } catch (error) {
      await emitCommandError(sessionId, `/mcp 커맨드 실패: ${getApiErrorMessage(error, '알 수 없는 오류')}`);
    } finally {
      setIsCommandLoading(false);
    }
  }, [activeCategory, ragEnabled, appendSystemHistory, emitCommandError]);

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
    ragEnabled,
    ragCacheRef,
    resetCommandState,
  };
};
