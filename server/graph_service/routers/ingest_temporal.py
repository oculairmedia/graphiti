"""
Temporal-native ingestion router for Graphiti.
Starts Temporal workflows directly without intermediate queue.
"""

import logging
import uuid as uuid_lib
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from graph_service.dto import AddMessagesRequest

logger = logging.getLogger(__name__)

router = APIRouter()


class TemporalIngestionStatus(BaseModel):
    episode_uuid: str
    workflow_id: str
    status: str = 'started'
    message: str


class TemporalIngestionResponse(BaseModel):
    success: bool
    message: str
    workflows: List[TemporalIngestionStatus]


def _get_temporal_client():
    """Lazily import and get Temporal ingestion client."""
    from graphiti_core.utils.temporal_visibility.client import (
        TemporalIngestionClient,
        TemporalIngestionConfig,
    )

    config = TemporalIngestionConfig.from_env()
    if not config.enabled:
        return None
    return TemporalIngestionClient(config)


@router.post('/temporal/messages', response_model=TemporalIngestionResponse)
async def ingest_messages_temporal(request: AddMessagesRequest):
    """
    Ingest messages via Temporal workflows.

    Each message spawns a separate Temporal workflow for processing.
    Returns immediately with workflow IDs for tracking.
    """
    temporal_client = _get_temporal_client()

    if temporal_client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='Temporal ingestion is not enabled. Set TEMPORAL_INGESTION_ENABLED=true',
        )

    workflows = []
    errors = []

    for msg in request.messages:
        episode_uuid = msg.uuid or str(uuid_lib.uuid4())

        try:
            # Build source description with role info
            source_desc = msg.source_description or ''
            if msg.role:
                source_desc = f'{msg.role} ({msg.role_type}): {source_desc}'

            # Start Temporal workflow
            workflow_id = await temporal_client.start_ingestion(
                episode_uuid=episode_uuid,
                group_id=request.group_id,
                name=msg.name,
                episode_body=msg.content,
                source='message',
                source_description=source_desc,
                reference_time=msg.timestamp.isoformat()
                if msg.timestamp
                else datetime.now(timezone.utc).isoformat(),
            )

            if workflow_id:
                workflows.append(
                    TemporalIngestionStatus(
                        episode_uuid=episode_uuid,
                        workflow_id=workflow_id,
                        status='started',
                        message=f'Workflow {workflow_id} started',
                    )
                )
                logger.info(f'Started Temporal workflow {workflow_id} for episode {episode_uuid}')
            else:
                errors.append(f'Failed to start workflow for episode {episode_uuid}')
                logger.error(f'Failed to start Temporal workflow for episode {episode_uuid}')

        except Exception as e:
            errors.append(f'Error starting workflow for episode {episode_uuid}: {str(e)}')
            logger.error(f'Error starting Temporal workflow: {e}')

    if not workflows and errors:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'All workflows failed to start: {"; ".join(errors)}',
        )

    success = len(errors) == 0
    message = f'Started {len(workflows)} workflow(s)'
    if errors:
        message += f', {len(errors)} failed'

    return TemporalIngestionResponse(success=success, message=message, workflows=workflows)


@router.get('/temporal/workflow/{workflow_id}')
async def get_workflow_status(workflow_id: str):
    """
    Get the status of a Temporal workflow.
    """
    temporal_client = _get_temporal_client()

    if temporal_client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='Temporal ingestion is not enabled',
        )

    try:
        # Get workflow handle and query status
        client = await temporal_client._get_client()
        handle = client.get_workflow_handle(workflow_id)

        # Try to get the result (will raise if still running)
        try:
            description = await handle.describe()
            return {
                'workflow_id': workflow_id,
                'status': str(description.status),
                'start_time': description.start_time.isoformat()
                if description.start_time
                else None,
                'close_time': description.close_time.isoformat()
                if description.close_time
                else None,
            }
        except Exception as e:
            return {'workflow_id': workflow_id, 'status': 'unknown', 'error': str(e)}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Failed to get workflow status: {str(e)}',
        )
