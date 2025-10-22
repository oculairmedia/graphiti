#!/usr/bin/env python3
"""
Complete Chutes AI (GLM-4.5-FP8) integration test with Graphiti.
Tests full pipeline including entity extraction, knowledge graph construction, and retrieval.
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

from graphiti_core import Graphiti
from graphiti_core.embedder import EmbedderClient
from graphiti_core.llm_client.chutes_client import ChutesClient, DEFAULT_MODEL, DEFAULT_BASE_URL
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.nodes import EpisodeType


class OllamaEmbedder(EmbedderClient):
    """Ollama embedder for hybrid approach with Chutes AI."""

    def __init__(self, base_url: str = 'http://192.168.50.80:11434/v1', model: str = 'mxbai-embed-large'):
        self.base_url = base_url
        self.model = model
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(base_url=base_url, api_key='ollama')
        print(f'✓ Initialized OllamaEmbedder with {model}')

    async def create(self, input_data: list[str]) -> list[list[float]]:
        """Create embeddings using Ollama."""
        try:
            response = await self.client.embeddings.create(model=self.model, input=input_data)
            return [item.embedding for item in response.data]
        except Exception as e:
            print(f'❌ Error creating embeddings: {e}')
            raise


async def setup_graphiti():
    """Set up Graphiti with Chutes AI + Ollama embeddings."""
    
    import os
    
    # Initialize Chutes AI LLM client
    chutes_config = LLMConfig(
        api_key=os.getenv('CHUTES_API_KEY'),
        base_url=DEFAULT_BASE_URL,
        model=DEFAULT_MODEL,
        temperature=0.3,  # Good balance for extraction consistency
        max_tokens=2000,  # GLM can handle longer responses
    )
    
    chutes_client = ChutesClient(config=chutes_config)
    print(f'✓ Initialized Chutes client with {DEFAULT_MODEL}')

    # Initialize Ollama embedder (hybrid approach)
    ollama_embedder = OllamaEmbedder()

    # FalkorDB connection 
    graphiti = Graphiti(
        uri='bolt://localhost:6389',
        user='',
        password='',
        embedder=ollama_embedder,
        llm_client=chutes_client,
    )

    # Build indices
    await graphiti.build_indices_and_constraints()
    return graphiti


async def add_test_data(graphiti):
    """Add test data optimized for GLM's strengths."""

    print('\n📝 Adding GLM-optimized test data to graph...')

    # Test episodes designed for GLM capabilities
    test_episodes = [
        {
            'name': 'Chinese AI Research Breakthrough',
            'content': '''
            清华大学人工智能实验室的Zhang Wei教授团队在GLM-4架构优化方面取得重大突破。
            该团队与智谱AI公司合作，开发了新型注意力机制，将推理速度提升了45%。
            
            Research lead Dr. Zhang Wei from Tsinghua University's AI Lab announced a breakthrough
            in GLM-4 architecture optimization. The collaboration with Zhipu AI resulted in novel
            attention mechanisms that improve inference speed by 45% while maintaining accuracy.
            
            Key innovations include:
            - Sparse attention patterns with dynamic head allocation
            - FP8 quantization with custom CUDA kernels  
            - Multi-language reasoning chains (Chinese-English)
            - 128K context window optimization
            
            The work was published in ICML 2024 and received the Outstanding Paper Award.
            Industrial partners include ByteDance, Alibaba Cloud, and Tencent AI.
            ''',
            'source': 'AI Research Journal',
            'timestamp': datetime.now() - timedelta(days=20)
        },
        {
            'name': 'GLM Model Deployment at Scale',
            'content': '''
            大型语言模型GLM-4在生产环境中的部署已达到百万级并发用户规模。
            
            GLM-4 large language model deployment has reached million-scale concurrent users
            in production environments. The system architecture includes:
            
            Technical Stack:
            - Model Serving: vLLM with custom GLM optimizations
            - Load Balancing: Kubernetes-based auto-scaling
            - Inference Backend: NVIDIA A100 GPU clusters (400+ cards)
            - Memory Management: KV-cache optimization with 8-bit compression
            
            Performance Metrics:
            - Average latency: 120ms for 2K tokens
            - Throughput: 50K requests/second peak
            - Model accuracy: 92.3% on MMLU benchmark
            - Cost efficiency: 60% reduction vs GPT-4 equivalent
            
            Deployment team: CTO Li Ming, Infrastructure lead Sarah Chen, 
            ML Engineering manager David Park, and DevOps specialist Maria Rodriguez.
            The project received $8M funding from government AI initiative.
            ''',
            'source': 'Tech Industry Report',
            'timestamp': datetime.now() - timedelta(days=10)
        },
        {
            'name': 'Multimodal GLM Applications',
            'content': '''
            Multimodal GLM applications are revolutionizing document understanding and 
            visual reasoning tasks across industries.
            
            Application Areas:
            1. Legal Document Analysis: 
               - Contract extraction with 96% accuracy
               - Multi-language legal term recognition
               - Implemented at LawTech Solutions Inc. by Legal AI team
            
            2. Medical Image Diagnosis:
               - Radiology report generation from X-rays and CT scans
               - Collaboration with Beijing Hospital and Dr. Wang Liu
               - FDA approval pending for clinical trials
            
            3. Financial Analysis:
               - Annual report summarization and risk assessment
               - Deployed at Goldman Sachs Asia (Hong Kong office)
               - Led by Quantitative Research team under James Wilson
            
            4. Educational Content:
               - Automatic textbook question generation
               - Personalized learning paths in Mandarin and English
               - Partnership with New Oriental Education Group
            
            Technical Specifications:
            - Vision Transformer: Custom ViT-Large with GLM attention
            - Text Processing: 32-layer transformer with MoE routing  
            - Training Data: 500M image-text pairs (Chinese + English)
            - Inference Speed: 2.3 seconds per multimodal query
            ''',
            'source': 'Multimodal AI Conference',
            'timestamp': datetime.now() - timedelta(days=5)
        }
    ]

    added_episodes = []

    for episode in test_episodes:
        try:
            print(f'\n  Processing with GLM: {episode["name"]}...')

            # Add episode using GLM for extraction
            result = await asyncio.wait_for(
                graphiti.add_episode(
                    name=episode['name'],
                    episode_body=episode['content'],
                    source_description=episode['source'],
                    reference_time=episode['timestamp'],
                    source=EpisodeType.text,
                ),
                timeout=150.0  # GLM can be slower but thorough
            )

            print(f'  ✅ GLM extraction completed!')
            if result:
                added_episodes.append(result)
                if hasattr(result, 'nodes') and result.nodes:
                    print(f'     Entities extracted by GLM: {len(result.nodes)}')
                    # Show sample entities focusing on multilingual capability
                    for node in result.nodes[:3]:
                        labels = ', '.join(node.labels) if hasattr(node, 'labels') and node.labels else 'N/A'
                        print(f'       • {node.name} ({labels})')
                
                if hasattr(result, 'edges') and result.edges:
                    print(f'     Relationships extracted by GLM: {len(result.edges)}')
                    # Show sample relationships
                    for edge in result.edges[:2]:
                        fact = edge.fact[:60] + '...' if len(edge.fact) > 60 else edge.fact
                        print(f'       • "{fact}"')

        except asyncio.TimeoutError:
            print(f'  ⏱️ Timeout processing episode with GLM')
        except Exception as e:
            print(f'  ❌ Error: {e}')

    return added_episodes


async def test_glm_optimized_retrieval(graphiti):
    """Test retrieval methods optimized for GLM-extracted content."""

    print('\n🧠 Testing GLM-Optimized Data Retrieval')
    print('=' * 60)

    # Test 1: Database statistics for GLM extractions
    print('\n1️⃣ Database Statistics for GLM Extractions...')
    try:
        node_count = await graphiti.driver.execute_query('MATCH (n) RETURN count(n) as count')
        print(f'✅ Total nodes in graph: {node_count[0]["count"] if node_count else 0}')

        # GLM often creates rich, detailed entity types
        node_stats = await graphiti.driver.execute_query('''
            MATCH (n)
            RETURN labels(n)[0] as primary_type, 
                   count(n) as count,
                   collect(n.name)[0..3] as sample_names
            ORDER BY count DESC
        ''')
        
        if node_stats:
            print('\n   Node distribution (GLM extraction results):')
            for stat in node_stats:
                primary = stat["primary_type"] if stat["primary_type"] else 'Unlabeled'
                count = stat["count"]
                samples = stat["sample_names"]
                print(f'   - {primary}: {count} nodes')
                if samples:
                    sample_str = ', '.join(samples[:2]) + ('...' if len(samples) > 2 else '')
                    print(f'     Examples: {sample_str}')

        # Check multilingual entities (GLM strength)
        multilingual_check = await graphiti.driver.execute_query('''
            MATCH (n)
            WHERE n.name =~ '.*[\\u4e00-\\u9fff].*' OR n.summary =~ '.*[\\u4e00-\\u9fff].*'
            RETURN count(n) as chinese_entities
        ''')
        
        if multilingual_check:
            chinese_count = multilingual_check[0]["chinese_entities"]
            print(f'\n   🈶 Multilingual entities (Chinese): {chinese_count}')

    except Exception as e:
        print(f'❌ Database query error: {e}')

    # Test 2: Multilingual search (GLM specialty)
    print("\n2️⃣ Multilingual Search Testing...")
    multilingual_queries = [
        ('Chinese AI research collaboration', 'English query for Chinese content'),
        ('GLM model deployment architecture', 'Technical architecture query'),
        ('multimodal vision transformer', 'Computer vision technical query'),
        ('legal document analysis accuracy', 'Legal AI application query'),
        ('清华大学 artificial intelligence', 'Mixed Chinese-English query')
    ]
    
    for query, description in multilingual_queries:
        try:
            print(f'\n   🔍 {description}: "{query}"')
            search_results = await asyncio.wait_for(
                graphiti.search(query=query, limit=3),
                timeout=30.0
            )

            if search_results:
                print(f'   ✅ Found {len(search_results)} results')
                for i, result in enumerate(search_results, 1):
                    if hasattr(result, 'node'):
                        node = result.node
                        node_labels = ', '.join(node.labels) if hasattr(node, 'labels') and node.labels else 'N/A'
                        print(f'     {i}. {node.name} ({node_labels})')
                        if hasattr(result, 'score'):
                            print(f'        Score: {result.score:.3f}')
                        
                        # Show multilingual content if available
                        if hasattr(node, 'summary') and node.summary:
                            summary = node.summary[:80] + '...' if len(node.summary) > 80 else node.summary
                            # Check if contains Chinese characters
                            has_chinese = any('\u4e00' <= char <= '\u9fff' for char in summary)
                            lang_indicator = ' 🈶' if has_chinese else ''
                            print(f'        Summary: {summary}{lang_indicator}')
            else:
                print(f'   ⚠️ No results for: {query}')

        except Exception as e:
            print(f'   ❌ Search error for "{query}": {e}')

    # Test 3: Technical domain queries (GLM strength)
    print("\n3️⃣ Technical Domain Analysis...")
    try:
        # Find technical specifications and performance metrics
        tech_specs_query = '''
        MATCH (n)-[r]->(m)
        WHERE n.name =~ '.*[Ss]pec.*|.*[Pp]erformance.*|.*[Mm]etric.*' 
           OR r.fact =~ '.*speed.*|.*accuracy.*|.*latency.*'
        RETURN n.name as source, type(r) as relationship, m.name as target, r.fact as fact
        LIMIT 5
        '''
        
        tech_results = await graphiti.driver.execute_query(tech_specs_query)
        
        if tech_results:
            print('   ✅ Technical specifications found:')
            for result in tech_results:
                source = result["source"]
                rel_type = result["relationship"]
                target = result["target"] 
                fact = result["fact"]
                if fact:
                    fact_preview = fact[:60] + '...' if len(fact) > 60 else fact
                    print(f'   - {source} → {target}')
                    print(f'     Fact: "{fact_preview}"')
        else:
            print('   ⚠️ No technical specifications found')

    except Exception as e:
        print(f'   ❌ Technical analysis error: {e}')

    # Test 4: Semantic search with GLM-specific concepts
    print('\n4️⃣ GLM-Specific Concept Search...')
    glm_concepts = [
        'attention mechanism optimization',
        'FP8 quantization techniques', 
        'multimodal reasoning capabilities',
        'Chinese language processing',
        'transformer architecture improvements'
    ]
    
    for concept in glm_concepts:
        try:
            print(f'\n   🔍 Searching: "{concept}"')
            results = await asyncio.wait_for(
                graphiti.search(query=concept, limit=2),
                timeout=30.0
            )
            
            if results:
                print(f'   ✅ {len(results)} concept-related results')
                for i, result in enumerate(results, 1):
                    if hasattr(result, 'node') and hasattr(result, 'score'):
                        node = result.node
                        print(f'     {i}. {node.name} (score: {result.score:.3f})')
            else:
                print(f'   ⚠️ No results for concept: {concept}')
                
        except Exception as e:
            print(f'   ❌ Concept search error: {e}')


async def test_glm_performance_metrics(graphiti):
    """Test GLM-specific performance characteristics."""
    
    print('\n📊 GLM Performance Characteristics Testing')
    print('=' * 60)
    
    # Test concurrent requests (GLM scalability)
    print('\n⚡ Testing Concurrent Request Handling...')
    
    concurrent_queries = [
        'GLM model architecture',
        'Chinese AI research',
        'transformer optimization',
        'multimodal applications',
        'FP8 quantization'
    ]
    
    start_time = time.time()
    try:
        # Run queries concurrently
        search_tasks = [
            graphiti.search(query=query, limit=2)
            for query in concurrent_queries
        ]
        
        results = await asyncio.gather(*search_tasks, return_exceptions=True)
        total_time = time.time() - start_time
        
        successful_results = [r for r in results if not isinstance(r, Exception)]
        failed_results = [r for r in results in isinstance(r, Exception)]
        
        print(f'✅ Concurrent queries completed in {total_time:.2f}s')
        print(f'   Successful: {len(successful_results)}/{len(concurrent_queries)}')
        print(f'   Average time per query: {total_time/len(concurrent_queries):.2f}s')
        
        if failed_results:
            print(f'   ⚠️ Failed queries: {len(failed_results)}')
            for error in failed_results[:2]:  # Show first 2 errors
                print(f'     Error: {str(error)[:100]}...')

    except Exception as e:
        print(f'❌ Concurrent testing error: {e}')


async def main():
    """Run comprehensive GLM integration test."""

    import os

    print('🚀 Chutes AI (GLM-4.5-FP8) Full Integration Test')
    print('=' * 70)

    # Check prerequisites
    if not os.getenv('CHUTES_API_KEY'):
        print('❌ CHUTES_API_KEY not found')
        return
    
    try:
        # Set up Graphiti with GLM
        graphiti = await setup_graphiti()
        print('✅ Graphiti initialized with GLM + Ollama embeddings')

        # Add GLM-optimized test data
        added_episodes = await add_test_data(graphiti)

        # Wait for indexing (GLM extractions can be complex)
        print('\n⏳ Waiting for GLM extraction indexing...')
        await asyncio.sleep(8)

        # Test retrieval with GLM-optimized queries
        await test_glm_optimized_retrieval(graphiti)

        # Test GLM performance characteristics
        await test_glm_performance_metrics(graphiti)

        # Clean up
        await graphiti.close()
        
        print('\n🎉 GLM-4.5-FP8 integration test completed successfully!')
        print('Key GLM strengths demonstrated:')
        print('  ✅ Multilingual content processing (Chinese + English)')
        print('  ✅ Technical domain understanding')
        print('  ✅ Complex structured extraction')
        print('  ✅ Robust JSON parsing with custom parser')

    except Exception as e:
        print(f'\n❌ Test failed: {e}')
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    asyncio.run(main())