import csv
import hashlib
import io
import os
from typing import Optional

HEADERS = [
    '직무', '시스템', 'Web_App_구분', '요청일', '요청_주차',
    '유형', '문의내용', '시스템PE', '조치시작일', '조치완료일',
    '조치내용', '완료여부',
]

COLUMN_WIDTHS = {
    0: 80,    # 직무
    1: 120,   # 시스템
    2: 100,   # Web_App_구분
    3: 100,   # 요청일
    4: 100,   # 요청_주차
    5: 140,   # 유형
    6: 280,   # 문의내용
    7: 100,   # 시스템PE
    8: 100,   # 조치시작일
    9: 100,   # 조치완료일
    10: 280,  # 조치내용
    11: 80,   # 완료여부
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


def workbook_to_csv_bytes(workbook_data: list) -> bytes:
    sheet = workbook_data[0] if workbook_data else {}
    celldata = sheet.get('celldata', [])
    cell_map = {}
    max_row = 0

    for item in celldata:
        row = item.get('r')
        col = item.get('c')
        if row is None or col is None:
            continue
        cell_value = _cell_display_value(item.get('v'))
        cell_map[(row, col)] = cell_value
        if row > 0 and cell_value.strip():
            max_row = max(max_row, row)

    output = io.StringIO(newline='')
    writer = csv.writer(output, quoting=csv.QUOTE_ALL, lineterminator='\r\n')
    writer.writerow(HEADERS)

    for row_idx in range(1, max_row + 1):
        row = [cell_map.get((row_idx, col_idx), '') for col_idx in range(len(HEADERS))]
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
