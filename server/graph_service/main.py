from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from graph_service.config import get_settings
from graph_service.routers import centrality, ingest, nodes, retrieve
from graph_service.zep_graphiti import initialize_graphiti
from graph_service.websocket_manager import manager
from graph_service.webhooks import webhook_service
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    await initialize_graphiti(settings)
    
    # Connect WebSocket manager to webhook service
    logger.info("Registering WebSocket broadcast handler with webhook service")
    await webhook_service.add_internal_handler(manager.broadcast_node_access)
    logger.info(f"WebSocket handler registered. Total handlers: {len(webhook_service.internal_handlers)}")
    
    yield
    # Shutdown
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

app.include_router(retrieve.router)
app.include_router(ingest.router)
app.include_router(centrality.router)
app.include_router(nodes.router)


@app.get('/healthcheck')
async def healthcheck():
    return JSONResponse(content={'status': 'healthy'}, status_code=200)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates."""
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await manager.handle_client_message(websocket, data)
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
