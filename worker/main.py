"""
Main entry point for the Graphiti ingestion worker service.
Runs workers and optional dashboard.
"""

import asyncio
import logging
import os
import signal
import sys
from typing import Optional

from graphiti_core import Graphiti
from graphiti_core.ingestion.queue_client import QueuedClient
from graphiti_core.ingestion.worker import WorkerPool

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class WorkerService:
    """Main worker service that manages the worker pool and dashboard"""
    
    def __init__(self):
        self.queue_client: Optional[QueuedClient] = None
        self.graphiti: Optional[Graphiti] = None
        self.worker_pool: Optional[WorkerPool] = None
        self.dashboard_task: Optional[asyncio.Task] = None
        self.shutdown_event = asyncio.Event()
        
    async def initialize(self):
        """Initialize all components"""
        logger.info("Initializing worker service...")
        
        # Initialize queue client
        queue_url = os.getenv("QUEUED_URL", "http://localhost:8090")
        self.queue_client = QueuedClient(base_url=queue_url)
        logger.info(f"Queue client initialized with URL: {queue_url}")
        
        # Initialize Graphiti
        from graphiti_core.llm_client import OllamaClient
        from graphiti_core.embedder import OllamaEmbedder
        from graphiti_core.driver import FalkorDriver
        
        # Configure LLM
        if os.getenv("USE_OLLAMA", "true").lower() == "true":
            llm_client = OllamaClient(
                base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
                model=os.getenv("OLLAMA_MODEL", "gemma3:12b"),
                temperature=0.7
            )
            embedder = OllamaEmbedder(
                base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
                model=os.getenv("OLLAMA_EMBEDDING_MODEL", "mxbai-embed-large:latest")
            )
        else:
            from graphiti_core.llm_client import OpenAIClient
            from graphiti_core.embedder import OpenAIEmbedder
            
            llm_client = OpenAIClient(
                api_key=os.getenv("OPENAI_API_KEY"),
                model="gpt-4-turbo-preview"
            )
            embedder = OpenAIEmbedder(
                api_key=os.getenv("OPENAI_API_KEY")
            )
        
        # Configure driver
        driver = FalkorDriver(
            host=os.getenv("FALKORDB_HOST", "localhost"),
            port=int(os.getenv("FALKORDB_PORT", "6379")),
            database=os.getenv("FALKORDB_DATABASE", "graphiti_migration")
        )
        
        # Initialize Graphiti
        self.graphiti = Graphiti(
            driver=driver,
            llm_client=llm_client,
            embedder=embedder
        )
        await self.graphiti.build_indices_and_constraints()
        logger.info("Graphiti initialized")
        
        # Initialize worker pool
        worker_count = int(os.getenv("WORKER_COUNT", "4"))
        batch_size = int(os.getenv("BATCH_SIZE", "10"))
        
        self.worker_pool = WorkerPool(
            queue_client=self.queue_client,
            graphiti=self.graphiti,
            worker_count=worker_count,
            batch_size=batch_size
        )
        logger.info(f"Worker pool configured with {worker_count} workers")
        
    async def start_dashboard(self):
        """Start the dashboard server if enabled"""
        if os.getenv("ENABLE_DASHBOARD", "true").lower() != "true":
            logger.info("Dashboard disabled")
            return
        
        try:
            import uvicorn
            from worker.dashboard import app, queue_client, worker_pool
            
            # Share instances with dashboard
            import worker.dashboard as dashboard_module
            dashboard_module.queue_client = self.queue_client
            dashboard_module.worker_pool = self.worker_pool
            
            # Run dashboard server
            config = uvicorn.Config(
                app=app,
                host="0.0.0.0",
                port=int(os.getenv("DASHBOARD_PORT", "8091")),
                log_level="info"
            )
            server = uvicorn.Server(config)
            
            logger.info("Starting dashboard server on port 8091")
            self.dashboard_task = asyncio.create_task(server.serve())
            
        except ImportError:
            logger.warning("Dashboard dependencies not installed, skipping dashboard")
        except Exception as e:
            logger.error(f"Failed to start dashboard: {e}")
    
    async def run(self):
        """Main run loop"""
        try:
            # Initialize components
            await self.initialize()
            
            # Start dashboard
            await self.start_dashboard()
            
            # Start worker pool
            await self.worker_pool.start()
            logger.info("Worker pool started")
            
            # Log initial metrics
            await self.log_metrics()
            
            # Wait for shutdown signal
            logger.info("Worker service running. Press Ctrl+C to stop.")
            await self.shutdown_event.wait()
            
        except Exception as e:
            logger.error(f"Fatal error in worker service: {e}")
            raise
        finally:
            await self.shutdown()
    
    async def log_metrics(self):
        """Periodically log metrics"""
        while not self.shutdown_event.is_set():
            try:
                # Get queue stats
                stats = await self.queue_client.get_stats()
                logger.info(f"Queue stats: {stats}")
                
                # Get worker metrics
                metrics = self.worker_pool.get_metrics()
                logger.info(f"Worker metrics: {metrics}")
                
            except Exception as e:
                logger.error(f"Error logging metrics: {e}")
            
            # Wait 60 seconds
            try:
                await asyncio.wait_for(self.shutdown_event.wait(), timeout=60)
            except asyncio.TimeoutError:
                pass
    
    async def shutdown(self):
        """Graceful shutdown"""
        logger.info("Shutting down worker service...")
        
        # Stop worker pool
        if self.worker_pool:
            await self.worker_pool.stop()
            logger.info("Worker pool stopped")
        
        # Stop dashboard
        if self.dashboard_task:
            self.dashboard_task.cancel()
            try:
                await self.dashboard_task
            except asyncio.CancelledError:
                pass
            logger.info("Dashboard stopped")
        
        # Close queue client
        if self.queue_client:
            await self.queue_client.close()
            logger.info("Queue client closed")
        
        # Close Graphiti
        if self.graphiti and hasattr(self.graphiti, 'close'):
            await self.graphiti.close()
            logger.info("Graphiti closed")
        
        logger.info("Worker service shutdown complete")
    
    def handle_signal(self, sig, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {sig}")
        self.shutdown_event.set()


async def main():
    """Main entry point"""
    service = WorkerService()
    
    # Register signal handlers
    signal.signal(signal.SIGINT, service.handle_signal)
    signal.signal(signal.SIGTERM, service.handle_signal)
    
    try:
        await service.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Service failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())