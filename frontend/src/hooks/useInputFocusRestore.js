import { useCallback, useEffect, useRef } from 'react';

const isNodeInside = (container, target) => {
  if (!container || !(target instanceof Node)) {
    return false;
  }
  return container.contains(target);
};

const useInputFocusRestore = ({ inputRef, scopeRef, isBusy }) => {
  const pendingRestoreRef = useRef(false);
  const shouldOwnFocusRef = useRef(false);
  const restoreFrameRef = useRef(null);

  const cancelScheduledRestore = useCallback(() => {
    if (restoreFrameRef.current !== null) {
      cancelAnimationFrame(restoreFrameRef.current);
      restoreFrameRef.current = null;
    }
  }, []);

  const clearPendingRestore = useCallback(() => {
    pendingRestoreRef.current = false;
    cancelScheduledRestore();
  }, [cancelScheduledRestore]);

  const focusInput = useCallback(({ cursor = 'end' } = {}) => {
    const inputElement = inputRef.current;
    if (!inputElement) {
      return false;
    }

    inputElement.focus();
    if (cursor === 'end' && typeof inputElement.setSelectionRange === 'function') {
      const nextLength = inputElement.value?.length ?? 0;
      inputElement.setSelectionRange(nextLength, nextLength);
    }
    return true;
  }, [inputRef]);

  const restoreFocusIfOwned = useCallback(() => {
    if (isBusy || !pendingRestoreRef.current || !shouldOwnFocusRef.current) {
      return;
    }

    const inputElement = inputRef.current;
    if (!inputElement) {
      return;
    }

    const scopeElement = scopeRef?.current ?? inputElement;
    const activeElement = document.activeElement;
    if (
      activeElement &&
      activeElement !== document.body &&
      activeElement !== inputElement &&
      !isNodeInside(scopeElement, activeElement)
    ) {
      pendingRestoreRef.current = false;
      return;
    }

    cancelScheduledRestore();
    restoreFrameRef.current = requestAnimationFrame(() => {
      restoreFrameRef.current = null;
      if (!pendingRestoreRef.current || !shouldOwnFocusRef.current) {
        return;
      }
      focusInput();
      pendingRestoreRef.current = false;
    });
  }, [cancelScheduledRestore, focusInput, inputRef, isBusy, scopeRef]);

  const requestRestoreFocus = useCallback(() => {
    shouldOwnFocusRef.current = true;
    pendingRestoreRef.current = true;
    restoreFocusIfOwned();
  }, [restoreFocusIfOwned]);

  const handleInputFocus = useCallback(() => {
    shouldOwnFocusRef.current = true;
  }, []);

  const handleInputBlur = useCallback((event) => {
    const scopeElement = scopeRef?.current ?? inputRef.current;
    if (isNodeInside(scopeElement, event.relatedTarget)) {
      return;
    }
    shouldOwnFocusRef.current = false;
    clearPendingRestore();
  }, [clearPendingRestore, inputRef, scopeRef]);

  const keepFocusOnPointerDown = useCallback((event) => {
    event.preventDefault();
    shouldOwnFocusRef.current = true;
  }, []);

  useEffect(() => {
    restoreFocusIfOwned();
    return cancelScheduledRestore;
  }, [cancelScheduledRestore, restoreFocusIfOwned]);

  return {
    focusInput,
    inputFocusProps: {
      onBlur: handleInputBlur,
      onFocus: handleInputFocus,
    },
    keepFocusOnPointerDown,
    requestRestoreFocus,
  };
};

export default useInputFocusRestore;
