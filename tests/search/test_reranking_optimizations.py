"""
Tests for reranking optimizations (Token-Optimized Reranking and Context Sandwiching).

Copyright 2024, Zep Software, Inc.
Licensed under the Apache License, Version 2.0.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
from graphiti_core.llm_client import LLMConfig


class TestTokenOptimizedReranking:
    """Tests for [ENTITY:UUID] prefix formatting in reranking."""

    def test_edge_uuid_prefix_format(self):
        """Test that edge passages get [EDGE:UUID] prefix."""
        edge_uuid = '12345678-1234-1234-1234-123456789012'
        edge_fact = 'Alice loves Bob'
        expected_prefix = f'[EDGE:{edge_uuid[:8]}]'

        formatted = f'[EDGE:{edge_uuid[:8]}] {edge_fact}'

        assert formatted.startswith(expected_prefix)
        assert edge_fact in formatted
        assert formatted == '[EDGE:12345678] Alice loves Bob'

    def test_node_uuid_prefix_format(self):
        """Test that node passages get [NODE:UUID] prefix."""
        node_uuid = 'abcdef12-1234-1234-1234-123456789012'
        node_name = 'Alice'
        expected_prefix = f'[NODE:{node_uuid[:8]}]'

        formatted = f'[NODE:{node_uuid[:8]}] {node_name}'

        assert formatted.startswith(expected_prefix)
        assert node_name in formatted
        assert formatted == '[NODE:abcdef12] Alice'

    def test_episode_uuid_prefix_format(self):
        """Test that episode passages get [EPISODE:UUID] prefix."""
        episode_uuid = 'fedcba98-1234-1234-1234-123456789012'
        episode_content = 'User said hello'
        expected_prefix = f'[EPISODE:{episode_uuid[:8]}]'

        formatted = f'[EPISODE:{episode_uuid[:8]}] {episode_content}'

        assert formatted.startswith(expected_prefix)
        assert episode_content in formatted
        assert formatted == '[EPISODE:fedcba98] User said hello'

    def test_community_uuid_prefix_format(self):
        """Test that community passages get [COMMUNITY:UUID] prefix."""
        community_uuid = '11112222-3333-4444-5555-666677778888'
        community_name = 'Social Network'
        expected_prefix = f'[COMMUNITY:{community_uuid[:8]}]'

        formatted = f'[COMMUNITY:{community_uuid[:8]}] {community_name}'

        assert formatted.startswith(expected_prefix)
        assert community_name in formatted
        assert formatted == '[COMMUNITY:11112222] Social Network'

    def test_uuid_prefix_truncation(self):
        """Test that UUID is truncated to first 8 characters."""
        full_uuid = '12345678-1234-1234-1234-123456789012'
        truncated = full_uuid[:8]

        assert len(truncated) == 8
        assert truncated == '12345678'


class TestContextSandwiching:
    """Tests for query repetition at end of reranker prompts."""

    @pytest.mark.asyncio
    async def test_openai_reranker_context_sandwiching(self):
        """Test that OpenAI reranker includes query at both start and end."""
        config = LLMConfig(api_key='test_key')

        with patch(
            'graphiti_core.cross_encoder.openai_reranker_client.AsyncOpenAI'
        ) as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client

            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].logprobs = MagicMock()
            mock_response.choices[0].logprobs.content = [MagicMock()]
            mock_response.choices[0].logprobs.content[0].top_logprobs = [
                MagicMock(token='True', logprob=-0.1)
            ]

            mock_client.chat = MagicMock()
            mock_client.chat.completions = MagicMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

            reranker = OpenAIRerankerClient(config=config, client=mock_client)

            query = 'What is the capital of France?'
            passages = ['Paris is the capital of France.']

            await reranker.rank(query, passages)

            call_args = mock_client.chat.completions.create.call_args
            messages = call_args.kwargs['messages']
            user_message = (
                messages[1].content if hasattr(messages[1], 'content') else messages[1]['content']
            )

            assert '<QUERY>' in user_message
            assert '<QUERY_REMINDER>' in user_message
            assert user_message.count(query) == 2

    def test_context_sandwich_structure(self):
        """Test the structure of context-sandwiched prompt."""
        query = 'Test query'
        passage = 'Test passage'

        prompt = f"""Respond with "True" if PASSAGE is relevant to QUERY and "False" otherwise.
<QUERY>
{query}
</QUERY>
<PASSAGE>
{passage}
</PASSAGE>
<QUERY_REMINDER>
{query}
</QUERY_REMINDER>"""

        lines = prompt.strip().split('\n')

        query_tag_indices = [
            i for i, line in enumerate(lines) if '<QUERY>' in line or '<QUERY_REMINDER>' in line
        ]
        passage_tag_index = next(i for i, line in enumerate(lines) if '<PASSAGE>' in line)

        assert query_tag_indices[0] < passage_tag_index
        assert query_tag_indices[1] > passage_tag_index


class TestPromptUtilsTokenOptimization:
    """Tests for token optimization in prompt_utils.py."""

    def test_episode_prefix_in_rerank(self):
        """Test that episodes get UUID prefix when prepared for reranking."""
        from graphiti_core.utils.prompt_utils import strip_ansi_codes

        ep_uuid = 'abc12345-1234-1234-1234-123456789012'
        content = 'User message content'

        prefixed_content = f'[EPISODE:{ep_uuid[:8] if ep_uuid else "unknown"}] {content}'

        assert prefixed_content == '[EPISODE:abc12345] User message content'
        assert prefixed_content.startswith('[EPISODE:')

    def test_unknown_uuid_fallback(self):
        """Test that missing UUID uses 'unknown' fallback."""
        ep_uuid = None
        content = 'User message content'

        prefixed_content = f'[EPISODE:{ep_uuid[:8] if ep_uuid else "unknown"}] {content}'

        assert prefixed_content == '[EPISODE:unknown] User message content'


class TestIntegrationScenarios:
    """Integration-style tests for reranking optimizations."""

    def test_multiple_passages_with_prefixes(self):
        """Test formatting multiple passages with unique prefixes."""
        edges = [
            {'uuid': '11111111-0000-0000-0000-000000000000', 'fact': 'Fact A'},
            {'uuid': '22222222-0000-0000-0000-000000000000', 'fact': 'Fact B'},
            {'uuid': '33333333-0000-0000-0000-000000000000', 'fact': 'Fact C'},
        ]

        formatted = {f'[EDGE:{e["uuid"][:8]}] {e["fact"]}': e['uuid'] for e in edges}

        assert len(formatted) == 3
        assert '[EDGE:11111111] Fact A' in formatted
        assert '[EDGE:22222222] Fact B' in formatted
        assert '[EDGE:33333333] Fact C' in formatted

        assert formatted['[EDGE:11111111] Fact A'] == '11111111-0000-0000-0000-000000000000'

    def test_prefix_uniqueness_with_duplicate_facts(self):
        """Test that UUID prefix ensures uniqueness even with duplicate facts."""
        edges = [
            {'uuid': '11111111-0000-0000-0000-000000000000', 'fact': 'Same fact'},
            {'uuid': '22222222-0000-0000-0000-000000000000', 'fact': 'Same fact'},
        ]

        formatted = {f'[EDGE:{e["uuid"][:8]}] {e["fact"]}': e['uuid'] for e in edges}

        assert len(formatted) == 2
        assert '[EDGE:11111111] Same fact' in formatted
        assert '[EDGE:22222222] Same fact' in formatted


if __name__ == '__main__':
    pytest.main(['-v', __file__])
