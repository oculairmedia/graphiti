from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ConsolidationConfig:
    task_queue: str
    max_concurrent_activities: int

    @classmethod
    def from_env(cls) -> 'ConsolidationConfig':
        return cls(
            task_queue=os.getenv('TEMPORAL_CONSOLIDATION_TASK_QUEUE', 'graphiti-consolidation'),
            max_concurrent_activities=int(os.getenv('TEMPORAL_CONSOLIDATION_MAX_ACTIVITIES', '2')),
        )
