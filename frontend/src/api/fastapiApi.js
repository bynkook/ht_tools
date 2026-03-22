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
  // params: { file1, file2, mode, diffThreshold, featureCount, alignmentAlgorithm, page1, page2, 
  //           cadMode, cadLineWidth, cadLineWidthEnabled, cadAlignTolerance, cadQualityThreshold,
  //           colors, quality, cropRect }
  compareImages: async (params) => {
    const { 
      file1, file2, mode, diffThreshold, featureCount, alignmentAlgorithm, page1, page2, 
      cadMode, cadLineWidth, cadLineWidthEnabled, cadAlignTolerance, cadQualityThreshold,
      hideHatchTransparency,
      colors,    // { diff_file1, diff_file2, diff_common, overlay_file1, overlay_file2 }
      quality,   // { output_quality, output_resolution, processing_resolution, pdf_dpi }
      cropRect,  // { x, y, width, height } 정규화 0-1 또는 null
    } = params;
    
    const formData = new FormData();
    formData.append('file1', file1);
    formData.append('file2', file2);
    formData.append('mode', mode);
    formData.append('diff_threshold', diffThreshold);
    formData.append('feature_count', featureCount);
    formData.append('alignment_algorithm', alignmentAlgorithm ?? 'orb');
    formData.append('page1', page1);
    formData.append('page2', page2);
    // CAD 전처리: 선두께 변경 또는 해치 제거 중 하나라도 켜져 있으면 cad_mode 적용
    const effectiveCadMode = cadMode && ((cadLineWidthEnabled ?? true) || !!hideHatchTransparency);
    formData.append('cad_mode', effectiveCadMode ? 'true' : 'false');
    formData.append('cad_line_width', cadLineWidth ?? 0.2);
    formData.append('apply_line_width', cadLineWidthEnabled ?? false);
    formData.append('hide_hatch_transparency', hideHatchTransparency ?? false);
    // CAD 정렬 파라미터 (CAD 모드일 때만 의미 있음)
    formData.append('cad_align_tolerance', cadAlignTolerance ?? 0.22);
    formData.append('cad_quality_threshold', cadQualityThreshold ?? 0.35);
    
    // crop 영역 파라미터 (4개 모두 있을 때만 전송)
    if (cropRect) {
      formData.append('crop_x', cropRect.x);
      formData.append('crop_y', cropRect.y);
      formData.append('crop_w', cropRect.width);
      formData.append('crop_h', cropRect.height);
    }

    // 품질 파라미터 추가
    if (quality) {
      if (quality.output_quality != null)        formData.append('output_quality',        quality.output_quality);
      if (quality.output_resolution != null)     formData.append('output_resolution',     quality.output_resolution);
      if (quality.processing_resolution != null) formData.append('processing_resolution', quality.processing_resolution);
      if (quality.pdf_dpi != null)               formData.append('pdf_dpi',               quality.pdf_dpi);
    }

    // 색상 파라미터 추가 (모든 모드 diff 3색 공통)
    if (colors) {
      if (colors.diff_file1)  formData.append('color_diff_file1',  colors.diff_file1);
      if (colors.diff_file2)  formData.append('color_diff_file2',  colors.diff_file2);
      if (colors.diff_common) formData.append('color_diff_common', colors.diff_common);
    }

    const response = await fastApiClient.post('/image-compare/process', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      timeout: 240000, // 240초 타임아웃 (대용량/복잡 도면 비교 대응)
    });
    
    return response.data;
  },

  // 단일 파일 미리보기 요청 (CropSelector 표시용)
  // PDF는 cad_mode/cad_line_width 를 넣어서 실제 비교와 동일한 렌더링 조건 적용
  previewFile: async ({ file, page, pdfDpi, cadMode, cadLineWidth, applyLineWidth, hideHatchTransparency }) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('page', page ?? 0);
    formData.append('pdf_dpi', pdfDpi ?? 150);
    formData.append('cad_mode', cadMode ? 'true' : 'false');
    formData.append('cad_line_width', cadLineWidth ?? 0.2);
    formData.append('apply_line_width', applyLineWidth ?? false);
    formData.append('hide_hatch_transparency', hideHatchTransparency ?? false);

    const response = await fastApiClient.post('/image-compare/preview', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 100000,
    });
    return response.data; // { image_base64, width, height, pages }
  },
};

// =============================================================================
// MCP Command API
// =============================================================================

/**
 * FastMCP Doc Server 커맨드 실행
 * fastmcp 서버(포트 8002)를 FastAPI Gateway(포트 8001)를 통해 간접 호출한다.
 * fastApi 객체가 아닌 fastApiClient axios 인스턴스를 직접 사용한다.
 */
export const mcpCommandApi = {
  /**
   * @param {{ action: string, query?: string, category?: string, filename?: string, max_results?: number }} params
   * @returns {Promise<AxiosResponse<{ success: boolean, content: string }>>}
   */
  execute: (params) => fastApiClient.post('/mcp-command', params),
};

// =============================================================================
// MCP RAG API
// =============================================================================

/**
 * RAG 파이프라인 전용 문서 검색 API
 * BM25 관련성 랭킹 + 최신 문서 우선으로 문서 스니펫 검색 후 systemPrompt 조립 반환
 */
export const mcpRagApi = {
  /**
   * @param {{ query: string, category?: string, max_docs?: number, snippet_chars?: number }} params
   * @returns {Promise<AxiosResponse<{ success: boolean, files: Array, query: string, category: string|null, system_prompt: string|null }>>}
   */
  search: (params) => fastApiClient.post('/mcp-command/rag-search', params),
};
