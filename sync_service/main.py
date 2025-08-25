"""
Main entry point for the Neo4j-FalkorDB sync service.

This module initializes and runs the sync service with proper configuration,
logging, and signal handling.
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path
from typing import Optional

from config.settings import load_config, validate_config, SyncServiceConfig
from monitoring.logging_setup import setup_logging, get_sync_logger
from monitoring.health_server import HealthServer
from orchestrator.sync_orchestrator import SyncOrchestrator

logger = logging.getLogger(__name__)


class SyncService:
    """Main sync service coordinator."""
    
    def __init__(self, config: SyncServiceConfig):
        """
        Initialize sync service.
        
        Args:
            config: Service configuration
        """
        self.config = config
        self.orchestrator: Optional[SyncOrchestrator] = None
        self.health_server: Optional[HealthServer] = None
        self._shutdown_event = asyncio.Event()
        
    async def start(self) -> None:
        """Start all service components."""
        sync_logger = get_sync_logger(__name__)
        
        try:
            sync_logger.info("Starting Neo4j-FalkorDB sync service")
            
            # Initialize sync orchestrator
            neo4j_config = {
                'uri': self.config.neo4j.uri,
                'user': self.config.neo4j.user,
                'password': self.config.neo4j.password,
                'database': self.config.neo4j.database,
                'pool_size': self.config.neo4j.pool_size,
            }
            
            falkordb_config = {
                'host': self.config.falkordb.host,
                'port': self.config.falkordb.port,
                'username': self.config.falkordb.username,
                'password': self.config.falkordb.password,
                'database': self.config.falkordb.database,
                'pool_size': self.config.falkordb.pool_size,
            }
            
            self.orchestrator = SyncOrchestrator(
                neo4j_config=neo4j_config,
                falkordb_config=falkordb_config,
                batch_size=self.config.sync.batch_size,
                sync_interval_seconds=self.config.sync.interval_seconds,
                max_retries=self.config.sync.max_retries,
                retry_delay_seconds=self.config.sync.retry_delay_seconds,
            )
            
            # Initialize health server
            self.health_server = HealthServer(
                config=self.config.monitoring,
                sync_orchestrator=self.orchestrator
            )
            
            # Start health server
            await self.health_server.start()
            
            # Perform initial sync if configured
            if self.config.sync.full_sync_on_startup:
                sync_logger.info("Performing initial full sync")
                operation_stats = await self.orchestrator.sync_full()
                if operation_stats.status.value == "completed":
                    sync_logger.log_sync_complete(
                        "full_startup",
                        operation_stats.duration_seconds,
                        operation_stats.total_items_processed,
                        operation_stats.success_rate
                    )
                else:
                    sync_logger.log_sync_error("full_startup", Exception("Initial sync failed"))
                    
            # Start continuous sync if enabled
            if self.config.sync.enable_continuous:
                sync_logger.info("Starting continuous sync")
                await self.orchestrator.start_continuous_sync()
                
            sync_logger.info("Sync service started successfully")
            
        except Exception as e:
            sync_logger.error(f"Failed to start sync service: {e}", exc_info=True)
            raise
            
    async def stop(self) -> None:
        """Stop all service components."""
        sync_logger = get_sync_logger(__name__)
        
        try:
            sync_logger.info("Stopping sync service")
            
            # Stop sync orchestrator
            if self.orchestrator:
                await self.orchestrator.stop_continuous_sync()
                
            # Stop health server
            if self.health_server:
                await self.health_server.stop()
                
            sync_logger.info("Sync service stopped")
            
        except Exception as e:
            sync_logger.error(f"Error stopping sync service: {e}", exc_info=True)
            
    async def run(self) -> None:
        """Run the service until shutdown signal."""
        await self.start()
        
        # Wait for shutdown signal
        await self._shutdown_event.wait()
        
        await self.stop()
        
    def shutdown(self) -> None:
        """Signal shutdown."""
        self._shutdown_event.set()


def setup_signal_handlers(service: SyncService) -> None:
    """Set up signal handlers for graceful shutdown."""
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        service.shutdown()
        
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)


async def main() -> int:
    """Main entry point."""
    try:
        # Load configuration
        config_file = sys.argv[1] if len(sys.argv) > 1 else None
        config = load_config(config_file)
        
        # Validate configuration
        validate_config(config)
        
        # Set up logging
        setup_logging(config.logging)
        
        logger.info("Neo4j-FalkorDB Sync Service starting...")
        logger.info(f"Configuration: Neo4j={config.neo4j.uri}, FalkorDB={config.falkordb.host}:{config.falkordb.port}")
        
        # Create and run service
        service = SyncService(config)
        
        # Set up signal handlers
        setup_signal_handlers(service)
        
        # Run service
        await service.run()
        
        logger.info("Sync service shut down cleanly")
        return 0
        
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return 0
    except Exception as e:
        logger.error(f"Sync service failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))