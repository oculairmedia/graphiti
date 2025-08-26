"""
Copyright 2024, Zep Software, Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import logging
import re
from typing import Any, Optional, TYPE_CHECKING

from graphiti_core.driver.driver import GraphDriver, GraphDriverSession
from .metrics import MetricsCollector

if TYPE_CHECKING:
    from graphiti_core.driver.falkordb_driver import FalkorDriver
    from graphiti_core.driver.neo4j_driver import Neo4jDriver

logger = logging.getLogger(__name__)


class DryRunDriverSession(GraphDriverSession):
    """Wrapper session that intercepts write operations while allowing reads"""
    
    def __init__(self, real_session: GraphDriverSession, metrics_collector: MetricsCollector):
        self.real_session = real_session
        self.metrics_collector = metrics_collector
    
    async def __aenter__(self):
        await self.real_session.__aenter__()
        return self
    
    async def __aexit__(self, exc_type, exc, tb):
        await self.real_session.__aexit__(exc_type, exc, tb)
    
    async def close(self):
        await self.real_session.close()
    
    async def execute_write(self, func, *args, **kwargs):
        # Intercept write operations - don't execute them
        logger.debug(f"DryRun: Intercepting execute_write call: {func.__name__}")
        self.metrics_collector.record_write_operation(
            query=f"execute_write: {func.__name__}",
            params=kwargs
        )
        # Return None to simulate successful write without actual execution
        return None
    
    async def run(self, query: str | list, **kwargs: Any) -> Any:
        if isinstance(query, list):
            # Handle batch queries
            for cypher, params in query:
                if self._is_write_query(str(cypher)):
                    logger.debug(f"DryRun: Intercepting batch write query: {cypher[:100]}...")
                    self.metrics_collector.record_write_operation(str(cypher), params)
                else:
                    # Execute read queries normally
                    await self.real_session.run(cypher, **params)
            return None
        else:
            if self._is_write_query(str(query)):
                logger.debug(f"DryRun: Intercepting write query: {query[:100]}...")
                self.metrics_collector.record_write_operation(str(query), kwargs)
                return None
            else:
                # Execute read queries normally
                return await self.real_session.run(query, **kwargs)
    
    def _is_write_query(self, query: str) -> bool:
        """Classify query as read or write operation"""
        query_lower = query.lower().strip()
        
        # Write operations
        write_patterns = [
            r'^\s*create\s',
            r'^\s*merge\s',
            r'^\s*set\s',
            r'^\s*delete\s',
            r'^\s*remove\s',
            r'^\s*drop\s',
            r'match\s+.*\s+set\s',
            r'match\s+.*\s+delete\s',
            r'match\s+.*\s+remove\s',
            r'^\s*call\s+.*\.index',  # Index operations
            r'^\s*call\s+.*\.constraint',  # Constraint operations
        ]
        
        for pattern in write_patterns:
            if re.search(pattern, query_lower):
                return True
        
        return False


class DryRunDriver(GraphDriver):
    """Wrapper driver that intercepts write operations for dry-run benchmarking"""
    
    def __init__(
        self, 
        real_driver: 'GraphDriver',
        metrics_collector: Optional[MetricsCollector] = None
    ):
        super().__init__()
        self.real_driver = real_driver
        self.metrics_collector = metrics_collector or MetricsCollector()
        self.provider = f"dry_run_{real_driver.provider}"
        self.fulltext_syntax = getattr(real_driver, 'fulltext_syntax', '@')
    
    async def execute_query(self, cypher_query: str, **kwargs: Any):
        """Execute query with write interception"""
        
        # Classify the query
        if self._is_write_query(cypher_query):
            logger.debug(f"DryRun: Intercepting write query: {cypher_query[:100]}...")
            
            # Record the intercepted operation
            self.metrics_collector.record_write_operation(cypher_query, kwargs)
            
            # Return empty result set to simulate successful execution
            return [], [], None
        else:
            # Execute read queries normally against the real database
            logger.debug(f"DryRun: Executing read query: {cypher_query[:100]}...")
            return await self.real_driver.execute_query(cypher_query, **kwargs)
    
    def session(self, database: str | None = None) -> GraphDriverSession:
        """Create a dry-run session wrapper"""
        real_session = self.real_driver.session(database)
        return DryRunDriverSession(real_session, self.metrics_collector)
    
    async def close(self) -> None:
        """Close the underlying driver"""
        await self.real_driver.close()
    
    async def delete_all_indexes(self, database_: str | None = None) -> None:
        """Intercept index deletion - don't execute in dry-run mode"""
        logger.debug("DryRun: Intercepting delete_all_indexes")
        self.metrics_collector.record_write_operation(
            "CALL db.indexes() YIELD name DROP INDEX name", 
            {"database_": database_}
        )
    
    def _is_write_query(self, query: str) -> bool:
        """Classify query as read or write operation"""
        query_lower = query.lower().strip()
        
        # Write operations
        write_patterns = [
            r'^\s*create\s',
            r'^\s*merge\s', 
            r'^\s*set\s',
            r'^\s*delete\s',
            r'^\s*remove\s',
            r'^\s*drop\s',
            r'match\s+.*\s+set\s',
            r'match\s+.*\s+delete\s',
            r'match\s+.*\s+remove\s',
            r'^\s*call\s+.*\.index',  # Index operations
            r'^\s*call\s+.*\.constraint',  # Constraint operations
        ]
        
        for pattern in write_patterns:
            if re.search(pattern, query_lower):
                return True
        
        return False
    
    def get_metrics_collector(self) -> MetricsCollector:
        """Get the metrics collector for this dry-run driver"""
        return self.metrics_collector


def create_dry_run_driver(
    real_driver: 'GraphDriver', 
    metrics_collector: Optional[MetricsCollector] = None
) -> DryRunDriver:
    """Factory function to create a dry-run wrapper around any GraphDriver"""
    return DryRunDriver(real_driver, metrics_collector)