"""Type stubs for graphiti_core.utils.datetime_utils module."""

from datetime import datetime
from typing import Optional, Union

def utc_now() -> datetime: ...

def parse_datetime(
    dt: Union[str, datetime, None],
    default: Optional[datetime] = None
) -> Optional[datetime]: ...

def format_datetime(dt: datetime) -> str: ...

def datetime_to_timestamp(dt: datetime) -> int: ...

def timestamp_to_datetime(timestamp: int) -> datetime: ...

__all__ = [
    'utc_now',
    'parse_datetime',
    'format_datetime',
    'datetime_to_timestamp',
    'timestamp_to_datetime',
]