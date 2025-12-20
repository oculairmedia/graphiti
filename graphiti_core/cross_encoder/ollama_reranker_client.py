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
from typing import Any

import httpx

from graphiti_core.cross_encoder.client import CrossEncoderClient

logger = logging.getLogger(__name__)


class OllamaRerankerClient(CrossEncoderClient):
    """
    OllamaRerankerClient is a client for using Ollama-hosted reranker models
    (e.g., Qwen3-Reranker-4B) to rank passages based on their relevance to a query.

    Uses the Ollama rerank API endpoint for efficient passage scoring.
    """

    def __init__(
        self,
        model: str = 'dengcao/Qwen3-Reranker-4B:Q5_K_M',
        base_url: str = 'http://192.168.50.80:11434',
        timeout: int = 120,
    ):
        """
        Initialize the Ollama reranker client.

        Args:
            model: The Ollama model to use for reranking
            base_url: The base URL of the Ollama service
            timeout: Request timeout in seconds
        """
        self.model = model
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)
        logger.info(f'Initialized OllamaRerankerClient with model {model} at {base_url}')

    async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
        """
        Rank the given passages based on their relevance to the query using Ollama reranker.

        Args:
            query: The query string to compare passages against
            passages: A list of passages to rank

        Returns:
            A list of tuples containing (passage, score), sorted by descending relevance score
        """
        if not passages:
            return []

        if len(passages) == 1:
            # Single passage, no need to rerank
            return [(passages[0], 1.0)]

        try:
            # Ollama rerank adapter API expects: query + documents array
            # Using the Letta toolselector reranker adapter format
            payload = {
                'query': query,
                'documents': passages,
            }

            logger.debug(f'Reranking {len(passages)} passages with query length {len(query)} chars')

            response = await self.client.post(
                f'{self.base_url}/rerank',
                json=payload,
            )
            response.raise_for_status()

            result = response.json()

            # Handle two response formats:
            # 1. Letta adapter: {"results": [{"index": 0, "relevance_score": 0.95}, ...]}
            # 2. vLLM reranker: {"results": [{"index": 0, "relevance_score": 0.95, "document": {...}}, ...]}
            results = result.get('results', [])

            if not results:
                logger.warning('Ollama reranker returned no results, returning original order')
                return [(p, 1.0 / (i + 1)) for i, p in enumerate(passages)]

            # Build scored passages list (handle both formats)
            scored_passages = []
            for item in results:
                idx = item['index']
                score = item['relevance_score']
                if 0 <= idx < len(passages):
                    scored_passages.append((passages[idx], float(score)))

            # Sort by score descending
            scored_passages.sort(key=lambda x: x[1], reverse=True)

            logger.info(
                f'Reranked {len(scored_passages)} passages, '
                f'top score: {scored_passages[0][1]:.3f}, '
                f'bottom score: {scored_passages[-1][1]:.3f}'
            )

            return scored_passages

        except httpx.HTTPStatusError as e:
            logger.error(
                f'Ollama reranker HTTP error: {e.response.status_code} - {e.response.text}'
            )
            # Fallback: return passages in original order with decreasing scores
            return [(p, 1.0 / (i + 1)) for i, p in enumerate(passages)]
        except Exception as e:
            logger.error(f'Ollama reranker error: {e}', exc_info=True)
            # Fallback: return passages in original order
            return [(p, 1.0 / (i + 1)) for i, p in enumerate(passages)]

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    def __del__(self):
        """Cleanup on deletion."""
        try:
            import asyncio

            asyncio.create_task(self.close())
        except Exception:
            pass
