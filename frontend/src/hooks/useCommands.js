import { useState, useCallback, useRef, useEffect } from 'react';
import { dashboardLinksApi, memoryApi } from '../api/djangoApi';
import { mcpCommandApi } from '../api/fastapiApi';

/**
 * 자연어 → 커맨드 매핑 패턴
 * { patterns: RegExp[], command: string }
 */
const NATURAL_LANGUAGE_PATTERNS = [
  {
    patterns: [
      /태블로.*대시보드/i,
      /tableau.*dashboard/i,
      /대시보드.*목록/i,
      /대시보드.*링크/i,
      /대시보드.*보여/i,
    ],
    command: '/dashboard'
  },
  // 추후 다른 커맨드 패턴 추가 가능
];

/**
 * 자연어 입력에서 커맨드 감지
 * @param {string} text - 사용자 입력
 * @returns {string|null} - 매칭된 커맨드 또는 null
 */
export const detectNaturalLanguageCommand = (text) => {
  const normalized = text.trim();
  for (const { patterns, command } of NATURAL_LANGUAGE_PATTERNS) {
    if (patterns.some(pattern => pattern.test(normalized))) {
      return command;
    }
  }
  return null;
};

/**
 * Chat 커맨드 처리를 위한 커스텀 훅
 * "/" 로 시작하는 커맨드들을 파싱하고 실행한다.
 * 
 * 지원 커맨드:
 * - /memory save|load|delete|list|clear "이름"
 * - /dashboard
 * - /mcp list|search|read|category|help
 * 
 * @param {Object} params
 * @param {Array} params.messages - 현재 메시지 배열
 * @param {Function} params.setMessages - 메시지 상태 setter
 * @param {Function} params.setError - 에러 메시지 setter
 * @param {Function} params.setSuccessMessage - 성공 메시지 setter
 * @param {string} params.currentSessionId - 현재 세션 ID
 * @returns {{ executeCommand: Function, isCommandLoading: boolean }}
 */
export const useCommands = ({
  messages,
  setMessages,
  setError,
  setSuccessMessage,
  currentSessionId
}) => {
  const [isCommandLoading, setIsCommandLoading] = useState(false);
  const [activeCategory, setActiveCategory] = useState(null); // /mcp 세션 카테고리
  const [ragEnabled, setRagEnabled] = useState(false);        // RAG 모드 활성화 여부
  const ragCacheRef = useRef(null); // { query, category, systemPrompt, cachedAt }

  // 세션 변경(New Chat, 다른 대화 이동) 시 RAG 상태 초기화
  useEffect(() => {
    setActiveCategory(null);
    setRagEnabled(false);
    ragCacheRef.current = null;
  }, [currentSessionId]);

  // ===== Memory Command Handlers =====

  const handleMemorySave = useCallback(async (name) => {
    if (!currentSessionId) {
      setError('세션을 먼저 생성한 후 스냅샷을 저장해주세요.');
      return;
    }
    setIsCommandLoading(true);
    try {
      const snapshotMessages = messages.filter(m => m.role !== 'system');
      if (snapshotMessages.length === 0) {
        setError('저장할 대화 내용이 없습니다.');
        return;
      }
      await memoryApi.saveSnapshot(currentSessionId, name, snapshotMessages);
      setSuccessMessage(`메모리 저장 완료: "${name}" (${snapshotMessages.length}개 메시지)`);
    } catch (err) {
      if (err.response?.data?.error?.includes('이미 존재')) {
        setError(`스냅샷 "${name}"이(가) 이미 존재합니다. 다른 이름을 사용해주세요.`);
      } else {
        setError('스냅샷 저장에 실패했습니다: ' + (err.response?.data?.error || err.message || '알 수 없는 오류'));
      }
    } finally {
      setIsCommandLoading(false);
    }
  }, [currentSessionId, messages, setError, setSuccessMessage]);

  const handleMemoryLoad = useCallback(async (name) => {
    if (!currentSessionId) {
      setError('세션을 먼저 생성한 후 스냅샷을 로드해주세요.');
      return;
    }
    setIsCommandLoading(true);
    try {
      const snapshot = await memoryApi.getSnapshotByName(currentSessionId, name);
      if (!snapshot) {
        setError(`스냅샷 "${name}"을(를) 찾을 수 없습니다.`);
        return;
      }
      const restoredMessages = snapshot.snapshot_data?.messages || [];
      if (restoredMessages.length === 0) {
        setError(`스냅샷 "${name}"에 저장된 메시지가 없습니다.`);
        return;
      }
      setMessages(restoredMessages);
      setSuccessMessage(`메모리 로드 완료: "${name}" (${restoredMessages.length}개 메시지, ${new Date(snapshot.created_at).toLocaleString('ko-KR')})`);
    } catch (err) {
      setError('스냅샷 로드에 실패했습니다: ' + (err.message || '알 수 없는 오류'));
    } finally {
      setIsCommandLoading(false);
    }
  }, [currentSessionId, setMessages, setError, setSuccessMessage]);

  const handleMemoryList = useCallback(async () => {
    if (!currentSessionId) {
      setError('세션을 먼저 생성한 후 목록을 조회해주세요.');
      return;
    }
    setIsCommandLoading(true);
    try {
      const snapshots = await memoryApi.listSnapshots(currentSessionId);
      if (snapshots.length === 0) {
        setMessages(prev => [...prev, { role: 'system', content: '저장된 스냅샷이 없습니다.' }]);
      } else {
        const listText = snapshots.map((s, i) =>
          `${i + 1}. "${s.name}" (${new Date(s.created_at).toLocaleString('ko-KR')})`
        ).join('\n');
        setMessages(prev => [...prev, {
          role: 'system',
          content: `저장된 스냅샷 (${snapshots.length}개):\n${listText}`
        }]);
      }
    } catch (err) {
      setError('스냅샷 목록 조회에 실패했습니다: ' + (err.message || '알 수 없는 오류'));
    } finally {
      setIsCommandLoading(false);
    }
  }, [currentSessionId, setMessages, setError]);

  const handleMemoryClear = useCallback(async () => {
    if (!currentSessionId) {
      setError('세션을 먼저 생성한 후 스냅샷을 삭제해주세요.');
      return;
    }
    setIsCommandLoading(true);
    try {
      const result = await memoryApi.clearSnapshots(currentSessionId);
      setSuccessMessage(`메모리 초기화 완료: ${result.deleted}개의 스냅샷 삭제`);
    } catch (err) {
      setError('스냅샷 삭제에 실패했습니다: ' + (err.message || '알 수 없는 오류'));
    } finally {
      setIsCommandLoading(false);
    }
  }, [currentSessionId, setError, setSuccessMessage]);

  const handleMemoryDelete = useCallback(async (name) => {
    if (!currentSessionId) {
      setError('세션을 먼저 생성한 후 스냅샷을 삭제해주세요.');
      return;
    }
    setIsCommandLoading(true);
    try {
      const result = await memoryApi.deleteSnapshotByName(currentSessionId, name);
      if (!result) {
        setError(`스냅샷 "${name}"을(를) 찾을 수 없습니다.`);
      } else {
        setSuccessMessage(`스냅샷 "${name}" 삭제 완료`);
      }
    } catch (err) {
      setError('스냅샷 삭제에 실패했습니다: ' + (err.message || '알 수 없는 오류'));
    } finally {
      setIsCommandLoading(false);
    }
  }, [currentSessionId, setError, setSuccessMessage]);

  const handleMemoryCommand = useCallback(async (command) => {
    if (command.startsWith('/memory save ')) {
      const name = command.replace('/memory save ', '').trim().replace(/^["']|["']$/g, '');
      if (!name) { setError('스냅샷 이름을 입력해주세요. 예: /memory save "이름"'); return; }
      await handleMemorySave(name);
      return;
    }
    if (command.startsWith('/memory load ')) {
      const name = command.replace('/memory load ', '').trim().replace(/^["']|["']$/g, '');
      if (!name) { setError('스냅샷 이름을 입력해주세요. 예: /memory load "이름"'); return; }
      await handleMemoryLoad(name);
      return;
    }
    if (command.startsWith('/memory delete ')) {
      const name = command.replace('/memory delete ', '').trim().replace(/^["']|["']$/g, '');
      if (!name) { setError('스냅샷 이름을 입력해주세요. 예: /memory delete "이름"'); return; }
      await handleMemoryDelete(name);
      return;
    }
    if (command === '/memory list') {
      await handleMemoryList();
      return;
    }
    if (command === '/memory clear') {
      await handleMemoryClear();
      return;
    }
    if (command === '/memory') {
      setError('사용법: /memory [save|load|delete|list|clear] "이름"');
      return;
    }
    setError('알 수 없는 /memory 커맨드입니다. 사용 가능한 커맨드: save, load, delete, list, clear');
  }, [handleMemorySave, handleMemoryLoad, handleMemoryDelete, handleMemoryList, handleMemoryClear, setError]);

  // ===== Dashboard Command Handler =====

  const handleDashboardCommand = useCallback(async () => {    setIsCommandLoading(true);
    try {
      const dashboards = await dashboardLinksApi.list();

      if (!dashboards || dashboards.length === 0) {
        setError('등록된 대시보드가 없습니다.');
        return;
      }

      const tableHeader = '| No | 대시보드 | 링크 | 설명 |';
      const tableDivider = '|:---:|:---|:---:|:---|';
      const tableRows = dashboards.map((dashboard, index) =>
        `| ${dashboard.id ?? index + 1} | ${dashboard.dashboard_name} | [${dashboard.linkname}](${dashboard.url}) | ${dashboard.desc} |`
      ).join('\n');

      const markdownTable = `📊 **Tableau 대시보드 목록**\n\n${tableHeader}\n${tableDivider}\n${tableRows}`;

      setMessages(prev => [...prev, {
        role: 'assistant',
        content: markdownTable
      }]);
    } catch (err) {
      setError('대시보드 목록 조회에 실패했습니다: ' + (err.message || '알 수 없는 오류'));
    } finally {
      setIsCommandLoading(false);
    }
  }, [setError, setMessages]);

  // ===== MCP Command Handler =====

  const handleMcpCommand = useCallback(async (command) => {
    const parts = command.trim().split(/\s+/);
    // parts[0] = "/mcp", parts[1] = action, parts[2..] = args
    const action = parts[1];

    // /mcp  또는  /mcp help
    if (!action || action === 'help') {
      const categoryStatus = activeCategory
        ? `🗂️ 현재 기본 카테고리: **"${activeCategory}"**`
        : `🗂️ 기본 카테고리: 없음 (전체 문서 검색)`;

      const helpContent = [
        `## 📖 MCP 문서 검색 커맨드`,
        ``,
        `| 커맨드 | 설명 |`,
        `|:---|:---|`,
        `| \`/mcp list\` | 카테고리 목록 + 문서 수 조회 |`,
        `| \`/mcp list <카테고리>\` | 해당 카테고리의 파일 목록 + 최종 수정일 조회 |`,
        `| \`/mcp search <키워드>\` | 키워드로 문서 검색 (기본 카테고리 자동 적용) |`,
        `| \`/mcp read <파일명>\` | 문서 읽기 (카테고리 설정 시 해당 카테고리 내 탐색, 없으면 전체 탐색) |`,
        `| \`/mcp read <카테고리/파일명>\` | 특정 카테고리의 문서 전체 내용 읽기 |`,
        `| \`/mcp set <카테고리명>\` | 카테고리 설정 + **RAG 자동 활성화** |`,
        `| \`/mcp clear\` | 카테고리 해제 + RAG 자동 비활성화 |`,
        `| \`/mcp rag off\` | RAG 모드 비활성화 (카테고리 유지) |`,
        `| \`/mcp rag on\` | RAG 모드 재활성화 |`,
        `| \`/mcp rag status\` | RAG 모드 상태 + 캐시 정보 확인 |`,
        `| \`/mcp rag refresh\` | RAG 검색 캐시 강제 초기화 |`,
        `| \`/mcp help\` | 이 도움말 표시 |`,
        ``,
        `---`,
        categoryStatus,
        ragEnabled
          ? `🤖 RAG 모드: **ON** — 일반 질문 입력 시 문서를 자동 검색합니다`
          : `🤖 RAG 모드: **OFF** — \`/mcp set <카테고리명>\` 으로 활성화`,
      ].join('\n');

      setMessages(prev => [...prev, { role: 'assistant', content: helpContent }]);
      return;
    }

    // /mcp set <카테고리명>  (카테고리 설정 + RAG 자동 활성화)
    if (action === 'set') {
      const cat = parts.slice(2).join(' ').trim();
      if (!cat) { setError('카테고리 이름을 입력하세요. 예: /mcp set safety'); return; }
      setActiveCategory(cat);
      setRagEnabled(true);
      ragCacheRef.current = null;
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: [
          `## 🗂️ 문서 카테고리 설정`,
          ``,
          `카테고리 **"${cat}"** 이(가) 설정되었습니다.`,
          `📚 **RAG 모드가 자동으로 활성화**되었습니다.`,
          ``,
          `> 이제 채팅창에서 일반 질문을 입력하면 해당 카테고리 문서를 자동 검색하여 답변에 활용합니다.`,
          `> RAG를 끄려면 \`/mcp rag off\` 를 입력하세요.`,
          `> 카테고리를 해제하려면 \`/mcp clear\` 를 입력하세요.`,
        ].join('\n'),
      }]);
      return;
    }

    // /mcp clear  (카테고리 해제 + RAG 비활성화)
    if (action === 'clear') {
      setActiveCategory(null);
      setRagEnabled(false);
      ragCacheRef.current = null;
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `🗂️ MCP 문서 카테고리가 해제되었습니다. RAG 모드도 비활성화되었습니다.`,
      }]);
      return;
    }

    // /mcp rag on | off | status | refresh
    if (action === 'rag') {
      const sub = parts[2];
      if (!sub || sub === 'status') {
        const cacheAge = ragCacheRef.current
          ? Math.round((Date.now() - ragCacheRef.current.cachedAt) / 1000)
          : null;
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: ragEnabled
            ? [
                `## 🤖 RAG 모드: **ON**`,
                `🗂️ 검색 카테고리: ${activeCategory ? `**"${activeCategory}"**` : '전체 (카테고리 미지정)'}`,
                `📊 용량: 문서 최대 10개 × 1,500자 스니펫 (BM25 관련성 랭킹 + 최신 우선)`,
                cacheAge !== null ? `🗃️ 캐시: ${cacheAge}초 전 검색 결과 보관 중` : `🗃️ 캐시: 없음 (첫 질문 시 검색)`,
              ].join('\n')
            : `🤖 RAG 모드: **OFF**\n\`/mcp set <카테고리>\` 로 활성화하세요.`,
        }]);
      } else if (sub === 'on') {
        setRagEnabled(true);
        ragCacheRef.current = null;
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: [
            `## 🤖 RAG 모드 활성화`,
            ``,
            `이제 일반 질문을 입력하면 **자동으로 문서를 검색**하여 LLM 답변에 활용합니다.`,
            ``,
            activeCategory
              ? `🗂️ 검색 대상: **"${activeCategory}"** 카테고리`
              : `🗂️ 검색 대상: 전체 문서 (카테고리 미지정)`,
            `📊 검색 규모: 문서 **최대 10개** × 스니펫 **1,500자** (BM25 관련성 랭킹 + 최신 우선)`,
            ``,
            `> 카테고리를 지정하려면 \`/mcp set <카테고리명>\` 을 입력하세요.`,
            `> 캐시를 초기화하려면 \`/mcp rag refresh\` 를 입력하세요.`,
            `> RAG를 끄려면 \`/mcp rag off\` 를 입력하세요.`,
          ].join('\n'),
        }]);
      } else if (sub === 'off') {
        setRagEnabled(false);
        ragCacheRef.current = null;
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: `🤖 RAG 모드 **비활성화** — LLM이 자체 지식으로 답변합니다.`,
        }]);
      } else if (sub === 'refresh') {
        ragCacheRef.current = null;
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: `🗃️ RAG 캐시 초기화 완료 — 다음 질문 시 새로 문서를 검색합니다.`,
        }]);
      } else {
        setError('사용법: /mcp rag on | off | status | refresh');
      }
      return;
    }

    // 서버 요청이 필요한 액션
    setIsCommandLoading(true);
    try {
      const params = { action };

      if (action === 'list') {
        // /mcp list [카테고리]  — 공백 포함 카테고리명 지원
        const cat = parts.slice(2).join(' ').trim() || null;
        if (cat) params.category = cat;

      } else if (action === 'search') {
        // /mcp search <키워드...>
        const queryParts = parts.slice(2);
        if (!queryParts.length) {
          setError('검색어를 입력하세요. 예: /mcp search 안전밸브');
          return;
        }
        params.query = queryParts.join(' ');
        if (activeCategory) params.category = activeCategory; // 세션 카테고리 자동 적용

      } else if (action === 'read') {
        // /mcp read <파일명> 또는 /mcp read <카테고리/파일명>  (공백 포함 가능)
        const filename = parts.slice(2).join(' ').trim();
        if (!filename) {
          setError('파일명을 입력하세요. 예: /mcp read valve_spec.md');
          return;
        }
        if (filename.includes('*') || filename.includes('?')) {
          setError('와일드카드(*, ?)는 허용하지 않습니다.');
          return;
        }
        params.filename = filename;
        // 파일명에 경로 구분자가 없고 세션 카테고리가 설정된 경우 → 카테고리 내에서 탐색
        if (!filename.includes('/') && !filename.includes('\\') && activeCategory) {
          params.category = activeCategory;
        }

      } else {
        setError(`알 수 없는 /mcp 커맨드: "${action}". /mcp help 로 확인하세요.`);
        return;
      }

      const res = await mcpCommandApi.execute(params);
      // res.data = { success: boolean, content: string }
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: res.data.content,
      }]);

    } catch (err) {
      setError('/mcp 커맨드 실패: ' + (err.message || '알 수 없는 오류'));
    } finally {
      setIsCommandLoading(false);
    }
  }, [activeCategory, ragEnabled, setMessages, setError, setSuccessMessage, setIsCommandLoading]);

  // ===== Command Dispatcher =====

  /**
   * 커맨드를 파싱하고 적절한 핸들러를 실행
   * @param {string} text - "/" 로 시작하는 커맨드 문자열
   * @returns {{ handled: boolean }} - 커맨드가 처리되었는지 여부
   */
  const executeCommand = useCallback(async (text) => {
    setSuccessMessage(null);
    setError(null);

    // /mcp 커맨드
    if (text.startsWith('/mcp')) {
      await handleMcpCommand(text);
      return { handled: true };
    }

    // /memory 커맨드
    if (text.startsWith('/memory')) {
      await handleMemoryCommand(text);
      return { handled: true };
    }

    // /dashboard 커맨드
    if (text === '/dashboard' || text === '/dashboard list') {
      await handleDashboardCommand();
      return { handled: true };
    }

    // 알 수 없는 커맨드
    setError(`알 수 없는 커맨드입니다: "${text.split(' ')[0]}"`);
    return { handled: true };
  }, [handleMcpCommand, handleMemoryCommand, handleDashboardCommand, setError, setSuccessMessage]);

  return {
    executeCommand,
    isCommandLoading,
    activeCategory,
    ragEnabled,
    ragCacheRef,
  };
};
