import { fastApiClient } from './axiosConfig';

/**
 * FastAPI Gateway Client
 * 
 * Streaming endpoints (use fetchEventSource directly):
 * - POST /agent-messages  - FabriX Agent Chat (SSE streaming)
 * - POST /chat-messages   - FabriX Chat (Model-based, SSE streaming)
 * 
 * Non-streaming endpoints (use fastApi below):
 * - GET  /agent-messages/agents       - Agent 목록 조회
 * - POST /agent-messages/file         - 파일 업로드 분석
 * - POST /image-compare/process       - 이미지 비교
 */
export const fastApi = {
  // =============================================================================
  // FabriX Agent Chat APIs
  // =============================================================================
  
  // 사용 가능한 FabriX Agent 목록 조회
  getAgents: async () => {
    // page, limit은 필요에 따라 파라미터화 가능 (현재 기본값 사용)
    const response = await fastApiClient.get('/agent-messages/agents');
    return response.data;
  },

  // 파일 업로드 및 분석 요청 (Agent Chat 전용)
  // file: File 객체, agentId: 선택된 에이전트 ID, query: 사용자의 요청(프롬프트)
  uploadFile: async (file, agentId, query) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('agentId', agentId);
    formData.append('contents', query); // FastAPI에서 List로 변환 처리됨

    const response = await fastApiClient.post('/agent-messages/file', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  // 이미지 비교 요청
  // params: { file1, file2, mode, diffThreshold, featureCount, page1, page2, colors }
  compareImages: async (params) => {
    const { 
      file1, file2, mode, diffThreshold, featureCount, page1, page2, 
      colors // { diff_file1, diff_file2, diff_common, overlay_file1, overlay_file2 }
    } = params;
    
    const formData = new FormData();
    formData.append('file1', file1);
    formData.append('file2', file2);
    formData.append('mode', mode);
    formData.append('diff_threshold', diffThreshold);
    formData.append('feature_count', featureCount);
    formData.append('page1', page1);
    formData.append('page2', page2);
    
    // 색상 파라미터 추가
    if (colors) {
      if (colors.diff_file1) formData.append('color_diff_file1', colors.diff_file1);
      if (colors.diff_file2) formData.append('color_diff_file2', colors.diff_file2);
      if (colors.diff_common) formData.append('color_diff_common', colors.diff_common);
      if (colors.overlay_file1) formData.append('color_overlay_file1', colors.overlay_file1);
      if (colors.overlay_file2) formData.append('color_overlay_file2', colors.overlay_file2);
    }

    const response = await fastApiClient.post('/image-compare/process', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      timeout: 60000, // 60초 타임아웃 (대용량 파일 처리)
    });
    
    return response.data;
  },
};