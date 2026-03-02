from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from django.conf import settings
import os
import re
import logging
import uuid
import random
import threading
from .utils import DuckDBEngine
from .exceptions import (
    DataExplorerBaseError,
    SessionExpiredError,
    QueryValidationError,
    DSLParsingError,
    DataLoadError,
)

logger = logging.getLogger(__name__)

# Configuration for data directory
DATA_DIR = os.path.join(settings.BASE_DIR.parent, 'data', 'data_explorer')
MAX_UPLOAD_SIZE_MB = 100


def _get_file_metadata_helper(filename):
    """
    Helper function to get file mtime and size.
    Defined at module level for use by multiple view classes.
    """
    if not filename:
        return None, None
    
    # Security check
    if '..' in filename or '/' in filename or '\\' in filename:
        return None, None
    
    file_path = os.path.normpath(os.path.join(DATA_DIR, filename))
    if not file_path.startswith(os.path.normpath(DATA_DIR)):
        return None, None
    
    if os.path.exists(file_path):
        stats = os.stat(file_path)
        return stats.st_mtime, stats.st_size
    
    return None, None

class DatasetListView(APIView):
    """
    Returns a list of files in the project's data directory that can be loaded by DuckDB.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        # Trigger cleanup of old temporary DB files with 1% probability
        if random.randint(1, 100) == 1:
            threading.Thread(target=DuckDBEngine.cleanup_old_upload_dbs, daemon=True).start()

        if not os.path.exists(DATA_DIR):
            try:
                os.makedirs(DATA_DIR)
            except Exception as e:
                return Response({"error": f"Could not create data directory: {str(e)}"}, status=500)

        datasets = []
        allowed_extensions = ['.csv', '.parquet', '.tsv']
        
        try:
            for filename in os.listdir(DATA_DIR):
                # Basic security check: skip hidden files
                # Also skip 'uploaded_' files as they are temporary and processed separately
                if filename.startswith('.') or filename.startswith('uploaded_'):
                    continue
                    
                ext = os.path.splitext(filename)[1].lower()
                if ext in allowed_extensions:
                    file_path = os.path.join(DATA_DIR, filename)
                    try:
                        stats = os.stat(file_path)
                        datasets.append({
                            "name": filename,
                            "size": stats.st_size,
                            "modified": stats.st_mtime,
                            "extension": ext.replace('.', '')
                        })
                    except PermissionError:
                        logger.warning(f"Permission denied accessing file: {filename}")
                        continue
            
            # Sort by name (A-Z, case-insensitive)
            datasets.sort(key=lambda x: x['name'].lower())
            
            return Response({"datasets": datasets}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Error listing datasets: {e}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DatasetInitView(APIView):
    """
    Initializes a dataset session.
    Loads data into persistent DuckDB (if needed) and returns schema fields.
    
    Supports optional 'columns' parameter for user-selected columns and types.
    """
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = (JSONParser,)

    def post(self, request):
        filename = request.data.get('filename')
        columns = request.data.get('columns')  # Optional: user-selected columns
        
        if not filename:
            return Response({"error": "Filename is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Security check
        if '..' in filename or '/' in filename or '\\' in filename:
             return Response({"error": "Invalid filename format"}, status=status.HTTP_400_BAD_REQUEST)

        file_path = os.path.normpath(os.path.join(DATA_DIR, filename))
        if not file_path.startswith(os.path.normpath(DATA_DIR)) or not os.path.exists(file_path):
            return Response({"error": "File not found"}, status=status.HTTP_404_NOT_FOUND)

        is_csv = not filename.lower().endswith('.parquet')

        try:
            selected_columns = None
            user_selections = {}
            column_types = {}

            # Build include list and semantic type mapping from user selections
            if columns:
                for col in columns:
                    if not isinstance(col, dict):
                        continue
                    name = col.get('name')
                    if not name:
                        continue
                    user_selections[name] = col

                selected_columns = [
                    name for name, cfg in user_selections.items()
                    if cfg.get('include', True)
                ]
                
                # Build column_types dict for included columns
                for name in selected_columns:
                    cfg = user_selections.get(name)
                    if cfg and cfg.get('semantic_type'):
                        column_types[name] = cfg['semantic_type']

            # Configure projection with user-specified types (type casting applied)
            schema_data = DuckDBEngine.configure_projection(
                file_path,
                is_csv,
                selected_columns=selected_columns,
                column_types=column_types,
            )

            # Respect projection-applied type fallback (e.g., temporal -> nominal when parsing fails).
            applied_types = schema_data.get('applied_column_types', {})
            for field in schema_data['fields']:
                col_name = field['fid']
                selection = user_selections.get(col_name)
                if not selection:
                    continue

                requested_type = selection.get('semantic_type')
                applied_type = applied_types.get(col_name)

                final_type = applied_type or requested_type
                if final_type in ['quantitative', 'temporal', 'nominal']:
                    field['semanticType'] = final_type
                    field['analyticType'] = 'measure' if final_type == 'quantitative' else 'dimension'
            
            # Security & Cleanup: If this was an uploaded file, delete the raw file
            # because data is now securely stored in the DuckDB persistent store.
            if filename.startswith('uploaded_') and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logger.info(f"Deleted temporary upload file: {filename}")
                except Exception as cleanup_error:
                    logger.warning(f"Failed to delete upload file {filename}: {cleanup_error}")

            # 이용량 로그 기록
            try:
                from apps.core.models import AppUsageLog
                AppUsageLog.objects.create(user=request.user, app='data_explorer')
            except Exception as log_err:
                logger.warning(f"[UsageLog] Data Explorer 로그 저장 실패: {log_err}")

            return Response({
                "fields": schema_data['fields'],
                "filename": filename,
                "row_count": schema_data['row_count'],
                "selected_columns": schema_data.get('selected_columns', []),
                "success": True
            }, status=status.HTTP_200_OK)
            
        except DataExplorerBaseError as e:
            logger.warning(f"Dataset init error ({type(e).__name__}): {e.message}")
            return Response(e.to_response_dict(include_detail=settings.DEBUG), status=e.status_code)
        except Exception as e:
            logger.exception(f"Dataset initialization failed: {e}")
            error_response = {"error": "데이터셋 초기화에 실패했습니다."}
            if settings.DEBUG:
                error_response["detail"] = str(e)
            return Response(error_response, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DatasetQueryView(APIView):
    """
    Executes SQL queries for Graphic Walker computation mode.
    
    Error Handling:
    - Custom exceptions are converted to appropriate HTTP responses
    - Technical details are only included in DEBUG mode
    """
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = (JSONParser,)

    def post(self, request):
        filename = request.data.get('filename')
        query = request.data.get('query')
        
        logger.info(f"Incoming Query for {filename}: {query}")

        if not filename or not query:
            return Response({"error": "Filename and query are required"}, status=status.HTTP_400_BAD_REQUEST)

        # Security check
        if '..' in filename or '/' in filename or '\\' in filename:
             return Response({"error": "Invalid filename format"}, status=status.HTTP_400_BAD_REQUEST)

        file_path = os.path.normpath(os.path.join(DATA_DIR, filename))
        
        try:
            # Execute query using the persistent engine
            result_data = DuckDBEngine.execute_query(file_path, query)
            return Response(result_data, status=status.HTTP_200_OK)
            
        except DataExplorerBaseError as e:
            # Custom exceptions have user-friendly messages and status codes
            logger.warning(f"Query error ({type(e).__name__}): {e.message}")
            response_data = e.to_response_dict(include_detail=settings.DEBUG)
            return Response(response_data, status=e.status_code)
        except FileNotFoundError:
            # Legacy fallback for old-style FileNotFoundError
            return Response(
                {"error": "세션이 만료되었습니다. 데이터셋을 다시 로드해주세요."},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            # Unexpected errors - log full details, return safe message
            logger.exception(f"Unexpected query error: {e}")
            error_response = {"error": "쿼리 실행 중 오류가 발생했습니다."}
            if settings.DEBUG:
                error_response["detail"] = str(e)
            return Response(error_response, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DatasetUploadView(APIView):
    """
    Handles file uploads for analysis.
    Files are saved to the data directory and can be loaded via init-session.
    Strict size limit of 100MB applies.
    """
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request):
        file_obj = request.FILES.get('file')
        
        if not file_obj:
            return Response({"error": "No file uploaded"}, status=status.HTTP_400_BAD_REQUEST)

        # 1. Check File Size
        file_size_mb = file_obj.size / (1024 * 1024)
        if file_size_mb > MAX_UPLOAD_SIZE_MB:
            return Response(
                {"error": f"File size exceeds the limit of {MAX_UPLOAD_SIZE_MB}MB. For larger files, please contact the administrator to add them to the server directly."},
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
            )

        # 2. Validate Extension
        ext = os.path.splitext(file_obj.name)[1].lower()
        if ext not in ['.csv', '.parquet', '.tsv']:
            return Response({"error": "Unsupported file type. Only CSV, Parquet, and TSV are allowed."}, status=status.HTTP_400_BAD_REQUEST)

        # 3. Save File
        # Use a unique prefix to avoid overwriting existing server datasets
        original_basename = os.path.basename(file_obj.name)
        sanitized_name = re.sub(r'[^A-Za-z0-9._-]+', '_', original_basename)
        if not sanitized_name or sanitized_name.startswith('.'):
            sanitized_name = f"file{ext}"
        safe_filename = f"uploaded_{uuid.uuid4().hex[:8]}_{sanitized_name}"
        file_path = os.path.join(DATA_DIR, safe_filename)

        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)

        try:
            with open(file_path, 'wb+') as destination:
                for chunk in file_obj.chunks():
                    destination.write(chunk)
            
            logger.info(f"File uploaded successfully: {safe_filename}")
            
            return Response({
                "filename": safe_filename,
                "original_name": file_obj.name,
                "message": "Upload successful"
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"File upload failed: {e}")
            return Response({"error": "Failed to save file"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DatasetPreviewView(APIView):
    """
    Returns preview data (first 10 rows) and detected column types.
    Used by Column Config Modal for user to select columns and set types.
    """
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = (JSONParser,)

    def post(self, request):
        filename = request.data.get('filename')
        
        if not filename:
            return Response({"error": "Filename is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Security check
        if '..' in filename or '/' in filename or '\\' in filename:
            return Response({"error": "Invalid filename format"}, status=status.HTTP_400_BAD_REQUEST)

        file_path = os.path.normpath(os.path.join(DATA_DIR, filename))
        if not file_path.startswith(os.path.normpath(DATA_DIR)) or not os.path.exists(file_path):
            return Response({"error": "File not found"}, status=status.HTTP_404_NOT_FOUND)

        is_csv = not filename.lower().endswith('.parquet')

        try:
            # Get preview data (10 rows) and detected columns
            preview_data = DuckDBEngine.get_preview_data(file_path, is_csv, limit=10)
            
            return Response({
                "success": True,
                "filename": filename,
                "preview": preview_data['preview'],
                "detected_columns": preview_data['detected_columns']
            }, status=status.HTTP_200_OK)
            
        except DataExplorerBaseError as e:
            logger.warning(f"Dataset preview error ({type(e).__name__}): {e.message}")
            return Response(e.to_response_dict(include_detail=settings.DEBUG), status=e.status_code)
        except Exception as e:
            logger.exception(f"Dataset preview failed: {e}")
            error_response = {"error": "데이터 미리보기를 불러올 수 없습니다."}
            if settings.DEBUG:
                error_response["detail"] = str(e)
            return Response(error_response, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== Preset Management Views ====================

from .models import DataExplorerPreset
from .serializers import DataExplorerPresetListSerializer, DataExplorerPresetDetailSerializer
from django.db.models import Q


class PresetListCreateView(APIView):
    """
    List all presets for the current user (includes public presets), or create a new preset.
    Admin users can see ALL presets.
    """
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = (JSONParser,)

    def get(self, request):
        """List all presets: user's own presets + public presets from other users.
        Admin users can see ALL presets.
        """
        is_admin = request.user.is_superuser or request.user.is_staff
        
        if is_admin:
            # Admin sees all presets
            presets = DataExplorerPreset.objects.select_related('user').all().order_by('-updated_at')
        else:
            # Regular user sees own presets + public presets
            presets = DataExplorerPreset.objects.filter(
                Q(user=request.user) | Q(is_public=True)
            ).select_related('user').distinct().order_by('-updated_at')
        
        serializer = DataExplorerPresetListSerializer(presets, many=True, context={'request': request})
        return Response({"presets": serializer.data, "is_admin": is_admin}, status=status.HTTP_200_OK)

    def post(self, request):
        """Create a new preset with file metadata for change detection."""
        import copy
        
        # Deep copy request data to safely modify
        data = copy.deepcopy(dict(request.data))
        data_config = data.get('data_config', {})
        
        if isinstance(data_config, dict) and 'filename' in data_config:
            filename = data_config['filename']
            mtime, size = _get_file_metadata_helper(filename)
            logger.info(f"[Preset Save] filename={filename}, mtime={mtime}, size={size}")
            if mtime is not None:
                data_config['file_mtime'] = mtime
                data_config['file_size'] = size
                data['data_config'] = data_config
                logger.info(f"[Preset Save] data_config updated with metadata")
        
        serializer = DataExplorerPresetDetailSerializer(data=data, context={'request': request})
        
        if serializer.is_valid():
            preset = serializer.save(user=request.user)
            logger.info(f"[Preset Save] Saved preset ID={preset.id}, data_config={preset.data_config}")
            
            return Response({
                "success": True,
                "preset": DataExplorerPresetDetailSerializer(preset).data
            }, status=status.HTTP_201_CREATED)
        
        return Response({
            "success": False,
            "errors": serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


class PresetDetailView(APIView):
    """
    Retrieve, update, or delete a specific preset.
    Includes file existence validation on GET.
    """
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = (JSONParser,)

    def _get_preset_for_read(self, request, preset_id):
        """Helper to get preset for reading (owner/public/admin)."""
        try:
            preset = DataExplorerPreset.objects.get(id=preset_id)
            is_admin = request.user.is_superuser or request.user.is_staff
            # Allow access if user owns it OR it's public OR user is admin
            if preset.user_id == request.user.id or preset.is_public or is_admin:
                return preset
            return None
        except DataExplorerPreset.DoesNotExist:
            return None

    def _get_preset_for_write(self, request, preset_id):
        """Helper to get preset for writing (ownership required)."""
        try:
            return DataExplorerPreset.objects.get(id=preset_id, user=request.user)
        except DataExplorerPreset.DoesNotExist:
            return None

    def _check_file_exists(self, filename):
        """Check if the source data file exists (not cache)."""
        if not filename:
            return False
        
        # Security check
        if '..' in filename or '/' in filename or '\\' in filename:
            return False
        
        file_path = os.path.normpath(os.path.join(DATA_DIR, filename))
        if not file_path.startswith(os.path.normpath(DATA_DIR)):
            return False
        
        # Check source file only (not DuckDB cache)
        return os.path.exists(file_path)

    def _get_file_metadata(self, filename):
        """Get file mtime and size for change detection."""
        return _get_file_metadata_helper(filename)

    def _check_file_changed(self, data_config):
        """
        Check if file has changed since preset was saved.
        Returns True if file mtime or size differs from saved values.
        """
        filename = data_config.get('filename', '')
        saved_mtime = data_config.get('file_mtime')
        saved_size = data_config.get('file_size')
        
        # If no saved metadata, can't detect changes (old preset)
        if saved_mtime is None or saved_size is None:
            logger.debug(f"[Preset Load] No saved metadata for {filename}, cannot detect changes")
            return False
        
        current_mtime, current_size = _get_file_metadata_helper(filename)
        
        # If file doesn't exist, return False (file_exists check handles this)
        if current_mtime is None:
            return False
        
        # Check if mtime or size changed
        changed = current_mtime != saved_mtime or current_size != saved_size
        if changed:
            logger.info(f"[Preset Load] File changed: {filename}, saved_mtime={saved_mtime}, current_mtime={current_mtime}, saved_size={saved_size}, current_size={current_size}")
        return changed

    def get(self, request, preset_id):
        """Retrieve a preset with file existence validation."""
        preset = self._get_preset_for_read(request, preset_id)
        if not preset:
            return Response({"error": "Preset not found"}, status=status.HTTP_404_NOT_FOUND)
        
        serializer = DataExplorerPresetDetailSerializer(preset, context={'request': request})
        data = serializer.data
        
        # Add file existence flag
        filename = preset.data_config.get('filename', '')
        data['file_exists'] = self._check_file_exists(filename)
        
        # Add file changed flag (check if mtime/size differs)
        data['file_changed'] = self._check_file_changed(preset.data_config)
        
        return Response({
            "success": True,
            "preset": data
        }, status=status.HTTP_200_OK)

    def put(self, request, preset_id):
        """Update a preset (owner only)."""
        preset = self._get_preset_for_write(request, preset_id)
        if not preset:
            return Response({"error": "Preset not found or access denied"}, status=status.HTTP_404_NOT_FOUND)
        
        serializer = DataExplorerPresetDetailSerializer(preset, data=request.data, partial=True)
        
        if serializer.is_valid():
            preset = serializer.save()
            return Response({
                "success": True,
                "preset": DataExplorerPresetDetailSerializer(preset).data
            }, status=status.HTTP_200_OK)
        
        return Response({
            "success": False,
            "errors": serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, preset_id):
        """Delete a preset. Owner or admin can delete."""
        # First check if user owns the preset
        preset = self._get_preset_for_write(request, preset_id)
        is_owner = preset is not None
        
        # If not owner, check if admin
        is_admin = request.user.is_superuser or request.user.is_staff
        
        if not is_owner and not is_admin:
            return Response({"error": "Preset not found or access denied"}, status=status.HTTP_404_NOT_FOUND)
        
        # If not owner but admin, get the preset
        if not preset:
            try:
                preset = DataExplorerPreset.objects.get(id=preset_id)
            except DataExplorerPreset.DoesNotExist:
                return Response({"error": "Preset not found"}, status=status.HTTP_404_NOT_FOUND)
        
        preset_name = preset.name
        preset.delete()
        
        return Response({
            "success": True,
            "message": f"Preset '{preset_name}' deleted successfully"
        }, status=status.HTTP_200_OK)


# ============================================================================
# Cache Rebuild Endpoints
# ============================================================================

class CacheStatusView(APIView):
    """
    Check DuckDB cache status for one or all data files.
    
    GET /api/data-explorer/cache-status/
        Returns status for all files in data directory
        
    GET /api/data-explorer/cache-status/?file=filename.csv
        Returns status for a specific file
    
    Response format:
        {
            "files": [
                {
                    "name": "data.csv",
                    "status": "valid" | "stale" | "none",
                    "file_mtime": 1234567890.0,
                    "file_size": 1024
                },
                ...
            ]
        }
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        filename = request.query_params.get('file')
        
        if filename:
            # Single file status check
            file_path = os.path.join(DATA_DIR, filename)
            
            # Security: validate filename
            if not filename or '..' in filename or filename.startswith('/'):
                return Response(
                    {"error": "Invalid filename"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if not os.path.exists(file_path):
                return Response(
                    {"error": f"File not found: {filename}"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            status_info = DuckDBEngine.get_cache_status(file_path)
            return Response({
                "files": [{
                    "name": filename,
                    **status_info
                }]
            })
        
        # All files status check
        if not os.path.exists(DATA_DIR):
            return Response({"files": []})
        
        allowed_extensions = ['.csv', '.parquet', '.tsv']
        files = []
        
        for fname in os.listdir(DATA_DIR):
            if fname.startswith('.') or fname.startswith('uploaded_'):
                continue
            
            ext = os.path.splitext(fname)[1].lower()
            if ext in allowed_extensions:
                file_path = os.path.join(DATA_DIR, fname)
                status_info = DuckDBEngine.get_cache_status(file_path)
                files.append({
                    "name": fname,
                    **status_info
                })
        
        # Sort by name
        files.sort(key=lambda x: x['name'].lower())
        
        return Response({"files": files})


class RebuildStartView(APIView):
    """
    Start a DuckDB cache rebuild task.
    
    POST /api/data-explorer/rebuild/start/
    Body:
        {
            "files": ["data1.csv", "data2.parquet"]
        }
    
    Response:
        {
            "task_id": "rebuild_abc123def456",
            "total": 2,
            "status": "pending"
        }
    """
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [JSONParser]
    
    def post(self, request):
        from .tasks import RebuildTaskManager
        
        files = request.data.get('files', [])
        
        if not files:
            return Response(
                {"error": "No files specified"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate file list
        valid_files = []
        errors = []
        
        for filename in files:
            if not filename or '..' in filename or filename.startswith('/'):
                errors.append(f"Invalid filename: {filename}")
                continue
            
            file_path = os.path.join(DATA_DIR, filename)
            if not os.path.exists(file_path):
                errors.append(f"File not found: {filename}")
                continue
            
            valid_files.append(filename)
        
        if not valid_files:
            return Response(
                {"error": "No valid files to rebuild", "details": errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create and start task
        task = RebuildTaskManager.create_task(valid_files)
        RebuildTaskManager.start_background(task.task_id)
        
        response_data = {
            "task_id": task.task_id,
            "total": task.total,
            "status": task.status,
        }
        
        if errors:
            response_data["warnings"] = errors
        
        return Response(response_data, status=status.HTTP_202_ACCEPTED)


class RebuildStatusView(APIView):
    """
    Get status of a running rebuild task.
    
    GET /api/data-explorer/rebuild/status/<task_id>/
    
    Response:
        {
            "task_id": "rebuild_abc123def456",
            "status": "running" | "completed" | "partial" | "failed",
            "total": 2,
            "completed": 1,
            "current": "data2.parquet",
            "results": [
                {"name": "data1.csv", "success": true, "row_count": 1000},
                ...
            ],
            "error": null
        }
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, task_id):
        from .tasks import RebuildTaskManager
        
        task = RebuildTaskManager.get_task(task_id)
        
        if not task:
            return Response(
                {"error": "Task not found or expired"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        return Response(task.to_dict())