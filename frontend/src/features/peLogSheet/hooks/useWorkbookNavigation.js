import { useCallback, useRef } from 'react';

const DEFAULT_ROW_HEIGHT = 22;
const MIN_PAGE_ROWS = 5;
const MAX_ROW_SAMPLE_SIZE = 120;
const VIEWPORT_PADDING = 120;
const DATA_START_ROW = 1;
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

export function useWorkbookNavigation(workbookRef, workbookContainerRef) {
  const sheetFocusRef = useRef(false);

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

  const workbookHooks = useRef({
    afterCellMouseDown: () => {
      sheetFocusRef.current = true;
    },
  }).current;

  return {
    handleKeyDownCapture,
    handleFocusCapture,
    handleMouseDownCapture,
    workbookHooks,
  };
}
