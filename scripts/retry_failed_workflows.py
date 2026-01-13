#!/usr/bin/env python3
"""
Retry timed-out/failed Temporal workflows by extracting original input
from workflow history and starting new workflows with longer timeout.
"""
import asyncio
import json
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def get_workflow_input(client, workflow_id: str) -> dict | None:
    """Extract original input from workflow history."""
    try:
        handle = client.get_workflow_handle(workflow_id)
        async for event in handle.fetch_history_events():
            if event.event_type == 1:  # WorkflowExecutionStarted
                attrs = event.workflow_execution_started_event_attributes
                if attrs.input and attrs.input.payloads:
                    payload_data = attrs.input.payloads[0].data
                    return json.loads(payload_data)
        return None
    except Exception as e:
        logger.error(f"Error getting input for {workflow_id}: {e}")
        return None


async def start_new_workflow(client, input_data: dict, task_queue: str, timeout_hours: int) -> str | None:
    """Start a new workflow with the same input but longer timeout."""
    from datetime import timedelta
    from graphiti_core.utils.temporal_visibility.ingestion_workflow import (
        IngestEpisodeWorkflow,
        IngestEpisodeInput,
    )
    
    episode_uuid = input_data['episode_uuid']
    new_wf_id = f"retry-{episode_uuid}"
    
    try:
        inp = IngestEpisodeInput(
            episode_uuid=episode_uuid,
            group_id=input_data['group_id'],
            name=input_data['name'],
            episode_body=input_data['episode_body'],
            source=input_data['source'],
            source_description=input_data['source_description'],
            reference_time=input_data['reference_time'],
            entity_types=input_data.get('entity_types'),
            excluded_entity_types=input_data.get('excluded_entity_types'),
            edge_types=input_data.get('edge_types'),
            edge_type_map=input_data.get('edge_type_map'),
            previous_episode_uuids=input_data.get('previous_episode_uuids'),
            store_raw_content=input_data.get('store_raw_content', True),
        )
        
        handle = await client.start_workflow(
            IngestEpisodeWorkflow.run,
            args=[inp],
            id=new_wf_id,
            task_queue=task_queue,
            execution_timeout=timedelta(hours=timeout_hours),
        )
        logger.info(f"Started retry workflow: {new_wf_id}")
        return new_wf_id
    except Exception as e:
        if "already started" in str(e).lower():
            logger.info(f"Workflow {new_wf_id} already exists, skipping")
            return None
        logger.error(f"Error starting workflow for {episode_uuid}: {e}")
        return None


async def main():
    from temporalio.client import Client
    
    # Config
    temporal_address = os.getenv('TEMPORAL_VISIBILITY_ADDRESS', '192.168.50.90:7233')
    namespace = os.getenv('TEMPORAL_VISIBILITY_NAMESPACE', 'graphiti')
    task_queue = os.getenv('TEMPORAL_INGESTION_TASK_QUEUE', 'graphiti-ingestion')
    timeout_hours = int(os.getenv('TEMPORAL_INGESTION_WORKFLOW_TIMEOUT_HOURS', '8'))
    
    # How many to retry (pass as arg or default to 100)
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    
    logger.info(f"Connecting to Temporal at {temporal_address}")
    client = await Client.connect(temporal_address, namespace=namespace)
    
    # Get failed/timed-out workflow IDs
    failed_wf_ids = []
    
    # Get timed out workflows
    logger.info("Fetching timed-out workflows...")
    async for wf in client.list_workflows(query="ExecutionStatus = 'TimedOut'"):
        if wf.id.startswith('ingest-episode-'):
            failed_wf_ids.append(wf.id)
            if len(failed_wf_ids) >= limit:
                break
    
    # Get failed workflows if we need more
    if len(failed_wf_ids) < limit:
        logger.info("Fetching failed workflows...")
        async for wf in client.list_workflows(query="ExecutionStatus = 'Failed'"):
            if wf.id.startswith('ingest-episode-'):
                failed_wf_ids.append(wf.id)
                if len(failed_wf_ids) >= limit:
                    break
    
    logger.info(f"Found {len(failed_wf_ids)} failed workflows to retry")
    
    # Process each
    retried = 0
    skipped = 0
    errors = 0
    
    for i, wf_id in enumerate(failed_wf_ids):
        logger.info(f"Processing {i+1}/{len(failed_wf_ids)}: {wf_id}")
        
        input_data = await get_workflow_input(client, wf_id)
        if not input_data:
            logger.warning(f"Could not get input for {wf_id}")
            errors += 1
            continue
        
        new_wf_id = await start_new_workflow(client, input_data, task_queue, timeout_hours)
        if new_wf_id:
            retried += 1
        else:
            skipped += 1
        
        # Small delay to avoid overwhelming
        await asyncio.sleep(0.1)
    
    logger.info(f"Done! Retried: {retried}, Skipped: {skipped}, Errors: {errors}")


if __name__ == '__main__':
    asyncio.run(main())
