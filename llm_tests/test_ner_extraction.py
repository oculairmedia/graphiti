#!/usr/bin/env python3
"""
Test slim-ner model for entity extraction performance.
Compares speed and accuracy against the current approach.
"""

import json
import asyncio
import time
from typing import List, Dict, Any, Set
import httpx
import os
from datetime import datetime

# Test cases with ground truth entities
TEST_CASES = [
    {
        "name": "Simple conversation",
        "text": "Bob Smith met with Alice Johnson at Microsoft headquarters in Seattle last Tuesday to discuss the new AI project.",
        "expected_entities": {
            "Person": ["Bob Smith", "Alice Johnson"],
            "Organization": ["Microsoft"],
            "Location": ["Seattle"],
            "Time": ["last Tuesday"]
        }
    },
    {
        "name": "Technical discussion",
        "text": "Dr. Chen from Stanford University published a paper on quantum computing with IBM Research in Nature journal, achieving 99.9% fidelity.",
        "expected_entities": {
            "Person": ["Dr. Chen"],
            "Organization": ["Stanford University", "IBM Research", "Nature"],
            "Metric": ["99.9% fidelity"]
        }
    },
    {
        "name": "Business context",
        "text": "CEO Sarah Williams announced that TechCorp acquired DataSystems for $2.5 billion, expanding their presence in New York and London markets.",
        "expected_entities": {
            "Person": ["Sarah Williams"],
            "Title": ["CEO"],
            "Organization": ["TechCorp", "DataSystems"],
            "Money": ["$2.5 billion"],
            "Location": ["New York", "London"]
        }
    },
    {
        "name": "Complex narrative",
        "text": "Robert Johnson, the former Google engineer, founded StartupAI in 2023 with $10M funding from Sequoia Capital. His co-founder Maria Garcia previously worked at Apple for 5 years.",
        "expected_entities": {
            "Person": ["Robert Johnson", "Maria Garcia"],
            "Organization": ["Google", "StartupAI", "Sequoia Capital", "Apple"],
            "Money": ["$10M"],
            "Time": ["2023", "5 years"]
        }
    },
    {
        "name": "Name variations",
        "text": "Bob met with Robert Smith (Bob S. as his friends call him) and Bobby Johnson at the NYC office of Microsoft Corp.",
        "expected_entities": {
            "Person": ["Bob", "Robert Smith", "Bob S.", "Bobby Johnson"],
            "Organization": ["Microsoft Corp"],
            "Location": ["NYC"]
        }
    }
]

# Prompts for different models
SLIM_NER_PROMPT = """Extract all named entities from the following text. Return a JSON object with entity types as keys and lists of entities as values.

Entity types to extract:
- Person: Names of people
- Organization: Companies, institutions, agencies
- Location: Cities, countries, addresses
- Time: Dates, times, durations
- Money: Monetary amounts
- Title: Job titles, positions
- Metric: Percentages, measurements, statistics

Text: {text}

Return only JSON with this structure:
{{"Person": ["name1", "name2"], "Organization": ["org1"], ...}}"""

GENERAL_LLM_PROMPT = """You are an entity extraction system. Extract all entities from the text and categorize them.

Categories:
- Person: Any person's name
- Organization: Any company, institution, or group
- Location: Any place or location
- Time: Any date, time, or duration
- Money: Any monetary amount
- Title: Any job title or position
- Metric: Any measurement or statistic

Text: {text}

Return only a JSON object with categories as keys and entity lists as values."""

async def test_model_extraction(base_url: str, model: str, prompt_template: str):
    """Test a model's entity extraction performance"""
    
    results = []
    total_time = 0
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        for test_case in TEST_CASES:
            prompt = prompt_template.format(text=test_case["text"])
            
            # Measure extraction time
            start_time = time.time()
            
            try:
                if "slim-ner" in model:
                    # Use generate endpoint for slim-ner without JSON format
                    response = await client.post(
                        f"{base_url}/api/generate",
                        json={
                            "model": model,
                            "prompt": test_case["text"],  # Just the raw text
                            "stream": False,
                            "options": {"temperature": 0.0}
                        }
                    )
                    raw_response = response.json().get('response', '')
                    
                    # Parse slim-ner's custom format
                    # Format: <classify> types </classify>\n<bot>:{'type': ['entity1', 'entity2']}
                    try:
                        # Extract the dictionary part after <bot>:
                        if '<bot>:' in raw_response:
                            dict_str = raw_response.split('<bot>:')[1].strip()
                            # Convert Python dict format to JSON
                            dict_str = dict_str.replace("'", '"')
                            content = dict_str
                        else:
                            content = "{}"
                    except:
                        content = "{}"
                else:
                    # Use chat endpoint for general models
                    response = await client.post(
                        f"{base_url}/api/chat",
                        json={
                            "model": model,
                            "messages": [{"role": "user", "content": prompt}],
                            "stream": False,
                            "format": "json",
                            "options": {"temperature": 0.0}
                        }
                    )
                    content = response.json()['message']['content']
                
                extraction_time = time.time() - start_time
                total_time += extraction_time
                
                # Parse extracted entities
                try:
                    extracted = json.loads(content)
                    
                    # Calculate metrics
                    metrics = calculate_metrics(extracted, test_case["expected_entities"])
                    
                    results.append({
                        "test": test_case["name"],
                        "extraction_time": extraction_time,
                        "extracted": extracted,
                        "metrics": metrics,
                        "success": True
                    })
                    
                except json.JSONDecodeError as e:
                    results.append({
                        "test": test_case["name"],
                        "extraction_time": extraction_time,
                        "error": f"JSON parse error: {str(e)}",
                        "raw_output": content[:200],
                        "success": False
                    })
                    
            except Exception as e:
                results.append({
                    "test": test_case["name"],
                    "extraction_time": 0,
                    "error": str(e),
                    "success": False
                })
    
    return results, total_time

def calculate_metrics(extracted: Dict[str, List[str]], expected: Dict[str, List[str]]):
    """Calculate precision, recall, and F1 score"""
    
    # Flatten all entities
    extracted_all = set()
    expected_all = set()
    
    for category, entities in extracted.items():
        extracted_all.update(normalize_entity(e) for e in entities)
    
    for category, entities in expected.items():
        expected_all.update(normalize_entity(e) for e in entities)
    
    # Calculate metrics
    true_positives = len(extracted_all & expected_all)
    false_positives = len(extracted_all - expected_all)
    false_negatives = len(expected_all - extracted_all)
    
    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0
    recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    
    # Per-category analysis
    category_scores = {}
    for category in set(list(extracted.keys()) + list(expected.keys())):
        ext_cat = set(normalize_entity(e) for e in extracted.get(category, []))
        exp_cat = set(normalize_entity(e) for e in expected.get(category, []))
        
        cat_tp = len(ext_cat & exp_cat)
        cat_total_expected = len(exp_cat)
        cat_total_extracted = len(ext_cat)
        
        category_scores[category] = {
            "extracted": cat_total_extracted,
            "expected": cat_total_expected,
            "correct": cat_tp
        }
    
    return {
        "precision": precision,
        "recall": recall,
        "f1_score": f1,
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "category_scores": category_scores
    }

def normalize_entity(entity: str) -> str:
    """Normalize entity for comparison"""
    return entity.lower().strip()

def print_detailed_results(model: str, results: List[Dict], total_time: float):
    """Print detailed test results"""
    
    print(f"\n{'='*80}")
    print(f"MODEL: {model}")
    print(f"{'='*80}")
    
    successful_tests = [r for r in results if r.get("success", False)]
    
    if successful_tests:
        # Calculate aggregate metrics
        avg_precision = sum(r["metrics"]["precision"] for r in successful_tests) / len(successful_tests)
        avg_recall = sum(r["metrics"]["recall"] for r in successful_tests) / len(successful_tests)
        avg_f1 = sum(r["metrics"]["f1_score"] for r in successful_tests) / len(successful_tests)
        avg_time = sum(r["extraction_time"] for r in successful_tests) / len(successful_tests)
        
        print(f"\nAGGREGATE METRICS:")
        print(f"  Average Precision: {avg_precision:.2%}")
        print(f"  Average Recall: {avg_recall:.2%}")
        print(f"  Average F1 Score: {avg_f1:.2%}")
        print(f"  Average Time: {avg_time:.3f}s")
        print(f"  Total Time: {total_time:.3f}s")
    
    print(f"\nDETAILED RESULTS:")
    for i, result in enumerate(results):
        test_name = result["test"]
        print(f"\n{i+1}. {test_name}")
        
        if result.get("success"):
            metrics = result["metrics"]
            print(f"   Time: {result['extraction_time']:.3f}s")
            print(f"   Precision: {metrics['precision']:.2%} | Recall: {metrics['recall']:.2%} | F1: {metrics['f1_score']:.2%}")
            
            # Show category breakdown
            print("   Category Performance:")
            for cat, scores in metrics["category_scores"].items():
                print(f"     {cat}: {scores['correct']}/{scores['expected']} found (extracted {scores['extracted']})")
                
        else:
            print(f"   ERROR: {result.get('error', 'Unknown error')}")

async def main():
    base_url = os.getenv('OLLAMA_BASE_URL', 'http://100.81.139.20:11434')
    if base_url.endswith('/v1'):
        base_url = base_url[:-3]
    
    # Test slim-ner
    print("Testing slim-ner:q4_k_m for entity extraction...")
    slim_results, slim_time = await test_model_extraction(
        base_url, 
        "slim-ner:q4_k_m",
        SLIM_NER_PROMPT
    )
    print_detailed_results("slim-ner:q4_k_m", slim_results, slim_time)
    
    # Test current model for comparison
    print("\n\nTesting qwen3-30b-a3b:iq4_nl for comparison...")
    qwen_results, qwen_time = await test_model_extraction(
        base_url,
        "qwen3-30b-a3b:iq4_nl", 
        GENERAL_LLM_PROMPT
    )
    print_detailed_results("qwen3-30b-a3b:iq4_nl", qwen_results, qwen_time)
    
    # Save results
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    results_file = f"ner_comparison_results_{timestamp}.json"
    with open(results_file, 'w') as f:
        json.dump({
            "timestamp": timestamp,
            "slim_ner": {
                "results": slim_results,
                "total_time": slim_time,
                "model": "slim-ner:q4_k_m"
            },
            "qwen": {
                "results": qwen_results,
                "total_time": qwen_time,
                "model": "qwen3-30b-a3b:iq4_nl"
            }
        }, f, indent=2)
    
    print(f"\n\nResults saved to: {results_file}")

if __name__ == "__main__":
    asyncio.run(main())