from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from graph_service.config import get_settings
from graph_service.routers import centrality, ingest, nodes, retrieve
from graph_service.routers import metrics, search_proxy
# Import others conditionally
try:
    from graph_service.routers import cached_retrieve
except ImportError:
    cached_retrieve = None
try:
    from graph_service.routers import relevance
except ImportError:
    relevance = None
try:
    from graph_service.routers import ingest_queue
except ImportError:
    ingest_queue = None
from graph_service.zep_graphiti import initialize_graphiti, ZepGraphiti
from graph_service.websocket_manager import manager
from graph_service.webhooks import webhook_service
from graph_service.async_webhooks import startup_webhook_dispatcher, shutdown_webhook_dispatcher, dispatcher
from graph_service.cache import initialize_caches, close_caches
from graph_service.factories import (
    create_embedder_client,
    create_llm_client,
    configure_non_ollama_clients,
)
from graphiti_core.config.replay_config import ReplayConfig
from graphiti_core.ingestion.queue_client import QueuedClient
from graphiti_core.utils.replay import MemoryReplayScheduler
import logging
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

replay_scheduler: MemoryReplayScheduler | None = None
replay_queue_client: QueuedClient | None = None
replay_graphiti: ZepGraphiti | None = None


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    await initialize_graphiti(settings)
    
    # Initialize caching system
    logger.info("Initializing cache systems")
    # Use same Redis/FalkorDB instance for caching (different DB)
    redis_url = os.getenv("FALKORDB_URI", "redis://falkordb:6379/2")  # Use DB 2 for cache
    await initialize_caches(redis_url)
    
    # Start async webhook dispatcher
    logger.info("Starting async webhook dispatcher")
    await startup_webhook_dispatcher()
    
    # Connect WebSocket manager to async dispatcher
    logger.info("Registering WebSocket broadcast handler with async dispatcher")
    await dispatcher.add_internal_handler(manager.broadcast_node_access)
    
    # Register data ingestion notification handler
    logger.info("Registering data ingestion notification handler")
    await dispatcher.add_data_handler(manager.broadcast_data_ingestion_notification)
    
    # Keep old webhook service for backward compatibility (will migrate gradually)
    await webhook_service.add_internal_handler(manager.broadcast_node_access)

    global replay_scheduler, replay_queue_client, replay_graphiti
    replay_config = ReplayConfig.from_env()
    if replay_config.enabled:
        try:
            llm_client = create_llm_client(settings)
            embedder_client = create_embedder_client(settings)
            replay_graphiti = ZepGraphiti(
                uri=settings.database_uri,
                user=settings.database_user,
                password=settings.database_password,
                llm_client=llm_client,
                embedder=embedder_client,
                use_falkordb=settings.use_falkordb or bool(settings.falkordb_uri or settings.falkordb_host),
            )
            configure_non_ollama_clients(replay_graphiti, settings)

            replay_queue_client = QueuedClient(base_url=settings.queue_url)
            await replay_queue_client.list_queues()
            replay_scheduler = MemoryReplayScheduler(
                queue_client=replay_queue_client,
                config=replay_config,
                graphiti=replay_graphiti,
            )
            await replay_scheduler.start()
            logger.info('Memory replay scheduler started')
        except Exception as exc:  # pragma: no cover - defensive path
            logger.exception('Failed to start memory replay scheduler: %s', exc)
            if replay_queue_client:
                await replay_queue_client.close()
                replay_queue_client = None
            if replay_graphiti:
                await replay_graphiti.close()
                replay_graphiti = None
            replay_scheduler = None
    else:
        logger.info('Memory replay scheduler disabled via configuration')

    yield
    
    # Shutdown
    logger.info("Shutting down services")
    if replay_scheduler:
        await replay_scheduler.stop()
        replay_scheduler = None
    if replay_queue_client:
        await replay_queue_client.close()
        replay_queue_client = None
    if replay_graphiti:
        await replay_graphiti.close()
        replay_graphiti = None
    await close_caches()
    await shutdown_webhook_dispatcher()
    await webhook_service.close()
    # No need to close Graphiti here, as it's handled per-request


app = FastAPI(lifespan=lifespan)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Comment out broken routers, use proxy instead  
app.include_router(retrieve.router)  # Re-enable for episodes endpoint
if cached_retrieve:
    app.include_router(cached_retrieve.router)  # Add cached endpoints
app.include_router(search_proxy.router)  # Use proxy to Rust search service
app.include_router(ingest.router)
if ingest_queue:
    app.include_router(ingest_queue.router, prefix="/api")  # Add queue-based ingestion
app.include_router(centrality.router)
app.include_router(nodes.router)
app.include_router(metrics.router)  # Add metrics endpoints
if relevance:
    app.include_router(relevance.router)  # Add relevance scoring endpoints


@app.get('/healthcheck')
async def healthcheck() -> JSONResponse:
    return JSONResponse(content={'status': 'healthy'}, status_code=200)


@app.get('/metrics/webhooks')
async def webhook_metrics() -> JSONResponse:
    """Get webhook dispatcher metrics for monitoring."""
    metrics = dispatcher.get_metrics()
    return JSONResponse(content=metrics, status_code=200)


@app.get('/metrics/replay')
async def replay_metrics() -> JSONResponse:
    """Expose memory replay scheduler status."""
    if replay_scheduler:
        payload = replay_scheduler.get_status().as_dict()
    else:
        payload = {
            'enabled': False,
            'running': False,
            'queue_name': None,
            'last_run_at': None,
            'last_scheduled': 0,
            'last_error': None,
            'batch_size': 0,
            'min_priority': 0.0,
        }
    return JSONResponse(content=payload, status_code=200)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time updates."""
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await manager.handle_client_message(websocket, data)
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
