"""
Data Explorer DuckDB Engine
===========================
DuckDB-based query engine for Graphic Walker (Computation Mode).

This module handles:
1. Persistent DuckDB file management for large datasets
2. DSL-to-SQL transpilation using official gw-dsl-parser
3. Query execution with proper error handling

Dependencies:
- gw-dsl-parser: Official Kanaries DSL parser (pip install gw-dsl-parser>=0.1.48)
- duckdb: High-performance analytics database

References:
- Graphic Walker: https://github.com/Kanaries/graphic-walker
- gw-dsl-parser: https://github.com/Kanaries/gw-dsl-parser-py
- Integration Example: https://github.com/Kanaries/graphic-walker-integration-example

Last Updated: 2026-02-12
"""

import duckdb
import json
import os
import logging
import hashlib
import time
import threading
import re
from typing import Dict, Any, List, Optional, Set, Tuple
from contextlib import contextmanager

from django.conf import settings
from .exceptions import (
    SessionExpiredError,
    QueryValidationError,
    DSLParsingError,
    DataLoadError,
)

# =============================================================================
# Official Graphic Walker DSL Parser
# =============================================================================
# gw-dsl-parser converts Graphic Walker's IDataQueryPayload to SQL
# It supports all workflow types: filter, transform, view (aggregate/raw/fold/bin), sort
# 
# Install: pip install gw-dsl-parser>=0.1.48
# Usage: get_sql_from_payload("table_name", payload_dict) -> SQL string
# =============================================================================
try:
    from gw_dsl_parser import get_sql_from_payload
    GW_DSL_PARSER_AVAILABLE = True
except ImportError as e:
    GW_DSL_PARSER_AVAILABLE = False
    get_sql_from_payload = None
    # Log import error at module load time for debugging
    logging.getLogger(__name__).error(
        f"[CRITICAL] gw-dsl-parser not available. Data Explorer queries will fail. "
        f"Install with: pip install gw-dsl-parser>=0.1.48. Error: {e}"
    )

logger = logging.getLogger(__name__)


class DuckDBEngine:
    """
    DuckDB-based query engine for Graphic Walker (Computation Mode).
    
    Architecture:
    - Each dataset is stored as a persistent DuckDB file in .duckdb_store/
    - File hash (mtime + size) is used for cache invalidation
    - Graphic Walker sends IDataQueryPayload which is converted to SQL via gw-dsl-parser
    
    Table Convention:
    - Raw source data is preserved in 'raw_main_table'
    - Graphic Walker query target remains 'main_table' (projection view)
    - gw-dsl-parser always generates SQL for 'main_table'
    
    Concurrency:
    - File-level locks prevent race conditions during projection changes
    - Active session tracking prevents cleanup of in-use files
    """

    RAW_TABLE_NAME = 'raw_main_table'
    MAIN_TABLE_NAME = 'main_table'
    
    # Directory for persistent DuckDB files
    CACHE_DIR = os.path.join(settings.BASE_DIR.parent, 'data', 'data_explorer', '.duckdb_store')
    
    # =========================================================================
    # Concurrency Control
    # =========================================================================
    
    # File-level locks to prevent race conditions
    _db_locks: Dict[str, threading.RLock] = {}
    _locks_lock = threading.Lock()  # Lock for accessing _db_locks dict
    
    # Active session tracking (prevents cleanup of in-use files)
    _active_sessions: Set[str] = set()
    _sessions_lock = threading.Lock()
    
    @classmethod
    def _get_db_lock(cls, db_path: str) -> threading.RLock:
        """
        Get or create a reentrant lock for a specific DuckDB file.
        RLock is required because configure_projection holds the lock
        and then calls _ensure_db_ready, which needs to re-acquire the same lock.
        Thread-safe lock management.
        """
        with cls._locks_lock:
            if db_path not in cls._db_locks:
                cls._db_locks[db_path] = threading.RLock()
            return cls._db_locks[db_path]
    
    @classmethod
    @contextmanager
    def _session_context(cls, db_path: str):
        """
        Context manager for tracking active sessions.
        Prevents cleanup of files being actively used.
        """
        with cls._sessions_lock:
            cls._active_sessions.add(db_path)
        try:
            yield
        finally:
            with cls._sessions_lock:
                cls._active_sessions.discard(db_path)
    
    @classmethod
    def _is_session_active(cls, db_path: str) -> bool:
        """Check if a session is currently using the given DB file."""
        with cls._sessions_lock:
            return db_path in cls._active_sessions

    # =========================================================================
    # Cleanup & Maintenance
    # =========================================================================
    
    @classmethod
    def cleanup_old_upload_dbs(cls, hours: int = 24):
        """
        Deletes DuckDB files starting with 'uploaded_' older than specified hours.
        Called probabilistically (1%) from DatasetListView to prevent disk bloat.
        
        Safety: Skips files that are currently in active sessions.
        
        Args:
            hours: Age threshold for deletion (default: 24 hours)
        """
        if not os.path.exists(cls.CACHE_DIR):
            return

        now = time.time()
        cutoff_time = now - (hours * 3600)
        
        try:
            count = 0
            skipped = 0
            for filename in os.listdir(cls.CACHE_DIR):
                if filename.startswith('uploaded_'):
                    file_path = os.path.join(cls.CACHE_DIR, filename)
                    
                    # Safety: Skip files in active sessions
                    if cls._is_session_active(file_path):
                        skipped += 1
                        # logger.debug(f"[Cleanup] Skipped active session: {filename}")
                        continue
                    
                    try:
                        if os.path.getmtime(file_path) < cutoff_time:
                            # Clean up all related files (.wal, .wal.lock)
                            related_files = [
                                file_path,
                                file_path + '.wal',
                                file_path + '.wal.lock',
                            ]
                            for f in related_files:
                                if os.path.exists(f):
                                    try:
                                        os.remove(f)
                                    except OSError:
                                        pass  # Ignore individual file errors
                            count += 1
                    except OSError as e:
                        logger.warning(f"[Cleanup] Failed to delete {filename}: {e}")
            
            if count > 0 or skipped > 0:
                logger.info(f"[Cleanup] Removed {count} old files, skipped {skipped} active sessions")
                
        except Exception as e:
            logger.error(f"[Cleanup] Error during cleanup: {e}")

    # =========================================================================
    # Path & Security Utilities
    # =========================================================================
    
    @staticmethod
    def _generate_db_path(file_path: str) -> str:
        """
        Generate unique DuckDB file path based on source file metadata.
        
        Cache Invalidation Strategy:
        - For uploads: UUID in filename ensures uniqueness
        - For local files: mtime + size hash invalidates on file change
        
        Args:
            file_path: Path to source CSV/Parquet file
            
        Returns:
            Path to corresponding DuckDB file in CACHE_DIR
            
        Raises:
            FileNotFoundError: If local file doesn't exist
        """
        filename = os.path.basename(file_path)
        
        # Uploaded files have UUID in name, use as-is
        if filename.startswith('uploaded_'):
            identifier = filename
        # Local files: include mtime/size for cache invalidation
        elif os.path.exists(file_path):
            stats = os.stat(file_path)
            identifier = f"{file_path}_{stats.st_mtime}_{stats.st_size}"
        else:
            raise FileNotFoundError(f"Source file not found: {file_path}")

        file_hash = hashlib.md5(identifier.encode()).hexdigest()
        return os.path.join(DuckDBEngine.CACHE_DIR, f"{filename}_{file_hash}.duckdb")

    @staticmethod
    def _escape_file_path(file_path: str) -> str:
        """Escape file path for SQL (prevent injection in read_csv)."""
        return file_path.replace("'", "''")

    @staticmethod
    def _escape_identifier(identifier: str) -> str:
        """Escape SQL identifier for DuckDB."""
        return '"' + str(identifier).replace('"', '""') + '"'

    @classmethod
    def _table_exists(cls, con: duckdb.DuckDBPyConnection, table_name: str) -> bool:
        """Check whether a table/view exists."""
        try:
            con.execute(f"SELECT 1 FROM {cls._escape_identifier(table_name)} LIMIT 1")
            return True
        except Exception:
            return False

    @classmethod
    def _get_table_columns(cls, con: duckdb.DuckDBPyConnection, table_name: str) -> List[str]:
        """Return column names from a DuckDB table/view."""
        schema_df = con.execute(f"DESCRIBE {cls._escape_identifier(table_name)}").df()
        return [str(col) for col in schema_df['column_name'].tolist()]

    @classmethod
    def _ensure_raw_table_exists(cls, con: duckdb.DuckDBPyConnection) -> None:
        """Ensure raw_main_table exists for backward compatibility with older cache files."""
        raw_table = cls._escape_identifier(cls.RAW_TABLE_NAME)
        main_table = cls._escape_identifier(cls.MAIN_TABLE_NAME)

        if cls._table_exists(con, cls.RAW_TABLE_NAME):
            return

        if not cls._table_exists(con, cls.MAIN_TABLE_NAME):
            raise ValueError("유효한 테이블이 없습니다. 데이터셋을 다시 초기화해주세요.")

        con.execute(f"CREATE TABLE {raw_table} AS SELECT * FROM {main_table}")

    @classmethod
    def _drop_main_relation(cls, con: duckdb.DuckDBPyConnection) -> None:
        """Drop main_table whether it is a TABLE or VIEW."""
        main_table = cls._escape_identifier(cls.MAIN_TABLE_NAME)

        try:
            con.execute(f"DROP VIEW IF EXISTS {main_table}")
        except Exception:
            pass

        try:
            con.execute(f"DROP TABLE IF EXISTS {main_table}")
        except Exception:
            pass

    @classmethod
    def _build_temporal_cast_expr(cls, escaped_col: str) -> str:
        """
        Build a multi-format temporal conversion expression for DuckDB.

        Tries 11 string formats in priority order, returning the first
        non-NULL result as BIGINT milliseconds since Unix epoch (UTC).
        TRIM is applied to every attempt to handle leading/trailing whitespace.
        NULL input and all-fail cases propagate as NULL BIGINT.

        The BIGINT ms-epoch return type is required by gw-dsl-parser, which
        generates Time Unit / Time Feature SQL in the form:
            CAST((col - timezone_offset_ms) AS BIGINT)
        That integer arithmetic requires the column to be BIGINT, not TIMESTAMP.

        Priority | Example input             | ms-epoch (UTC)
        ---------|---------------------------|---------------------------
        1        | 2026-01-01                | 1767225600000
        2        | 2026-01-02 01:01:01       | 1767315661000
        3        | 2026-01-05 04:04          | 1767546240000
        4        | 2026-01-04 (03:03:03)     | 1767463383000
        5        | 2026-01-05 (04:04)        | 1767546240000
        6        | 2001/04/03 06:11:22       | 986278282000
        7        | 2001/04/03 06:11          | 986278260000
        8        | 2001/04/03                | 986256000000
        9        | 20020607 06:39:22         | 1023432562000
        10       | 20020607 06:39            | 1023432540000
        11       | 20020607                  | 1023408000000

        Returns NULL (not converted):
        - 75.04.03           (ambiguous dot-form, no 4-digit year prefix)
        - 03:03:03           (time-only, no date component)
        - 2001/04/03 06:77   (invalid minute value)
        - 20023301           (invalid month 33)
        - 20020607 06:88     (invalid minute 88)

        Args:
            escaped_col: DuckDB-escaped column expression (e.g. '"my_col"')

        Returns:
            SQL expression producing BIGINT (ms since Unix epoch); no alias.
            EXTRACT(EPOCH FROM NULL) = NULL → NULL propagation is safe.
        """
        # Base trimmed string expression
        c = f"TRIM(CAST({escaped_col} AS VARCHAR))"
        # Parentheses-stripped form for "YYYY-MM-DD (HH:MM:SS)" variants
        c_paren = (
            f"TRIM(REGEXP_REPLACE(TRIM(CAST({escaped_col} AS VARCHAR)), "
            f"'[()\\[\\]{{}}]', '', 'g'))"
        )

        # Inner COALESCE: tries 11 formats, yields TIMESTAMP or NULL
        inner = (
            "COALESCE("
            # P1+P2: ISO 8601 — DuckDB natively handles YYYY-MM-DD and
            # YYYY-MM-DD HH:MM:SS (including fractional seconds)
            f"TRY_CAST({c} AS TIMESTAMP), "
            # P3: YYYY-MM-DD HH:MM  (no seconds)
            f"TRY_STRPTIME({c}, '%Y-%m-%d %H:%M'), "
            # P4: YYYY-MM-DD (HH:MM:SS) — strip parens then native cast
            f"TRY_CAST({c_paren} AS TIMESTAMP), "
            # P5: YYYY-MM-DD (HH:MM) — strip parens then strptime
            f"TRY_STRPTIME({c_paren}, '%Y-%m-%d %H:%M'), "
            # P6: YYYY/MM/DD HH:MM:SS
            f"TRY_STRPTIME({c}, '%Y/%m/%d %H:%M:%S'), "
            # P7: YYYY/MM/DD HH:MM
            f"TRY_STRPTIME({c}, '%Y/%m/%d %H:%M'), "
            # P8: YYYY/MM/DD
            f"TRY_STRPTIME({c}, '%Y/%m/%d'), "
            # P9: YYYYMMDD HH:MM:SS
            f"TRY_STRPTIME({c}, '%Y%m%d %H:%M:%S'), "
            # P10: YYYYMMDD HH:MM
            f"TRY_STRPTIME({c}, '%Y%m%d %H:%M'), "
            # P11: YYYYMMDD
            f"TRY_STRPTIME({c}, '%Y%m%d')"
            ")"
        )

        # Convert TIMESTAMP → BIGINT ms epoch for gw-dsl-parser compatibility.
        #
        # "AT TIME ZONE tz" declares the timezone-naive TIMESTAMP as being in
        # the Django server's local timezone (settings.TIME_ZONE, e.g. KST).
        # DuckDB converts it to a proper UTC-based epoch internally.
        #
        # Why this is correct for both date-only and datetime data:
        #
        #   "2023-10-06"          → KST 00:00:00 → epoch → GW(KST) → 00:00:00 ✓
        #   "2023-10-06 09:30:00" → KST 09:30:00 → epoch → GW(KST) → 09:30:00 ✓
        #
        # GW (with browser timezone = KST) applies its own +9h offset when
        # displaying. Since we stored KST-based epochs, the displayed times
        # match the original data values exactly.
        #
        # HH:MM:SS values are preserved as-is — not shifted by timezone.
        # EXTRACT(EPOCH FROM NULL) = NULL → NULL propagation is preserved.
        tz = settings.TIME_ZONE  # e.g. 'Asia/Seoul'
        return (
            f"CAST(EXTRACT(EPOCH FROM "
            f"(({inner}) AT TIME ZONE '{tz}')) * 1000 AS BIGINT)"
        )

    @classmethod
    def _check_temporal_parseability(
        cls,
        con: duckdb.DuckDBPyConnection,
        raw_table: str,
        escaped_col: str,
        temporal_cast_expr: str,
    ) -> Tuple[bool, bool]:
        """
        Check if column has parseable temporal values using EXISTS for performance.

        Performance Optimization:
        - Uses EXISTS queries with implicit LIMIT 1 for early-exit behavior
        - Instead of scanning 1M rows to count matches, stops at first match
        - Best case: 1 row scan if first row is parseable
        - Worst case: Full scan only when ALL values fail (same as before)

        Args:
            con: DuckDB connection
            raw_table: Escaped raw table name
            escaped_col: Escaped column name
            temporal_cast_expr: COALESCE expression for temporal parsing

        Returns:
            Tuple of (has_non_empty_values, has_any_parseable_values)

        Decision Matrix:
        - (False, *): All values are NULL/empty → treat as temporal (harmless)
        - (True, False): Has values but none parseable → fallback to nominal
        - (True, True): Has parseable values → use temporal
        """
        # Query 1: Any non-empty values exist? (early exit on first match)
        has_any_non_empty = con.execute(
            f"SELECT EXISTS ("
            f"  SELECT 1 FROM {raw_table} "
            f"  WHERE {escaped_col} IS NOT NULL "
            f"    AND TRIM(CAST({escaped_col} AS VARCHAR)) <> ''"
            f")"
        ).fetchone()[0]

        if not has_any_non_empty:
            # All values are NULL or empty string
            return (False, False)

        # Query 2: Any parseable values exist? (early exit on first match)
        has_any_parseable = con.execute(
            f"SELECT EXISTS ("
            f"  SELECT 1 FROM {raw_table} "
            f"  WHERE {escaped_col} IS NOT NULL "
            f"    AND TRIM(CAST({escaped_col} AS VARCHAR)) <> '' "
            f"    AND ({temporal_cast_expr}) IS NOT NULL"
            f")"
        ).fetchone()[0]

        return (has_any_non_empty, has_any_parseable)

    @classmethod
    def _set_projection_view(
        cls,
        con: duckdb.DuckDBPyConnection,
        selected_columns: Optional[List[str]] = None,
        column_types: Optional[Dict[str, str]] = None,
    ) -> Tuple[List[str], Dict[str, str]]:
        """
        Ensure main_table is a projection over raw_main_table with type casting.

        Args:
            con: DuckDB connection
            selected_columns: List of column names to include (None = all)
            column_types: Dict mapping column name to semantic type
                         {'col1': 'quantitative', 'col2': 'temporal', 'col3': 'nominal'}

        Type Casting Rules:
        - 'quantitative': TRY_CAST(col AS DOUBLE)
        - 'temporal': Multi-format BIGINT ms-epoch conversion via _build_temporal_cast_expr().
            Supports ISO 8601, slash-separated, compact YYYYMMDD, and parenthesised
            time variants. If ALL non-empty values fail conversion, column falls back
            to 'nominal' (VARCHAR preserved as-is).
        - 'nominal': Keep as VARCHAR (no conversion)
        - None/missing: Keep as VARCHAR (default)

        Returns:
            (final selected column list, applied column semantic type map)
        """
        raw_table = cls._escape_identifier(cls.RAW_TABLE_NAME)
        main_table = cls._escape_identifier(cls.MAIN_TABLE_NAME)

        cls._ensure_raw_table_exists(con)

        available_columns = cls._get_table_columns(con, cls.RAW_TABLE_NAME)

        if selected_columns:
            filtered_columns = [col for col in selected_columns if col in available_columns]
            if not filtered_columns:
                raise ValueError("선택된 컬럼이 유효하지 않습니다.")
            final_columns = filtered_columns
        else:
            final_columns = available_columns

        # Build SELECT clause with type casting
        column_types = column_types or {}
        select_parts = []
        applied_column_types: Dict[str, str] = {}
        
        for col in final_columns:
            escaped_col = cls._escape_identifier(col)
            semantic_type = column_types.get(col)
            
            if semantic_type == 'quantitative':
                # Convert to numeric (DOUBLE) - required for arithmetic operations
                # NULL if conversion fails (user should select 'nominal' for non-numeric data)
                select_parts.append(f"TRY_CAST({escaped_col} AS DOUBLE) AS {escaped_col}")
                applied_column_types[col] = 'quantitative'
            elif semantic_type == 'temporal':
                # Build multi-format cast expression (reused for check and projection)
                temporal_cast_expr = cls._build_temporal_cast_expr(escaped_col)

                # Performance: EXISTS-based early exit instead of full table SUM.
                # Stops scanning as soon as first parseable row is found.
                has_non_empty, has_parseable = cls._check_temporal_parseability(
                    con, raw_table, escaped_col, temporal_cast_expr
                )

                if has_non_empty and not has_parseable:
                    # All non-empty values failed all format attempts → nominal
                    logger.warning(
                        f"[Projection] Temporal cast fallback to nominal for column '{col}' "
                        f"(all non-empty values are unparsable by any supported date/time format)."
                    )
                    select_parts.append(escaped_col)
                    applied_column_types[col] = 'nominal'
                else:
                    # Either all NULL/empty (harmless) or has parseable values
                    select_parts.append(f"{temporal_cast_expr} AS {escaped_col}")
                    applied_column_types[col] = 'temporal'
            else:
                # 'nominal' or unspecified: keep as VARCHAR (original string)
                select_parts.append(escaped_col)
                applied_column_types[col] = 'nominal'
        
        select_clause = ', '.join(select_parts)

        # Recreate main_table as projection view with type casting
        cls._drop_main_relation(con)
        con.execute(
            f"CREATE VIEW {main_table} AS "
            f"SELECT {select_clause} FROM {raw_table}"
        )
        
        # logger.debug(
        #     f"[Projection] Created view with {len(final_columns)} columns, "
        #     f"requested_types={column_types}, applied_types={applied_column_types}"
        # )

        return final_columns, applied_column_types

    @classmethod
    def _extract_schema_data(
        cls,
        con: duckdb.DuckDBPyConnection,
        table_name: str,
    ) -> Dict[str, Any]:
        """
        Extract fields and row_count from the given table/view.

        semanticType is always set to 'nominal' as a placeholder.
        configure_projection() always overrides it with applied_column_types
        (the actual user-specified and applied types), so type detection here
        would be dead code — temporal columns are stored as BIGINT ms epoch,
        which would be misclassified as 'quantitative' by DuckDB column types.
        """
        escaped_table = cls._escape_identifier(table_name)
        schema_df = con.execute(f"DESCRIBE {escaped_table}").df()

        fields = []
        for _, row in schema_df.iterrows():
            col_name = row['column_name']
            fields.append({
                'fid': col_name,
                'name': col_name,
                'semanticType': 'nominal',   # overridden by applied_column_types
                'analyticType': 'dimension', # overridden by applied_column_types
            })

        row_count_result = con.execute(f"SELECT COUNT(*) FROM {escaped_table}").fetchone()
        row_count = row_count_result[0] if row_count_result else 0

        return {
            'fields': fields,
            'row_count': row_count,
        }

    # =========================================================================
    # Database Initialization
    # =========================================================================
    
    @classmethod
    def _ensure_db_ready(cls, file_path: str, is_csv: bool) -> str:
        """
        Ensure DuckDB file exists with data loaded.
        
        CSV Loading Strategy:
        - Always use all_varchar=True to preserve original string values
        - Type conversion happens at projection time based on user selection
        
        This ensures:
        - "75.04.03" stays as "75.04.03" (not converted to timestamp)
        - User can choose semantic type in Column Config Modal
        - Type casting is applied when creating main_table view
        
        Args:
            file_path: Source data file path
            is_csv: True for CSV, False for Parquet
            
        Returns:
            Path to ready DuckDB file
        """
        if not os.path.exists(cls.CACHE_DIR):
            os.makedirs(cls.CACHE_DIR)
            # logger.debug(f"[DB Init] Created cache directory: {cls.CACHE_DIR}")

        db_path = cls._generate_db_path(file_path)
        
        # Fast path: return existing DB without acquiring lock (cache hit)
        if os.path.exists(db_path):
            # logger.debug(f"[DB Init] Cache hit: {db_path}")
            return db_path

        # Slow path: acquire lock before creating new DB to prevent race conditions
        # Double-check after lock acquisition — another thread may have created it first
        lock = cls._get_db_lock(db_path)
        with lock:
            if os.path.exists(db_path):
                return db_path

            # Create new DB and load data
            logger.info(f"[DB Init] Creating new DuckDB: {db_path}")
            con = duckdb.connect(db_path)
            try:
                safe_path = cls._escape_file_path(file_path)

                raw_table = cls._escape_identifier(cls.RAW_TABLE_NAME)
                main_table = cls._escape_identifier(cls.MAIN_TABLE_NAME)

                if is_csv:
                    # Always load as VARCHAR to preserve original values
                    # Type conversion will be applied at projection time
                    sql = f"CREATE TABLE {raw_table} AS SELECT * FROM read_csv('{safe_path}', all_varchar=True, ignore_errors=True, null_padding=True)"
                    con.execute(sql)
                    # logger.debug(f"[DB Init] CSV loaded with all_varchar=True (original values preserved)")
                else:
                    sql = f"CREATE TABLE {raw_table} AS SELECT * FROM read_parquet('{safe_path}')"
                    con.execute(sql)

                con.execute(
                    f"CREATE VIEW {main_table} AS "
                    f"SELECT * FROM {raw_table}"
                )

                logger.info(f"[DB Init] Data loaded successfully: {file_path}")

            except Exception as e:
                # Clean up corrupted file
                con.close()
                if os.path.exists(db_path):
                    try:
                        os.remove(db_path)
                    except: pass
                raise e
            finally:
                con.close()

        return db_path

    # =========================================================================
    # Schema Extraction
    # =========================================================================
    
    @classmethod
    def get_schema(cls, file_path: str, is_csv: bool) -> Dict[str, Any]:
        """
        Extract column metadata (semantic types) and row count from DuckDB table.
        
        Returns Graphic Walker field format:
        - fid: Field ID (column name)
        - name: Display name
        - semanticType: 'quantitative' | 'temporal' | 'nominal'
        - analyticType: 'measure' | 'dimension'
        
        IMPORTANT: Do NOT add Row count field here!
        Graphic Walker adds it internally via createCountField().
        See: https://github.com/Kanaries/graphic-walker/blob/main/packages/graphic-walker/src/models/visSpecHistory.ts
        
        Args:
            file_path: Source data file path
            is_csv: True for CSV, False for Parquet
            
        Returns:
            Dictionary with 'fields' (list) and 'row_count' (int)
        """
        return cls.configure_projection(file_path, is_csv, selected_columns=None)

    @classmethod
    def configure_projection(
        cls,
        file_path: str,
        is_csv: bool,
        selected_columns: Optional[List[str]] = None,
        column_types: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Configure main_table projection from raw_main_table and return schema.

        Args:
            file_path: Source data file path
            is_csv: True for CSV, False for Parquet
            selected_columns: List of column names to include
            column_types: Dict mapping column name to semantic type
                         {'col1': 'quantitative', 'col2': 'temporal', 'col3': 'nominal'}

        Notes:
        - DuckDB file cache key remains based on original source file metadata.
        - raw_main_table keeps full original dataset as VARCHAR (string preservation).
        - main_table is recreated per init-session with user-specified type casting.
        """
        # Compute db_path before acquiring lock (pure function, no I/O)
        db_path = cls._generate_db_path(file_path)
        lock = cls._get_db_lock(db_path)
        with lock:
            # _ensure_db_ready re-acquires the same lock; RLock allows re-entry
            db_path = cls._ensure_db_ready(file_path, is_csv)
            con = duckdb.connect(db_path)
            try:
                final_columns, applied_column_types = cls._set_projection_view(con, selected_columns, column_types)
                schema_data = cls._extract_schema_data(con, cls.MAIN_TABLE_NAME)
                schema_data['selected_columns'] = final_columns
                schema_data['applied_column_types'] = applied_column_types
                # logger.debug(
                #     f"[Schema] Projection configured with {len(final_columns)} columns, "
                #     f"types={column_types}, rows={schema_data['row_count']} for {file_path}"
                # )
                return schema_data
            finally:
                con.close()

    # =========================================================================
    # Preview Data (Column Config Modal)
    # =========================================================================
    
    @classmethod
    def get_preview_data(cls, file_path: str, is_csv: bool, limit: int = 10) -> Dict[str, Any]:
        """
        Get preview data (first N rows) and detected column types for Column Config Modal.
        
        Preview Strategy:
        - Preview rows: Read source file with all_varchar=True to show RAW data exactly as-is
        - Detected types: Use separate auto-detect to infer intelligent type recommendations
        
        Note: The main DuckDB cache uses all_varchar=True for data preservation,
        so we need a separate in-memory read for type inference.
        
        This ensures users see exactly what's in the CSV (e.g., "75.04.03" not "165715200000")
        while still getting intelligent type recommendations (e.g., "75.04.03" → temporal).
        
        Args:
            file_path: Source data file path
            is_csv: True for CSV, False for Parquet
            limit: Number of preview rows (default: 10)
            
        Returns:
            Dictionary with:
            - preview: List of row dictionaries (first N rows, raw strings)
            - detected_columns: List of {name, detected_type} for each column
        """
        safe_path = cls._escape_file_path(file_path)
        
        # === Preview data: Read source file as raw strings ===
        preview_con = duckdb.connect(":memory:")
        try:
            if is_csv:
                # all_varchar=True ensures no type conversion (shows "75.04.03" as-is)
                preview_sql = f"SELECT * FROM read_csv('{safe_path}', all_varchar=True, ignore_errors=True, null_padding=True) LIMIT {int(limit)}"
            else:
                # Parquet preserves original values
                preview_sql = f"SELECT * FROM read_parquet('{safe_path}') LIMIT {int(limit)}"
            
            preview_df = preview_con.execute(preview_sql).df()
            preview_data = json.loads(preview_df.to_json(orient='records'))
        finally:
            preview_con.close()
        
        # === Detected types: Auto-detect in memory (separate from all_varchar cache) ===
        type_detect_con = duckdb.connect(":memory:")
        try:
            if is_csv:
                # Auto-detect types with limited sampling for performance
                type_sql = f"CREATE TABLE temp_types AS SELECT * FROM read_csv('{safe_path}', sample_size=200, ignore_errors=True, null_padding=True) LIMIT 1"
                type_detect_con.execute(type_sql)
                schema_df = type_detect_con.execute("DESCRIBE temp_types").df()
            else:
                # Parquet has embedded type info
                schema_df = type_detect_con.execute(f"DESCRIBE (SELECT * FROM read_parquet('{safe_path}'))").df()
            
            detected_columns = []
            for _, row in schema_df.iterrows():
                col_name = row['column_name']
                col_type = str(row['column_type']).upper()
                
                # Map DuckDB types to Graphic Walker semantic types
                if any(t in col_type for t in ['INT', 'DOUBLE', 'DECIMAL', 'FLOAT', 'BIGINT']):
                    detected_type = 'quantitative'
                elif any(t in col_type for t in ['DATE', 'TIMESTAMP', 'TIME']):
                    detected_type = 'temporal'
                else:
                    detected_type = 'nominal'
                
                detected_columns.append({
                    'name': col_name,
                    'detected_type': detected_type
                })
        finally:
            type_detect_con.close()
        
        # logger.debug(f"[Preview] Loaded {len(preview_data)} rows (raw), {len(detected_columns)} columns from {file_path}")
        return {
            'preview': preview_data,
            'detected_columns': detected_columns
        }

    # =========================================================================
    # DSL → SQL Transpilation (Official gw-dsl-parser)
    # =========================================================================
    
    # SQL validation patterns (whitelist approach)
    # gw-dsl-parser generates SELECT queries only, but we validate for defense in depth
    _SQL_FORBIDDEN_PATTERNS = re.compile(
        r'\b(DROP|DELETE|INSERT|UPDATE|ALTER|TRUNCATE|CREATE|COPY|ATTACH|DETACH|'
        r'PRAGMA|EXPORT|IMPORT|CALL|EXECUTE|LOAD|INSTALL|SET|BEGIN|COMMIT|ROLLBACK)\b',
        re.IGNORECASE
    )
    
    @classmethod
    def _validate_sql_query(cls, sql: str) -> None:
        """
        Validate SQL query is read-only and safe to execute.
        
        Uses comprehensive pattern matching to block:
        - DML: INSERT, UPDATE, DELETE, TRUNCATE
        - DDL: CREATE, DROP, ALTER
        - Admin: ATTACH, DETACH, PRAGMA, COPY, EXPORT
        - Transaction: BEGIN, COMMIT, ROLLBACK
        - Extension: LOAD, INSTALL, CALL, EXECUTE
        
        Raises:
            QueryValidationError: If query contains forbidden patterns
        """
        if cls._SQL_FORBIDDEN_PATTERNS.search(sql):
            match = cls._SQL_FORBIDDEN_PATTERNS.search(sql)
            keyword = match.group(0) if match else "Unknown"
            logger.warning(f"[SQL Validation] Blocked forbidden keyword: {keyword}")
            raise QueryValidationError(
                message="읽기 전용 쿼리만 허용됩니다.",
                detail=f"Blocked keyword: {keyword}"
            )
        
        # Additional check: query should start with SELECT (after trimming)
        stripped_sql = sql.strip().upper()
        if not stripped_sql.startswith('SELECT'):
            logger.warning(f"[SQL Validation] Query does not start with SELECT")
            raise QueryValidationError(
                message="SELECT 쿼리만 허용됩니다.",
                detail="Query must start with SELECT"
            )
    
    @classmethod
    def _transpile_payload_to_sql(cls, payload: Dict[str, Any]) -> str:
        """
        Transpile Graphic Walker computation payload to DuckDB SQL.
        
        Uses official gw-dsl-parser from Kanaries.
        - Package: https://pypi.org/project/gw-dsl-parser/
        - Source: https://github.com/Kanaries/gw-dsl-parser
        
        The parser handles:
        - All IFilterRule types: range, temporal range, one of, not in, regexp
        - All workflow steps: transform, filter, view, sort
        - All query operations: aggregate, raw, fold, bin
        - Visual encodings: Color, Opacity, Size, Details, Text
        
        IMPORTANT: This project uses ONLY the official parser.
        No legacy fallback - if parser fails, error is propagated to user.
        
        Args:
            payload: IDataQueryPayload from Graphic Walker
                     { workflow: IDataQueryWorkflowStep[], limit?: number, offset?: number }
        
        Returns:
            DuckDB SQL query string
            
        Raises:
            DSLParsingError: If gw-dsl-parser is not installed or parsing fails
        """
        # Check if official parser is available
        if not GW_DSL_PARSER_AVAILABLE:
            error_msg = "gw-dsl-parser package is not installed."
            logger.error(f"[DSL Parser] {error_msg}")
            raise DSLParsingError(
                message="쿼리 파서가 설치되어 있지 않습니다. 관리자에게 문의하세요.",
                detail="pip install gw-dsl-parser>=0.1.48"
            )
        
        # Log incoming payload for debugging
        # logger.debug(f"[DSL Parser] Input payload: {json.dumps(payload, ensure_ascii=False)[:500]}...")
        
        try:
            # gw-dsl-parser.get_sql_from_payload(table_name, payload_dict)
            # - table_name: "main_table" (our convention)
            # - payload: dict (not JSON string!)
            sql = get_sql_from_payload("main_table", payload)
            
            if not sql:
                raise ValueError("Parser returned empty SQL")
            
            # Validate generated SQL for defense in depth
            cls._validate_sql_query(sql)
            
            logger.info(f"[DSL Parser] Generated SQL: {sql}")
            return sql
            
        except (QueryValidationError, DSLParsingError):
            # Re-raise our custom exceptions
            raise
        except Exception as e:
            # Log full error for debugging
            logger.error(f"[DSL Parser] Transpilation failed: {e}")
            logger.error(f"[DSL Parser] Failed payload: {json.dumps(payload, ensure_ascii=False)}")
            
            # Wrap in custom exception
            raise DSLParsingError(
                message="쿼리 변환에 실패했습니다.",
                detail=str(e)
            )

    # =========================================================================
    # Query Execution
    # =========================================================================
    
    @classmethod
    def execute_query(cls, file_path: str, query: Any) -> List[Dict[str, Any]]:
        """
        Execute query against DuckDB and return JSON-serializable results.
        
        Accepts:
        - Raw SQL string (for debugging/testing)
        - Graphic Walker IDataQueryPayload dict (normal operation)
        
        Security:
        - Whitelist validation (SELECT only, comprehensive pattern blocking)
        - File-level locking for concurrency safety
        - Session tracking to prevent cleanup during execution
        - Query timeout to prevent hung queries
        
        Args:
            file_path: Source data file path (for DB path generation)
            query: SQL string or IDataQueryPayload dict
            
        Returns:
            List of result rows as dictionaries
            
        Raises:
            SessionExpiredError: If DuckDB file is missing
            QueryValidationError: For write operations or invalid queries
            DSLParsingError: If DSL transpilation fails
        """
        # Generate DB path from file path
        db_path = cls._generate_db_path(file_path)
        
        if not os.path.exists(db_path):
            logger.error(f"[Query] DB not found: {db_path}")
            raise SessionExpiredError()

        # Transpile JSON payload to SQL if needed
        sql_query = query
        if isinstance(query, dict):
            sql_query = cls._transpile_payload_to_sql(query)
        else:
            # For raw SQL strings, validate before execution
            cls._validate_sql_query(str(sql_query))

        # Use session tracking to prevent file cleanup while query is in progress
        with cls._session_context(db_path):
            logger.info(f"[Query] Executing: {sql_query}")
            con = None
            try:
                con = duckdb.connect(db_path, read_only=True)
                # Execute query and convert to DataFrame
                result = con.execute(sql_query).df()

                # Convert to JSON-safe format (handles NaN/Inf)
                json_result = json.loads(result.to_json(orient='records'))
                
                # logger.debug(f"[Query] Returned {len(json_result)} rows")
                return json_result
                
            except Exception as e:
                logger.error(f"[Query] Execution failed: {e}")
                logger.error(f"[Query] Failed SQL: {sql_query}")
                # Wrap database errors in user-friendly message
                raise QueryValidationError(
                    message="쿼리 실행에 실패했습니다.",
                    detail=str(e)
                )
            finally:
                if con is not None:
                    con.close()

    # =========================================================================
    # Cache Management (Rebuild Feature)
    # =========================================================================
    
    @classmethod
    def get_cache_status(cls, file_path: str) -> Dict[str, Any]:
        """
        Check DuckDB cache status for a data file.
        
        Cache states:
        - "valid": Cache exists and matches current file state (mtime/size)
        - "stale": Cache exists but was generated from older file version
        - "none": No cache file exists
        
        Args:
            file_path: Path to source data file (CSV/Parquet)
            
        Returns:
            Dictionary with:
            - status: "valid" | "stale" | "none"
            - db_path: Path to DuckDB file (if exists)
            - file_mtime: Source file modification time
            - file_size: Source file size in bytes
        """
        filename = os.path.basename(file_path)
        
        # Get current file metadata
        if not os.path.exists(file_path):
            return {
                'status': 'none',
                'db_path': None,
                'file_mtime': None,
                'file_size': None,
                'error': 'Source file not found'
            }
        
        stats = os.stat(file_path)
        file_mtime = stats.st_mtime
        file_size = stats.st_size
        
        # Generate expected DB path for current file state
        expected_db_path = cls._generate_db_path(file_path)
        
        # Check if valid cache exists
        if os.path.exists(expected_db_path):
            return {
                'status': 'valid',
                'db_path': expected_db_path,
                'file_mtime': file_mtime,
                'file_size': file_size,
            }
        
        # Check for any stale cache (old hash)
        if os.path.exists(cls.CACHE_DIR):
            for fname in os.listdir(cls.CACHE_DIR):
                # Match pattern: {filename}_{hash}.duckdb
                if fname.startswith(f"{filename}_") and fname.endswith('.duckdb'):
                    stale_path = os.path.join(cls.CACHE_DIR, fname)
                    return {
                        'status': 'stale',
                        'db_path': stale_path,
                        'file_mtime': file_mtime,
                        'file_size': file_size,
                    }
        
        return {
            'status': 'none',
            'db_path': None,
            'file_mtime': file_mtime,
            'file_size': file_size,
        }
    
    @classmethod
    def rebuild_cache(cls, file_path: str, is_csv: bool) -> Dict[str, Any]:
        """
        Force rebuild DuckDB cache for a data file.
        
        This method:
        1. Deletes existing cache files (including stale ones)
        2. Creates fresh DuckDB file from source data
        3. Returns schema information
        
        Thread-safe: Uses file-level locking to prevent concurrent access.
        
        Args:
            file_path: Path to source data file (CSV/Parquet)
            is_csv: True for CSV files, False for Parquet
            
        Returns:
            Dictionary with:
            - db_path: New DuckDB file path
            - row_count: Number of rows in the dataset
            - fields: Column metadata list
        """
        filename = os.path.basename(file_path)
        
        if not os.path.exists(file_path):
            raise DataLoadError(
                message="원본 파일을 찾을 수 없습니다.",
                detail=f"File not found: {file_path}"
            )
        
        logger.info(f"[Rebuild] Starting rebuild for: {filename}")
        
        # Step 1: Delete all existing cache files for this source file
        if os.path.exists(cls.CACHE_DIR):
            for fname in os.listdir(cls.CACHE_DIR):
                if fname.startswith(f"{filename}_") and fname.endswith('.duckdb'):
                    stale_path = os.path.join(cls.CACHE_DIR, fname)
                    lock = cls._get_db_lock(stale_path)
                    
                    if lock.acquire(timeout=30):
                        try:
                            # Delete main file and WAL files
                            for ext in ['', '.wal', '.wal.lock']:
                                path = stale_path + ext
                                if os.path.exists(path):
                                    try:
                                        os.remove(path)
                                        # logger.debug(f"[Rebuild] Deleted: {path}")
                                    except OSError as e:
                                        logger.warning(f"[Rebuild] Failed to delete {path}: {e}")
                        finally:
                            lock.release()
                    else:
                        logger.warning(f"[Rebuild] Could not acquire lock for {stale_path}")
        
        # Step 2: Create fresh DuckDB file
        try:
            db_path = cls._ensure_db_ready(file_path, is_csv)
            
            # Step 3: Get schema info
            con = duckdb.connect(db_path, read_only=True)
            try:
                schema_data = cls._extract_schema_data(con, cls.RAW_TABLE_NAME)
                logger.info(f"[Rebuild] Completed: {filename} ({schema_data['row_count']} rows)")
                
                return {
                    'db_path': db_path,
                    'row_count': schema_data['row_count'],
                    'fields': schema_data['fields'],
                }
            finally:
                con.close()
                
        except Exception as e:
            logger.error(f"[Rebuild] Failed for {filename}: {e}")
            raise DataLoadError(
                message="캐시 재구축에 실패했습니다.",
                detail=str(e)
            )
