import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { MaterialReactTable, useMaterialReactTable } from 'material-react-table';
import {
  alpha,
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  createTheme,
  IconButton,
  Stack,
  ThemeProvider,
  Tooltip,
  Typography,
  useTheme,
} from '@mui/material';
import { ArrowLeft, Plus, Save, Trash2 } from 'lucide-react';

import { dashboardLinksApi } from '../../api/djangoApi';

/**
 * crypto.randomUUID() 폴리필 - HTTP 환경(non-secure context) 지원
 * secure context에서는 native 사용, 아니면 Math.random 기반 fallback
 */
const generateUUID = () => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  // RFC 4122 v4 UUID fallback
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
};

const EMPTY_ROW = {
  dashboard_name: '',
  url: '',
  linkname: '',
  desc: '',
};

const EDITABLE_COLUMNS = [
  { key: 'dashboard_name', header: '대시보드명', placeholder: '대시보드 이름', size: 260 },
  { key: 'url', header: 'URL', placeholder: 'https://...', size: 380 },
  { key: 'linkname', header: '링크명', placeholder: '표시 텍스트', size: 200 },
  { key: 'desc', header: '설명', placeholder: '설명', size: 260 },
];

const EDITABLE_COLUMN_KEYS = EDITABLE_COLUMNS.map((column) => column.key);

const createClientRow = (row = {}, index = 0) => ({
  clientKey: generateUUID(),
  id: row.id ?? index + 1,
  dashboard_name: row.dashboard_name ?? '',
  url: row.url ?? '',
  linkname: row.linkname ?? '',
  desc: row.desc ?? '',
  updated_at: row.updated_at ?? null,
});

const isRowComplete = (row) => ['dashboard_name', 'url', 'linkname', 'desc']
  .every((key) => typeof row[key] === 'string' && row[key].trim() !== '');

const normalizeRows = (targetRows) => targetRows.map(({ clientKey, updated_at, id, ...row }) => row);

const getCellErrorKey = (clientKey, columnId) => `${clientKey}:${columnId}`;

const validateCellValue = (columnId, value) => {
  const trimmedValue = value.trim();

  if (!trimmedValue) {
    return '필수 입력 항목입니다.';
  }

  if (columnId === 'url' && !/^https?:\/\//i.test(trimmedValue)) {
    return 'http:// 또는 https:// 형식으로 입력하세요.';
  }

  return '';
};

const parseClipboardMatrix = (text) => text
  .replace(/\r\n/g, '\n')
  .replace(/\r/g, '\n')
  .replace(/\n$/, '')
  .split('\n')
  .map((line) => line.split('\t'));

const DashboardTablePage = () => {
  const globalTheme = useTheme();
  const navigate = useNavigate();
  const gridWrapperRef = useRef(null);
  const pendingEditTargetRef = useRef(null);
  const [rows, setRows] = useState([]);
  const [originalRows, setOriginalRows] = useState([]);
  const [selectedCell, setSelectedCell] = useState(null);
  const [validationErrors, setValidationErrors] = useState({});
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState(null);
  const [isDirty, setIsDirty] = useState(false);

  const syncDirtyState = useCallback((nextRows, baseRows = originalRows) => {
    setIsDirty(JSON.stringify(normalizeRows(nextRows)) !== JSON.stringify(normalizeRows(baseRows)));
  }, [originalRows]);

  const tableTheme = useMemo(() => createTheme({
    ...globalTheme,
    palette: {
      ...globalTheme.palette,
      background: {
        ...globalTheme.palette.background,
        default: '#f8f9fa',
        paper: '#ffffff',
      },
      primary: {
        ...globalTheme.palette.primary,
        main: '#1a1a1a',
      },
      secondary: {
        ...globalTheme.palette.secondary,
        main: '#6b7280',
      },
    },
    typography: {
      ...globalTheme.typography,
      fontFamily: 'Segoe UI, Malgun Gothic, sans-serif',
      button: {
        ...globalTheme.typography.button,
        textTransform: 'none',
        fontWeight: 600,
      },
    },
  }), [globalTheme]);

  const loadRows = useCallback(async () => {
    try {
      setIsLoading(true);
      setMessage(null);
      const data = await dashboardLinksApi.list();
      const loadedRows = data.map((row, index) => createClientRow(row, index));
      setRows(loadedRows);
      setOriginalRows(loadedRows);
      setSelectedCell(loadedRows.length > 0 ? { rowIndex: 0, columnId: EDITABLE_COLUMN_KEYS[0] } : null);
      setValidationErrors({});
      setIsDirty(false);
    } catch (error) {
      setMessage({ type: 'error', text: error.message || '대시보드 데이터를 불러오지 못했습니다.' });
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadRows();
  }, [loadRows]);

  useEffect(() => {
    const handleBeforeUnload = (event) => {
      if (!isDirty) {
        return;
      }

      event.preventDefault();
      event.returnValue = '';
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [isDirty]);

  const focusGridWrapper = useCallback(() => {
    gridWrapperRef.current?.focus();
  }, []);

  const commitCellValue = useCallback((rowIndex, columnId, value) => {
    const nextRows = rows.map((row, index) => (
      index === rowIndex ? { ...row, [columnId]: value } : row
    ));

    setRows(nextRows);
    syncDirtyState(nextRows);

    const clientKey = nextRows[rowIndex]?.clientKey;
    if (!clientKey) {
      return;
    }

    const errorKey = getCellErrorKey(clientKey, columnId);
    const validationError = validateCellValue(columnId, value);

    setValidationErrors((prev) => {
      if (!validationError && !prev[errorKey]) {
        return prev;
      }

      const next = { ...prev };
      if (validationError) {
        next[errorKey] = validationError;
      } else {
        delete next[errorKey];
      }
      return next;
    });
  }, [rows, syncDirtyState]);

  const deleteRow = useCallback((rowIndex) => {
    const targetRow = rows[rowIndex];
    if (!targetRow) {
      return;
    }

    const nextRows = rows.filter((_, index) => index !== rowIndex);
    setRows(nextRows);
    syncDirtyState(nextRows);
    setValidationErrors((prev) => {
      const next = { ...prev };
      Object.keys(next).forEach((key) => {
        if (key.startsWith(`${targetRow.clientKey}:`)) {
          delete next[key];
        }
      });
      return next;
    });

    if (nextRows.length === 0) {
      setSelectedCell(null);
      return;
    }

    const nextRowIndex = Math.min(rowIndex, nextRows.length - 1);
    setSelectedCell({ rowIndex: nextRowIndex, columnId: EDITABLE_COLUMN_KEYS[0] });
  }, [rows, syncDirtyState]);

  const applyClipboardMatrix = useCallback((matrix, startRowIndex, startColumnId) => {
    const startColumnIndex = EDITABLE_COLUMN_KEYS.indexOf(startColumnId);
    if (startColumnIndex === -1 || matrix.length === 0) {
      return;
    }

    const nextRows = [...rows];
    const touchedCells = [];

    while (nextRows.length < startRowIndex + matrix.length) {
      nextRows.push(createClientRow(EMPTY_ROW, nextRows.length));
    }

    matrix.forEach((pastedRow, rowOffset) => {
      const targetRowIndex = startRowIndex + rowOffset;
      const nextRow = { ...nextRows[targetRowIndex] };

      pastedRow.forEach((cellValue, columnOffset) => {
        const targetColumnId = EDITABLE_COLUMN_KEYS[startColumnIndex + columnOffset];
        if (!targetColumnId) {
          return;
        }

        nextRow[targetColumnId] = cellValue;
        touchedCells.push({
          clientKey: nextRow.clientKey,
          columnId: targetColumnId,
          value: cellValue,
        });
      });

      nextRows[targetRowIndex] = nextRow;
    });

    setRows(nextRows);
    syncDirtyState(nextRows);
    setValidationErrors((prev) => {
      const next = { ...prev };
      touchedCells.forEach(({ clientKey, columnId, value }) => {
        const errorKey = getCellErrorKey(clientKey, columnId);
        const validationError = validateCellValue(columnId, value);
        if (validationError) {
          next[errorKey] = validationError;
        } else {
          delete next[errorKey];
        }
      });
      return next;
    });
  }, [rows, syncDirtyState]);

  const handleAddRow = useCallback(() => {
    const nextRows = [...rows, createClientRow(EMPTY_ROW, rows.length)];
    const nextTarget = { rowIndex: nextRows.length - 1, columnId: EDITABLE_COLUMN_KEYS[0] };
    setRows(nextRows);
    syncDirtyState(nextRows);
    setSelectedCell(nextTarget);
    pendingEditTargetRef.current = nextTarget;
  }, [rows, syncDirtyState]);

  const handleBack = () => {
    if (isDirty && !window.confirm('저장되지 않은 변경사항이 있습니다. 나가시겠습니까?')) {
      return;
    }

    navigate('/');
  };

  const handleSave = async () => {
    try {
      setIsSaving(true);
      setMessage(null);

      const validRows = rows
        .filter(isRowComplete)
        .map((row) => ({
          dashboard_name: row.dashboard_name.trim(),
          url: row.url.trim(),
          linkname: row.linkname.trim(),
          desc: row.desc.trim(),
        }));

      const skippedCount = rows.length - validRows.length;
      const response = await dashboardLinksApi.bulkUpdate(validRows);
      const savedRows = (response.rows || []).map((row, index) => createClientRow(row, index));

      setRows(savedRows);
      setOriginalRows(savedRows);
      setSelectedCell(savedRows.length > 0 ? { rowIndex: 0, columnId: EDITABLE_COLUMN_KEYS[0] } : null);
      setValidationErrors({});
      setIsDirty(false);
      setMessage({
        type: 'success',
        text: skippedCount > 0
          ? `저장 완료: ${response.saved_count ?? savedRows.length}개 저장, ${skippedCount}개 row 제외`
          : `저장 완료: ${response.saved_count ?? savedRows.length}개 row 반영`,
      });
    } catch (error) {
      setMessage({
        type: 'error',
        text: error.response?.data?.detail || error.response?.data?.rows?.[0] || '저장 중 오류가 발생했습니다.',
      });
    } finally {
      setIsSaving(false);
    }
  };

  const columns = useMemo(() => EDITABLE_COLUMNS.map((column) => ({
    accessorKey: column.key,
    header: column.header,
    size: column.size,
    grow: column.key === 'url' ? 1.3 : 1,
    muiEditTextFieldProps: ({ cell, row }) => {
      const errorKey = getCellErrorKey(row.original.clientKey, cell.column.id);
      const nextColumnIndex = EDITABLE_COLUMN_KEYS.indexOf(cell.column.id);

      return {
        autoFocus: true,
        fullWidth: true,
        variant: 'standard',
        placeholder: column.placeholder,
        error: Boolean(validationErrors[errorKey]),
        helperText: validationErrors[errorKey] || ' ',
        required: true,
        onBlur: (event) => {
          commitCellValue(row.index, cell.column.id, event.currentTarget.value);
        },
        onKeyDown: (event) => {
          if (event.key === 'Escape') {
            event.currentTarget.blur();
            return;
          }

          if (!['Enter', 'Tab', 'ArrowUp', 'ArrowDown'].includes(event.key)) {
            return;
          }

          event.preventDefault();
          commitCellValue(row.index, cell.column.id, event.currentTarget.value);

          let targetRowIndex = row.index;
          let targetColumnIndex = nextColumnIndex;

          if (event.key === 'ArrowUp') {
            targetRowIndex = Math.max(0, row.index - 1);
          } else if (event.key === 'ArrowDown') {
            targetRowIndex = Math.min(rows.length - 1, row.index + 1);
          } else if (event.key === 'Tab') {
            if (event.shiftKey) {
              targetColumnIndex = Math.max(0, nextColumnIndex - 1);
            } else {
              targetColumnIndex = Math.min(EDITABLE_COLUMN_KEYS.length - 1, nextColumnIndex + 1);
            }
          }

          const nextTarget = {
            rowIndex: targetRowIndex,
            columnId: EDITABLE_COLUMN_KEYS[targetColumnIndex],
          };

          pendingEditTargetRef.current = nextTarget;
          setSelectedCell(nextTarget);
          event.currentTarget.blur();
        },
        sx: {
          '& .MuiInputBase-input': {
            fontSize: 13,
            lineHeight: 1.45,
            py: 0.75,
          },
          '& .MuiInputBase-root:before': {
            borderBottomColor: alpha('#374151', 0.35),
          },
          '& .MuiInputBase-root.Mui-focused:after': {
            borderBottomColor: '#374151',
          },
          '& .MuiFormHelperText-root': {
            mx: 0,
            mt: 0.25,
            fontSize: 11,
          },
        },
      };
    },
  })), [commitCellValue, rows.length, validationErrors]);

  const table = useMaterialReactTable({
    columns,
    data: rows,
    editDisplayMode: 'cell',
    enableEditing: true,
    enableCellActions: true,
    enableClickToCopy: 'context-menu',
    enableColumnActions: false,
    enableColumnResizing: true,
    enableDensityToggle: false,
    enableFullScreenToggle: false,
    enableHiding: false,
    enablePagination: false,
    enableBottomToolbar: false,
    enableTopToolbar: false,
    enableRowActions: true,
    enableRowNumbers: true,
    enableSorting: false,
    enableStickyHeader: true,
    columnResizeMode: 'onChange',
    getRowId: (row) => row.clientKey,
    layoutMode: 'grid',
    positionActionsColumn: 'last',
    initialState: {
      columnPinning: {
        left: ['mrt-row-numbers'],
        right: ['mrt-row-actions'],
      },
      density: 'compact',
    },
    displayColumnDefOptions: {
      'mrt-row-numbers': {
        header: '#',
        size: 64,
      },
      'mrt-row-actions': {
        header: '행',
        size: 74,
      },
    },
    mrtTheme: () => ({
      baseBackgroundColor: '#ffffff',
      draggingBorderColor: '#374151',
      menuBackgroundColor: '#ffffff',
      pinnedRowBackgroundColor: alpha('#6b7280', 0.06),
      selectedRowBackgroundColor: alpha('#374151', 0.08),
    }),
    muiTablePaperProps: {
      elevation: 0,
      sx: {
        borderRadius: 1,
        border: '1px solid #e5e7eb',
        boxShadow: '0 1px 3px rgba(0, 0, 0, 0.1), 0 1px 2px rgba(0, 0, 0, 0.06)',
        overflow: 'hidden',
      },
    },
    muiTableContainerProps: {
      sx: {
        maxHeight: 'calc(100vh - 320px)',
      },
    },
    muiTableHeadCellProps: ({ column }) => ({
      sx: {
        backgroundColor: column.id.startsWith('mrt-') ? '#f3f4f6' : '#f9fafb',
        borderBottom: '1px solid #e5e7eb',
        borderRight: '1px solid #e5e7eb',
        color: '#111827',
        fontSize: 13,
        fontWeight: 600,
        minHeight: 42,
        px: 1.25,
        py: 0.75,
        '& .Mui-TableHeadCell-Content': {
          justifyContent: 'flex-start',
        },
      },
    }),
    muiTableBodyRowProps: ({ row }) => ({
      hover: false,
      sx: {
        '&:hover td': {
          backgroundColor: alpha('#6b7280', 0.04),
        },
        ...(Object.keys(validationErrors).some((key) => key.startsWith(`${row.original.clientKey}:`))
          ? {
              '& td': {
                backgroundColor: alpha('#ef4444', 0.06),
              },
            }
          : {}),
        ...(!isRowComplete(row.original)
          ? {
              '& td': {
                backgroundColor: alpha('#f59e0b', 0.06),
              },
            }
          : {}),
      },
    }),
    muiTableBodyCellProps: ({ cell, row, table: tableInstance }) => {
      const isEditable = EDITABLE_COLUMN_KEYS.includes(cell.column.id);
      const isSelected = Boolean(
        selectedCell
        && selectedCell.rowIndex === row.index
        && selectedCell.columnId === cell.column.id,
      );
      const errorKey = getCellErrorKey(row.original.clientKey, cell.column.id);
      const hasError = Boolean(validationErrors[errorKey]);

      return {
        onClick: isEditable ? () => {
          setSelectedCell({ rowIndex: row.index, columnId: cell.column.id });
          focusGridWrapper();
        } : undefined,
        onDoubleClick: isEditable ? () => {
          setSelectedCell({ rowIndex: row.index, columnId: cell.column.id });
          focusGridWrapper();
          tableInstance.setEditingCell(cell);
        } : undefined,
        sx: {
          backgroundColor: isSelected ? alpha('#374151', 0.08) : '#ffffff',
          borderBottom: '1px solid #e5e7eb',
          borderRight: '1px solid #e5e7eb',
          boxShadow: isSelected
            ? 'inset 0 0 0 2px #374151'
            : hasError
              ? `inset 0 0 0 1px ${alpha('#dc2626', 0.65)}`
              : 'none',
          cursor: isEditable ? 'cell' : 'default',
          fontSize: 13,
          minHeight: 38,
          px: 1.25,
          py: 0.5,
          verticalAlign: 'top',
        },
      };
    },
    renderRowActions: ({ row }) => (
      <Tooltip title="행 삭제">
        <IconButton
          aria-label="행 삭제"
          color="error"
          size="small"
          onClick={() => deleteRow(row.index)}
        >
          <Trash2 size={14} />
        </IconButton>
      </Tooltip>
    ),
  });

  const openEditingCellAt = useCallback((rowIndex, columnId) => {
    const targetRow = table.getRowModel().rows[rowIndex];
    if (!targetRow) {
      return;
    }

    const targetCell = targetRow.getAllCells().find((cell) => cell.column.id === columnId);
    if (!targetCell) {
      return;
    }

    table.setEditingCell(targetCell);
  }, [table]);

  useEffect(() => {
    const nextTarget = pendingEditTargetRef.current;
    if (!nextTarget) {
      return;
    }

    pendingEditTargetRef.current = null;
    requestAnimationFrame(() => {
      openEditingCellAt(nextTarget.rowIndex, nextTarget.columnId);
    });
  }, [openEditingCellAt, selectedCell]);

  const handleGridKeyDown = useCallback((event) => {
    if (!selectedCell || table.getState().editingCell) {
      return;
    }

    const currentColumnIndex = EDITABLE_COLUMN_KEYS.indexOf(selectedCell.columnId);
    if (currentColumnIndex === -1) {
      return;
    }

    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'v') {
      return;
    }

    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'c') {
      event.preventDefault();
      const cellValue = rows[selectedCell.rowIndex]?.[selectedCell.columnId] ?? '';
      navigator.clipboard.writeText(cellValue).catch(() => {});
      return;
    }

    if (event.key === 'Enter' || event.key === 'F2') {
      event.preventDefault();
      openEditingCellAt(selectedCell.rowIndex, selectedCell.columnId);
      return;
    }

    if (event.key === 'Delete' || event.key === 'Backspace') {
      event.preventDefault();
      commitCellValue(selectedCell.rowIndex, selectedCell.columnId, '');
      return;
    }

    const nextSelection = {
      rowIndex: selectedCell.rowIndex,
      columnId: selectedCell.columnId,
    };

    if (event.key === 'ArrowUp') {
      nextSelection.rowIndex = Math.max(0, selectedCell.rowIndex - 1);
    } else if (event.key === 'ArrowDown') {
      nextSelection.rowIndex = Math.min(rows.length - 1, selectedCell.rowIndex + 1);
    } else if (event.key === 'ArrowLeft') {
      nextSelection.columnId = EDITABLE_COLUMN_KEYS[Math.max(0, currentColumnIndex - 1)];
    } else if (event.key === 'ArrowRight' || event.key === 'Tab') {
      nextSelection.columnId = EDITABLE_COLUMN_KEYS[Math.min(EDITABLE_COLUMN_KEYS.length - 1, currentColumnIndex + 1)];
    } else {
      return;
    }

    event.preventDefault();
    setSelectedCell(nextSelection);
  }, [commitCellValue, openEditingCellAt, rows.length, selectedCell, table]);

  const handleGridPaste = useCallback((event) => {
    if (!selectedCell || table.getState().editingCell) {
      return;
    }

    const pastedText = event.clipboardData?.getData('text');
    if (!pastedText) {
      return;
    }

    const matrix = parseClipboardMatrix(pastedText);
    if (matrix.length === 0) {
      return;
    }

    event.preventDefault();
    applyClipboardMatrix(matrix, selectedCell.rowIndex, selectedCell.columnId);
  }, [applyClipboardMatrix, selectedCell, table]);

  const incompleteRowsCount = rows.filter((row) => !isRowComplete(row)).length;

  if (isLoading) {
    return (
      <Box sx={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 2 }}>
        <CircularProgress size={32} />
        <Typography color="text.secondary">대시보드 링크를 불러오는 중...</Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ minHeight: '100vh', background: '#f3f4f6', p: 4 }}>
      <Box sx={{ maxWidth: 1600, mx: 'auto' }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={2} sx={{ mb: 3, flexWrap: 'wrap' }}>
          <Stack direction="row" alignItems="center" spacing={2}>
            <Button variant="outlined" color="inherit" startIcon={<ArrowLeft size={16} />} onClick={handleBack}>
              돌아가기
            </Button>
            <Box>
              <Typography variant="h5" sx={{ fontWeight: 800 }}>대시보드 링크 관리</Typography>
              <Typography variant="body2" color="text.secondary">
                /dashboard 커맨드 응답에 사용되는 데이터를 편집합니다.
              </Typography>
            </Box>
          </Stack>

          <Stack direction="row" spacing={1} alignItems="center">
            {isDirty && <Chip color="warning" label="저장 필요" />}
            {incompleteRowsCount > 0 && <Chip color="default" label={`미완성 ${incompleteRowsCount}행`} />}
            <Button variant="outlined" startIcon={<Plus size={16} />} onClick={handleAddRow}>
              빈 행 추가
            </Button>
            <Button variant="contained" startIcon={<Save size={16} />} onClick={handleSave} disabled={isSaving || !isDirty}>
              {isSaving ? '저장 중...' : '테이블 저장'}
            </Button>
          </Stack>
        </Stack>

        {message && (
          <Alert severity={message.type === 'success' ? 'success' : 'error'} sx={{ mb: 2 }}>
            {message.text}
          </Alert>
        )}

        <Alert severity="info" sx={{ mb: 2 }}>
          모든 컬럼 값이 채워진 row만 저장됩니다. 저장 시 현재 row 순서 기준으로 번호가 다시 생성됩니다.
        </Alert>

        <Alert severity="info" variant="outlined" sx={{ mb: 2, borderColor: '#d1d5db', backgroundColor: '#ffffff' }}>
          엑셀형 UX: 셀 클릭 선택, 더블클릭/Enter 편집, 방향키 이동, Delete 비우기, Ctrl+C 복사, Ctrl+V 붙여넣기
        </Alert>

        <ThemeProvider theme={tableTheme}>
          <Box
            ref={gridWrapperRef}
            onKeyDown={handleGridKeyDown}
            onPaste={handleGridPaste}
            sx={{
              outline: 'none',
            }}
            tabIndex={0}
          >
            <MaterialReactTable table={table} />
          </Box>
        </ThemeProvider>
      </Box>
    </Box>
  );
};

export default DashboardTablePage;