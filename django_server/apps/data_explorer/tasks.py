"""
Background task management for DuckDB rebuild operations.

This module provides:
1. In-memory task storage for tracking rebuild progress
2. Background thread execution for long-running rebuilds
3. Status polling support for frontend progress display

Usage:
    from .tasks import RebuildTaskManager
    
    task = RebuildTaskManager.create_task(['file1.csv', 'file2.csv'])
    RebuildTaskManager.start_background(task.task_id)
    
    # Poll status
    status = RebuildTaskManager.get_task(task.task_id)
"""

import threading
import time
import uuid
import os
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field

from django.conf import settings

logger = logging.getLogger(__name__)

# In-memory task storage
_tasks: Dict[str, 'RebuildTask'] = {}
_lock = threading.Lock()

# Task expiry (1 hour)
TASK_EXPIRY_SECONDS = 3600

# Data directory
DATA_DIR = os.path.join(settings.BASE_DIR.parent, 'data', 'data_explorer')


@dataclass
class RebuildTask:
    """
    Represents a DuckDB cache rebuild task.
    
    Attributes:
        task_id: Unique task identifier
        files: List of filenames to rebuild
        status: Task status (pending, running, completed, partial, failed)
        total: Total number of files
        completed: Number of completed files
        current: Currently processing filename
        results: List of per-file results
        error: Error message if failed
        created_at: Task creation timestamp
    """
    task_id: str
    files: List[str]
    status: str = "pending"  # pending, running, completed, partial, failed
    total: int = 0
    completed: int = 0
    current: Optional[str] = None
    results: List[dict] = field(default_factory=list)
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    
    def to_dict(self) -> dict:
        """Convert task to dictionary for API response."""
        return {
            "task_id": self.task_id,
            "status": self.status,
            "total": self.total,
            "completed": self.completed,
            "current": self.current,
            "results": self.results,
            "error": self.error,
        }


class RebuildTaskManager:
    """
    Manages DuckDB rebuild tasks.
    
    Provides:
    - Task creation and tracking
    - Background thread execution
    - Status polling
    - Automatic cleanup of old tasks
    """
    
    @classmethod
    def create_task(cls, filenames: List[str]) -> RebuildTask:
        """
        Create a new rebuild task.
        
        Args:
            filenames: List of filenames to rebuild
            
        Returns:
            New RebuildTask instance
        """
        task_id = f"rebuild_{uuid.uuid4().hex[:12]}"
        task = RebuildTask(
            task_id=task_id,
            files=filenames,
            total=len(filenames),
        )
        with _lock:
            _tasks[task_id] = task
            cls._cleanup_old_tasks()
        
        logger.info(f"[Rebuild Task] Created task {task_id} for {len(filenames)} files")
        return task
    
    @classmethod
    def get_task(cls, task_id: str) -> Optional[RebuildTask]:
        """
        Get task by ID.
        
        Args:
            task_id: Task identifier
            
        Returns:
            RebuildTask if found, None otherwise
        """
        with _lock:
            return _tasks.get(task_id)
    
    @classmethod
    def start_background(cls, task_id: str):
        """
        Start task execution in background thread.
        
        Args:
            task_id: Task identifier to execute
        """
        thread = threading.Thread(
            target=cls._execute_task,
            args=(task_id,),
            daemon=True,
            name=f"rebuild-{task_id}"
        )
        thread.start()
        logger.info(f"[Rebuild Task] Started background thread for {task_id}")
    
    @classmethod
    def _execute_task(cls, task_id: str):
        """
        Execute rebuild task (runs in background thread).
        
        Args:
            task_id: Task identifier to execute
        """
        # Import here to avoid circular imports
        from .utils import DuckDBEngine
        
        task = cls.get_task(task_id)
        if not task:
            logger.error(f"[Rebuild Task] Task not found: {task_id}")
            return
        
        task.status = "running"
        logger.info(f"[Rebuild Task] Starting execution for {task_id}")
        
        success_count = 0
        fail_count = 0
        
        for filename in task.files:
            task.current = filename
            file_path = os.path.join(DATA_DIR, filename)
            is_csv = not filename.lower().endswith('.parquet')
            
            logger.info(f"[Rebuild Task] Processing {filename}")
            
            try:
                result = DuckDBEngine.rebuild_cache(file_path, is_csv)
                task.results.append({
                    "name": filename,
                    "success": True,
                    "row_count": result["row_count"],
                    "message": None
                })
                success_count += 1
                logger.info(f"[Rebuild Task] Completed {filename}: {result['row_count']} rows")
                
            except Exception as e:
                logger.error(f"[Rebuild Task] Failed for {filename}: {e}")
                task.results.append({
                    "name": filename,
                    "success": False,
                    "row_count": None,
                    "message": str(e)
                })
                fail_count += 1
            
            task.completed += 1
        
        task.current = None
        
        # Set final status
        if fail_count == 0:
            task.status = "completed"
        elif success_count == 0:
            task.status = "failed"
            task.error = "All files failed to rebuild"
        else:
            task.status = "partial"
        
        logger.info(
            f"[Rebuild Task] Task {task_id} finished: "
            f"status={task.status}, success={success_count}, failed={fail_count}"
        )
    
    @classmethod
    def _cleanup_old_tasks(cls):
        """Remove expired tasks (called within lock)."""
        now = time.time()
        expired = [
            tid for tid, task in _tasks.items()
            if now - task.created_at > TASK_EXPIRY_SECONDS
        ]
        for tid in expired:
            del _tasks[tid]
            logger.debug(f"[Rebuild Task] Cleaned up expired task: {tid}")
