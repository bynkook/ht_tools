from copy import deepcopy

from .csv_loader import (
    apply_ops_to_workbook_data,
    get_cell_display_value,
    get_cell_payload,
    normalize_workbook_data,
)


STRUCTURAL_OPS = {'insertRowCol', 'deleteRowCol', 'addSheet', 'deleteSheet'}


def _cell_address(row: int, column: int) -> str:
    label = ''
    current = column
    while True:
        current, remainder = divmod(current, 26)
        label = chr(65 + remainder) + label
        if current == 0:
            break
        current -= 1
    return f'{label}{row + 1}'


def _extract_touched_cells(ops: list[dict]) -> dict:
    touched = {}
    structural_ops = []

    for op in ops or []:
        op_name = op.get('op')
        path = op.get('path') or []
        sheet_id = op.get('id') or 'pe-log-main'

        if op_name in STRUCTURAL_OPS:
            structural_ops.append({
                'sheet_id': sheet_id,
                'conflict_type': 'structural',
                'operation': op_name,
            })
            continue

        if len(path) >= 3 and path[0] == 'data' and isinstance(path[1], int) and isinstance(path[2], int):
            key = (sheet_id, path[1], path[2])
            touched[key] = {
                'sheet_id': sheet_id,
                'row': path[1],
                'column': path[2],
                'path': deepcopy(path),
                'operation': op_name,
            }

    return {
        'cells': touched,
        'structural_ops': structural_ops,
        'batch_size': len(touched),
    }


def _build_structural_conflict(state_revision: int, workbook_data: list, operation: str, editor=None) -> dict:
    return {
        'revision': state_revision,
        'conflicts': [{
            'conflict_type': 'structural',
            'operation': operation,
            'server_editor': getattr(editor, 'username', None),
        }],
        'workbook_data': workbook_data,
    }


def detect_conflicts(state, base_revision: int, incoming_ops: list[dict], incoming_snapshot: list | None) -> dict | None:
    revisions = list(
        state.revisions.filter(new_revision__gt=base_revision).select_related('editor').order_by('new_revision')
    )
    incoming = _extract_touched_cells(incoming_ops)

    # Same-revision: no intervening changes, so no conflict possible
    if not revisions:
        return None

    # Revision gap exists: structural ops become non-mergeable
    if incoming['structural_ops']:
        first = incoming['structural_ops'][0]
        return _build_structural_conflict(state.revision, state.workbook_data, first['operation'])

    for revision in revisions:
        server = _extract_touched_cells(revision.ops)
        if server['structural_ops']:
            first = server['structural_ops'][0]
            return _build_structural_conflict(
                state.revision,
                state.workbook_data,
                first['operation'],
                editor=revision.editor,
            )

    conflicts = []
    snapshot = incoming_snapshot or []

    for revision in revisions:
        server = _extract_touched_cells(revision.ops)
        for key, incoming_cell in incoming['cells'].items():
            if key not in server['cells']:
                continue

            sheet_id, row, column = key
            client_cell = get_cell_payload(snapshot, sheet_id, row, column)
            server_cell = get_cell_payload(state.workbook_data, sheet_id, row, column)
            conflicts.append({
                'sheet_id': sheet_id,
                'row': row,
                'column': column,
                'cell_address': _cell_address(row, column),
                'conflict_type': 'cell-edit',
                'client_value': get_cell_display_value(client_cell),
                'server_value': get_cell_display_value(server_cell),
                'client_cell': deepcopy(client_cell),
                'server_cell': deepcopy(server_cell),
                'server_editor': revision.editor.username if revision.editor else None,
                'server_revision': revision.new_revision,
            })

    if conflicts:
        return {
            'revision': state.revision,
            'conflicts': conflicts,
            'workbook_data': state.workbook_data,
        }

    return None


def merge_ops_into_workbook(workbook_data: list, ops: list[dict]) -> list:
    runtime_sheets = apply_ops_to_workbook_data(workbook_data, ops)
    return normalize_workbook_data(runtime_sheets)
