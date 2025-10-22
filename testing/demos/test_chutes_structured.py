#!/usr/bin/env python3
"""
Test Chutes AI (GLM-4.5-FP8) structured output capabilities.
Tests JSON generation, parsing robustness, and GLM-specific features.
"""

import asyncio
import json
import time
from datetime import datetime
from typing import Dict, Any, List

from graphiti_core.llm_client.chutes_client import ChutesClient, DEFAULT_MODEL, DEFAULT_BASE_URL
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.prompts.models import Message


class ChutesStructuredTester:
    """Test suite for Chutes AI structured output capabilities."""
    
    def __init__(self):
        self.test_results = []
        
    async def setup_client(self) -> ChutesClient:
        """Set up Chutes AI client."""
        config = LLMConfig(
            api_key=os.getenv('CHUTES_API_KEY'),
            base_url=DEFAULT_BASE_URL,
            model=DEFAULT_MODEL,
            temperature=0.3,  # Balanced for structured output
            max_tokens=1000,
        )
        
        return ChutesClient(config=config)

    async def test_basic_json_structure(self, client: ChutesClient) -> Dict[str, Any]:
        """Test basic JSON structure generation."""
        
        print('\n📋 Testing Basic JSON Structure Generation...')
        
        test_message = Message(
            role='user',
            content='''
            Extract entities from this text and return as JSON:
            
            "Dr. Sarah Chen, a researcher at Stanford University, published a paper on 
            neural networks in collaboration with MIT's AI Lab."
            
            Return JSON with this structure:
            {
                "entities": [
                    {"name": "entity_name", "type": "entity_type", "context": "brief_context"}
                ]
            }
            '''
        )
        
        start_time = time.time()
        try:
            response = await asyncio.wait_for(
                client._generate_response([test_message]),
                timeout=60.0
            )
            
            duration = time.time() - start_time
            
            if isinstance(response, dict) and 'entities' in response:
                entities = response['entities']
                print(f'   ✅ Valid JSON structure with {len(entities)} entities')
                print(f'   ⏱️ Response time: {duration:.2f}s')
                
                # Show sample entities
                for entity in entities[:2]:
                    print(f'     • {entity.get("name", "N/A")} ({entity.get("type", "N/A")})')
                
                return {
                    'test': 'basic_json',
                    'success': True,
                    'duration': duration,
                    'entities_count': len(entities),
                    'response_format': 'valid_dict'
                }
            else:
                print(f'   ❌ Invalid structure: {type(response)}')
                return {
                    'test': 'basic_json',
                    'success': False,
                    'duration': duration,
                    'error': 'Invalid response structure'
                }
                
        except Exception as e:
            duration = time.time() - start_time
            print(f'   ❌ Error: {e}')
            return {
                'test': 'basic_json',
                'success': False,
                'duration': duration,
                'error': str(e)
            }

    async def test_complex_nested_structure(self, client: ChutesClient) -> Dict[str, Any]:
        """Test complex nested JSON structure."""
        
        print('\n🏗️ Testing Complex Nested Structure...')
        
        test_message = Message(
            role='user',
            content='''
            Analyze this business scenario and return structured data:
            
            "TechCorp Inc., founded in 2018 by CEO Alice Johnson and CTO Bob Smith, 
            raised $15M in Series A funding led by VentureX Partners. The company 
            specializes in AI-powered logistics optimization and has partnerships 
            with Amazon and FedEx."
            
            Return JSON with this structure:
            {
                "company": {
                    "name": "company_name",
                    "founded_year": year_as_number,
                    "founders": [{"name": "name", "role": "role"}],
                    "funding": {
                        "round": "round_type",
                        "amount": "amount",
                        "lead_investor": "investor_name"
                    },
                    "business": {
                        "focus": "description",
                        "partnerships": ["partner1", "partner2"]
                    }
                }
            }
            '''
        )
        
        start_time = time.time()
        try:
            response = await asyncio.wait_for(
                client._generate_response([test_message]),
                timeout=90.0
            )
            
            duration = time.time() - start_time
            
            if isinstance(response, dict) and 'company' in response:
                company = response['company']
                print(f'   ✅ Complex structure parsed successfully')
                print(f'   ⏱️ Response time: {duration:.2f}s')
                
                # Validate nested structure
                required_fields = ['name', 'founded_year', 'founders', 'funding', 'business']
                missing_fields = [field for field in required_fields if field not in company]
                
                if not missing_fields:
                    print(f'   ✅ All required fields present')
                    print(f'   📊 Company: {company.get("name", "N/A")}')
                    print(f'   👥 Founders: {len(company.get("founders", []))}')
                    print(f'   💰 Funding: {company.get("funding", {}).get("amount", "N/A")}')
                    
                    return {
                        'test': 'complex_nested',
                        'success': True,
                        'duration': duration,
                        'structure_complete': True,
                        'missing_fields': []
                    }
                else:
                    print(f'   ⚠️ Missing fields: {missing_fields}')
                    return {
                        'test': 'complex_nested',
                        'success': True,
                        'duration': duration,
                        'structure_complete': False,
                        'missing_fields': missing_fields
                    }
            else:
                print(f'   ❌ Invalid response format')
                return {
                    'test': 'complex_nested',
                    'success': False,
                    'duration': duration,
                    'error': 'Invalid response format'
                }
                
        except Exception as e:
            duration = time.time() - start_time
            print(f'   ❌ Error: {e}')
            return {
                'test': 'complex_nested',
                'success': False,
                'duration': duration,
                'error': str(e)
            }

    async def test_glm_specific_capabilities(self, client: ChutesClient) -> Dict[str, Any]:
        """Test GLM-4.5-FP8 specific capabilities."""
        
        print('\n🧠 Testing GLM-4.5-FP8 Specific Capabilities...')
        
        # GLM models are known for strong reasoning and code understanding
        test_message = Message(
            role='user',
            content='''
            Analyze this technical content and extract structured information:
            
            "The GLM-4.5-FP8 model implements a novel attention mechanism with 
            sparse matrices, achieving 40% memory reduction while maintaining 
            95% accuracy on MMLU benchmarks. The model uses FP8 quantization 
            techniques developed by researchers at Tsinghua University and 
            Zhipu AI, with support for 128K context length."
            
            Extract technical details in this JSON format:
            {
                "model_info": {
                    "name": "model_name",
                    "innovations": ["innovation1", "innovation2"],
                    "performance": {
                        "memory_reduction": "percentage",
                        "benchmark": "benchmark_name",
                        "accuracy": "percentage"
                    },
                    "technical_specs": {
                        "quantization": "technique",
                        "context_length": "length",
                        "developers": ["org1", "org2"]
                    }
                },
                "reasoning": "brief_analysis_of_technical_significance"
            }
            '''
        )
        
        start_time = time.time()
        try:
            response = await asyncio.wait_for(
                client._generate_response([test_message]),
                timeout=90.0
            )
            
            duration = time.time() - start_time
            
            if isinstance(response, dict) and 'model_info' in response:
                model_info = response['model_info']
                print(f'   ✅ GLM technical analysis successful')
                print(f'   ⏱️ Response time: {duration:.2f}s')
                
                # Check technical understanding
                if 'performance' in model_info and 'technical_specs' in model_info:
                    print(f'   🔬 Performance metrics extracted')
                    print(f'   ⚙️ Technical specs identified')
                    
                    # Check reasoning capability
                    reasoning = response.get('reasoning', '')
                    if reasoning and len(reasoning) > 50:
                        print(f'   🧠 Reasoning analysis provided ({len(reasoning)} chars)')
                        print(f'     Preview: "{reasoning[:100]}..."')
                        
                        return {
                            'test': 'glm_specific',
                            'success': True,
                            'duration': duration,
                            'technical_analysis': True,
                            'reasoning_quality': len(reasoning),
                            'structure_depth': len(str(model_info))
                        }
                    else:
                        print(f'   ⚠️ Limited reasoning analysis')
                        return {
                            'test': 'glm_specific',
                            'success': True,
                            'duration': duration,
                            'technical_analysis': True,
                            'reasoning_quality': len(reasoning),
                            'structure_depth': len(str(model_info))
                        }
                else:
                    print(f'   ⚠️ Incomplete technical structure')
                    return {
                        'test': 'glm_specific',
                        'success': False,
                        'duration': duration,
                        'error': 'Incomplete technical structure'
                    }
            else:
                print(f'   ❌ Invalid response structure')
                return {
                    'test': 'glm_specific',
                    'success': False,
                    'duration': duration,
                    'error': 'Invalid response structure'
                }
                
        except Exception as e:
            duration = time.time() - start_time
            print(f'   ❌ Error: {e}')
            return {
                'test': 'glm_specific',
                'success': False,
                'duration': duration,
                'error': str(e)
            }

    async def test_parsing_robustness(self, client: ChutesClient) -> Dict[str, Any]:
        """Test Chutes AI parser robustness with edge cases."""
        
        print('\n🛠️ Testing Parsing Robustness...')
        
        # Test challenging parsing scenarios
        test_message = Message(
            role='user',
            content='''
            Extract data from this complex text with mixed formats:
            
            "Company: 'Tech Solutions Inc.' (est. 2019) - Revenue: $2.5M USD; 
            Employees: 50+ staff; Location: San Francisco, CA & Austin, TX; 
            CEO: Maria Garcia-Rodriguez; Products: 'AI Platform v2.1', 'Data Analytics Suite'"
            
            Return clean JSON:
            {
                "company_name": "name_without_quotes",
                "established": year_as_number,
                "revenue": "clean_amount",
                "employee_count": "approximate_number",
                "locations": ["location1", "location2"],
                "leadership": {"ceo": "full_name"},
                "products": ["product1", "product2"]
            }
            '''
        )
        
        start_time = time.time()
        try:
            response = await asyncio.wait_for(
                client._generate_response([test_message]),
                timeout=60.0
            )
            
            duration = time.time() - start_time
            
            if isinstance(response, dict):
                print(f'   ✅ Successfully parsed complex input')
                print(f'   ⏱️ Response time: {duration:.2f}s')
                
                # Check data cleaning quality
                company_name = response.get('company_name', '')
                established = response.get('established')
                locations = response.get('locations', [])
                
                # Validate cleaning
                quote_free = "'" not in company_name and '"' not in company_name
                year_is_number = isinstance(established, (int, float)) if established else False
                locations_are_clean = isinstance(locations, list) and len(locations) > 0
                
                print(f'   🧹 Data cleaning quality:')
                print(f'     Quote removal: {"✅" if quote_free else "❌"}')
                print(f'     Year conversion: {"✅" if year_is_number else "❌"}')
                print(f'     Location parsing: {"✅" if locations_are_clean else "❌"}')
                
                cleaning_score = sum([quote_free, year_is_number, locations_are_clean])
                
                return {
                    'test': 'parsing_robustness',
                    'success': True,
                    'duration': duration,
                    'cleaning_score': cleaning_score,
                    'max_score': 3,
                    'response_structure': 'valid_dict'
                }
            else:
                print(f'   ❌ Response parsing failed')
                return {
                    'test': 'parsing_robustness',
                    'success': False,
                    'duration': duration,
                    'error': 'Response parsing failed'
                }
                
        except Exception as e:
            duration = time.time() - start_time
            print(f'   ❌ Error: {e}')
            return {
                'test': 'parsing_robustness',
                'success': False,
                'duration': duration,
                'error': str(e)
            }

    def print_summary(self):
        """Print comprehensive test summary."""
        
        print('\n📊 CHUTES AI (GLM-4.5-FP8) STRUCTURED OUTPUT SUMMARY')
        print('=' * 70)
        
        if not self.test_results:
            print('❌ No test results available')
            return
        
        # Overall statistics
        successful_tests = [r for r in self.test_results if r.get('success', False)]
        total_tests = len(self.test_results)
        success_rate = len(successful_tests) / total_tests * 100
        
        print(f'📈 Overall Success Rate: {success_rate:.1f}% ({len(successful_tests)}/{total_tests})')
        
        # Performance metrics
        if successful_tests:
            durations = [r['duration'] for r in successful_tests if 'duration' in r]
            if durations:
                avg_duration = sum(durations) / len(durations)
                min_duration = min(durations)
                max_duration = max(durations)
                
                print(f'⏱️ Performance:')
                print(f'   Average response time: {avg_duration:.2f}s')
                print(f'   Fastest response: {min_duration:.2f}s')
                print(f'   Slowest response: {max_duration:.2f}s')
        
        # Test-specific results
        print(f'\n📋 Detailed Results:')
        for result in self.test_results:
            test_name = result.get('test', 'Unknown')
            success = result.get('success', False)
            duration = result.get('duration', 0)
            
            status = '✅ PASS' if success else '❌ FAIL'
            print(f'   {status} {test_name}: {duration:.2f}s')
            
            # Additional details per test
            if test_name == 'basic_json' and success:
                entities_count = result.get('entities_count', 0)
                print(f'        Extracted {entities_count} entities')
                
            elif test_name == 'complex_nested' and success:
                complete = result.get('structure_complete', False)
                missing = result.get('missing_fields', [])
                print(f'        Structure complete: {"Yes" if complete else "Partial"}')
                if missing:
                    print(f'        Missing fields: {missing}')
                    
            elif test_name == 'glm_specific' and success:
                reasoning_quality = result.get('reasoning_quality', 0)
                print(f'        Reasoning analysis: {reasoning_quality} characters')
                
            elif test_name == 'parsing_robustness' and success:
                score = result.get('cleaning_score', 0)
                max_score = result.get('max_score', 1)
                print(f'        Data cleaning: {score}/{max_score}')
            
            # Show errors
            if not success and 'error' in result:
                print(f'        Error: {result["error"]}')
        
        # GLM-specific analysis
        print(f'\n🧠 GLM-4.5-FP8 Specific Analysis:')
        
        # Check if technical analysis worked
        glm_test = next((r for r in self.test_results if r.get('test') == 'glm_specific'), None)
        if glm_test and glm_test.get('success'):
            print('   ✅ Technical content analysis: Strong')
            print('   ✅ Structured reasoning: Available') 
            print('   ✅ Complex JSON generation: Successful')
        else:
            print('   ⚠️ GLM-specific capabilities not fully demonstrated')
        
        # Performance compared to expectations
        if successful_tests and durations:
            avg_time = sum(durations) / len(durations)
            if avg_time < 30:
                print('   ✅ Response speed: Good (< 30s average)')
            elif avg_time < 60:
                print('   ⚠️ Response speed: Moderate (30-60s average)')
            else:
                print('   ⚠️ Response speed: Slow (> 60s average)')
        
        # Recommendations
        print(f'\n💡 Recommendations:')
        if success_rate >= 80:
            print('   ✅ GLM-4.5-FP8 shows good structured output capability')
            print('   🎯 Suitable for production entity extraction tasks')
        else:
            print('   ⚠️ Some structured output issues detected')
            print('   🔧 Consider adjusting temperature or prompt engineering')


async def main():
    """Run Chutes AI structured output tests."""
    
    import os
    
    print('🚀 Chutes AI (GLM-4.5-FP8) Structured Output Test')
    print('=' * 70)
    
    # Check API key
    if not os.getenv('CHUTES_API_KEY'):
        print('❌ CHUTES_API_KEY not found')
        return
    
    tester = ChutesStructuredTester()
    client = await tester.setup_client()
    
    print(f'✅ Testing with model: {DEFAULT_MODEL}')
    print(f'🌐 Base URL: {DEFAULT_BASE_URL}')
    
    # Run tests
    tests = [
        ('Basic JSON', tester.test_basic_json_structure),
        ('Complex Nested', tester.test_complex_nested_structure), 
        ('GLM Capabilities', tester.test_glm_specific_capabilities),
        ('Parsing Robustness', tester.test_parsing_robustness)
    ]
    
    for test_name, test_func in tests:
        print(f'\n🧪 Running {test_name} test...')
        try:
            result = await test_func(client)
            tester.test_results.append(result)
        except Exception as e:
            print(f'   ❌ Test failed: {e}')
            tester.test_results.append({
                'test': test_name.lower().replace(' ', '_'),
                'success': False,
                'error': str(e)
            })
        
        # Brief pause between tests
        await asyncio.sleep(2)
    
    # Print summary
    tester.print_summary()
    
    print(f'\n🎉 Chutes AI structured output testing completed!')


if __name__ == '__main__':
    import os
    asyncio.run(main())