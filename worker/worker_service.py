#!/usr/bin/env python3
"""
Worker service for processing ingestion queue tasks.
Connects to queued service and Graphiti to process tasks.
"""

import asyncio
import logging
import os
import signal
import sys
from typing import Optional

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from graphiti_core.ingestion.queue_client import QueuedClient
from graphiti_core.ingestion.worker import IngestionWorker, WorkerPool
from zep_graphiti import ZepGraphiti

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class WorkerService:
    """Main worker service that manages the worker pool"""
    
    def __init__(self):
        self.worker_pool: Optional[WorkerPool] = None
        self.queue_client: Optional[QueuedClient] = None
        self.graphiti: Optional[ZepGraphiti] = None
        self.running = False
        
    async def initialize(self):
        """Initialize all components"""
        logger.info("Initializing worker service...")
        
        # Get configuration from environment
        queued_url = os.getenv("QUEUED_URL", "http://queued:8080")
        falkordb_host = os.getenv("FALKORDB_HOST", "falkordb")
        falkordb_port = int(os.getenv("FALKORDB_PORT", "6379"))
        falkordb_database = os.getenv("FALKORDB_DATABASE", "graphiti_migration")
        
        worker_count = int(os.getenv("WORKER_COUNT", "4"))
        batch_size = int(os.getenv("BATCH_SIZE", "10"))
        poll_interval = float(os.getenv("POLL_INTERVAL", "1.0"))
        
        # Initialize queue client
        logger.info(f"Connecting to queued service at {queued_url}")
        self.queue_client = QueuedClient(base_url=queued_url)
        
        # Test queue connection
        try:
            queues = await self.queue_client.list_queues()
            logger.info(f"Connected to queued. Available queues: {queues}")
        except Exception as e:
            logger.error(f"Failed to connect to queued service: {e}")
            raise
        
        # Set FalkorDB connection environment variables
        logger.info(f"Connecting to FalkorDB at {falkordb_host}:{falkordb_port}/{falkordb_database}")
        os.environ["DRIVER_TYPE"] = "falkordb"
        os.environ["FALKORDB_HOST"] = falkordb_host
        os.environ["FALKORDB_PORT"] = str(falkordb_port)
        os.environ["FALKORDB_DATABASE"] = falkordb_database
        
        # Initialize LLM and embedder using factory pattern
        # This supports OpenAI, Ollama, and Cerebras based on environment variables
        from graphiti_core.client_factory import GraphitiClientFactory
        
        # Determine which LLM provider is being used
        if os.getenv("USE_CEREBRAS", "false").lower() == "true":
            logger.info("Using Cerebras for LLM")
        elif os.getenv("USE_OLLAMA", "false").lower() == "true":
            logger.info("Using Ollama for LLM and embeddings")
        else:
            logger.info("Using OpenAI for LLM and embeddings")
            openai_key = os.getenv("OPENAI_API_KEY")
            if not openai_key:
                raise ValueError("OPENAI_API_KEY environment variable is required when not using Ollama or Cerebras")
        
        # Create clients using factory
        logger.info("Creating LLM and embedder clients using factory...")
        llm_client = GraphitiClientFactory.create_llm_client()
        embedder = GraphitiClientFactory.create_embedder()
        
        if llm_client is None:
            raise ValueError("Failed to create LLM client")
        if embedder is None:
            raise ValueError("Failed to create embedder client")
        
        logger.info(f"LLM client type: {type(llm_client).__name__}")
        logger.info(f"Embedder type: {type(embedder).__name__}")
        
        # Initialize Graphiti with FalkorDB driver
        logger.info("Initializing Graphiti with FalkorDB driver...")
        from graphiti_core.driver.falkordb_driver import FalkorDriver
        
        # Create FalkorDB driver using environment variables
        falkor_driver = FalkorDriver(
            host=falkordb_host,
            port=falkordb_port,
            database=falkordb_database,
            username=None,  # FalkorDB typically doesn't use auth
            password=None
        )
        
        self.graphiti = ZepGraphiti(
            uri=None,  # Not needed when using graph_driver
            llm_client=llm_client,
            embedder=embedder,
            graph_driver=falkor_driver
        )
        
        # Initialize worker pool
        logger.info(f"Creating worker pool with {worker_count} workers")
        self.worker_pool = WorkerPool(
            queue_client=self.queue_client,
            graphiti=self.graphiti,
            worker_count=worker_count,
            batch_size=batch_size
        )
        
        logger.info("Worker service initialized successfully")
    
    async def start(self):
        """Start the worker service"""
        if self.running:
            logger.warning("Worker service already running")
            return
        
        self.running = True
        logger.info("Starting worker service...")
        
        # Start worker pool
        await self.worker_pool.start()
        
        logger.info("Worker service started")
    
    async def stop(self):
        """Stop the worker service gracefully"""
        if not self.running:
            return
        
        logger.info("Stopping worker service...")
        self.running = False
        
        # Stop worker pool
        if self.worker_pool:
            await self.worker_pool.stop()
        
        # Close queue client
        if self.queue_client:
            await self.queue_client.close()
        
        logger.info("Worker service stopped")
    
    async def run(self):
        """Main run loop"""
        try:
            await self.initialize()
            await self.start()
            
            # Keep running until interrupted
            while self.running:
                await asyncio.sleep(1)
                
                # Periodically log stats
                # TODO: Add metrics collection when WorkerPool supports it
                pass
                
        except Exception as e:
            logger.error(f"Worker service error: {e}")
            raise
        finally:
            await self.stop()


async def main():
    """Main entry point"""
    service = WorkerService()
    
    # Handle shutdown signals
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        service.running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await service.run()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())