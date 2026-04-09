import csv
import hashlib
import io
import os
from copy import deepcopy
from typing import Optional

DEFAULT_HEADERS = [
    '요청부서_현장명', '요청자', '직무', '시스템', 'Web_App_구분', '요청일', '요청_주차',
    '유형', '문의내용', '시스템PE', '조치시작일', '조치완료일', '조치내용', '완료여부',
]

DEFAULT_COLUMN_WIDTH = 73

ROW_CONFIG_KEYS = {'rowlen', 'rowhidden', 'customHeight', 'rowReadOnly'}
COLUMN_CONFIG_KEYS = {'columnlen', 'colhidden', 'customWidth', 'colReadOnly'}


def has_structural_ops(ops: list[dict]) -> bool:
    return any(op.get('op') in {'insertRowCol', 'deleteRowCol', 'addSheet', 'deleteSheet'} for op in (ops or []))


def _text_cell(value: Optional[str], extra: dict = None) -> Optional[dict]:
    if value is None:
        return None
    s = str(value).strip()
    cell = {
        'v': s if s else None,
        'm': s,
        'ct': {'fa': '@', 't': 'inlineStr'},
        'ht': 0,
        'vt': 0,
        'tb': '2',
    }
    if extra:
        cell.update(extra)
    return cell


def _header_cell(value: str) -> dict:
    return {
        'v': value,
        'm': value,
        'ct': {'fa': '@', 't': 'inlineStr'},
        'bl': 1,
        'fc': '#FFFFFF',
        'bg': '#4472C4',
        'ht': 0,
        'vt': 0,
    }


def _normalize_header_value(value, index: int) -> str:
    text = '' if value is None else str(value).strip()
    return text or f'Column {index + 1}'


def _normalize_headers(headers: list | None, target_width: int = 0) -> list[str]:
    source = list(headers or [])
    width = max(len(source), target_width, 0)
    if width == 0:
        return deepcopy(DEFAULT_HEADERS)
    return [_normalize_header_value(source[idx] if idx < len(source) else None, idx) for idx in range(width)]


def _default_column_width(index: int) -> int:
    return DEFAULT_COLUMN_WIDTH


def _default_column_config(column_count: int) -> dict:
    return {str(index): _default_column_width(index) for index in range(column_count)}


def _build_workbook_from_rows(headers: list | None, rows: list[list]) -> list:
    max_width = max((len(row) for row in rows), default=0)
    normalized_headers = _normalize_headers(headers, max_width)
    column_count = max(len(normalized_headers), max_width, 1)
    normalized_headers = _normalize_headers(normalized_headers, column_count)

    celldata = []

    for column, header in enumerate(normalized_headers):
        celldata.append({'r': 0, 'c': column, 'v': _header_cell(header)})

    for row_index, row_values in enumerate(rows, start=1):
        for column in range(column_count):
            raw = row_values[column] if column < len(row_values) else ''
            value = raw.strip() if isinstance(raw, str) else raw
            cell = _text_cell(value if value else None)
            if cell is not None:
                celldata.append({'r': row_index, 'c': column, 'v': cell})

    total_rows = max(len(rows) + 101, 400)

    sheet = {
        'id': 'pe-log-main',
        'name': 'PE 로그',
        'order': 0,
        'status': 1,
        'row': total_rows,
        'column': column_count,
        'celldata': celldata,
        'showGridLines': 1,
        'defaultRowHeight': 22,
        'defaultColWidth': DEFAULT_COLUMN_WIDTH,
        'config': {},
        'frozen': {
            'type': 'row',
            'range': {'row_focus': 0, 'column_focus': 0},
        },
    }

    return [sheet]


def _read_csv_rows_from_text(csv_text: str) -> tuple[list[str], list[list[str]]]:
    parsed_rows = list(csv.reader(io.StringIO(csv_text)))
    if not parsed_rows:
        return deepcopy(DEFAULT_HEADERS), []

    max_width = max((len(row) for row in parsed_rows), default=0)
    headers = _normalize_headers(parsed_rows[0], max_width)
    data_rows = []
    for raw_row in parsed_rows[1:]:
        padded = [raw_row[index] if index < len(raw_row) else '' for index in range(len(headers))]
        data_rows.append(padded)
    return headers, data_rows


def csv_to_workbook(csv_path: str) -> list:
    try:
        with open(csv_path, encoding='utf-8-sig') as file:
            headers, rows = _read_csv_rows_from_text(file.read())
            return _build_workbook_from_rows(headers, rows)
    except FileNotFoundError:
        return _build_workbook_from_rows(DEFAULT_HEADERS, [])


def csv_upload_to_workbook(uploaded_file) -> list:
    csv_text = uploaded_file.read().decode('utf-8-sig')
    headers, rows = _read_csv_rows_from_text(csv_text)
    return _build_workbook_from_rows(headers, rows)


def _cell_display_value(cell: Optional[dict]) -> str:
    if not cell:
        return ''
    if cell.get('m') is not None:
        return str(cell['m'])
    value = cell.get('v')
    return '' if value is None else str(value)


def _cell_display_value_from_any(cell) -> str:
    if cell is None:
        return ''
    if isinstance(cell, dict):
        return _cell_display_value(cell)
    return str(cell)


def _sheet_to_row_matrix(sheet: dict) -> list[list[str]]:
    data = sheet.get('data')
    if isinstance(data, list):
        rows = []
        for row in data:
            if not isinstance(row, list):
                rows.append([])
                continue
            rows.append([_cell_display_value_from_any(cell) for cell in row])
        return rows

    celldata = sheet.get('celldata', [])
    cell_map = {}
    max_row = 0
    max_col = 0

    for item in celldata:
        row = item.get('r')
        col = item.get('c')
        if row is None or col is None:
            continue
        cell_map[(row, col)] = _cell_display_value(item.get('v'))
        max_row = max(max_row, row)
        max_col = max(max_col, col)

    rows = []
    for row_idx in range(max_row + 1):
        rows.append([cell_map.get((row_idx, col_idx), '') for col_idx in range(max_col + 1)])
    return rows


def get_sheet_headers(sheet: dict) -> list[str]:
    rows = _sheet_to_row_matrix(sheet)
    if not rows:
        return _normalize_headers([], sheet.get('column') or 0)
    return _normalize_headers(rows[0], sheet.get('column') or len(rows[0]))


def _sheet_to_data_matrix(sheet: dict) -> list[list[dict | None]]:
    data = sheet.get('data')
    if isinstance(data, list):
        return deepcopy(data)

    row_count = sheet.get('row') or 0
    col_count = sheet.get('column') or 0
    matrix = [[None for _ in range(col_count)] for _ in range(row_count)]
    for item in sheet.get('celldata', []):
        row = item.get('r')
        col = item.get('c')
        payload = item.get('v')
        if row is None or col is None:
            continue
        while row >= len(matrix):
            matrix.append([None for _ in range(col_count or 1)])
        while col >= len(matrix[row]):
            for existing_row in matrix:
                existing_row.extend([None] * (col - len(existing_row) + 1))
        matrix[row][col] = deepcopy(payload)
    return matrix


def _normalize_cell_payload(cell):
    if cell is None:
        return None
    if isinstance(cell, dict):
        return deepcopy(cell)

    if isinstance(cell, bool):
        return {
            'v': cell,
            'm': 'TRUE' if cell else 'FALSE',
            'ct': {'fa': 'General', 't': 'b'},
        }

    if isinstance(cell, (int, float)):
        return {
            'v': cell,
            'm': str(cell),
            'ct': {'fa': 'General', 't': 'n'},
        }

    return {
        'v': str(cell),
        'm': str(cell),
        'ct': {'fa': '@', 't': 'inlineStr'},
    }


def _data_matrix_to_celldata(data: list) -> list[dict]:
    celldata = []
    for row_idx, row in enumerate(data):
        if not isinstance(row, list):
            continue
        for col_idx, cell in enumerate(row):
            payload = _normalize_cell_payload(cell)
            if payload is None:
                continue
            celldata.append({'r': row_idx, 'c': col_idx, 'v': payload})
    return celldata


def _sanitize_config(config) -> dict:
    if not isinstance(config, dict):
        return {}

    allowed_map_fields = {
        'merge',
        'rowlen',
        'columnlen',
        'rowhidden',
        'colhidden',
        'customHeight',
        'customWidth',
        'authority',
        'rowReadOnly',
        'colReadOnly',
        'borderInfo',
    }
    sanitized = {}
    for key in allowed_map_fields:
        value = config.get(key)
        if isinstance(value, (dict, list)):
            sanitized[key] = deepcopy(value)
    return sanitized


def normalize_workbook_data(workbook_data: list) -> list:
    normalized_sheets = []

    for index, raw_sheet in enumerate(workbook_data or []):
        if not isinstance(raw_sheet, dict):
            continue

        data = raw_sheet.get('data')
        if isinstance(data, list):
            celldata = _data_matrix_to_celldata(data)
            inferred_row = len(data)
            inferred_col = max((len(row) for row in data if isinstance(row, list)), default=0)
        else:
            celldata = []
            inferred_row = 0
            inferred_col = 0
            for item in raw_sheet.get('celldata', []):
                row = item.get('r')
                col = item.get('c')
                payload = _normalize_cell_payload(item.get('v'))
                if row is None or col is None or payload is None:
                    continue
                celldata.append({'r': row, 'c': col, 'v': payload})
                inferred_row = max(inferred_row, row + 1)
                inferred_col = max(inferred_col, col + 1)

        normalized_sheet = {
            'id': raw_sheet.get('id') or f'pe-log-sheet-{index}',
            'name': raw_sheet.get('name') or f'Sheet{index + 1}',
            'order': raw_sheet.get('order', index),
            'status': raw_sheet.get('status', 1 if index == 0 else 0),
            'row': max(raw_sheet.get('row') or 0, inferred_row, 1),
            'column': max(raw_sheet.get('column') or 0, inferred_col, 1),
            'celldata': celldata,
            'showGridLines': raw_sheet.get('showGridLines', 1),
            'defaultRowHeight': raw_sheet.get('defaultRowHeight', 22),
            'defaultColWidth': raw_sheet.get('defaultColWidth', DEFAULT_COLUMN_WIDTH),
            'config': _sanitize_config(raw_sheet.get('config')),
        }

        if raw_sheet.get('hide') is not None:
            normalized_sheet['hide'] = raw_sheet.get('hide')
        if raw_sheet.get('color'):
            normalized_sheet['color'] = raw_sheet.get('color')
        if raw_sheet.get('addRows') is not None:
            normalized_sheet['addRows'] = raw_sheet.get('addRows')
        if raw_sheet.get('frozen'):
            normalized_sheet['frozen'] = deepcopy(raw_sheet.get('frozen'))

        normalized_sheets.append(normalized_sheet)

    return normalized_sheets


def get_cell_payload(workbook_data: list, sheet_id: str, row: int, column: int):
    for sheet in workbook_data or []:
        if not isinstance(sheet, dict):
            continue
        if (sheet.get('id') or 'pe-log-main') != sheet_id:
            continue

        data = sheet.get('data')
        if isinstance(data, list):
            if row < len(data) and isinstance(data[row], list) and column < len(data[row]):
                return deepcopy(data[row][column])
            return None

        for item in sheet.get('celldata', []):
            if item.get('r') == row and item.get('c') == column:
                return deepcopy(item.get('v'))
        return None
    return None


def get_cell_display_value(cell) -> str:
    return _cell_display_value_from_any(cell)


def _ensure_matrix_bounds(matrix: list, row: int, column: int):
    target_columns = max(column + 1, max((len(item) for item in matrix if isinstance(item, list)), default=0), 1)
    while row >= len(matrix):
        matrix.append([None for _ in range(target_columns)])

    for existing_row in matrix:
        if not isinstance(existing_row, list):
            continue
        while column >= len(existing_row):
            existing_row.append(None)


def _ensure_minimum_matrix_shape(matrix: list, min_rows: int = 1, min_columns: int = 1):
    target_columns = max(max((len(item) for item in matrix if isinstance(item, list)), default=0), min_columns, 1)
    while len(matrix) < max(min_rows, 1):
        matrix.append([None for _ in range(target_columns)])
    for existing_row in matrix:
        if not isinstance(existing_row, list):
            continue
        while len(existing_row) < target_columns:
            existing_row.append(None)


def _set_nested_value(target: dict, path: list, value, remove: bool = False):
    current = target
    for key in path[:-1]:
        if key not in current or not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]

    final_key = path[-1]
    if remove:
        current.pop(final_key, None)
    else:
        current[final_key] = deepcopy(value)


def _shift_indexed_config_map(config: dict, key: str, start_index: int, delta: int, delete_count: int = 0):
    value = config.get(key)
    if not isinstance(value, dict):
        return

    shifted = {}
    for raw_index, entry in value.items():
        try:
            index = int(raw_index)
        except (TypeError, ValueError):
            shifted[raw_index] = deepcopy(entry)
            continue

        if delta < 0 and start_index <= index < start_index + delete_count:
            continue
        if index >= start_index:
            index += delta
        shifted[str(index)] = deepcopy(entry)
    config[key] = shifted


def _apply_insert_row(sheet: dict, index: int, count: int):
    data = sheet['data']
    column_count = max(sheet.get('column') or 0, max((len(row) for row in data if isinstance(row, list)), default=0), 1)
    insert_at = max(0, min(index, len(data)))
    for _ in range(count):
        data.insert(insert_at, [None for _ in range(column_count)])
    for key in ROW_CONFIG_KEYS:
        _shift_indexed_config_map(sheet['config'], key, insert_at, count)
    sheet['row'] = len(data)


def _apply_delete_row(sheet: dict, index: int, count: int):
    data = sheet['data']
    if not data:
        _ensure_minimum_matrix_shape(data)
    delete_at = max(0, min(index, len(data) - 1))
    del data[delete_at:delete_at + count]
    _ensure_minimum_matrix_shape(data)
    for key in ROW_CONFIG_KEYS:
        _shift_indexed_config_map(sheet['config'], key, delete_at, -count, delete_count=count)
    sheet['row'] = len(data)


def _apply_insert_column(sheet: dict, index: int, count: int):
    data = sheet['data']
    _ensure_minimum_matrix_shape(data)
    current_columns = max(sheet.get('column') or 0, max((len(row) for row in data if isinstance(row, list)), default=0), 1)
    insert_at = max(0, min(index, current_columns))
    for row in data:
        if not isinstance(row, list):
            continue
        for _ in range(count):
            row.insert(insert_at, None)
    for key in COLUMN_CONFIG_KEYS:
        _shift_indexed_config_map(sheet['config'], key, insert_at, count)
    columnlen = sheet['config'].setdefault('columnlen', {})
    for offset in range(count):
        columnlen[str(insert_at + offset)] = _default_column_width(insert_at + offset)
    sheet['column'] = max((len(row) for row in data if isinstance(row, list)), default=current_columns + count)


def _apply_delete_column(sheet: dict, index: int, count: int):
    data = sheet['data']
    _ensure_minimum_matrix_shape(data)
    current_columns = max(sheet.get('column') or 0, max((len(row) for row in data if isinstance(row, list)), default=0), 1)
    delete_at = max(0, min(index, current_columns - 1))
    for row in data:
        if not isinstance(row, list):
            continue
        del row[delete_at:delete_at + count]
        if not row:
            row.append(None)
    for key in COLUMN_CONFIG_KEYS:
        _shift_indexed_config_map(sheet['config'], key, delete_at, -count, delete_count=count)
    _ensure_minimum_matrix_shape(data)
    sheet['column'] = max((len(row) for row in data if isinstance(row, list)), default=1)


def _apply_structural_op(sheet: dict, op: dict):
    value = op.get('value') or {}
    if not isinstance(value, dict):
        raise ValueError(f'Invalid structural op payload: {op}')

    operation_type = value.get('type')

    if op.get('op') == 'insertRowCol':
        index = int(value.get('index', 0))
        count = max(int(value.get('count', 1)), 1)
        if operation_type == 'row':
            _apply_insert_row(sheet, index, count)
            return
        if operation_type == 'column':
            _apply_insert_column(sheet, index, count)
            return
    elif op.get('op') == 'deleteRowCol':
        start = int(value.get('start', value.get('index', 0)))
        end = int(value.get('end', start + max(int(value.get('count', 1)), 1) - 1))
        count = max(end - start + 1, 1)
        if operation_type == 'row':
            _apply_delete_row(sheet, start, count)
            return
        if operation_type == 'column':
            _apply_delete_column(sheet, start, count)
            return

    raise ValueError(f'Unsupported structural op: {op}')


def apply_ops_to_workbook_data(workbook_data: list, ops: list[dict]) -> list:
    runtime_sheets = []
    for sheet in normalize_workbook_data(workbook_data):
        runtime_sheet = deepcopy(sheet)
        runtime_sheet['data'] = _sheet_to_data_matrix(sheet)
        runtime_sheet.pop('celldata', None)
        runtime_sheet['config'] = deepcopy(runtime_sheet.get('config') or {})
        _ensure_minimum_matrix_shape(runtime_sheet['data'])
        runtime_sheets.append(runtime_sheet)

    sheet_index = {(sheet.get('id') or f'pe-log-sheet-{idx}'): idx for idx, sheet in enumerate(runtime_sheets)}

    for op in ops or []:
        op_name = op.get('op')
        sheet_id = op.get('id') or 'pe-log-main'

        if op_name in {'addSheet', 'deleteSheet'}:
            raise ValueError(f'Unsupported structural op: {op_name}')

        if sheet_id not in sheet_index:
            raise ValueError(f'Unknown sheet id: {sheet_id}')
        sheet = runtime_sheets[sheet_index[sheet_id]]
        path = op.get('path') or []

        if op_name in {'insertRowCol', 'deleteRowCol'}:
            _apply_structural_op(sheet, op)
            continue

        if len(path) >= 3 and path[0] == 'data' and isinstance(path[1], int) and isinstance(path[2], int):
            row = path[1]
            column = path[2]
            _ensure_matrix_bounds(sheet['data'], row, column)

            if len(path) == 3:
                if op_name == 'remove':
                    sheet['data'][row][column] = None
                else:
                    sheet['data'][row][column] = _normalize_cell_payload(op.get('value'))
                continue

            cell = sheet['data'][row][column]
            if cell is None or not isinstance(cell, dict):
                cell = {}
                sheet['data'][row][column] = cell
            _set_nested_value(cell, path[3:], op.get('value'), remove=op_name == 'remove')
            continue

        if path:
            if op_name == 'remove':
                current = sheet
                for key in path[:-1]:
                    current = current.get(key, {})
                    if not isinstance(current, dict):
                        current = {}
                        break
                if isinstance(current, dict):
                    current.pop(path[-1], None)
            else:
                current = sheet
                for key in path[:-1]:
                    if key not in current or not isinstance(current[key], dict):
                        current[key] = {}
                    current = current[key]
                current[path[-1]] = deepcopy(op.get('value'))

    return runtime_sheets


def is_workbook_schema_valid(workbook_data: list) -> bool:
    normalized = normalize_workbook_data(workbook_data)
    if not normalized:
        return False
    sheet = normalized[0]
    return (sheet.get('row') or 0) >= 1 and (sheet.get('column') or 0) >= 1


def workbook_to_csv_bytes(workbook_data: list) -> bytes:
    sheet = workbook_data[0] if workbook_data else {}
    headers = get_sheet_headers(sheet)
    rows = _sheet_to_row_matrix(sheet)

    output = io.StringIO(newline='')
    writer = csv.writer(output, quoting=csv.QUOTE_ALL, lineterminator='\r\n')
    writer.writerow(headers)

    header_width = len(headers)
    for row in rows[1:]:
        normalized_row = [(row[col_idx] if col_idx < len(row) else '') for col_idx in range(header_width)]
        if any(str(value).strip() for value in normalized_row):
            writer.writerow(normalized_row)

    return output.getvalue().encode('utf-8-sig')


def write_workbook_csv(csv_path: str, workbook_data: list) -> None:
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    with open(csv_path, 'wb') as file:
        file.write(workbook_to_csv_bytes(workbook_data))


def compute_csv_checksum(csv_path: str) -> str:
    if not os.path.exists(csv_path):
        return ''
    with open(csv_path, 'rb') as file:
        return hashlib.md5(file.read()).hexdigest()
