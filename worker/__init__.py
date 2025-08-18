"""
Graphiti ingestion worker module.
Provides queue-based processing for scalable data ingestion.
"""

from .main import WorkerService

__all__ = ['WorkerService']