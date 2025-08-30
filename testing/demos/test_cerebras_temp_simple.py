#!/usr/bin/env python3
"""
Simple Temperature Test for Cerebras qwen-3-coder-480b
Uses the working schema from test_cerebras_structured_quality.py
"""

import asyncio
import json
import os
import time
import statistics
from typing import Dict, List, Any, Tuple
from datetime import datetime
from cerebras.cloud.sdk import Cerebras

# Use the same test episodes and schema that worked before
TEST_EPISODES = [
    {
        "name": "tech_meeting",
        "content": "Alice from Microsoft and Bob from Google met in Seattle on January 15, 2024 to discuss AI collaboration. They agreed to share research on large language models and set up monthly sync meetings. The project budget was set at $5 million.",
        "expected_entities": ["Alice", "Bob", "Microsoft", "Google", "Seattle", "AI collaboration", "large language models"],
        "expected_relationships": [("Alice", "works_at", "Microsoft"), ("Bob", "works_at", "Google"), ("Alice", "met_with", "Bob"), ("Microsoft", "collaborates_with", "Google")]
    },
    {
        "name": "product_launch", 
        "content": "Sarah announced that DataCorp will launch CloudSync 2.0 on March 1st. The new version includes real-time collaboration, end-to-end encryption, and supports up to 10TB storage. The pricing starts at $99/month for teams.",
        "expected_entities": ["Sarah", "DataCorp", "CloudSync 2.0", "real-time collaboration", "encryption", "10TB storage"],
        "expected_relationships": [("Sarah", "works_at", "DataCorp"), ("DataCorp", "launches", "CloudSync 2.0"), ("CloudSync 2.0", "includes", "real-time collaboration")]
    }
]

# Temperature values to test
TEMPERATURES = [0.0, 0.1, 0.2, 0.3, 0.5]

# Exact working schema from successful test
entity_extraction_schema = {
    "type": "object",
    "properties": {
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "type": {"type": "string"},
                    "description": {"type": "string"}
                },
                "required": ["name", "type", "description"],
                "additionalProperties": False
            }
        },
        "relationships": {
            "type": "array", 
            "items": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "relation": {"type": "string"},
                    "target": {"type": "string"},
                    "confidence": {"type": "number"}
                },
                "required": ["source", "relation", "target", "confidence"],
                "additionalProperties": False
            }
        }
    },
    "required": ["entities", "relationships"],
    "additionalProperties": False
}

def calculate_precision_recall(extracted: List[str], expected: List[str]) -> tuple:
    """Calculate precision, recall, and F1."""
    extracted_set = set(str(e).lower() for e in extracted)
    expected_set = set(str(e).lower() for e in expected)
    
    if not extracted_set:
        return 0.0, 0.0, 0.0
        
    true_positives = len(extracted_set & expected_set)
    precision = true_positives / len(extracted_set) if extracted_set else 0
    recall = true_positives / len(expected_set) if expected_set else 0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    
    return precision, recall, f1

def calculate_relationship_f1(extracted_rels: List[Tuple], expected_rels: List[Tuple]) -> tuple:
    """Calculate relationship F1 with fuzzy matching."""
    if not extracted_rels:
        return 0.0, 0.0, 0.0
    
    matches = 0
    for extracted_rel in extracted_rels:
        for expected_rel in expected_rels:
            source_match = (extracted_rel[0].lower() in expected_rel[0].lower() or expected_rel[0].lower() in extracted_rel[0].lower())
            target_match = (extracted_rel[2].lower() in expected_rel[2].lower() or expected_rel[2].lower() in extracted_rel[2].lower())
            
            if source_match and target_match:
                matches += 1
                break
    
    precision = matches / len(extracted_rels) if extracted_rels else 0
    recall = matches / len(expected_rels) if expected_rels else 0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    
    return precision, recall, f1

async def test_temperature(client: Cerebras, episode: Dict, temperature: float) -> Dict[str, Any]:
    """Test extraction with specific temperature."""
    start = time.time()
    
    try:
        response = client.chat.completions.create(
            model="qwen-3-coder-480b",
            messages=[
                {"role": "system", "content": "You are an expert at extracting entities and relationships from text. Extract all meaningful entities (people, organizations, locations, concepts) and their relationships."},
                {"role": "user", "content": f"Extract entities and relationships from this text:\n\n{episode['content']}"}
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "entity_extraction", 
                    "strict": True,
                    "schema": entity_extraction_schema
                }
            },
            temperature=temperature,
            top_p=0.8,
            max_completion_tokens=1500
        )
        
        end_time = time.time()
        result = json.loads(response.choices[0].message.content)
        
        entities = [entity["name"] for entity in result["entities"]]
        relationships = [(rel["source"], rel["relation"], rel["target"]) for rel in result["relationships"]]
        
        # Calculate metrics
        entity_precision, entity_recall, entity_f1 = calculate_precision_recall(entities, episode['expected_entities'])
        rel_precision, rel_recall, rel_f1 = calculate_relationship_f1(relationships, episode['expected_relationships'])
        
        return {
            "success": True,
            "temperature": temperature,
            "response_time": end_time - start,
            "entities": entities,
            "relationships": relationships,
            "entity_f1": entity_f1,
            "entity_precision": entity_precision,
            "entity_recall": entity_recall,
            "rel_f1": rel_f1,
            "rel_precision": rel_precision,
            "rel_recall": rel_recall,
            "num_entities": len(entities),
            "num_relationships": len(relationships)
        }
        
    except Exception as e:
        return {
            "success": False,
            "temperature": temperature,
            "error": str(e),
            "response_time": time.time() - start
        }

async def main():
    """Run temperature sweep."""
    print("=" * 70)
    print("🌡️  CEREBRAS TEMPERATURE OPTIMIZATION")
    print("=" * 70)
    print(f"Model: qwen-3-coder-480b")
    print(f"Temperatures: {TEMPERATURES}")
    print(f"Start: {datetime.now().isoformat()}\n")
    
    api_key = os.environ.get("CEREBRAS_API_KEY")
    if not api_key:
        print("❌ CEREBRAS_API_KEY not set")
        return
    
    client = Cerebras(api_key=api_key)
    print("✓ Cerebras client initialized")
    
    results = {}
    
    for temp in TEMPERATURES:
        print(f"\n{'='*50}")
        print(f"🌡️  Testing Temperature: {temp}")
        print(f"{'='*50}")
        
        temp_results = []
        
        for episode in TEST_EPISODES:
            print(f"\n📄 Episode: {episode['name']}")
            result = await test_temperature(client, episode, temp)
            temp_results.append(result)
            
            if result["success"]:
                print(f"  ✓ Entities: {result['num_entities']}, Relationships: {result['num_relationships']}")
                print(f"  📊 Entity F1: {result['entity_f1']:.2%}, Rel F1: {result['rel_f1']:.2%}")
                print(f"  ⏱️  Time: {result['response_time']:.2f}s")
            else:
                print(f"  ✗ Error: {result['error']}")
            
            # Rate limiting
            await asyncio.sleep(4)
        
        results[temp] = temp_results
    
    # Analysis
    print(f"\n{'='*70}")
    print("📊 TEMPERATURE COMPARISON")
    print(f"{'='*70}")
    
    print(f"\n{'Temp':<6} {'Success':<8} {'Avg Entity F1':<14} {'Avg Rel F1':<12} {'Avg Time':<10} {'Total F1'}")
    print("-" * 65)
    
    best_temp = None
    best_f1 = 0
    
    for temp in TEMPERATURES:
        temp_results = results[temp]
        successful = [r for r in temp_results if r["success"]]
        
        if successful:
            success_rate = len(successful) / len(temp_results)
            avg_entity_f1 = statistics.mean([r["entity_f1"] for r in successful])
            avg_rel_f1 = statistics.mean([r["rel_f1"] for r in successful])
            avg_time = statistics.mean([r["response_time"] for r in successful])
            total_f1 = (avg_entity_f1 + avg_rel_f1) / 2
            
            print(f"{temp:<6.1f} {success_rate:<8.2%} {avg_entity_f1:<14.2%} {avg_rel_f1:<12.2%} {avg_time:<10.2f} {total_f1:.2%}")
            
            if total_f1 > best_f1:
                best_f1 = total_f1
                best_temp = temp
        else:
            print(f"{temp:<6.1f} {'0.00%':<8} {'N/A':<14} {'N/A':<12} {'N/A':<10} {'N/A'}")
    
    print(f"\n🏆 Best Temperature: {best_temp}")
    print(f"🏆 Best Total F1: {best_f1:.2%}")
    
    if best_temp is not None:
        print(f"\n💡 Recommendation:")
        if best_temp == 0.0:
            print(f"  • Keep current temperature (0.0) - optimal for deterministic extraction")
        else:
            print(f"  • Update production to use temperature={best_temp}")
            print(f"  • This improves F1 score from baseline to {best_f1:.2%}")
    
    # Save results
    with open(f"temp_sweep_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json", "w") as f:
        json.dump({
            "model": "qwen-3-coder-480b",
            "best_temperature": best_temp,
            "best_f1": best_f1,
            "results": results
        }, f, indent=2, default=str)
    
    print("=" * 70)
    
    return best_temp, best_f1

if __name__ == "__main__":
    asyncio.run(main())