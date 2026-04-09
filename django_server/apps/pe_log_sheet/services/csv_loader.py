import csv
import hashlib
import io
import os
from copy import deepcopy
from typing import Optional

HEADERS = [
    '요청부서_현장명', '요청자', '직무', '시스템', 'Web_App_구분', '요청일', '요청_주차',
    '유형', '문의내용', '시스템PE', '조치시작일', '조치완료일', '조치내용', '완료여부',
]

COLUMN_WIDTHS = {
    0: 140,   # 요청부서_현장명
    1: 100,   # 요청자
    2: 90,    # 직무
    3: 120,   # 시스템
    4: 100,   # Web_App_구분
    5: 100,   # 요청일
    6: 100,   # 요청_주차
    7: 140,   # 유형
    8: 320,   # 문의내용
    9: 100,   # 시스템PE
    10: 100,  # 조치시작일
    11: 100,  # 조치완료일
    12: 320,  # 조치내용
    13: 80,   # 완료여부
}


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
        'tb': '2',  # word wrap
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


def _build_workbook_from_rows(rows: list[dict]) -> list:
    celldata = []

    for c, header in enumerate(HEADERS):
        celldata.append({'r': 0, 'c': c, 'v': _header_cell(header)})

    row_idx = 1
    for row in rows:
        for c, col in enumerate(HEADERS):
            raw = row.get(col, '')
            val = raw.strip() if isinstance(raw, str) else raw
            cell = _text_cell(val if val else None)
            if cell is not None:
                celldata.append({'r': row_idx, 'c': c, 'v': cell})
        row_idx += 1

    total_rows = max(row_idx + 100, 400)

    sheet = {
        'id': 'pe-log-main',
        'name': 'PE 로그',
        'order': 0,
        'status': 1,
        'row': total_rows,
        'column': len(HEADERS),
        'celldata': celldata,
        'showGridLines': 1,
        'defaultRowHeight': 22,
        'defaultColWidth': 100,
        'config': {
            'columnlen': {str(c): w for c, w in COLUMN_WIDTHS.items()},
        },
        'frozen': {
            'type': 'row',
            'range': {'row_focus': 0, 'column_focus': 0},
        },
    }

    return [sheet]


def _read_csv_rows_from_text(csv_text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(csv_text))
    if reader.fieldnames != HEADERS:
        raise ValueError('CSV 헤더가 PE Log Sheet 형식과 일치하지 않습니다.')
    return [row for row in reader]


def csv_to_workbook(csv_path: str) -> list:
    """Convert PE log CSV to FortuneSheet workbook_data (list of Sheet dicts)."""
    try:
        with open(csv_path, encoding='utf-8-sig') as f:
            return _build_workbook_from_rows(_read_csv_rows_from_text(f.read()))
    except FileNotFoundError:
        return _build_workbook_from_rows([])


def csv_upload_to_workbook(uploaded_file) -> list:
    csv_text = uploaded_file.read().decode('utf-8-sig')
    return _build_workbook_from_rows(_read_csv_rows_from_text(csv_text))


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
            'defaultColWidth': raw_sheet.get('defaultColWidth', 100),
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


def apply_ops_to_workbook_data(workbook_data: list, ops: list[dict]) -> list:
    runtime_sheets = []
    for sheet in normalize_workbook_data(workbook_data):
        runtime_sheet = deepcopy(sheet)
        runtime_sheet['data'] = _sheet_to_data_matrix(sheet)
        runtime_sheet.pop('celldata', None)
        runtime_sheets.append(runtime_sheet)

    sheet_index = {(sheet.get('id') or f'pe-log-sheet-{idx}'): idx for idx, sheet in enumerate(runtime_sheets)}

    for op in ops or []:
        op_name = op.get('op')
        if op_name in {'insertRowCol', 'deleteRowCol', 'addSheet', 'deleteSheet'}:
            raise ValueError(f'Unsupported structural op: {op_name}')

        sheet_id = op.get('id') or 'pe-log-main'
        if sheet_id not in sheet_index:
            raise ValueError(f'Unknown sheet id: {sheet_id}')
        sheet = runtime_sheets[sheet_index[sheet_id]]
        path = op.get('path') or []

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
    if not workbook_data:
        return False
    sheet = normalize_workbook_data(workbook_data)[0] if normalize_workbook_data(workbook_data) else {}
    if sheet.get('column') != len(HEADERS):
        return False
    rows = _sheet_to_row_matrix(sheet)
    if not rows:
        return False
    header_row = rows[0]
    return header_row[:len(HEADERS)] == HEADERS


def workbook_to_csv_bytes(workbook_data: list) -> bytes:
    sheet = workbook_data[0] if workbook_data else {}
    output = io.StringIO(newline='')
    writer = csv.writer(output, quoting=csv.QUOTE_ALL, lineterminator='\r\n')
    writer.writerow(HEADERS)

    rows = _sheet_to_row_matrix(sheet)
    for row in rows[1:]:
        row = [(row[col_idx] if col_idx < len(row) else '') for col_idx in range(len(HEADERS))]
        if any(str(value).strip() for value in row):
            writer.writerow(row)

    return output.getvalue().encode('utf-8-sig')


def write_workbook_csv(csv_path: str, workbook_data: list) -> None:
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    with open(csv_path, 'wb') as f:
        f.write(workbook_to_csv_bytes(workbook_data))


def compute_csv_checksum(csv_path: str) -> str:
    if not os.path.exists(csv_path):
        return ''
    with open(csv_path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()
