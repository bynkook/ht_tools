import { useCallback, useEffect, useRef } from 'react';

const canRestoreFocus = (activeElement, inputElement) => {
  if (!inputElement) return false;
  if (!activeElement || activeElement === document.body) return true;
  return activeElement === inputElement;
};

const useInputFocusRestore = ({ inputRef, isLoading }) => {
  const pendingRestoreRef = useRef(false);

  const restoreFocusIfSafe = useCallback(() => {
    const inputElement = inputRef.current;
    if (!inputElement) {
      pendingRestoreRef.current = false;
      return;
    }

    const activeElement = document.activeElement;
    if (!canRestoreFocus(activeElement, inputElement)) {
      pendingRestoreRef.current = false;
      return;
    }

    requestAnimationFrame(() => {
      inputElement.focus();
    });
    pendingRestoreRef.current = false;
  }, [inputRef]);

  const requestRestoreFocus = useCallback(() => {
    pendingRestoreRef.current = true;
    if (!isLoading) {
      restoreFocusIfSafe();
    }
  }, [isLoading, restoreFocusIfSafe]);

  useEffect(() => {
    if (!isLoading && pendingRestoreRef.current) {
      restoreFocusIfSafe();
    }
  }, [isLoading, restoreFocusIfSafe]);

  return {
    requestRestoreFocus,
  };
};

export default useInputFocusRestore;