#!/usr/bin/env python3

"""
Test Chutes AI (GLM-4.5-FP8) summary generation capabilities.

This test specifically validates that Chutes correctly generates summaries
for EntityNodes using the extract_attributes prompt system.
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from graphiti_core.llm_client.chutes_client import ChutesClient
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.nodes import EntityNode, EpisodicNode, EpisodeType
from graphiti_core.utils.maintenance.node_operations import extract_attributes_from_node
from graphiti_core.prompts import prompt_library

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ChutesSummaryTester:
    """Test suite for Chutes AI summary generation capabilities."""
    
    def __init__(self):
        self.test_results = []
        
    async def setup_client(self) -> ChutesClient:
        """Set up Chutes AI client."""
        api_key = os.getenv('CHUTES_API_KEY')
        if not api_key:
            raise ValueError("CHUTES_API_KEY environment variable not set")
            
        config = LLMConfig(
            api_key=api_key,
            base_url="https://llm.chutes.ai/v1",
            model="zai-org/GLM-4.5-FP8",
            temperature=0.3,
            max_tokens=2000,
        )
        
        return ChutesClient(config=config)

    async def test_direct_summary_generation(self, client: ChutesClient) -> Dict[str, Any]:
        """Test direct summary generation using extract_attributes prompt."""
        
        logger.info("🧪 Testing Direct Summary Generation...")
        
        # Create test episode content
        episode_content = """
        Dr. Sarah Chen, the lead AI researcher at Stanford University, published groundbreaking 
        research on transformer architectures. Her work focuses on improving computational 
        efficiency while maintaining model performance. She collaborates frequently with 
        researchers from MIT and has published over 50 papers in top-tier conferences.
        """
        
        # Create test context for extract_attributes prompt
        test_context = {
            'node': {
                'name': 'Sarah Chen',
                'summary': '',
                'entity_types': ['Person', 'Researcher'],
                'attributes': {}
            },
            'episode_content': episode_content,
            'previous_episodes': []
        }
        
        try:
            # Test the extract_attributes prompt directly
            start_time = datetime.now()
            messages = prompt_library.extract_nodes.extract_attributes(test_context)
            
            response = await client.generate_response(
                messages,
                response_model=None  # Allow flexible response
            )
            
            duration = (datetime.now() - start_time).total_seconds()
            
            result = {
                'test': 'direct_summary_generation',
                'success': True,
                'duration': duration,
                'response': response,
                'has_summary': 'summary' in response if isinstance(response, dict) else False,
                'summary_length': len(response.get('summary', '')) if isinstance(response, dict) else 0
            }
            
            if isinstance(response, dict) and 'summary' in response:
                logger.info(f"✅ Summary generated: {len(response['summary'])} characters")
                logger.info(f"   Summary preview: {response['summary'][:100]}...")
            else:
                logger.warning(f"⚠️ No summary in response: {type(response)}")
                logger.warning(f"   Response: {response}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Direct summary test failed: {e}")
            return {
                'test': 'direct_summary_generation',
                'success': False,
                'error': str(e)
            }

    async def test_node_attribute_extraction(self, client: ChutesClient) -> Dict[str, Any]:
        """Test EntityNode attribute extraction including summary."""
        
        logger.info("🔬 Testing Node Attribute Extraction...")
        
        try:
            # Create test episode
            episode = EpisodicNode(
                name="Test Episode",
                group_id="test_group",
                labels=[],
                source=EpisodeType.message,
                content="""
                Alice Johnson is a senior software engineer at TechCorp, specializing in 
                machine learning infrastructure. She leads a team of 8 engineers and has 
                been instrumental in developing the company's AI platform. Alice holds a 
                PhD in Computer Science from MIT and has 15 years of industry experience.
                """,
                source_description="Test episode for summary generation",
                created_at=datetime.now(),
                valid_at=datetime.now(),
            )
            
            # Create test EntityNode
            node = EntityNode(
                uuid=str(uuid4()),
                name="Alice Johnson",
                labels=["Person", "Engineer"],
                group_id="test_group",
                summary="",  # Empty summary to start
            )
            
            # Test extract_attributes_from_node function
            start_time = datetime.now()
            updated_node = await extract_attributes_from_node(
                llm_client=client,
                node=node,
                episode=episode,
                previous_episodes=[]
            )
            duration = (datetime.now() - start_time).total_seconds()
            
            result = {
                'test': 'node_attribute_extraction',
                'success': True,
                'duration': duration,
                'original_summary_length': len(node.summary),
                'updated_summary_length': len(updated_node.summary),
                'summary_generated': len(updated_node.summary) > len(node.summary),
                'updated_summary': updated_node.summary[:200] + "..." if len(updated_node.summary) > 200 else updated_node.summary
            }
            
            if updated_node.summary:
                logger.info(f"✅ Summary extracted: {len(updated_node.summary)} characters")
                logger.info(f"   Summary: {updated_node.summary}")
            else:
                logger.warning("⚠️ No summary generated for EntityNode")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Node attribute extraction test failed: {e}")
            return {
                'test': 'node_attribute_extraction',
                'success': False,
                'error': str(e)
            }

    async def test_summary_quality_validation(self, client: ChutesClient) -> Dict[str, Any]:
        """Test summary quality and constraints."""
        
        logger.info("📏 Testing Summary Quality & Constraints...")
        
        test_cases = [
            {
                'name': 'Short Content',
                'content': 'John Smith is a developer at Google.',
                'entity': 'John Smith'
            },
            {
                'name': 'Long Content',
                'content': '''
                Dr. Maria Rodriguez is a distinguished professor of artificial intelligence at 
                Carnegie Mellon University, where she has been teaching and conducting research 
                for over 20 years. Her work spans multiple areas including natural language 
                processing, computer vision, and reinforcement learning. She has published 
                over 200 peer-reviewed papers and has received numerous awards including the 
                ACM Fellowship and the IEEE Neural Networks Pioneer Award. Dr. Rodriguez leads 
                a research lab with 15 graduate students and 3 postdocs. She frequently 
                collaborates with industry partners including Google, Microsoft, and OpenAI. 
                Her recent work on large language models has been particularly influential in 
                the development of more efficient training algorithms.
                ''',
                'entity': 'Maria Rodriguez'
            },
            {
                'name': 'Technical Content',
                'content': '''
                The GraphQL API endpoint uses Apollo Server with Redis caching. The schema 
                supports real-time subscriptions via WebSocket connections. Query complexity 
                is limited to prevent DoS attacks. The resolver functions interact with 
                PostgreSQL database using Prisma ORM.
                ''',
                'entity': 'GraphQL API'
            }
        ]
        
        results = []
        
        for test_case in test_cases:
            try:
                logger.info(f"   Testing: {test_case['name']}")
                
                # Create test context
                test_context = {
                    'node': {
                        'name': test_case['entity'],
                        'summary': '',
                        'entity_types': ['Entity'],
                        'attributes': {}
                    },
                    'episode_content': test_case['content'],
                    'previous_episodes': []
                }
                
                messages = prompt_library.extract_nodes.extract_attributes(test_context)
                response = await client.generate_response(messages, response_model=None)
                
                if isinstance(response, dict) and 'summary' in response:
                    summary = response['summary']
                    word_count = len(summary.split())
                    
                    case_result = {
                        'test_case': test_case['name'],
                        'success': True,
                        'summary_length': len(summary),
                        'word_count': word_count,
                        'within_250_words': word_count <= 250,
                        'summary': summary[:100] + "..." if len(summary) > 100 else summary
                    }
                    
                    logger.info(f"      ✅ Generated {word_count} words ({'✅ within' if word_count <= 250 else '❌ exceeds'} 250 word limit)")
                    
                else:
                    case_result = {
                        'test_case': test_case['name'],
                        'success': False,
                        'error': 'No summary generated'
                    }
                    logger.warning(f"      ⚠️ No summary generated")
                
                results.append(case_result)
                
            except Exception as e:
                logger.error(f"      ❌ Error in {test_case['name']}: {e}")
                results.append({
                    'test_case': test_case['name'],
                    'success': False,
                    'error': str(e)
                })
        
        return {
            'test': 'summary_quality_validation',
            'results': results,
            'success_rate': len([r for r in results if r.get('success')]) / len(results)
        }

    async def run_all_tests(self) -> Dict[str, Any]:
        """Run all summary generation tests."""
        
        logger.info("=" * 80)
        logger.info("🧪 Chutes AI Summary Generation Test Suite")
        logger.info("=" * 80)
        
        try:
            client = await self.setup_client()
            logger.info("✅ Chutes client setup successful")
        except Exception as e:
            logger.error(f"❌ Failed to setup Chutes client: {e}")
            return {'error': 'Client setup failed', 'details': str(e)}
        
        # Run all tests
        tests = [
            self.test_direct_summary_generation(client),
            self.test_node_attribute_extraction(client),
            self.test_summary_quality_validation(client)
        ]
        
        results = []
        for test_coro in tests:
            try:
                result = await test_coro
                results.append(result)
            except Exception as e:
                logger.error(f"❌ Test failed with exception: {e}")
                results.append({'error': str(e)})
        
        # Calculate overall results
        successful_tests = [r for r in results if r.get('success')]
        total_tests = len([r for r in results if 'success' in r])
        
        summary = {
            'total_tests': total_tests,
            'successful_tests': len(successful_tests),
            'success_rate': len(successful_tests) / total_tests if total_tests > 0 else 0,
            'results': results
        }
        
        logger.info("\n" + "=" * 80)
        logger.info("📊 Test Summary")
        logger.info("=" * 80)
        logger.info(f"✅ Successful tests: {len(successful_tests)}/{total_tests}")
        logger.info(f"📈 Success rate: {summary['success_rate']:.1%}")
        
        if summary['success_rate'] >= 0.8:
            logger.info("🎉 Chutes summary generation is working well!")
        elif summary['success_rate'] >= 0.5:
            logger.warning("⚠️ Chutes summary generation has some issues")
        else:
            logger.error("❌ Chutes summary generation needs investigation")
        
        return summary


async def main():
    """Run the summary generation test suite."""
    tester = ChutesSummaryTester()
    results = await tester.run_all_tests()
    
    # Save results for further analysis
    with open('/opt/stacks/graphiti/testing/demos/chutes_summary_test_results.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    return results


if __name__ == "__main__":
    asyncio.run(main())