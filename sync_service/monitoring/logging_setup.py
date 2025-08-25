"""
Logging configuration and setup for sync service.

This module provides structured logging with support for JSON formatting,
file rotation, and different log levels.
"""

import logging
import logging.config
import logging.handlers
import sys
import json
from datetime import datetime
from typing import Any, Dict, Optional
from pathlib import Path

from config.settings import LoggingConfig


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        # Create base log entry
        log_entry = {
            "timestamp": datetime.utcfromtimestamp(record.created).isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
            
        # Add extra fields from LoggerAdapter or custom fields
        if hasattr(record, 'sync_operation_id'):
            log_entry["sync_operation_id"] = record.sync_operation_id
        if hasattr(record, 'data_type'):
            log_entry["data_type"] = record.data_type
        if hasattr(record, 'batch_size'):
            log_entry["batch_size"] = record.batch_size
        if hasattr(record, 'processing_time'):
            log_entry["processing_time"] = record.processing_time
            
        return json.dumps(log_entry)


class TextFormatter(logging.Formatter):
    """Custom text formatter with sync-specific fields."""
    
    def __init__(self):
        super().__init__(
            fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as text with optional extra fields."""
        base_message = super().format(record)
        
        # Add extra fields if present
        extra_fields = []
        if hasattr(record, 'sync_operation_id'):
            extra_fields.append(f"op_id={record.sync_operation_id}")
        if hasattr(record, 'data_type'):
            extra_fields.append(f"type={record.data_type}")
        if hasattr(record, 'batch_size'):
            extra_fields.append(f"batch={record.batch_size}")
        if hasattr(record, 'processing_time'):
            extra_fields.append(f"time={record.processing_time:.2f}s")
            
        if extra_fields:
            base_message += f" [{', '.join(extra_fields)}]"
            
        return base_message


class SyncLoggerAdapter(logging.LoggerAdapter):
    """Logger adapter for sync operations with contextual information."""
    
    def __init__(self, logger: logging.Logger, sync_operation_id: Optional[str] = None):
        """
        Initialize logger adapter.
        
        Args:
            logger: Base logger instance
            sync_operation_id: Optional sync operation identifier
        """
        extra = {}
        if sync_operation_id:
            extra['sync_operation_id'] = sync_operation_id
            
        super().__init__(logger, extra)
        
    def process(self, msg: Any, kwargs: Dict[str, Any]) -> tuple:
        """Process log message and add extra context."""
        # Add sync operation ID if available
        extra = kwargs.get('extra', {})
        extra.update(self.extra)
        kwargs['extra'] = extra
        
        return msg, kwargs
        
    def log_batch_processing(
        self, 
        level: int,
        data_type: str,
        batch_size: int,
        processing_time: float,
        success_count: int,
        error_count: int = 0
    ):
        """Log batch processing results with structured data."""
        message = f"Processed {data_type} batch: {success_count}/{batch_size} successful"
        if error_count > 0:
            message += f", {error_count} errors"
            
        self.log(
            level, 
            message,
            extra={
                'data_type': data_type,
                'batch_size': batch_size,
                'processing_time': processing_time,
                'success_count': success_count,
                'error_count': error_count,
            }
        )
        
    def log_sync_start(self, mode: str, since_timestamp: Optional[datetime] = None):
        """Log sync operation start."""
        message = f"Starting {mode} sync"
        extra = {'sync_mode': mode}
        
        if since_timestamp:
            message += f" since {since_timestamp}"
            extra['since_timestamp'] = since_timestamp.isoformat()
            
        self.info(message, extra=extra)
        
    def log_sync_complete(
        self, 
        mode: str, 
        duration_seconds: float,
        total_items: int,
        success_rate: float
    ):
        """Log sync operation completion."""
        message = f"Completed {mode} sync: {total_items} items in {duration_seconds:.2f}s ({success_rate:.1%} success)"
        
        self.info(
            message,
            extra={
                'sync_mode': mode,
                'duration_seconds': duration_seconds,
                'total_items': total_items,
                'success_rate': success_rate,
            }
        )
        
    def log_sync_error(self, mode: str, error: Exception, duration_seconds: float = 0.0):
        """Log sync operation error."""
        message = f"Failed {mode} sync after {duration_seconds:.2f}s: {error}"
        
        self.error(
            message,
            extra={
                'sync_mode': mode,
                'duration_seconds': duration_seconds,
                'error_type': type(error).__name__,
            },
            exc_info=True
        )


def setup_logging(config: LoggingConfig) -> None:
    """
    Set up logging configuration for the sync service.
    
    Args:
        config: Logging configuration
    """
    # Choose formatter based on config
    if config.format == "json":
        formatter = JSONFormatter()
    else:
        formatter = TextFormatter()
        
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, config.level))
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Console handler (always present)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(getattr(logging, config.level))
    root_logger.addHandler(console_handler)
    
    # File handler (optional)
    if config.file_path:
        file_path = Path(config.file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.handlers.RotatingFileHandler(
            filename=config.file_path,
            maxBytes=config.max_file_size_mb * 1024 * 1024,  # Convert MB to bytes
            backupCount=config.backup_count,
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(getattr(logging, config.level))
        root_logger.addHandler(file_handler)
        
    # Set specific logger levels to reduce noise
    logging.getLogger('neo4j').setLevel(logging.WARNING)
    logging.getLogger('falkordb').setLevel(logging.WARNING)
    logging.getLogger('asyncio').setLevel(logging.WARNING)
    
    # Log successful setup
    logger = logging.getLogger(__name__)
    logger.info(f"Logging initialized: level={config.level}, format={config.format}")
    if config.file_path:
        logger.info(f"Log file: {config.file_path}")


def get_sync_logger(name: str, sync_operation_id: Optional[str] = None) -> SyncLoggerAdapter:
    """
    Get a logger adapter for sync operations.
    
    Args:
        name: Logger name
        sync_operation_id: Optional sync operation identifier
        
    Returns:
        SyncLoggerAdapter instance
    """
    base_logger = logging.getLogger(name)
    return SyncLoggerAdapter(base_logger, sync_operation_id)


def log_performance_metrics(
    logger: logging.Logger,
    operation: str,
    duration_seconds: float,
    items_processed: int = 0,
    memory_usage_mb: Optional[float] = None
):
    """
    Log performance metrics for analysis.
    
    Args:
        logger: Logger instance
        operation: Operation name
        duration_seconds: Operation duration
        items_processed: Number of items processed
        memory_usage_mb: Optional memory usage in MB
    """
    message = f"Performance: {operation} took {duration_seconds:.2f}s"
    extra = {
        'operation': operation,
        'duration_seconds': duration_seconds,
        'performance_metric': True
    }
    
    if items_processed > 0:
        items_per_second = items_processed / duration_seconds if duration_seconds > 0 else 0
        message += f", {items_processed} items ({items_per_second:.1f} items/s)"
        extra['items_processed'] = items_processed
        extra['items_per_second'] = items_per_second
        
    if memory_usage_mb is not None:
        message += f", {memory_usage_mb:.1f}MB memory"
        extra['memory_usage_mb'] = memory_usage_mb
        
    logger.info(message, extra=extra)


def log_database_stats(
    logger: logging.Logger,
    database_name: str,
    stats: Dict[str, Any]
):
    """
    Log database statistics.
    
    Args:
        logger: Logger instance
        database_name: Name of database
        stats: Dictionary of statistics
    """
    total_items = sum(v for v in stats.values() if isinstance(v, int))
    
    message = f"{database_name} stats: {total_items} total items"
    extra = {
        'database': database_name,
        'database_stats': True,
        'total_items': total_items,
        **stats
    }
    
    logger.info(message, extra=extra)