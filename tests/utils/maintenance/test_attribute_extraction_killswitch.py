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

Unit tests for the ENABLE_ATTRIBUTE_EXTRACTION kill-switch.
"""

from collections.abc import Coroutine
from unittest.mock import AsyncMock

import pytest  # type: ignore

from graphiti_core.driver.driver import GraphDriver, GraphDriverSession
from graphiti_core.embedder import EmbedderClient
from graphiti_core.graphiti_types import GraphitiClients
from graphiti_core.llm_client.client import LLMClient
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.nodes import EntityNode
from graphiti_core.utils.maintenance.node_operations import extract_attributes_from_nodes


class _TestDriverSession(GraphDriverSession):
    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def run(self, query: str, **kwargs):
        raise NotImplementedError()

    async def close(self):
        return None

    async def execute_write(self, func, *args, **kwargs):
        raise NotImplementedError()


class _TestDriver(GraphDriver):
    provider = 'test'

    def execute_query(self, cypher_query_: str, **kwargs) -> Coroutine:
        raise NotImplementedError()

    def session(self, database: str | None = None) -> GraphDriverSession:
        return _TestDriverSession()

    def close(self):
        return None

    def delete_all_indexes(self, database_: str | None = None) -> Coroutine:
        raise NotImplementedError()


class _TestEmbedder(EmbedderClient):
    def __init__(self, embeddings: list[list[float]]):
        self._embeddings = embeddings
        self.create_batch_mock = AsyncMock(return_value=embeddings)

    async def create(self, input_data):
        return self._embeddings[0]

    async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
        return await self.create_batch_mock(input_data_list)


class _TestLLMClient(LLMClient):
    def __init__(self, response: dict):
        super().__init__(LLMConfig())
        self._response = response
        self.call_count = 0
        self.last_response_model = None

    async def _generate_response(
        self,
        messages,
        response_model=None,
        max_tokens=None,
        model_size=None,
    ):
        self.call_count += 1
        self.last_response_model = response_model
        return dict(self._response)


@pytest.mark.asyncio
async def test_extract_attributes_from_nodes_skips_llm_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv('ENABLE_ATTRIBUTE_EXTRACTION', 'false')

    embedder = _TestEmbedder([[0.0], [1.0]])
    llm_client = _TestLLMClient({})
    driver = _TestDriver()
    clients = GraphitiClients(driver=driver, llm_client=llm_client, embedder=embedder)

    nodes = [
        EntityNode(name='Alice', group_id='g1', labels=['Entity'], summary=''),
        EntityNode(name='Bob', group_id='g1', labels=['Entity'], summary=''),
    ]

    result = await extract_attributes_from_nodes(
        clients, nodes, episode=None, previous_episodes=None
    )

    assert result is nodes
    assert llm_client.call_count == 0

    embedder.create_batch_mock.assert_awaited_once_with(['Alice', 'Bob'])
    assert nodes[0].name_embedding == [0.0]
    assert nodes[1].name_embedding == [1.0]


@pytest.mark.asyncio
async def test_extract_attributes_from_nodes_calls_llm_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv('ENABLE_ATTRIBUTE_EXTRACTION', 'true')

    embedder = _TestEmbedder([[0.0]])
    llm_client = _TestLLMClient({'summary': 'new summary'})
    driver = _TestDriver()
    clients = GraphitiClients(driver=driver, llm_client=llm_client, embedder=embedder)

    nodes = [EntityNode(name='Alice', group_id='g1', labels=['Entity'], summary='')]

    result = await extract_attributes_from_nodes(
        clients, nodes, episode=None, previous_episodes=None
    )

    assert result[0].summary == 'new summary'
    assert llm_client.call_count == 1
    embedder.create_batch_mock.assert_awaited_once_with(['Alice'])
