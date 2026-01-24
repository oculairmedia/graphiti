"""
Maintenance and tooling endpoints for Graphiti API.

Provides tools for graph maintenance operations like pruning stale nodes.
"""

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from graph_service.zep_graphiti import ZepGraphitiDep

router = APIRouter(prefix='/tools', tags=['tools'])


class PruneMissingFilesRequest(BaseModel):
    group_id: str = Field(..., description='Group ID to scope the pruning operation')
    active_files: list[str] = Field(
        ..., description='List of file paths that currently exist (will NOT be invalidated)'
    )
    file_patterns: list[str] | None = Field(
        None,
        description='Optional patterns to identify file nodes (default: common extensions)',
    )


class PruneMissingFilesResponse(BaseModel):
    invalidated_count: int
    invalidated_files: list[dict[str, str]]
    group_id: str
    active_files_count: int


@router.post('/prune-missing', response_model=PruneMissingFilesResponse)
async def prune_missing_files(
    request: PruneMissingFilesRequest,
    graphiti: ZepGraphitiDep,
) -> dict[str, Any]:
    """
    Mark file-like EntityNodes as invalid if they're not in the active files list.

    Use this endpoint after file deletions to clean up stale nodes from the graph.
    Nodes are marked with invalid_at timestamp rather than deleted (preserving history).

    Example:
        POST /api/tools/prune-missing
        {
            "group_id": "vibesync_project_123",
            "active_files": ["src/main.py", "src/utils.py", "README.md"]
        }

    This will invalidate any file-like nodes in that group that aren't in the active list.
    """
    from graphiti_core.utils.maintenance.node_operations import prune_stale_files

    result = await prune_stale_files(
        driver=graphiti.driver,
        group_id=request.group_id,
        active_files=request.active_files,
        file_patterns=request.file_patterns,
    )

    return result
