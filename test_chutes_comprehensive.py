#!/usr/bin/env python3
"""
Comprehensive Chutes AI Evaluation for All Memory Ingestion Tasks.

Tests Chutes AI (zai-org/GLM-4.5-FP8) on all critical ingestion tasks:
1. Entity extraction
2. Entity deduplication  
3. Relationship extraction
4. Entity summarization
5. Edge invalidation
"""

import asyncio
import json
import re
import time
from datetime import datetime
from typing import List, Dict, Any

from graphiti_core.llm_client.openai_client import OpenAIClient
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.prompts.models import Message


class ComprehensiveChutesEvaluator:
    """Comprehensive evaluation of Chutes AI on all ingestion tasks."""
    
    def __init__(self):
        # Configure with longer timeouts for slow model
        self.config = LLMConfig(
            api_key='cpk_f62b08fa4c2b4ae0b195b944fd47d6fc.bb20b5a1d58c50c9bc051e74b2a39d7c.roXSCXsJnWAk8mcZ26umGcrPjkCaqXlh',
            base_url='https://llm.chutes.ai/v1',
            model='zai-org/GLM-4.5-FP8',
            temperature=0.1,
            max_tokens=2048
        )
        self.client = OpenAIClient(config=self.config)
        self.results = {
            'evaluation_id': f"chutes_comprehensive_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            'model': 'zai-org/GLM-4.5-FP8',
            'start_time': datetime.now().isoformat(),
            'tasks': {}
        }
    
    async def call_llm_with_timeout(self, messages: List[Message], task_name: str, timeout_seconds: int = 60) -> Dict[str, Any]:
        """Call LLM with timeout and comprehensive error handling."""
        start_time = time.time()
        
        try:
            # Use asyncio.wait_for for timeout
            response = await asyncio.wait_for(
                self.client.generate_response(messages=messages),
                timeout=timeout_seconds
            )
            
            end_time = time.time()
            response_time = (end_time - start_time) * 1000
            
            # Extract content
            if isinstance(response, dict):
                content = response.get('content', str(response))
            elif hasattr(response, 'content'):
                content = response.content
            else:
                content = str(response)
            
            return {
                'success': True,
                'response_time_ms': response_time,
                'content': content,
                'timeout_used': timeout_seconds
            }
            
        except asyncio.TimeoutError:
            end_time = time.time()
            return {
                'success': False,
                'error': f'Timeout after {timeout_seconds}s',
                'response_time_ms': (end_time - start_time) * 1000,
                'timeout_used': timeout_seconds
            }
        except Exception as e:
            end_time = time.time()
            return {
                'success': False,
                'error': str(e),
                'response_time_ms': (end_time - start_time) * 1000,
                'timeout_used': timeout_seconds
            }
    
    async def test_entity_extraction(self) -> Dict[str, Any]:
        """Test entity extraction with complex content."""
        print("🔍 Testing Entity Extraction...")
        
        test_content = """
        During the quarterly board meeting on March 15th, 2024, CEO Sarah Johnson announced that TechCorp Inc. 
        would be partnering with Microsoft Azure to deploy their new AI platform across data centers in 
        San Francisco and New York. The project, codenamed "Project Phoenix", will utilize OpenAI's GPT-4 
        technology and be managed by the engineering team led by Dr. Michael Chen. The implementation is 
        scheduled to begin in Q2 2024 with an initial budget of $2.5 million. Sarah emphasized that this 
        strategic partnership aligns with TechCorp's mission to revolutionize enterprise software solutions.
        """
        
        messages = [
            Message(
                role='system',
                content='You are an expert entity extractor. Extract all entities from text and classify them by type. Return valid JSON with an "entities" array containing objects with "name", "type", and "context" fields.'
            ),
            Message(
                role='user',
                content=f'Extract all entities (people, organizations, locations, technologies, events, amounts, dates) from this text:\n\n{test_content}\n\nReturn only valid JSON.'
            )
        ]
        
        result = await self.call_llm_with_timeout(messages, 'entity_extraction', timeout_seconds=60)
        
        if result['success']:
            # Try to parse and validate JSON
            try:
                content = result['content']
                parsed = None
                
                # Try to parse content directly as JSON (if it's already JSON)
                try:
                    parsed = json.loads(content)
                except json.JSONDecodeError:
                    # Look for JSON pattern in response
                    json_match = re.search(r'\{.*\}', content, re.DOTALL)
                    if json_match:
                        parsed = json.loads(json_match.group())
                
                if parsed and 'entities' in parsed:
                    entities = parsed.get('entities', [])
                    result['parsed_json'] = True
                    result['entities_found'] = len(entities)
                    result['entity_types'] = list(set(e.get('type', 'unknown').lower() for e in entities))
                    result['sample_entities'] = entities[:5]  # First 5 for review
                else:
                    result['parsed_json'] = False
                    result['entities_found'] = 0
            except json.JSONDecodeError:
                result['parsed_json'] = False
                result['entities_found'] = 0
        
        print(f"   ⏱️  Response time: {result.get('response_time_ms', 0):.1f}ms")
        print(f"   📊 Entities found: {result.get('entities_found', 0)}")
        return result
    
    async def test_entity_deduplication(self) -> Dict[str, Any]:
        """Test entity deduplication logic."""
        print("🔗 Testing Entity Deduplication...")
        
        messages = [
            Message(
                role='system', 
                content='You are an entity deduplication expert. Given a target entity and candidate duplicates, identify which candidates are duplicates. Return JSON with "is_duplicate" boolean array.'
            ),
            Message(
                role='user',
                content='''
                Target entity: {"name": "Apple Inc", "type": "organization", "summary": "Technology company that makes iPhones and computers"}
                
                Candidate entities to check for duplicates:
                1. {"name": "Apple Inc.", "type": "organization", "summary": "Tech company founded by Steve Jobs"}
                2. {"name": "APPLE", "type": "organization", "summary": "Technology corporation in Cupertino"}  
                3. {"name": "Apple Computer", "type": "organization", "summary": "Computer manufacturer"}
                4. {"name": "Microsoft", "type": "organization", "summary": "Software company"}
                5. {"name": "Apple Fruit Corp", "type": "organization", "summary": "Agricultural company growing apples"}
                
                Return JSON: {"duplicates": [{"index": 1, "is_duplicate": true, "confidence": 0.95, "reason": "Same company, minor punctuation difference"}, ...]}
                '''
            )
        ]
        
        result = await self.call_llm_with_timeout(messages, 'entity_deduplication', timeout_seconds=60)
        
        if result['success']:
            try:
                json_match = re.search(r'\{.*\}', result['content'], re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group())
                    duplicates = parsed.get('duplicates', [])
                    result['parsed_json'] = True
                    result['duplicates_identified'] = len([d for d in duplicates if d.get('is_duplicate')])
                    result['total_candidates'] = len(duplicates)
                else:
                    result['parsed_json'] = False
            except json.JSONDecodeError:
                result['parsed_json'] = False
        
        print(f"   ⏱️  Response time: {result.get('response_time_ms', 0):.1f}ms")
        print(f"   🎯 Duplicates identified: {result.get('duplicates_identified', 0)}")
        return result
    
    async def test_relationship_extraction(self) -> Dict[str, Any]:
        """Test relationship/edge extraction."""
        print("🌐 Testing Relationship Extraction...")
        
        test_content = """
        John Smith works as a Software Engineer at Google in Mountain View. He reports to his manager 
        Lisa Wong, who heads the AI Research division. John graduated from Stanford University in 2020 
        with a degree in Computer Science. He previously worked at Facebook before joining Google in 2021.
        Google is headquartered in Mountain View, California and was founded by Larry Page and Sergey Brin.
        """
        
        messages = [
            Message(
                role='system',
                content='You are a relationship extraction expert. Extract relationships between entities from text. Return JSON with a "relationships" array containing objects with "source", "target", "relationship_type", and "context" fields.'
            ),
            Message(
                role='user',
                content=f'Extract all relationships between entities from this text:\n\n{test_content}\n\nReturn only valid JSON with relationships.'
            )
        ]
        
        result = await self.call_llm_with_timeout(messages, 'relationship_extraction', timeout_seconds=75)
        
        if result['success']:
            try:
                json_match = re.search(r'\{.*\}', result['content'], re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group())
                    relationships = parsed.get('relationships', [])
                    result['parsed_json'] = True
                    result['relationships_found'] = len(relationships)
                    result['relationship_types'] = list(set(r.get('relationship_type', 'unknown').lower() for r in relationships))
                    result['sample_relationships'] = relationships[:5]
                else:
                    result['parsed_json'] = False
            except json.JSONDecodeError:
                result['parsed_json'] = False
        
        print(f"   ⏱️  Response time: {result.get('response_time_ms', 0):.1f}ms")
        print(f"   🔗 Relationships found: {result.get('relationships_found', 0)}")
        return result
    
    async def test_entity_summarization(self) -> Dict[str, Any]:
        """Test entity summarization and description generation."""
        print("📝 Testing Entity Summarization...")
        
        entity_mentions = [
            "Microsoft announced their new AI initiative",
            "Microsoft Azure cloud services expanded to new regions", 
            "Microsoft's CEO Satya Nadella spoke at the conference",
            "The Microsoft Office suite received major updates",
            "Microsoft partnered with OpenAI for advanced AI integration"
        ]
        
        messages = [
            Message(
                role='system',
                content='You are an entity summarization expert. Given multiple mentions of an entity, create a comprehensive summary. Return JSON with "entity_name", "summary", "key_attributes", and "confidence_score" fields.'
            ),
            Message(
                role='user', 
                content=f'Create a summary for the entity "Microsoft" based on these mentions:\n\n' + 
                       '\n'.join(f'{i+1}. {mention}' for i, mention in enumerate(entity_mentions)) + 
                       '\n\nReturn comprehensive JSON summary.'
            )
        ]
        
        result = await self.call_llm_with_timeout(messages, 'entity_summarization', timeout_seconds=60)
        
        if result['success']:
            try:
                json_match = re.search(r'\{.*\}', result['content'], re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group())
                    result['parsed_json'] = True
                    result['has_summary'] = bool(parsed.get('summary'))
                    result['has_attributes'] = bool(parsed.get('key_attributes'))
                    result['summary_length'] = len(parsed.get('summary', ''))
                else:
                    result['parsed_json'] = False
            except json.JSONDecodeError:
                result['parsed_json'] = False
        
        print(f"   ⏱️  Response time: {result.get('response_time_ms', 0):.1f}ms")
        print(f"   📄 Summary generated: {result.get('has_summary', False)}")
        return result
    
    async def test_temporal_reasoning(self) -> Dict[str, Any]:
        """Test temporal reasoning and edge invalidation logic."""
        print("⏰ Testing Temporal Reasoning...")
        
        messages = [
            Message(
                role='system',
                content='You are a temporal reasoning expert. Given contradictory statements about relationships, determine which relationships are valid at different times. Return JSON with timeline analysis.'
            ),
            Message(
                role='user',
                content='''
                Analyze these statements about John's employment:
                1. "John works at Apple" (mentioned on Jan 1, 2024)
                2. "John started working at Google" (mentioned on March 15, 2024)  
                3. "John left Apple last month" (mentioned on April 1, 2024)
                4. "John has been at Google since March" (mentioned on May 1, 2024)
                
                Return JSON with: {"timeline": [{"period": "Jan-Mar 2024", "employer": "Apple", "status": "valid"}, ...], "invalidated_relationships": [...]}
                '''
            )
        ]
        
        result = await self.call_llm_with_timeout(messages, 'temporal_reasoning', timeout_seconds=60)
        
        if result['success']:
            try:
                json_match = re.search(r'\{.*\}', result['content'], re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group())
                    result['parsed_json'] = True
                    result['timeline_periods'] = len(parsed.get('timeline', []))
                    result['invalidations_identified'] = len(parsed.get('invalidated_relationships', []))
                else:
                    result['parsed_json'] = False
            except json.JSONDecodeError:
                result['parsed_json'] = False
        
        print(f"   ⏱️  Response time: {result.get('response_time_ms', 0):.1f}ms")
        print(f"   📅 Timeline periods: {result.get('timeline_periods', 0)}")
        return result
    
    async def run_comprehensive_evaluation(self) -> Dict[str, Any]:
        """Run all evaluation tasks."""
        print("🚀 Starting Comprehensive Chutes AI Evaluation")
        print("=" * 70)
        print(f"Model: {self.config.model}")
        print(f"Max tokens: {self.config.max_tokens}")
        print(f"Temperature: {self.config.temperature}")
        print("=" * 70)
        
        # Run all tests
        tasks = [
            ('entity_extraction', self.test_entity_extraction),
            ('entity_deduplication', self.test_entity_deduplication), 
            ('relationship_extraction', self.test_relationship_extraction),
            ('entity_summarization', self.test_entity_summarization),
            ('temporal_reasoning', self.test_temporal_reasoning)
        ]
        
        for task_name, task_func in tasks:
            print(f"\n📋 Running {task_name.replace('_', ' ').title()}...")
            try:
                task_result = await task_func()
                self.results['tasks'][task_name] = task_result
                
                if task_result['success']:
                    print(f"   ✅ Success")
                else:
                    print(f"   ❌ Failed: {task_result.get('error', 'Unknown error')}")
                    
            except Exception as e:
                print(f"   💥 Exception: {e}")
                self.results['tasks'][task_name] = {
                    'success': False,
                    'error': f'Exception: {str(e)}',
                    'response_time_ms': 0
                }
        
        # Generate summary
        self._generate_summary()
        
        # Save results
        results_file = f"chutes_comprehensive_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(results_file, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
        
        print(f"\n📁 Detailed results saved to: {results_file}")
        return self.results
    
    def _generate_summary(self):
        """Generate evaluation summary."""
        self.results['end_time'] = datetime.now().isoformat()
        
        tasks = self.results['tasks']
        successful_tasks = [name for name, result in tasks.items() if result.get('success')]
        total_tasks = len(tasks)
        
        total_response_time = sum(result.get('response_time_ms', 0) for result in tasks.values() if result.get('success'))
        avg_response_time = total_response_time / len(successful_tasks) if successful_tasks else 0
        
        json_compliance = sum(1 for result in tasks.values() if result.get('parsed_json')) / total_tasks if total_tasks else 0
        
        self.results['summary'] = {
            'total_tasks': total_tasks,
            'successful_tasks': len(successful_tasks),
            'success_rate': len(successful_tasks) / total_tasks if total_tasks else 0,
            'avg_response_time_ms': avg_response_time,
            'json_compliance_rate': json_compliance,
            'successful_task_names': successful_tasks
        }
        
        print("\n" + "=" * 70)
        print("📊 COMPREHENSIVE EVALUATION RESULTS")
        print("=" * 70)
        print(f"✅ Successful tasks: {len(successful_tasks)}/{total_tasks}")
        print(f"📈 Success rate: {len(successful_tasks)/total_tasks:.1%}")
        print(f"⏱️  Average response time: {avg_response_time:.1f}ms")
        print(f"📋 JSON compliance: {json_compliance:.1%}")
        print(f"🎯 Successful tasks: {', '.join(successful_tasks)}")


async def main():
    """Run the comprehensive evaluation."""
    evaluator = ComprehensiveChutesEvaluator()
    await evaluator.run_comprehensive_evaluation()


if __name__ == "__main__":
    asyncio.run(main())