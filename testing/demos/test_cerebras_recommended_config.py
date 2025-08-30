#!/usr/bin/env python3
"""
Test Cerebras Recommended Configuration: temperature=0.7, top_p=0.8
Compare against current optimal configuration: temperature=0.0, top_p=0.8
"""

import asyncio
import json
import os
import time
import statistics
from typing import Dict, List, Any, Tuple
from datetime import datetime
from cerebras.cloud.sdk import Cerebras

# Extended test episodes for more comprehensive evaluation
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
    },
    {
        "name": "research_findings",
        "content": "Dr. Chen's team at MIT discovered a new quantum algorithm that reduces computation time by 60%. The algorithm, named QuantumBoost, can solve NP-complete problems faster than classical computers. IBM and Intel have expressed interest in licensing the technology.",
        "expected_entities": ["Dr. Chen", "MIT", "quantum algorithm", "QuantumBoost", "IBM", "Intel", "NP-complete problems"],
        "expected_relationships": [("Dr. Chen", "works_at", "MIT"), ("Dr. Chen", "discovered", "quantum algorithm"), ("quantum algorithm", "named", "QuantumBoost"), ("IBM", "interested_in", "QuantumBoost")]
    }
]

# Configurations to compare
CONFIGS = [
    {"name": "Current Optimal", "temperature": 0.0, "top_p": 0.8},
    {"name": "Recommended", "temperature": 0.7, "top_p": 0.8}
]

ITERATIONS_PER_CONFIG = 3  # Multiple runs to measure consistency

# Working schema
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

async def test_configuration(client: Cerebras, episode: Dict, config: Dict) -> Dict[str, Any]:
    """Test extraction with specific configuration."""
    start = time.time()
    
    try:
        response = client.chat.completions.create(
            model="qwen-3-coder-480b",
            messages=[
                {"role": "system", "content": "You are an expert at extracting entities and relationships from text. Extract all meaningful entities (people, organizations, locations, concepts) and their relationships. Provide detailed descriptions and confidence scores."},
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
            temperature=config["temperature"],
            top_p=config["top_p"],
            max_completion_tokens=2000
        )
        
        end_time = time.time()
        result = json.loads(response.choices[0].message.content)
        
        entities = [entity["name"] for entity in result["entities"]]
        relationships = [(rel["source"], rel["relation"], rel["target"]) for rel in result["relationships"]]
        
        # Calculate metrics
        entity_precision, entity_recall, entity_f1 = calculate_precision_recall(entities, episode['expected_entities'])
        rel_precision, rel_recall, rel_f1 = calculate_relationship_f1(relationships, episode['expected_relationships'])
        
        # Calculate confidence scores
        confidences = [rel["confidence"] for rel in result["relationships"]]
        avg_confidence = statistics.mean(confidences) if confidences else 0.0
        
        return {
            "success": True,
            "config": config["name"],
            "temperature": config["temperature"],
            "top_p": config["top_p"],
            "response_time": end_time - start,
            "entities": entities,
            "relationships": relationships,
            "entity_f1": entity_f1,
            "entity_precision": entity_precision,
            "entity_recall": entity_recall,
            "rel_f1": rel_f1,
            "rel_precision": rel_precision,
            "rel_recall": rel_recall,
            "avg_confidence": avg_confidence,
            "num_entities": len(entities),
            "num_relationships": len(relationships),
            "raw_result": result
        }
        
    except Exception as e:
        return {
            "success": False,
            "config": config["name"],
            "temperature": config["temperature"],
            "top_p": config["top_p"],
            "error": str(e),
            "response_time": time.time() - start
        }

async def main():
    """Compare configurations."""
    print("=" * 80)
    print("🔬 CEREBRAS RECOMMENDED vs CURRENT CONFIGURATION TEST")
    print("=" * 80)
    print(f"Model: qwen-3-coder-480b")
    print(f"Configurations:")
    for config in CONFIGS:
        print(f"  • {config['name']}: temperature={config['temperature']}, top_p={config['top_p']}")
    print(f"Iterations per config: {ITERATIONS_PER_CONFIG}")
    print(f"Start: {datetime.now().isoformat()}\n")
    
    api_key = os.environ.get("CEREBRAS_API_KEY")
    if not api_key:
        print("❌ CEREBRAS_API_KEY not set")
        return
    
    client = Cerebras(api_key=api_key)
    print("✓ Cerebras client initialized")
    
    all_results = {}
    
    for config in CONFIGS:
        print(f"\n{'='*60}")
        print(f"🧪 Testing Configuration: {config['name']}")
        print(f"   Temperature: {config['temperature']}, Top-p: {config['top_p']}")
        print(f"{'='*60}")
        
        config_results = []
        
        for episode in TEST_EPISODES:
            print(f"\n📄 Episode: {episode['name']}")
            episode_results = []
            
            # Multiple iterations to measure consistency
            for iteration in range(ITERATIONS_PER_CONFIG):
                print(f"  Iteration {iteration + 1}/{ITERATIONS_PER_CONFIG}: ", end="", flush=True)
                
                result = await test_configuration(client, episode, config)
                episode_results.append(result)
                
                if result["success"]:
                    print(f"✓ E:{result['num_entities']} R:{result['num_relationships']} F1:{result['entity_f1']:.1%}/{result['rel_f1']:.1%} ({result['response_time']:.1f}s)")
                else:
                    print(f"✗ Error: {result['error'][:50]}...")
                
                # Rate limiting
                if iteration < ITERATIONS_PER_CONFIG - 1:
                    await asyncio.sleep(4)
            
            # Calculate episode statistics
            successful = [r for r in episode_results if r["success"]]
            if successful:
                episode_stats = {
                    "episode": episode["name"],
                    "success_rate": len(successful) / len(episode_results),
                    "entity_f1_scores": [r["entity_f1"] for r in successful],
                    "rel_f1_scores": [r["rel_f1"] for r in successful],
                    "response_times": [r["response_time"] for r in successful],
                    "confidence_scores": [r["avg_confidence"] for r in successful],
                    "all_results": episode_results
                }
                
                # Show variance
                entity_mean = statistics.mean(episode_stats["entity_f1_scores"])
                entity_stdev = statistics.stdev(episode_stats["entity_f1_scores"]) if len(episode_stats["entity_f1_scores"]) > 1 else 0
                rel_mean = statistics.mean(episode_stats["rel_f1_scores"])
                rel_stdev = statistics.stdev(episode_stats["rel_f1_scores"]) if len(episode_stats["rel_f1_scores"]) > 1 else 0
                
                print(f"  📊 Entity F1: {entity_mean:.2%} ±{entity_stdev:.3f}")
                print(f"  📊 Relationship F1: {rel_mean:.2%} ±{rel_stdev:.3f}")
                print(f"  📊 Avg Confidence: {statistics.mean(episode_stats['confidence_scores']):.3f}")
                
                config_results.append(episode_stats)
            else:
                print(f"  ❌ All iterations failed")
        
        all_results[config["name"]] = config_results
        
        # Brief pause between configurations
        if config != CONFIGS[-1]:
            print(f"\n⏳ Pausing 15 seconds before next configuration...")
            await asyncio.sleep(15)
    
    # Final Comparison
    print(f"\n{'='*80}")
    print("🏆 CONFIGURATION COMPARISON")
    print(f"{'='*80}")
    
    comparison_data = []
    
    for config_name, config_results in all_results.items():
        if config_results:
            # Calculate overall metrics
            all_entity_f1 = []
            all_rel_f1 = []
            all_response_times = []
            all_confidences = []
            
            for episode_result in config_results:
                all_entity_f1.extend(episode_result["entity_f1_scores"])
                all_rel_f1.extend(episode_result["rel_f1_scores"])
                all_response_times.extend(episode_result["response_times"])
                all_confidences.extend(episode_result["confidence_scores"])
            
            if all_entity_f1:
                config_summary = {
                    "name": config_name,
                    "entity_f1_mean": statistics.mean(all_entity_f1),
                    "entity_f1_stdev": statistics.stdev(all_entity_f1) if len(all_entity_f1) > 1 else 0,
                    "rel_f1_mean": statistics.mean(all_rel_f1),
                    "rel_f1_stdev": statistics.stdev(all_rel_f1) if len(all_rel_f1) > 1 else 0,
                    "total_f1": (statistics.mean(all_entity_f1) + statistics.mean(all_rel_f1)) / 2,
                    "avg_response_time": statistics.mean(all_response_times),
                    "avg_confidence": statistics.mean(all_confidences),
                    "consistency": 1 - (statistics.stdev(all_entity_f1) if len(all_entity_f1) > 1 else 0)
                }
                comparison_data.append(config_summary)
    
    # Display comparison table
    print(f"\n{'Configuration':<20} {'Entity F1':<12} {'Rel F1':<12} {'Total F1':<12} {'Avg Time':<10} {'Confidence':<12} {'Consistency'}")
    print("-" * 95)
    
    for config in comparison_data:
        print(f"{config['name']:<20} "
              f"{config['entity_f1_mean']:<12.2%} "
              f"{config['rel_f1_mean']:<12.2%} "
              f"{config['total_f1']:<12.2%} "
              f"{config['avg_response_time']:<10.2f} "
              f"{config['avg_confidence']:<12.3f} "
              f"{config['consistency']:<.3f}")
    
    # Determine winner
    if len(comparison_data) >= 2:
        current = comparison_data[0]  # Current Optimal
        recommended = comparison_data[1]  # Recommended
        
        print(f"\n🎯 Analysis:")
        print(f"  Current (T=0.0):    {current['total_f1']:.2%} total F1")
        print(f"  Recommended (T=0.7): {recommended['total_f1']:.2%} total F1")
        
        if recommended['total_f1'] > current['total_f1']:
            improvement = recommended['total_f1'] - current['total_f1']
            print(f"  🏆 Recommended config is BETTER by {improvement:.2%}")
            print(f"  ✅ Should update production to temperature=0.7")
        else:
            decline = current['total_f1'] - recommended['total_f1']
            print(f"  🏆 Current config is BETTER by {decline:.2%}")
            print(f"  ✅ Should keep current temperature=0.0")
        
        # Additional insights
        print(f"\n💡 Additional Insights:")
        print(f"  • Response Time: {current['avg_response_time']:.2f}s vs {recommended['avg_response_time']:.2f}s")
        print(f"  • Confidence: {current['avg_confidence']:.3f} vs {recommended['avg_confidence']:.3f}")
        print(f"  • Consistency: {current['consistency']:.3f} vs {recommended['consistency']:.3f}")
    
    # Save detailed results
    final_results = {
        "timestamp": datetime.now().isoformat(),
        "model": "qwen-3-coder-480b",
        "test_type": "configuration_comparison",
        "configurations": CONFIGS,
        "summary": comparison_data,
        "detailed_results": all_results
    }
    
    filename = f"cerebras_config_comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, "w") as f:
        json.dump(final_results, f, indent=2, default=str)
    
    print(f"\n💾 Detailed results saved to {filename}")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())