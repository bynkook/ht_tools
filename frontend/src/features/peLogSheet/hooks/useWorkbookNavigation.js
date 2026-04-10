import { useCallback, useEffect, useRef } from 'react';

const DEFAULT_ROW_HEIGHT = 22;
const MIN_PAGE_ROWS = 5;
const MAX_ROW_SAMPLE_SIZE = 120;
const VIEWPORT_PADDING = 120;
const DATA_START_ROW = 1;
// Integration boundary for PE log sheet cell soft-locking:
// `.luckysheet-cell-input` focus/blur is the phase-1 entry point for lock
// lifecycle because FortuneSheet 1.0.4 does not provide a reliable native
// edit-start hook. Selection hooks still matter for navigation, but not for
// lock ownership.
const SHEET_AREA_SELECTOR = '.fortune-sheet-overlay, .fortune-sheet-container, .fortune-sheet-canvas, .luckysheet-cell-input';
const NON_SHEET_AREA_SELECTOR = '.fortune-toolbar, .fortune-fx-input-container, .fortune-fx-input';

function buildRowSample(anchorRow, rowCount) {
  const rows = [];
  const maxIndex = Math.max((rowCount ?? 1) - 1, 0);
  const start = Math.min(Math.max(anchorRow, 0), maxIndex);
  const end = Math.min(start + MAX_ROW_SAMPLE_SIZE - 1, maxIndex);

  for (let row = start; row <= end; row += 1) {
    rows.push(row);
  }

  return rows;
}

function getCurrentSheet(workbookApi) {
  return workbookApi?.getSheet?.() ?? null;
}

function getSelectionRange(workbookApi) {
  const selection = workbookApi?.getSelection?.();
  const first = Array.isArray(selection) ? selection[0] : null;

  if (!first?.row || !first?.column) {
    return {
      row: [0, 0],
      column: [0, 0],
    };
  }

  return first;
}

function getSelectionState(workbookApi) {
  const sheet = getCurrentSheet(workbookApi);
  const firstRange = getSelectionRange(workbookApi);
  const runtimeSelection = sheet?.luckysheet_select_save?.[0];

  return {
    row: firstRange.row,
    column: firstRange.column,
    rowFocus: runtimeSelection?.row_focus ?? firstRange.row[0],
    columnFocus: runtimeSelection?.column_focus ?? firstRange.column[0],
    sheet,
  };
}

function getActiveCellSelection(workbookApi) {
  const selectionState = getSelectionState(workbookApi);
  const sheet = selectionState.sheet;

  return {
    sheet_id: sheet?.id ?? sheet?.sheetId ?? sheet?.sheet_id ?? null,
    row: Number.isFinite(selectionState.rowFocus) ? selectionState.rowFocus : selectionState.row?.[0] ?? 0,
    column: Number.isFinite(selectionState.columnFocus) ? selectionState.columnFocus : selectionState.column?.[0] ?? 0,
  };
}

function getEffectiveRowCount(sheet, selectionEnd) {
  return Math.max(
    Number.isFinite(sheet?.row) ? sheet.row : 0,
    Array.isArray(sheet?.data) ? sheet.data.length : 0,
    selectionEnd + 1,
    DATA_START_ROW + 1,
  );
}

function getFocusZone(target) {
  if (!(target instanceof HTMLElement)) {
    return null;
  }

  if (target.closest(NON_SHEET_AREA_SELECTOR)) {
    return 'non-sheet';
  }

  if (target.closest(SHEET_AREA_SELECTOR)) {
    return 'sheet';
  }

  return null;
}

export function useWorkbookNavigation(workbookRef, workbookContainerRef, { onCellEditStart, onCellEditEnd } = {}) {
  const sheetFocusRef = useRef(false);
  const cellInputPresentRef = useRef(false);

  const getContainerRoot = useCallback(() => {
    const container = workbookContainerRef?.current;

    if (container instanceof HTMLElement) {
      return container;
    }

    if (document.body instanceof HTMLElement) {
      return document.body;
    }

    return null;
  }, [workbookContainerRef]);

  const syncCellEditState = useCallback((rootNode) => {
    if (!(rootNode instanceof HTMLElement)) {
      return;
    }

    const hasCellInput = Boolean(rootNode.querySelector('.luckysheet-cell-input'));

    if (hasCellInput && !cellInputPresentRef.current) {
      cellInputPresentRef.current = true;
      sheetFocusRef.current = true;

      if (typeof onCellEditStart === 'function') {
        const selection = getActiveCellSelection(workbookRef.current);
        if (selection.sheet_id != null) {
          onCellEditStart(selection.sheet_id, selection.row, selection.column);
        }
      }
      return;
    }

    if (!hasCellInput && cellInputPresentRef.current) {
      cellInputPresentRef.current = false;
      sheetFocusRef.current = false;

      if (typeof onCellEditEnd === 'function') {
        onCellEditEnd();
      }
    }
  }, [onCellEditEnd, onCellEditStart, workbookRef]);

  const markFocusFromTarget = useCallback((target) => {
    const zone = getFocusZone(target);

    if (zone === 'sheet') {
      sheetFocusRef.current = true;
    } else if (zone === 'non-sheet') {
      sheetFocusRef.current = false;
    }
  }, []);

  const getPageRowStep = useCallback((anchorRow, effectiveRowCount) => {
    const workbookApi = workbookRef.current;
    const wrapper = workbookContainerRef.current;

    if (!workbookApi?.getRowHeight || !wrapper) {
      return MIN_PAGE_ROWS;
    }

    const viewportHeight = Math.max(wrapper.clientHeight - VIEWPORT_PADDING, DEFAULT_ROW_HEIGHT * MIN_PAGE_ROWS);
    const sampledRows = buildRowSample(anchorRow, effectiveRowCount);

    if (!sampledRows.length) {
      return MIN_PAGE_ROWS;
    }

    const heights = workbookApi.getRowHeight(sampledRows) ?? {};
    let consumedHeight = 0;
    let step = 0;

    for (const row of sampledRows) {
      consumedHeight += heights[row] ?? DEFAULT_ROW_HEIGHT;
      step += 1;

      if (consumedHeight >= viewportHeight) {
        break;
      }
    }

    return Math.max(step, MIN_PAGE_ROWS);
  }, [workbookContainerRef, workbookRef]);

  const dispatchSheetArrow = useCallback((container, arrowKey, repeat) => {
    if (!(container instanceof HTMLElement) || repeat <= 0) {
      return;
    }

    const eventTarget =
      document.activeElement instanceof HTMLElement && container.contains(document.activeElement)
        ? document.activeElement
        : container.querySelector('.fortune-sheet-overlay') ?? container;

    for (let index = 0; index < repeat; index += 1) {
      const nativeEvent = new KeyboardEvent('keydown', {
        key: arrowKey,
        code: arrowKey,
        bubbles: true,
        cancelable: true,
      });
      eventTarget.dispatchEvent(nativeEvent);
    }
  }, []);

  const handleKeyDownCapture = useCallback((event) => {
    if (
      event.defaultPrevented ||
      event.altKey ||
      event.ctrlKey ||
      event.metaKey ||
      event.shiftKey ||
      !['PageDown', 'PageUp'].includes(event.key)
    ) {
      return;
    }

    const workbookRoot = workbookContainerRef.current;
    const workbookApi = workbookRef.current;

    if (!(workbookRoot instanceof HTMLElement) || !workbookApi) {
      return;
    }

    markFocusFromTarget(event.target);

    if (!sheetFocusRef.current) {
      return;
    }

    const selectionState = getSelectionState(workbookApi);
    const [rowStart, rowEnd] = selectionState.row;
    const effectiveRowCount = getEffectiveRowCount(selectionState.sheet, rowEnd);
    const pageStep = getPageRowStep(selectionState.rowFocus, effectiveRowCount);
    const moveCount = pageStep;
    const moveKey = event.key === 'PageDown' ? 'ArrowDown' : 'ArrowUp';

    if (!moveKey || moveCount <= 0) {
      return;
    }

    dispatchSheetArrow(workbookRoot, moveKey, moveCount);

    event.preventDefault();
    event.stopPropagation();
  }, [dispatchSheetArrow, getPageRowStep, markFocusFromTarget, workbookContainerRef, workbookRef]);

  const handleFocusCapture = useCallback((event) => {
    markFocusFromTarget(event.target);
  }, [markFocusFromTarget]);

  const handleMouseDownCapture = useCallback((event) => {
    markFocusFromTarget(event.target);
  }, [markFocusFromTarget]);

  useEffect(() => {
    const rootNode = getContainerRoot();
    if (!(rootNode instanceof HTMLElement)) {
      return undefined;
    }

    const handleFocusIn = (event) => {
      if (!(event.target instanceof HTMLElement) || !event.target.closest('.luckysheet-cell-input')) {
        return;
      }

      syncCellEditState(rootNode);
    };

    const handleFocusOut = (event) => {
      if (!(event.target instanceof HTMLElement) || !event.target.closest('.luckysheet-cell-input')) {
        return;
      }

      const relatedTarget = event.relatedTarget;
      if (relatedTarget instanceof HTMLElement && relatedTarget.closest('.luckysheet-cell-input')) {
        return;
      }

      syncCellEditState(rootNode);
    };

    const observer = new MutationObserver(() => {
      syncCellEditState(rootNode);
    });

    rootNode.addEventListener('focusin', handleFocusIn);
    rootNode.addEventListener('focusout', handleFocusOut);
    observer.observe(rootNode, {
      childList: true,
      subtree: true,
    });

    syncCellEditState(rootNode);

    return () => {
      observer.disconnect();
      rootNode.removeEventListener('focusin', handleFocusIn);
      rootNode.removeEventListener('focusout', handleFocusOut);

      if (cellInputPresentRef.current) {
        cellInputPresentRef.current = false;
        sheetFocusRef.current = false;

        if (typeof onCellEditEnd === 'function') {
          onCellEditEnd();
        }
      }
    };
  }, [getContainerRoot, onCellEditEnd, syncCellEditState]);

  const workbookHooks = useRef({
    // `afterCellMouseDown` fires for selection changes, so it is useful for
    // keyboard-navigation focus bookkeeping only. It is NOT sufficient for
    // cell-lock acquisition because selection alone must never imply edit
    // ownership.
    afterCellMouseDown: () => {
      sheetFocusRef.current = true;
    },
    // Phase-1 cell-lock boundary: FortuneSheet's commit-time `beforeUpdateCell`
    // hook is where trailing-user saves will eventually be cancelled by
    // returning false after the lock check. This file documents the boundary
    // only; functional lock enforcement is intentionally deferred.
  }).current;

  return {
    handleKeyDownCapture,
    handleFocusCapture,
    handleMouseDownCapture,
    workbookHooks,
  };
}
