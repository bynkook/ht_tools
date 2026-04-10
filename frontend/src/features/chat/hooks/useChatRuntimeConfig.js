import { useCallback, useEffect, useRef, useState } from 'react';

import { modelApi } from '../../../api/djangoApi';

const DEFAULT_RUNTIME_CONFIG = {
  mode: 'normal',
  isTestMode: false,
  requiresModelSelection: true,
  supportsExternalLlm: true,
};

const normalizeRuntimeConfig = (data = {}) => ({
  mode: data.mode || DEFAULT_RUNTIME_CONFIG.mode,
  isTestMode: data.is_test_mode ?? DEFAULT_RUNTIME_CONFIG.isTestMode,
  requiresModelSelection: data.requires_model_selection ?? DEFAULT_RUNTIME_CONFIG.requiresModelSelection,
  supportsExternalLlm: data.supports_external_llm ?? DEFAULT_RUNTIME_CONFIG.supportsExternalLlm,
});

export const useChatRuntimeConfig = () => {
  const configRef = useRef(null);
  const [runtimeConfig, setRuntimeConfig] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  const loadRuntimeConfig = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await modelApi.getRuntimeConfig();
      const normalized = normalizeRuntimeConfig(data);
      configRef.current = normalized;
      setRuntimeConfig(normalized);
      return normalized;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const ensureRuntimeConfig = useCallback(async () => {
    if (configRef.current) {
      return configRef.current;
    }
    return await loadRuntimeConfig();
  }, [loadRuntimeConfig]);

  useEffect(() => {
    loadRuntimeConfig().catch((error) => {
      console.error('[ChatRuntimeConfig] Failed to load runtime config:', error);
    });
  }, [loadRuntimeConfig]);

  return {
    runtimeConfig: runtimeConfig || DEFAULT_RUNTIME_CONFIG,
    hasLoadedRuntimeConfig: runtimeConfig !== null,
    isRuntimeConfigLoading: isLoading,
    ensureRuntimeConfig,
  };
};

export default useChatRuntimeConfig;
