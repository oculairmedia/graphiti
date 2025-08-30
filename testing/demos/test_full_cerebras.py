#!/usr/bin/env python3
"""
Test Graphiti with full Cerebras setup - Qwen for LLM, Ollama for embeddings.
Adapted from test_full_ollama.py for Cerebras/Qwen testing.
"""

import asyncio
import hashlib
import logging
import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime

from graphiti_core import Graphiti
from graphiti_core.embedder import EmbedderClient
from graphiti_core.llm_client.cerebras_client import CerebrasClient, DEFAULT_CEREBRAS_MODEL
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.nodes import EpisodeType
from graphiti_core.prompts.models import Message


# Timer context manager for performance tracking
@contextmanager
def timer(name):
    start = time.time()
    yield
    elapsed = time.time() - start
    print(f'{name} took {elapsed:.2f} seconds')


# Configure logging for Cerebras-specific debugging
logging.basicConfig(
    level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
# Enable Cerebras client debug logging
logging.getLogger('graphiti_core.llm_client.cerebras_client').setLevel(logging.DEBUG)
logging.getLogger('neo4j').setLevel(logging.INFO)
logging.getLogger('httpcore').setLevel(logging.INFO)
logging.getLogger('httpx').setLevel(logging.INFO)
logging.getLogger('graphiti_core.search.search').setLevel(logging.INFO)


class OllamaEmbedder(EmbedderClient):
    """Custom embedder that uses Ollama for embeddings (keeping embedding separate)."""

    def __init__(self, base_url: str, model: str = 'mxbai-embed-large'):
        self.base_url = base_url
        self.model = model
        # Import here to avoid issues if not installed
        from openai import AsyncOpenAI

        self.client = AsyncOpenAI(
            base_url=base_url,
            api_key='ollama',  # Ollama doesn't need a real API key
        )
        print(f'✓ Initialized OllamaEmbedder with model: {model}')

    async def create(self, input_data: list[str]) -> list[list[float]]:
        """Create embeddings using Ollama."""
        try:
            # Ollama's OpenAI-compatible endpoint for embeddings
            response = await self.client.embeddings.create(model=self.model, input=input_data)

            # Extract embeddings from response
            embeddings = [item.embedding for item in response.data]
            return embeddings

        except Exception as e:
            print(f'❌ Error creating embeddings: {e}')
            raise


# Test episode content - updated for Qwen's strengths
test_episode = {
    'content': """Understanding Qwen: Architecture and Capabilities

    Qwen (Tongyi Qianwen) is a large language model series developed by Alibaba Cloud. The model features 
    a transformer architecture optimized for multilingual understanding and code generation. Key capabilities include:
    
    1. Code Understanding: Excellent performance on programming tasks with support for 100+ languages
    2. Mathematical Reasoning: Strong capabilities in complex mathematical problem solving
    3. Multilingual Support: Native support for Chinese, English, and many other languages
    4. Structured Output: Reliable JSON generation and schema adherence
    5. Long Context: Efficient handling of extended context windows
    
    The Qwen-Coder variant is specifically fine-tuned for software development tasks, making it ideal
    for applications requiring precise code analysis and structured data extraction.""",
    'metadata': {
        'source': 'qwen_technical_documentation',
        'timestamp': '2025-01-29T15:00:00Z',
    },
}


async def make_concurrent_cerebras_request(client, messages, response_model=None):
    """Make a concurrent Cerebras/Qwen LLM request."""
    try:
        # Convert to Message objects if needed
        if isinstance(messages[0], dict):
            message_objs = [Message(role=msg['role'], content=msg['content']) for msg in messages]
        else:
            message_objs = messages
            
        response = await client._generate_response(message_objs, response_model)
        return response
    except Exception as e:
        print(f'Error in concurrent Cerebras request: {e}')
        return None


async def test_qwen_specific_capabilities(client):
    """Test Qwen-specific capabilities that differ from other models."""
    
    print('\n🧠 Testing Qwen-specific capabilities...')
    
    # Test 1: Code analysis (Qwen's strength)
    code_analysis_msg = [Message(
        role='user',
        content='''Analyze this Python function and extract entities:

def calculate_graph_metrics(nodes, edges):
    """Calculate centrality metrics for graph nodes."""
    degree_centrality = {}
    betweenness_centrality = {}
    
    for node in nodes:
        degree_centrality[node] = len([e for e in edges if node in e])
    
    return {"degree": degree_centrality, "betweenness": betweenness_centrality}

Extract programming concepts, functions, and data structures as entities.'''
    )]
    
    try:
        code_response = await make_concurrent_cerebras_request(client, code_analysis_msg)
        if code_response:
            print('   ✅ Code analysis completed')
            if isinstance(code_response, dict) and 'entities' in code_response:
                entities = code_response['entities']
                print(f'      - Found {len(entities)} code-related entities')
            else:
                print('      - Response format differs from expected')
        else:
            print('   ❌ Code analysis failed')
    except Exception as e:
        print(f'   ❌ Code analysis error: {e}')
    
    # Test 2: Mathematical reasoning
    math_msg = [Message(
        role='user',
        content='''Solve this graph theory problem and extract mathematical entities:

Given a graph G with 10 vertices and 15 edges, where each vertex has degree at least 2:
1. What is the average degree?
2. Is this graph connected?
3. What's the minimum number of edges needed for connectivity?

Extract mathematical concepts, theorems, and results as entities.'''
    )]
    
    try:
        math_response = await make_concurrent_cerebras_request(client, math_msg)
        if math_response:
            print('   ✅ Mathematical reasoning completed')
        else:
            print('   ❌ Mathematical reasoning failed')
    except Exception as e:
        print(f'   ❌ Math reasoning error: {e}')


async def test_graphiti_cerebras():
    print('\n🧠 Testing Graphiti with Cerebras/Qwen + Ollama Embeddings')
    print('=' * 70)

    # Cerebras LLM Configuration for Qwen
    cerebras_config = LLMConfig(
        model=DEFAULT_CEREBRAS_MODEL,
        temperature=0.3,  # Optimal for Qwen extraction tasks
        max_tokens=2000,  # Qwen can handle longer responses efficiently
    )
    
    cerebras_llm_client = CerebrasClient(config=cerebras_config)
    
    print(f'✓ Initialized Cerebras client with {DEFAULT_CEREBRAS_MODEL}')

    # Embedder Configuration for Ollama (keeping embeddings separate for now)
    ollama_embedder = OllamaEmbedder(
        base_url='http://192.168.50.80:11434/v1',  # Use embedding-specific endpoint
        model='mxbai-embed-large',
    )

    # FalkorDB connection
    print('\n📊 Connecting to FalkorDB...')
    graphiti = Graphiti(
        uri='bolt://localhost:6389',
        user='',
        password='',
        embedder=ollama_embedder,
        llm_client=cerebras_llm_client,
    )

    # Build indices and constraints
    print('🔨 Building indices and constraints...')
    await graphiti.build_indices_and_constraints()

    # Generate deterministic UUID for the episode
    episode_content = test_episode['content']
    GRAPHITI_APP_NAMESPACE = uuid.UUID('9a14a468-3730-4c69-b391-57f979239d51')
    content_hash = hashlib.sha256(episode_content.encode('utf-8')).hexdigest()
    deterministic_episode_uuid = str(uuid.uuid5(GRAPHITI_APP_NAMESPACE, content_hash))

    print(f'\n📝 Processing episode with UUID: {deterministic_episode_uuid}')

    # Test concurrent Qwen requests with domain-specific queries
    test_queries = [
        'Explain the architectural innovations in the Qwen transformer model',
        'Compare Qwen-Coder capabilities with other code-focused language models',
        'What are the key advantages of Qwen for multilingual applications?',
        'How does Qwen handle structured output generation?',
    ]

    test_messages = [[Message(role='user', content=query)] for query in test_queries]

    with timer('Total processing'):
        # Test Qwen-specific capabilities first
        await test_qwen_specific_capabilities(cerebras_llm_client)
        
        # Test concurrent Cerebras requests
        with timer('Concurrent Cerebras requests'):
            print('\n🔄 Making concurrent Qwen/Cerebras requests...')
            concurrent_results = await asyncio.gather(
                *[make_concurrent_cerebras_request(cerebras_llm_client, msgs) for msgs in test_messages]
            )

            print('\n📤 Concurrent Qwen request results:')
            for i, result in enumerate(concurrent_results):
                print(f'\nRequest {i + 1}:')
                print(f'Query: {test_queries[i]}')
                if result:
                    # Handle both dict and string responses
                    if isinstance(result, dict):
                        result_str = str(result)
                    else:
                        result_str = str(result)
                    
                    print(
                        f'Response: {result_str[:150]}...'
                        if len(result_str) > 150
                        else f'Response: {result_str}'
                    )
                else:
                    print('Response: None')

        # Add episode to graph using Qwen for extraction
        with timer('Episode addition (Qwen extraction)'):
            print('\n➕ Adding episode to graph using Qwen extraction...')
            episode_result = await graphiti.add_episode(
                episode_body=episode_content,
                source_description=test_episode['metadata']['source'],
                reference_time=datetime.fromisoformat(
                    test_episode['metadata']['timestamp'].replace('Z', '+00:00')
                ),
                uuid=deterministic_episode_uuid,
                source=EpisodeType.text,
            )

        # Display results with Qwen-specific analysis
        if episode_result:
            if hasattr(episode_result, 'episode') and episode_result.episode:
                print(f'\n✅ Episode Processed with Qwen: {episode_result.episode.uuid}')
            else:
                print(f'\n✅ Episode Processed with Qwen')

            print('\n🔹 Extracted Entities (via Qwen):')
            if hasattr(episode_result, 'nodes') and episode_result.nodes:
                for node in episode_result.nodes:
                    labels = (
                        ', '.join(node.labels) if hasattr(node, 'labels') and node.labels else 'N/A'
                    )
                    print(f'  - Name: {node.name}, UUID: {node.uuid}, Type(s): {labels}')
                    # Show summary if available (Qwen often provides good summaries)
                    if hasattr(node, 'summary') and node.summary:
                        summary_preview = node.summary[:100] + '...' if len(node.summary) > 100 else node.summary
                        print(f'    Summary: {summary_preview}')
            else:
                print('  No entities extracted by Qwen.')

            print('\n🔗 Created Relationships (via Qwen):')
            if hasattr(episode_result, 'edges') and episode_result.edges:
                for edge in episode_result.edges:
                    print(f'  - Name: {edge.name}, Fact: "{edge.fact}"')
                    print(f'    Source: {edge.source_node_uuid}, Target: {edge.target_node_uuid}')
            else:
                print('  No relationships created by Qwen.')

            print('\n📍 Created Episodic Edges (Mentions):')
            if hasattr(episode_result, 'episodic_edges') and episode_result.episodic_edges:
                for ep_edge in episode_result.episodic_edges:
                    print(
                        f'  - Episode: {ep_edge.source_node_uuid} -> Entity: {ep_edge.target_node_uuid}'
                    )
            else:
                print('  No episodic edges created.')

            print('\n👥 Identified/Created Communities:')
            if hasattr(episode_result, 'communities') and episode_result.communities:
                for comm in episode_result.communities:
                    print(f'  - Name: {comm.name}, UUID: {comm.uuid}')
                    if hasattr(comm, 'description') and comm.description:
                        print(f'    Description: {comm.description}')
            else:
                print('  No communities identified/created.')
        else:
            print('\n❌ Episode processing did not return a result.')

        # Test search functionality with Qwen-extracted content
        with timer('Search operation'):
            print('\n🔍 Testing search functionality on Qwen-extracted data...')
            search_queries = [
                'Qwen transformer architecture',
                'multilingual code generation',
                'structured output capabilities'
            ]
            
            for search_query in search_queries:
                print(f"\n🔎 Searching for: '{search_query}'")
                search_result = await graphiti.search(query=search_query, limit=3)
                
                if search_result:
                    for i, result in enumerate(search_result, 1):
                        print(f'  Result {i}:')
                        if hasattr(result, 'content'):
                            content_preview = result.content[:100] + '...' if len(result.content) > 100 else result.content
                            print(f'    Content: {content_preview}')
                        elif hasattr(result, 'node'):
                            node = result.node
                            if hasattr(node, 'name'):
                                print(f'    Name: {node.name}')
                            if hasattr(node, 'summary'):
                                summary_preview = node.summary[:100] + '...' if len(node.summary) > 100 else node.summary
                                print(f'    Summary: {summary_preview}')
                        else:
                            print(f'    {result}')
                        
                        # Show relevance score if available
                        if hasattr(result, 'score'):
                            print(f'    Score: {result.score:.3f}')
                else:
                    print(f'    No results found for: {search_query}')

    # Close the connection
    await graphiti.close()
    print('\n✨ Cerebras/Qwen integration test complete!')


async def test_cerebras_performance_metrics():
    """Test and report Qwen-specific performance characteristics."""
    
    print('\n📊 Testing Cerebras/Qwen Performance Metrics')
    print('-' * 50)
    
    config = LLMConfig(
        model=DEFAULT_CEREBRAS_MODEL,
        temperature=0.2,
        max_tokens=500,
    )
    
    client = CerebrasClient(config=config)
    
    # Test response consistency (important for extraction tasks)
    test_message = Message(
        role='user',
        content='Extract exactly 3 entities from: "Dr. Sarah Chen leads the AI research team at TechCorp."'
    )
    
    print('🔄 Testing response consistency (5 runs)...')
    responses = []
    times = []
    
    for i in range(5):
        start_time = time.time()
        try:
            response = await client._generate_response([test_message], max_tokens=200)
            end_time = time.time()
            
            responses.append(response)
            times.append(end_time - start_time)
            print(f'  Run {i+1}: {end_time - start_time:.2f}s')
            
        except Exception as e:
            print(f'  Run {i+1}: Error - {e}')
    
    if times:
        avg_time = sum(times) / len(times)
        print(f'\n📈 Performance Summary:')
        print(f'  - Average response time: {avg_time:.2f}s')
        print(f'  - Min/Max time: {min(times):.2f}s / {max(times):.2f}s')
        print(f'  - Successful responses: {len([r for r in responses if r])}/{len(responses)}')


if __name__ == '__main__':
    print('🚀 Starting Full Cerebras/Qwen Integration Test')
    
    async def main():
        await test_graphiti_cerebras()
        await test_cerebras_performance_metrics()
    
    asyncio.run(main())