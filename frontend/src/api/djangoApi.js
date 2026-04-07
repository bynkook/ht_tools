import { djangoClient } from './axiosConfig';

export const authApi = {
  // 회원가입
  signup: async (userData) => {
    // userData: { username, password, email, auth_key }
    const response = await djangoClient.post('/api/auth/signup/', userData);
    return response.data;
  },
  
  // 로그인
  login: async (credentials) => {
    // credentials: { username, password }
    const response = await djangoClient.post('/api/auth/login/', credentials);
    return response.data;
  },
  
  // 로그아웃
  logout: async () => {
    const response = await djangoClient.post('/api/auth/logout/');
    return response.data;
  },

  // 비밀번호 초기화
  resetPassword: async (data) => {
    // data: { username, recovery_pin, new_password }
    const response = await djangoClient.post('/api/auth/password-reset/', data);
    return response.data;
  },

  // 프로필 조회
  getProfile: async () => {
    const response = await djangoClient.get('/api/auth/profile/');
    return response.data;
  },

  // 프로필 수정 (비밀번호/PIN 변경)
  updateProfile: async (data) => {
    // data: { new_password, new_pin }
    const response = await djangoClient.patch('/api/auth/profile/', data);
    return response.data;
  },
};

// =============================================================================
// FabriX Agent Chat APIs (Agent 기반 채팅 - /api/agent-chat/)
// =============================================================================

// Agent 목록 조회 API
export const agentApi = {
  getAgents: async () => {
    const response = await djangoClient.get('/api/agent-chat/agents/');
    return response.data;
  },
};

// Agent Chat 세션 API
export const agentChatApi = {
  // 대화방 목록 조회
  getSessions: async () => {
    const response = await djangoClient.get('/api/agent-chat/sessions/');
    return Array.isArray(response.data) ? response.data : (response.data?.results || []);
  },

  // 새 대화방 생성
  createSession: async (agentId, title) => {
    const response = await djangoClient.post('/api/agent-chat/sessions/', {
      agent_id: agentId,
      title: title || "New Chat",
    });
    return response.data;
  },

  // 대화방 상세 조회 (메시지 내역 포함)
  getSessionDetail: async (sessionId) => {
    const response = await djangoClient.get(`/api/agent-chat/sessions/${sessionId}/`);
    return response.data;
  },

  // 메시지 저장 (User 질문 또는 AI 답변)
  saveMessage: async (sessionId, role, content) => {
    const response = await djangoClient.post(`/api/agent-chat/sessions/${sessionId}/messages/`, {
      role,
      content,
    });
    return response.data;
  },

  // 대화방 삭제
  deleteSession: async (sessionId) => {
    const response = await djangoClient.delete(`/api/agent-chat/sessions/${sessionId}/`);
    return response.data;
  },
};

// 역호환성을 위한 별칭 (기존 코드에서 chatApi를 사용하는 경우)
export const chatApi = agentChatApi;

// =============================================================================
// FabriX Chat APIs (Model 기반 채팅 - /api/chat/)
// =============================================================================

// Model 목록 조회 API
export const modelApi = {
  getRuntimeConfig: async () => {
    const response = await djangoClient.get('/api/chat/runtime-config/');
    return response.data;
  },

  getModels: async () => {
    const response = await djangoClient.get('/api/chat/models/');
    return response.data;
  },
};

// Model Chat 세션 API
export const modelChatApi = {
  // 대화방 목록 조회
  getSessions: async () => {
    const response = await djangoClient.get('/api/chat/sessions/');
    return Array.isArray(response.data) ? response.data : (response.data?.results || []);
  },

  // 새 대화방 생성
  createSession: async (modelId, title) => {
    const payload = {
      title: title || "New Chat",
    };
    if (modelId) {
      payload.model_id = modelId;
    }
    const response = await djangoClient.post('/api/chat/sessions/', payload);
    return response.data;
  },

  // 대화방 상세 조회 (메시지 내역 포함)
  getSessionDetail: async (sessionId) => {
    const response = await djangoClient.get(`/api/chat/sessions/${sessionId}/`);
    return response.data;
  },

  // 대화방 정보 수정 (예: 제목 갱신)
  updateSession: async (sessionId, data) => {
    const response = await djangoClient.patch(`/api/chat/sessions/${sessionId}/`, data);
    return response.data;
  },

  // 메시지 저장 (User 질문 또는 AI 답변)
  saveMessage: async (sessionId, role, content, metadata = null) => {
    const response = await djangoClient.post(`/api/chat/sessions/${sessionId}/messages/`, {
      role,
      content,
      ...(metadata ? { metadata } : {}),
    });
    return response.data;
  },

  saveMessages: async (sessionId, messages) => {
    const response = await djangoClient.post(`/api/chat/sessions/${sessionId}/messages/bulk/`, {
      messages,
    });
    return response.data;
  },

  // 대화방 삭제
  deleteSession: async (sessionId) => {
    const response = await djangoClient.delete(`/api/chat/sessions/${sessionId}/`);
    return response.data;
  },
};


export const boardApi = {
  listBoards: async () => {
    const response = await djangoClient.get('/api/board/boards/');
    return response.data;
  },

  getBoard: async (slug) => {
    const response = await djangoClient.get(`/api/board/boards/${slug}/`);
    return response.data;
  },

  getPost: async (postId) => {
    const response = await djangoClient.get(`/api/board/posts/${postId}/`);
    return response.data;
  },

  createPost: async (slug, formData) => {
    const response = await djangoClient.post(`/api/board/boards/${slug}/posts/`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  updatePost: async (postId, formData) => {
    const response = await djangoClient.patch(`/api/board/posts/${postId}/`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  deletePost: async (postId) => {
    const response = await djangoClient.delete(`/api/board/posts/${postId}/`);
    return response.data;
  },

  listComments: async (postId) => {
    const response = await djangoClient.get(`/api/board/posts/${postId}/comments/`);
    return response.data;
  },

  createComment: async (postId, body) => {
    const response = await djangoClient.post(`/api/board/posts/${postId}/comments/`, { body });
    return response.data;
  },

  updateComment: async (commentId, body) => {
    const response = await djangoClient.patch(`/api/board/comments/${commentId}/`, { body });
    return response.data;
  },

  deleteComment: async (commentId) => {
    const response = await djangoClient.delete(`/api/board/comments/${commentId}/`);
    return response.data;
  },
};

// =============================================================================
// Memory Snapshot APIs (/memory 커맨드용)
// =============================================================================

/**
 * Memory Snapshot API 팩토리
 * Chat과 Agent Chat에서 동일 구조의 API를 URL 경로만 다르게 생성
 * @param {string} basePath - '/api/chat' 또는 '/api/agent-chat'
 */
const createMemoryApi = (basePath) => ({
  /**
   * 스냅샷 저장
   * @param {number} sessionId - 세션 ID
   * @param {string} name - 스냅샷 이름
   * @param {Array} messages - 저장할 메시지 배열
   */
  saveSnapshot: async (sessionId, name, messages) => {
    const response = await djangoClient.post(
      `${basePath}/sessions/${sessionId}/memory-snapshots/`,
      {
        name,
        snapshot_data: { messages },
      }
    );
    return response.data;
  },

  /**
   * 스냅샷 목록 조회
   * @param {number} sessionId - 세션 ID
   * @param {string} searchName - 검색할 이름 (선택)
   */
  listSnapshots: async (sessionId, searchName = null) => {
    const params = searchName ? { name: searchName } : {};
    const response = await djangoClient.get(
      `${basePath}/sessions/${sessionId}/memory-snapshots/`,
      { params }
    );
    return response.data;
  },

  /**
   * 이름으로 스냅샷 검색 및 로드 (2단계 API 호출)
   * Step 1: 목록에서 ID 조회 → Step 2: 상세 API로 snapshot_data 획득
   */
  getSnapshotByName: async (sessionId, name) => {
    const listResponse = await djangoClient.get(
      `${basePath}/sessions/${sessionId}/memory-snapshots/`,
      { params: { name } }
    );
    const snapshots = listResponse.data;
    const found = snapshots.find(s => s.name === name);
    if (!found) return null;

    const detailResponse = await djangoClient.get(
      `${basePath}/sessions/${sessionId}/memory-snapshots/${found.id}/`
    );
    return detailResponse.data;
  },

  /**
   * 세션의 모든 스냅샷 삭제 (/memory clear)
   */
  clearSnapshots: async (sessionId) => {
    const response = await djangoClient.delete(
      `${basePath}/sessions/${sessionId}/memory-snapshots/clear/`
    );
    return response.data;
  },

  /**
   * 이름으로 스냅샷 삭제 (/memory delete "이름")
   * Step 1: 목록에서 이름으로 검색 → Step 2: ID로 삭제
   */
  deleteSnapshotByName: async (sessionId, name) => {
    const listResponse = await djangoClient.get(
      `${basePath}/sessions/${sessionId}/memory-snapshots/`,
      { params: { name } }
    );
    const snapshots = listResponse.data;
    const found = snapshots.find(s => s.name === name);
    if (!found) return null;

    await djangoClient.delete(
      `${basePath}/sessions/${sessionId}/memory-snapshots/${found.id}/delete/`
    );
    return { deleted: true, name };
  },
});

// FabriX Chat 용 Memory API
export const memoryApi = createMemoryApi('/api/chat');

// Agent Chat 용 Memory API
export const agentMemoryApi = createMemoryApi('/api/agent-chat');

export const dataExplorerApi = {
  // 서버 로컬 데이터셋 목록 조회
  getDatasets: async () => {
    const response = await djangoClient.get('/api/data-explorer/datasets/');
    return response.data;
  },

  // Preview: 컬럼 설정 모달용 미리보기 데이터 조회
  previewDataset: async (filename) => {
    const response = await djangoClient.post('/api/data-explorer/preview/', {
      filename
    });
    return response.data;
  },

  // Computation Mode: 세션 초기화 (스키마 조회)
  // columns: optional array of {name, semantic_type, include}
  initSession: async (filename, columns = null) => {
    const payload = { filename };
    if (columns) {
      payload.columns = columns;
    }
    const response = await djangoClient.post('/api/data-explorer/init-session/', payload);
    return response.data;
  },

  // Computation Mode: SQL 쿼리 실행
  queryParams: async (filename, query) => {
    const response = await djangoClient.post('/api/data-explorer/query/', {
      filename,
      query
    });
    return response.data;
  },

  // 파일 업로드 (100MB 제한)
  uploadDataset: async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    
    const response = await djangoClient.post('/api/data-explorer/upload/', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  // Cache status: 캐시 상태 확인
  // filename: optional - 특정 파일만 확인, 없으면 전체 파일 확인
  getCacheStatus: async (filename = null) => {
    const url = filename 
      ? `/api/data-explorer/cache-status/?file=${encodeURIComponent(filename)}`
      : '/api/data-explorer/cache-status/';
    const response = await djangoClient.get(url);
    return response.data;
  },

  // Rebuild: 캐시 재구축 작업 시작
  // files: array of filenames to rebuild
  startRebuild: async (files) => {
    const response = await djangoClient.post('/api/data-explorer/rebuild/start/', {
      files
    });
    return response.data;
  },

  // Rebuild: 작업 상태 조회
  getRebuildStatus: async (taskId) => {
    const response = await djangoClient.get(`/api/data-explorer/rebuild/status/${taskId}/`);
    return response.data;
  },
};

// Preset API for Data Explorer
export const presetApi = {
  // 프리셋 목록 조회
  list: async () => {
    const response = await djangoClient.get('/api/data-explorer/presets/');
    return response.data;
  },

  // 프리셋 생성
  create: async (presetData) => {
    // presetData: { name, description, data_config, chart_spec, fields_meta }
    const response = await djangoClient.post('/api/data-explorer/presets/', presetData);
    return response.data;
  },

  // 프리셋 상세 조회 (파일 존재 여부 포함)
  get: async (presetId) => {
    const response = await djangoClient.get(`/api/data-explorer/presets/${presetId}/`);
    return response.data;
  },

  // 프리셋 수정
  update: async (presetId, presetData) => {
    const response = await djangoClient.put(`/api/data-explorer/presets/${presetId}/`, presetData);
    return response.data;
  },

  // 프리셋 삭제
  delete: async (presetId) => {
    const response = await djangoClient.delete(`/api/data-explorer/presets/${presetId}/`);
    return response.data;
  },
};

// =============================================================================
// Doc Uploader APIs (/api/doc-uploader/)
// =============================================================================
export const docUploaderApi = {
  // 변환 작업 목록 조회
  listJobs: async () => {
    const response = await djangoClient.get('/api/doc-uploader/jobs/');
    return response.data;
  },
  // 카테고리 목록 조회
  listCategories: async () => {
    const response = await djangoClient.get('/api/doc-uploader/categories/');
    return response.data;
  },
  // 카테고리 생성
  createCategory: async (name) => {
    const response = await djangoClient.post('/api/doc-uploader/categories/', { name });
    return response.data;
  },
  // 카테고리 이름 변경
  renameCategory: async (oldName, newName) => {
    const response = await djangoClient.patch(`/api/doc-uploader/categories/${encodeURIComponent(oldName)}/`, { new_name: newName });
    return response.data;
  },
};

export const settingsApi = {
  // 사용자 설정 조회
  getSettings: async () => {
    const response = await djangoClient.get('/api/settings/');
    return response.data;
  },
  
  // 사용자 설정 업데이트 (Partial Update)
  updateSettings: async (settings) => {
    const response = await djangoClient.patch('/api/settings/', {
      preferences: settings
    });
    return response.data;
  },
};

// =============================================================================
// ESC 물가변동 산출 APIs (/api/esc/)
// =============================================================================
export const escApi = {
  getProjects: async () => {
    const response = await djangoClient.get('/api/esc/projects/');
    return Array.isArray(response.data) ? response.data : (response.data?.results || []);
  },
  createProject: async (data) => {
    const response = await djangoClient.post('/api/esc/projects/', data);
    return response.data;
  },
  updateProject: async (id, data) => {
    const response = await djangoClient.put(`/api/esc/projects/${id}/`, data);
    return response.data;
  },
  deleteProject: async (id) => {
    const response = await djangoClient.delete(`/api/esc/projects/${id}/`);
    return response.data;
  },
  resetKosisCache: async (dataType = 'wage') => {
    const response = await djangoClient.post('/api/esc/kosis/cache/reset/', { data_type: dataType });
    return response.data;
  },
  getKosisPpi: async (start, end) => {
    const response = await djangoClient.get('/api/esc/kosis/ppi/', { params: { start, end } });
    return response.data;
  },
  getKosisWage: async (start, end) => {
    const response = await djangoClient.get('/api/esc/kosis/wage/', { params: { start, end } });
    return response.data;
  },
};
