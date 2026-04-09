import csv
import hashlib
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


def csv_to_workbook(csv_path: str) -> list:
    """Convert PE log CSV to FortuneSheet workbook_data (list of Sheet dicts)."""
    celldata = []

    for c, header in enumerate(HEADERS):
        celldata.append({'r': 0, 'c': c, 'v': _header_cell(header)})

    row_idx = 1
    try:
        with open(csv_path, encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                for c, col in enumerate(HEADERS):
                    raw = row.get(col, '')
                    val = raw.strip() if raw else None
                    cell = _text_cell(val if val else None)
                    if cell is not None:
                        celldata.append({'r': row_idx, 'c': c, 'v': cell})
                row_idx += 1
    except FileNotFoundError:
        pass

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


def compute_csv_checksum(csv_path: str) -> str:
    if not os.path.exists(csv_path):
        return ''
    with open(csv_path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()
