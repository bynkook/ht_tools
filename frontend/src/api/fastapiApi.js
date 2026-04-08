import { fastApiClient } from './axiosConfig';

/**
 * FastAPI Gateway Client
 *
 * Streaming endpoints (use fetchEventSource directly):
 * - POST /agent-messages  - FabriX Agent Chat (SSE streaming)
 * - POST /chat-messages   - FabriX Chat (SSE streaming)
 *
 * Non-streaming endpoints (use fastApi below):
 * - GET  /agent-messages/agents
 * - POST /agent-messages/file
 * - POST /image-compare/process
 */
export const fastApi = {
  getAgents: async () => {
    const response = await fastApiClient.get('/agent-messages/agents');
    return response.data;
  },

  uploadFile: async (file, agentId, query) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('agentId', agentId);
    formData.append('contents', query);
    const response = await fastApiClient.post('/agent-messages/file', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  compareImages: async (params) => {
    const {
      file1, file2, mode, diffThreshold, featureCount, alignmentAlgorithm, page1, page2,
      cadMode, cadLineWidth, cadLineWidthEnabled, cadAlignTolerance, cadQualityThreshold,
      hideHatchTransparency,
      colors,
      quality,
      cropRect,
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

    const effectiveCadMode = cadMode && ((cadLineWidthEnabled ?? true) || !!hideHatchTransparency);
    formData.append('cad_mode', effectiveCadMode ? 'true' : 'false');
    formData.append('cad_line_width', cadLineWidth ?? 0.2);
    formData.append('apply_line_width', cadLineWidthEnabled ?? false);
    formData.append('hide_hatch_transparency', hideHatchTransparency ?? false);
    formData.append('cad_align_tolerance', cadAlignTolerance ?? 0.22);
    formData.append('cad_quality_threshold', cadQualityThreshold ?? 0.35);

    if (cropRect) {
      formData.append('crop_x', cropRect.x);
      formData.append('crop_y', cropRect.y);
      formData.append('crop_w', cropRect.width);
      formData.append('crop_h', cropRect.height);
    }

    if (quality) {
      if (quality.output_quality != null) formData.append('output_quality', quality.output_quality);
      if (quality.output_resolution != null) formData.append('output_resolution', quality.output_resolution);
      if (quality.processing_resolution != null) formData.append('processing_resolution', quality.processing_resolution);
      if (quality.pdf_dpi != null) formData.append('pdf_dpi', quality.pdf_dpi);
    }

    if (colors) {
      if (colors.diff_file1) formData.append('color_diff_file1', colors.diff_file1);
      if (colors.diff_file2) formData.append('color_diff_file2', colors.diff_file2);
      if (colors.diff_common) formData.append('color_diff_common', colors.diff_common);
    }

    const response = await fastApiClient.post('/image-compare/process', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      timeout: 240000,
    });

    return response.data;
  },

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
    return response.data;
  },
};

export const docConverterApi = {
  uploadFile: async (file, category) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('category', category);
    const response = await fastApiClient.post('/doc-converter/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 30000,
    });
    return response.data;
  },
};

export const mcpCommandApi = {
  /**
   * @param {{ action: string, query?: string, category?: string, filename?: string, max_results?: number, provider_id?: string }} params
   * @returns {Promise<AxiosResponse<{ success: boolean, content: string }>>}
   */
  execute: (params) => fastApiClient.post('/mcp-command', params),

  /**
   * `/mcp set`는 `/mcp list`와 같은 backend category catalog를 통과한 값만 수용한다.
   */
  validateCategory: (category, providerId) => fastApiClient.post('/mcp-command/validate-category', {
    category,
    ...(providerId ? { provider_id: providerId } : {}),
  }),
};

export const mcpRagApi = {
  /**
   * @param {{ query: string, category?: string, max_docs?: number|null, snippet_chars?: number|null, provider_id?: string }} params
   * @returns {Promise<AxiosResponse<{ success: boolean, files: Array, query: string, category: string|null, system_prompt: string|null }>>}
   */
  search: (params) => fastApiClient.post('/mcp-command/rag-search', params),
};
