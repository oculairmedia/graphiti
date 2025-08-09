import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from functools import partial

import httpx
from fastapi import APIRouter, FastAPI, status
from graphiti_core.nodes import EpisodeType
from graphiti_core.utils.maintenance.graph_data_operations import clear_data

from graph_service.config import get_settings
from graph_service.dto import AddEntityNodeRequest, AddMessagesRequest, Message, Result
from graph_service.zep_graphiti import ZepGraphitiDep

logger = logging.getLogger(__name__)

# Centrality calculation debouncing
_centrality_timer = None
_centrality_groups = set()
_centrality_lock = asyncio.Lock()


async def trigger_centrality_calculation(group_id: str | None = None):
    """Trigger centrality calculation after data changes with debouncing"""
    global _centrality_timer, _centrality_groups

    async with _centrality_lock:
        # Cancel existing timer if any
        if _centrality_timer and not _centrality_timer.done():
            _centrality_timer.cancel()

        # Add group to process
        if group_id:
            _centrality_groups.add(group_id)

        # Schedule new calculation in 5 seconds
        _centrality_timer = asyncio.create_task(_delayed_centrality_calculation())


async def _delayed_centrality_calculation():
    """Execute centrality calculation after debounce delay"""
    global _centrality_groups

    # Wait for debounce delay
    await asyncio.sleep(5.0)

    async with _centrality_lock:
        groups_to_process = list(_centrality_groups)
        _centrality_groups.clear()

    print(
        f'=== CENTRALITY_DEBUG: Processing centrality for {len(groups_to_process)} groups ===',
        flush=True,
    )

    try:
        settings = get_settings()

        if not settings.use_rust_centrality:
            print('CENTRALITY_DEBUG: Rust centrality service disabled, skipping', flush=True)
            return

        # Use the Rust centrality service
        async with httpx.AsyncClient(timeout=30.0) as client:
            print(
                f'CENTRALITY_DEBUG: Calling centrality service at {settings.rust_centrality_url}',
                flush=True,
            )

            # If we have specific groups, process them individually
            if groups_to_process:
                for group_id in groups_to_process:
                    try:
                        response = await client.post(
                            f'{settings.rust_centrality_url}/centrality/all',
                            json={'group_id': group_id, 'store_results': True},
                        )

                        if response.status_code == 200:
                            result = response.json()
                            print(
                                f'CENTRALITY_DEBUG: ✅ Centrality for group {group_id} - processed {len(result.get("scores", {}))} nodes',
                                flush=True,
                            )
                        else:
                            print(
                                f'CENTRALITY_DEBUG: ❌ Centrality for group {group_id} failed with status {response.status_code}',
                                flush=True,
                            )
                    except Exception as e:
                        print(
                            f'CENTRALITY_DEBUG: ❌ Error calculating centrality for group {group_id}: {e}',
                            flush=True,
                        )
            else:
                # Process entire graph
                try:
                    response = await client.post(
                        f'{settings.rust_centrality_url}/centrality/all',
                        json={'store_results': True},  # No group_id means process all
                    )

                    if response.status_code == 200:
                        result = response.json()
                        print(
                            f'CENTRALITY_DEBUG: ✅ Centrality calculation successful - processed {len(result.get("scores", {}))} nodes',
                            flush=True,
                        )
                        logger.info(
                            f'Centrality calculated for {len(result.get("scores", {}))} nodes'
                        )
                    else:
                        print(
                            f'CENTRALITY_DEBUG: ❌ Centrality calculation failed with status {response.status_code}',
                            flush=True,
                        )
                        logger.warning(f'Centrality calculation failed: {response.status_code}')

                except Exception as e:
                    print(
                        f'CENTRALITY_DEBUG: ❌ Error calculating centrality for entire graph: {e}',
                        flush=True,
                    )
    except Exception as e:
        print(
            f'CENTRALITY_DEBUG: ❌ Exception in centrality calculation: {type(e).__name__}: {e}',
            flush=True,
        )
        logger.error(f'Error in centrality calculation: {e}')
        # Don't fail the main operation if centrality calculation fails


async def invalidate_cache():
    """Invalidate the Rust server cache after data changes"""
    print(f'=== CACHE_INVALIDATION_DEBUG: Function called at {datetime.now()} ===', flush=True)

    try:
        settings = get_settings()
        print(
            f'CACHE_DEBUG: Settings loaded - enable_cache_invalidation={settings.enable_cache_invalidation}',
            flush=True,
        )
        print(f'CACHE_DEBUG: rust_server_url={settings.rust_server_url}', flush=True)
        print(
            f'CACHE_DEBUG: cache_invalidation_timeout={settings.cache_invalidation_timeout}ms',
            flush=True,
        )

        if not settings.enable_cache_invalidation:
            print('CACHE_DEBUG: Cache invalidation disabled, returning early', flush=True)
            return

        timeout = settings.cache_invalidation_timeout / 1000.0  # Convert to seconds
        print(f'CACHE_DEBUG: About to make HTTP request with timeout={timeout}s', flush=True)
        print(f'CACHE_DEBUG: Target URL: {settings.rust_server_url}/api/cache/clear', flush=True)

        # Test network connectivity first
        print('NETWORK_DEBUG: Testing network connectivity to Rust server...', flush=True)
        try:
            async with httpx.AsyncClient(timeout=2.0) as test_client:
                print(
                    f'NETWORK_DEBUG: Attempting health check to {settings.rust_server_url}/health',
                    flush=True,
                )
                health_response = await test_client.get(f'{settings.rust_server_url}/health')
                print(
                    f'NETWORK_DEBUG: Health check status: {health_response.status_code}', flush=True
                )
                print(
                    f'NETWORK_DEBUG: Health check response: {health_response.text[:100]}',
                    flush=True,
                )
        except Exception as conn_e:
            print(
                f'NETWORK_DEBUG: ❌ Network connectivity test failed: {type(conn_e).__name__}: {conn_e}',
                flush=True,
            )

        async with httpx.AsyncClient(timeout=timeout) as client:
            print('CACHE_DEBUG: HTTP client created, making POST request', flush=True)
            response = await client.post(f'{settings.rust_server_url}/api/cache/clear')
            print(
                f'CACHE_DEBUG: HTTP response received - status_code={response.status_code}',
                flush=True,
            )
            print(f'CACHE_DEBUG: Response headers: {dict(response.headers)}', flush=True)
            print(f'CACHE_DEBUG: Response body: {response.text[:200]}', flush=True)

            if response.status_code == 200:
                print('CACHE_DEBUG: ✅ Cache invalidated successfully', flush=True)
                logger.info('Cache invalidated successfully')
            else:
                print(
                    f'CACHE_DEBUG: ❌ Cache invalidation failed with status {response.status_code}',
                    flush=True,
                )
                logger.warning(f'Cache invalidation failed: {response.status_code}')

    except Exception as e:
        print(f'CACHE_DEBUG: ❌ Exception in invalidate_cache: {type(e).__name__}: {e}', flush=True)
        import traceback

        full_traceback = traceback.format_exc()
        print(f'CACHE_DEBUG: Full traceback:\n{full_traceback}', flush=True)
        logger.error(f'Error invalidating cache: {e}')
        logger.error(f'Full traceback: {full_traceback}')
        # Don't fail the main operation if cache invalidation fails


class AsyncWorker:
    def __init__(self):
        self.queue = asyncio.Queue()
        self.task = None

    async def worker(self):
        while True:
            try:
                print(f'Got a job: (size of remaining queue: {self.queue.qsize()})', flush=True)
                job = await self.queue.get()
                print(f'DEBUG: Job type: {type(job).__name__}', flush=True)
                print(f'DEBUG: Job details: {str(job)[:200]}', flush=True)
                await job()
                print('Job completed successfully', flush=True)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f'ERROR_DEBUG: ❌ Error processing job: {type(e).__name__}: {e}', flush=True)
                import traceback

                full_traceback = traceback.format_exc()
                print(f'ERROR_DEBUG: Full job processing traceback:\n{full_traceback}', flush=True)
                logger.error(f'Job processing error: {e}')
                logger.error(f'Full traceback: {full_traceback}')

    async def start(self):
        self.task = asyncio.create_task(self.worker())

    async def stop(self):
        if self.task:
            self.task.cancel()
            await self.task
        while not self.queue.empty():
            self.queue.get_nowait()


async_worker = AsyncWorker()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await async_worker.start()
    yield
    await async_worker.stop()


router = APIRouter(lifespan=lifespan)


@router.post('/messages', status_code=status.HTTP_202_ACCEPTED)
async def add_messages(
    request: AddMessagesRequest,
    graphiti: ZepGraphitiDep,
):
    async def add_messages_task(m: Message):
        print(
            f'=== TASK DEBUG: Processing message - group_id={request.group_id}, name={m.name} ===',
            flush=True,
        )
        print(f'TASK DEBUG: Message content: {m.content[:100]}...', flush=True)

        try:
            print(f'EPISODE_DEBUG: About to call add_episode for uuid={m.uuid}', flush=True)
            print(f'EPISODE_DEBUG: Using graphiti instance: {type(graphiti).__name__}', flush=True)
            print(
                f'EPISODE_DEBUG: Driver type: {type(graphiti.driver).__name__ if hasattr(graphiti, "driver") else "Unknown"}',
                flush=True,
            )

            result = await graphiti.add_episode(
                uuid=m.uuid,
                group_id=request.group_id,
                name=m.name,
                episode_body=f'{m.role or ""}({m.role_type}): {m.content}',
                reference_time=m.timestamp,
                source=EpisodeType.message,
                source_description=m.source_description,
            )

            print(
                f'EPISODE_DEBUG: add_episode returned, result type: {type(result).__name__ if result else "None"}',
                flush=True,
            )

            if result:
                print(
                    f'EPISODE_DEBUG: Episode created: {result.episode.uuid if hasattr(result, "episode") and result.episode else "No episode in result"}',
                    flush=True,
                )
                print(
                    f'EPISODE_DEBUG: Episode group_id: {result.episode.group_id if hasattr(result, "episode") and result.episode and hasattr(result.episode, "group_id") else "N/A"}',
                    flush=True,
                )
                print(
                    f'EPISODE_DEBUG: Entities created: {len(result.nodes) if hasattr(result, "nodes") and result.nodes else 0}',
                    flush=True,
                )

                # Log the actual episode data
                if hasattr(result, 'episode') and result.episode:
                    print(
                        f'EPISODE_DEBUG: Episode data - name: {result.episode.name if hasattr(result.episode, "name") else "N/A"}',
                        flush=True,
                    )
                    print(
                        f'EPISODE_DEBUG: Episode data - content: {result.episode.content[:100] if hasattr(result.episode, "content") else "N/A"}...',
                        flush=True,
                    )
            else:
                print('EPISODE_DEBUG: ⚠️ add_episode returned None!', flush=True)

            logger.info(
                f'DEBUG: add_episode result - episode created: {result.episode.uuid if result and result.episode else "None"}'
            )
            logger.info(
                f'DEBUG: Entities created: {len(result.nodes) if result and result.nodes else 0}'
            )

            # Invalidate cache after successful data operation
            await invalidate_cache()
            
            # Emit webhook for data ingestion
            if result and (result.nodes or result.edges):
                from graph_service.webhooks import webhook_service
                await webhook_service.emit_data_ingestion(
                    operation="add_episode",
                    nodes=result.nodes if result.nodes else [],
                    edges=result.edges if result.edges else [],
                    episode=result.episode if result.episode else None,
                    group_id=request.group_id,
                    metadata={
                        "message_uuid": m.uuid,
                        "message_name": m.name,
                        "source": m.source_description
                    }
                )
                logger.info(f"Data ingestion webhook sent for episode {result.episode.uuid if result and result.episode else 'None'}")

            # Trigger centrality calculation for new data
            await trigger_centrality_calculation(request.group_id)
        except Exception as e:
            logger.error(f'DEBUG: Error in add_episode: {type(e).__name__}: {e}')
            raise

    print(
        f'=== ADD_MESSAGES DEBUG: Received {len(request.messages)} messages for group_id={request.group_id} ===',
        flush=True,
    )

    for m in request.messages:
        print(f'DEBUG: Queueing message - content={m.content[:50]}...', flush=True)
        task = partial(add_messages_task, m)
        await async_worker.queue.put(task)
        print(f'DEBUG: Message queued, queue size: {async_worker.queue.qsize()}', flush=True)

    print(f'=== ADD_MESSAGES DEBUG: All messages queued ===', flush=True)
    return Result(message='Messages added to processing queue', success=True)


@router.post('/entity-node', status_code=status.HTTP_201_CREATED)
async def add_entity_node(
    request: AddEntityNodeRequest,
    graphiti: ZepGraphitiDep,
):
    node = await graphiti.save_entity_node(
        uuid=request.uuid,
        group_id=request.group_id,
        name=request.name,
        summary=request.summary,
    )
    # Invalidate cache after successful data operation
    await invalidate_cache()
    
    # Emit webhook for entity node creation
    if node:
        from graph_service.webhooks import webhook_service
        await webhook_service.emit_data_ingestion(
            operation="add_entity",
            nodes=[node],
            edges=[],
            episode=None,
            group_id=request.group_id,
            metadata={
                "entity_uuid": request.uuid,
                "entity_name": request.name
            }
        )
        logger.info(f"Data ingestion webhook sent for entity node {node.uuid}")
    
    # Trigger centrality calculation for new node
    await trigger_centrality_calculation(request.group_id)
    return node


@router.delete('/entity-edge/{uuid}', status_code=status.HTTP_200_OK)
async def delete_entity_edge(uuid: str, graphiti: ZepGraphitiDep):
    await graphiti.delete_entity_edge(uuid)
    # Invalidate cache after successful data operation
    await invalidate_cache()
    return Result(message='Entity Edge deleted', success=True)


@router.delete('/group/{group_id}', status_code=status.HTTP_200_OK)
async def delete_group(group_id: str, graphiti: ZepGraphitiDep):
    await graphiti.delete_group(group_id)
    # Invalidate cache after successful data operation
    await invalidate_cache()
    return Result(message='Group deleted', success=True)


@router.delete('/episode/{uuid}', status_code=status.HTTP_200_OK)
async def delete_episode(uuid: str, graphiti: ZepGraphitiDep):
    await graphiti.delete_episodic_node(uuid)
    # Invalidate cache after successful data operation
    await invalidate_cache()
    return Result(message='Episode deleted', success=True)


@router.post('/clear', status_code=status.HTTP_200_OK)
async def clear(
    graphiti: ZepGraphitiDep,
):
    await clear_data(graphiti.driver)
    await graphiti.build_indices_and_constraints()
    # Invalidate cache after successful data operation
    await invalidate_cache()
    return Result(message='Graph cleared', success=True)
