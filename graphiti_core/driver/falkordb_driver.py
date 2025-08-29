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
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from falkordb import Graph as FalkorGraph
    from falkordb.asyncio import FalkorDB
else:
    try:
        from falkordb import Graph as FalkorGraph
        from falkordb.asyncio import FalkorDB
    except ImportError:
        # If falkordb is not installed, raise an ImportError
        raise ImportError(
            'falkordb is required for FalkorDriver. '
            'Install it with: pip install graphiti-core[falkordb]'
        ) from None

from graphiti_core.driver.driver import GraphDriver, GraphDriverSession

logger = logging.getLogger(__name__)


def _is_vector_list(val: Any) -> bool:
    """Detect if a value is a vector (list or tuple of numbers)."""
    try:
        return (
            isinstance(val, (list, tuple))
            and len(val) > 0
            and all(isinstance(x, (float, int)) for x in val)
        )
    except Exception:
        return False


def _flatten_params(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Flatten nested params dictionaries that come from execute_query calls."""
    params = dict(kwargs)
    nested = params.pop('params', None)
    if isinstance(nested, dict):
        for k, v in nested.items():
            if k not in params:
                params[k] = v
    return params


def _preprocess_vectors_in_params(params: dict[str, Any]) -> dict[str, Any]:
    """Pre-process parameters to handle vectors in nested structures for FalkorDB.
    
    This is specifically needed for UNWIND operations where vectors are in nested dictionaries.
    FalkorDB cannot convert lists to Vectorf32 within query execution for UNWIND variables.
    """
    # Import here to avoid circular dependency
    try:
        from falkordb import VectorF32
    except ImportError:
        # If VectorF32 is not available, return params unchanged
        return params
    
    def convert_vectors(obj: Any) -> Any:
        """Recursively convert vector lists to VectorF32 objects."""
        if _is_vector_list(obj):
            # Convert Python list to FalkorDB VectorF32
            return VectorF32(obj)
        elif isinstance(obj, dict):
            # Recursively process dictionary values
            return {k: convert_vectors(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            # Process each item in the list
            return [convert_vectors(item) for item in obj]
        else:
            # Return unchanged for non-vector, non-container types
            return obj
    
    # Process specific parameters that are known to contain nested vectors
    processed_params = {}
    for key, value in params.items():
        if key in ['edges', 'nodes', 'entities']:  # Parameters likely to contain nested vectors
            processed_params[key] = convert_vectors(value)
        else:
            processed_params[key] = value
    
    return processed_params


def _wrap_vector_params_in_query(query: str, params: dict[str, Any]) -> str:
    """Wrap any $key in the query with vecf32($key) when the param is a vector-like list.
    
    This fixes FalkorDB type mismatch errors where Python lists need to be converted
    to VectorF32 types for vector operations.
    """
    # Handle top-level vector parameters (existing functionality)
    for key, val in params.items():
        if _is_vector_list(val):
            needle = f"${key}"
            wrapped = f"vecf32({needle})"
            # Skip if already wrapped to avoid double-wrapping
            if wrapped in query:
                continue
            # Replace bare $key with vecf32($key)
            query = query.replace(needle, wrapped)
    
    return query


class FalkorDriverSession(GraphDriverSession):
    def __init__(self, graph: FalkorGraph):
        self.graph = graph

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        # No cleanup needed for Falkor, but method must exist
        pass

    async def close(self):
        # No explicit close needed for FalkorDB, but method must exist
        pass

    async def execute_write(self, func, *args, **kwargs):
        # Directly await the provided async function with `self` as the transaction/session
        return await func(self, *args, **kwargs)

    async def run(self, query: str | list, **kwargs: Any) -> Any:
        # FalkorDB does not support argument for Label Set, so it's converted into an array of queries
        if isinstance(query, list):
            for cypher, params in query:
                params = convert_datetimes_to_strings(params)
                params = _preprocess_vectors_in_params(params)
                cypher = _wrap_vector_params_in_query(str(cypher), params)
                await self.graph.query(cypher, params)  # type: ignore[reportUnknownArgumentType]
        else:
            params = _flatten_params(dict(kwargs))
            params = convert_datetimes_to_strings(params)
            params = _preprocess_vectors_in_params(params)
            query = _wrap_vector_params_in_query(str(query), params)
            await self.graph.query(query, params)  # type: ignore[reportUnknownArgumentType]
        # Assuming `graph.query` is async (ideal); otherwise, wrap in executor
        return None


class FalkorDriver(GraphDriver):
    provider: str = 'falkordb'

    def __init__(
        self,
        host: str = 'localhost',
        port: int = 6379,
        username: str | None = None,
        password: str | None = None,
        falkor_db: FalkorDB | None = None,
        database: str = 'default_db',
    ):
        """
        Initialize the FalkorDB driver.

        FalkorDB is a multi-tenant graph database.
        To connect, provide the host and port.
        The default parameters assume a local (on-premises) FalkorDB instance.
        """
        super().__init__()
        if falkor_db is not None:
            # If a FalkorDB instance is provided, use it directly
            self.client = falkor_db
        else:
            self.client = FalkorDB(host=host, port=port, username=username, password=password)
            self._database = database

        self.fulltext_syntax = '@'  # FalkorDB uses a redisearch-like syntax for fulltext queries see https://redis.io/docs/latest/develop/ai/search-and-query/query/full-text/

    def _get_graph(self, graph_name: str | None) -> FalkorGraph:
        # FalkorDB requires a non-None database name for multi-tenant graphs; the default is "default_db"
        if graph_name is None:
            graph_name = self._database
        return self.client.select_graph(graph_name)

    async def execute_query(self, cypher_query_, **kwargs: Any):
        graph_name = kwargs.pop('database_', self._database)
        graph = self._get_graph(graph_name)

        # 1) Flatten params dicts (handle nested params parameter)
        raw_params = _flatten_params(kwargs)

        # 2) Convert datetime objects to ISO strings (FalkorDB does not support datetime objects directly)
        params = convert_datetimes_to_strings(raw_params)

        # 3) Pre-process nested vectors in parameters (for UNWIND operations)
        params = _preprocess_vectors_in_params(params)

        # 4) Driver-level wrapping for vector params (fixes "expected Vectorf32 but was List" errors)
        cypher_query_ = _wrap_vector_params_in_query(cypher_query_, params)

        try:
            result = await graph.query(cypher_query_, params)  # type: ignore[reportUnknownArgumentType]
        except Exception as e:
            if 'already indexed' in str(e):
                # check if index already exists
                logger.info(f'Index already exists: {e}')
                return None
            logger.error(f'Error executing FalkorDB query: {e}')
            raise

        # Convert the result header to a list of strings
        header = [h[1] for h in result.header]

        # Convert FalkorDB's result format (list of lists) to the format expected by Graphiti (list of dicts)
        records = []
        for row in result.result_set:
            record = {}
            for i, field_name in enumerate(header):
                if i < len(row):
                    record[field_name] = row[i]
                else:
                    # If there are more fields in header than values in row, set to None
                    record[field_name] = None
            records.append(record)

        return records, header, None

    def session(self, database: str | None = None) -> GraphDriverSession:
        return FalkorDriverSession(self._get_graph(database))

    async def close(self) -> None:
        """Close the driver connection."""
        if hasattr(self.client, 'aclose'):
            await self.client.aclose()  # type: ignore[reportUnknownMemberType]
        elif hasattr(self.client.connection, 'aclose'):
            await self.client.connection.aclose()
        elif hasattr(self.client.connection, 'close'):
            await self.client.connection.close()

    async def delete_all_indexes(self, database_: str | None = None) -> None:
        database = database_ or self._database
        await self.execute_query(
            'CALL db.indexes() YIELD name DROP INDEX name',
            database_=database,
        )


def convert_datetimes_to_strings(obj):
    if isinstance(obj, dict):
        return {k: convert_datetimes_to_strings(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_datetimes_to_strings(item) for item in obj]
    elif isinstance(obj, tuple):
        return tuple(convert_datetimes_to_strings(item) for item in obj)
    elif isinstance(obj, datetime):
        return obj.isoformat()
    else:
        return obj
