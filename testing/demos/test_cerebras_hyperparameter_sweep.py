#!/usr/bin/env python3
"""
Cerebras Hyperparameter Sweep Test for qwen-3-coder-480b
Tests different temperature values to optimize extraction quality and success rate
"""

import asyncio
import json
import os
import time
import statistics
from typing import Dict, List, Any, Tuple
from datetime import datetime
from cerebras.cloud.sdk import Cerebras

# Test scenarios for consistent evaluation
TEST_EPISODES = [
    {
        "name": "tech_meeting",
        "content": "Alice from Microsoft and Bob from Google met in Seattle on January 15, 2024 to discuss AI collaboration. They agreed to share research on large language models and set up monthly sync meetings. The project budget was set at $5 million.",
        "expected_entities": ["Alice", "Bob", "Microsoft", "Google", "Seattle", "AI collaboration", "large language models"],
        "expected_relationships": [
            ("Alice", "works_at", "Microsoft"),
            ("Bob", "works_at", "Google"), 
            ("Alice", "met_with", "Bob"),
            ("Microsoft", "collaborates_with", "Google")
        ]
    },
    {
        "name": "product_launch", 
        "content": "Sarah announced that DataCorp will launch CloudSync 2.0 on March 1st. The new version includes real-time collaboration, end-to-end encryption, and supports up to 10TB storage. The pricing starts at $99/month for teams.",
        "expected_entities": ["Sarah", "DataCorp", "CloudSync 2.0", "real-time collaboration", "encryption", "10TB storage"],
        "expected_relationships": [
            ("Sarah", "works_at", "DataCorp"),
            ("DataCorp", "launches", "CloudSync 2.0"),
            ("CloudSync 2.0", "includes", "real-time collaboration")
        ]
    },
    {
        "name": "research_findings",
        "content": "Dr. Chen's team at MIT discovered a new quantum algorithm that reduces computation time by 60%. The algorithm, named QuantumBoost, can solve NP-complete problems faster than classical computers. IBM and Intel have expressed interest in licensing the technology.",
        "expected_entities": ["Dr. Chen", "MIT", "quantum algorithm", "QuantumBoost", "IBM", "Intel", "NP-complete problems"],
        "expected_relationships": [
            ("Dr. Chen", "works_at", "MIT"),
            ("Dr. Chen", "discovered", "quantum algorithm"),
            ("quantum algorithm", "named", "QuantumBoost"),
            ("IBM", "interested_in", "QuantumBoost")
        ]
    }
]

# Hyperparameters to test
TEMPERATURE_VALUES = [0.0, 0.1, 0.2, 0.3, 0.5, 0.7]
TOP_P_VALUES = [0.7, 0.8, 0.9]  # Test only if temperature shows improvement
ITERATIONS_PER_CONFIG = 3  # Multiple runs to measure consistency

# JSON Schema for structured extraction
entity_extraction_schema = {
    "type": "object",
    "properties": {
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "type": {"type": "string"}
                },
                "required": ["name", "type"],
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
                    "target": {"type": "string"}
                },
                "required": ["source", "relation", "target"],
                "additionalProperties": False
            }
        },
        "extraction_quality": {
            "type": "object",
            "properties": {
                "completeness": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0}
            },
            "required": ["completeness", "confidence"],
            "additionalProperties": False
        }
    },
    "required": ["entities", "relationships", "extraction_quality"],
    "additionalProperties": False
}

def calculate_f1_score(extracted: List[str], expected: List[str]) -> Tuple[float, float, float]:
    """Calculate precision, recall, and F1 score."""
    extracted_set = set(str(e).lower() for e in extracted)
    expected_set = set(str(e).lower() for e in expected)
    
    if not extracted_set:
        return 0.0, 0.0, 0.0
        
    true_positives = len(extracted_set & expected_set)
    precision = true_positives / len(extracted_set) if extracted_set else 0
    recall = true_positives / len(expected_set) if expected_set else 0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    
    return precision, recall, f1

def calculate_relationship_f1(extracted_rels: List[Tuple], expected_rels: List[Tuple]) -> Tuple[float, float, float]:
    """Calculate F1 for relationships with fuzzy matching."""
    if not extracted_rels:
        return 0.0, 0.0, 0.0
    
    matches = 0
    for extracted_rel in extracted_rels:
        for expected_rel in expected_rels:
            # Fuzzy matching: check if entities are contained in each other
            source_match = (extracted_rel[0].lower() in expected_rel[0].lower() or 
                          expected_rel[0].lower() in extracted_rel[0].lower())
            target_match = (extracted_rel[2].lower() in expected_rel[2].lower() or 
                          expected_rel[2].lower() in extracted_rel[2].lower())
            
            if source_match and target_match:
                matches += 1
                break
    
    precision = matches / len(extracted_rels) if extracted_rels else 0
    recall = matches / len(expected_rels) if expected_rels else 0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    
    return precision, recall, f1

async def test_single_configuration(client: Cerebras, episode: Dict, temperature: float, top_p: float = 0.8) -> Dict[str, Any]:
    """Test a single hyperparameter configuration."""
    start_time = time.time()
    
    try:
        response = client.chat.completions.create(
            model="qwen-3-coder-480b",
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert at extracting entities and relationships from text. Extract all meaningful entities and their relationships. Provide confidence scores for your extractions."
                },
                {
                    "role": "user",
                    "content": f"Extract entities and relationships from this text. Rate the completeness and confidence of your extraction:\n\n{episode['content']}"
                }
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
            top_p=top_p,
            max_completion_tokens=2000
        )
        
        end_time = time.time()
        result = json.loads(response.choices[0].message.content)
        
        # Extract data for analysis
        entities = [entity["name"] for entity in result["entities"]]
        relationships = [(rel["source"], rel["relation"], rel["target"]) for rel in result["relationships"]]
        
        # Calculate metrics
        entity_precision, entity_recall, entity_f1 = calculate_f1_score(entities, episode['expected_entities'])
        rel_precision, rel_recall, rel_f1 = calculate_relationship_f1(relationships, episode['expected_relationships'])
        
        # Calculate simple confidence metrics
        avg_entity_confidence = 1.0  # Simplified since confidence is optional
        avg_rel_confidence = 1.0     # Simplified since confidence is optional
        
        extraction_quality = result.get("extraction_quality", {})
        reported_completeness = extraction_quality.get("completeness", 0.0)
        reported_confidence = extraction_quality.get("confidence", 0.0)
        
        return {
            "success": True,
            "response_time": end_time - start_time,
            "entities": entities,
            "relationships": relationships,
            "entity_f1": entity_f1,
            "entity_precision": entity_precision,
            "entity_recall": entity_recall,
            "rel_f1": rel_f1,
            "rel_precision": rel_precision,
            "rel_recall": rel_recall,
            "avg_entity_confidence": avg_entity_confidence,
            "avg_rel_confidence": avg_rel_confidence,
            "reported_completeness": reported_completeness,
            "reported_confidence": reported_confidence,
            "raw_response": result
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "response_time": time.time() - start_time
        }

async def run_hyperparameter_sweep():
    """Run comprehensive hyperparameter sweep."""
    print("=" * 80)
    print("🔬 CEREBRAS HYPERPARAMETER SWEEP")
    print("=" * 80)
    print(f"Model: qwen-3-coder-480b")
    print(f"Temperature values: {TEMPERATURE_VALUES}")
    print(f"Iterations per config: {ITERATIONS_PER_CONFIG}")
    print(f"Start: {datetime.now().isoformat()}\n")
    
    # Initialize client
    api_key = os.environ.get("CEREBRAS_API_KEY")
    if not api_key:
        print("❌ CEREBRAS_API_KEY not set")
        return
    
    client = Cerebras(api_key=api_key)
    print("✓ Cerebras client initialized")
    
    all_results = []
    
    # Test each temperature value
    for temp_idx, temperature in enumerate(TEMPERATURE_VALUES, 1):
        print(f"\n{'='*60}")
        print(f"🌡️  Testing Temperature: {temperature} ({temp_idx}/{len(TEMPERATURE_VALUES)})")
        print(f"{'='*60}")
        
        temp_results = {
            "temperature": temperature,
            "top_p": 0.8,
            "episodes": []
        }
        
        for episode in TEST_EPISODES:
            print(f"\n📄 Episode: {episode['name']}")
            episode_results = []
            
            # Run multiple iterations for consistency measurement
            for iteration in range(ITERATIONS_PER_CONFIG):
                print(f"  Iteration {iteration + 1}/{ITERATIONS_PER_CONFIG}: ", end="", flush=True)
                
                result = await test_single_configuration(client, episode, temperature)
                episode_results.append(result)
                
                if result["success"]:
                    print(f"✓ F1: {result['entity_f1']:.2%} entities, {result['rel_f1']:.2%} relationships")
                else:
                    print(f"✗ Error: {result['error']}")
                
                # Rate limiting - wait between requests
                if iteration < ITERATIONS_PER_CONFIG - 1:
                    await asyncio.sleep(4)  # 4 second delay
            
            # Calculate statistics for this episode
            successful_results = [r for r in episode_results if r["success"]]
            
            if successful_results:
                entity_f1_scores = [r["entity_f1"] for r in successful_results]
                rel_f1_scores = [r["rel_f1"] for r in successful_results]
                response_times = [r["response_time"] for r in successful_results]
                
                episode_stats = {
                    "episode_name": episode["name"],
                    "success_rate": len(successful_results) / len(episode_results),
                    "entity_f1_mean": statistics.mean(entity_f1_scores),
                    "entity_f1_stdev": statistics.stdev(entity_f1_scores) if len(entity_f1_scores) > 1 else 0,
                    "rel_f1_mean": statistics.mean(rel_f1_scores),
                    "rel_f1_stdev": statistics.stdev(rel_f1_scores) if len(rel_f1_scores) > 1 else 0,
                    "avg_response_time": statistics.mean(response_times),
                    "all_results": episode_results
                }
                
                print(f"  📊 Entity F1: {episode_stats['entity_f1_mean']:.2%} ±{episode_stats['entity_f1_stdev']:.3f}")
                print(f"  📊 Relationship F1: {episode_stats['rel_f1_mean']:.2%} ±{episode_stats['rel_f1_stdev']:.3f}")
                print(f"  ⏱️  Avg response time: {episode_stats['avg_response_time']:.2f}s")
            else:
                episode_stats = {
                    "episode_name": episode["name"],
                    "success_rate": 0,
                    "error": "All iterations failed"
                }
            
            temp_results["episodes"].append(episode_stats)
        
        all_results.append(temp_results)
        
        # Brief pause between temperature tests
        if temp_idx < len(TEMPERATURE_VALUES):
            print(f"\n⏳ Pausing 10 seconds before next temperature...")
            await asyncio.sleep(10)
    
    # Analyze overall results
    print(f"\n{'='*80}")
    print("📊 HYPERPARAMETER SWEEP ANALYSIS")
    print(f"{'='*80}")
    
    best_temp = None
    best_overall_f1 = 0
    
    print(f"\n🏆 Results Summary:")
    print(f"{'Temp':<6} {'Entity F1':<12} {'Rel F1':<12} {'Overall F1':<12} {'Success':<8} {'Consistency'}")
    print("-" * 70)
    
    for temp_result in all_results:
        temp = temp_result["temperature"]
        
        # Calculate overall metrics across all episodes
        entity_f1_scores = []
        rel_f1_scores = []
        success_rates = []
        entity_stdevs = []
        
        for episode_result in temp_result["episodes"]:
            if episode_result.get("entity_f1_mean") is not None:
                entity_f1_scores.append(episode_result["entity_f1_mean"])
                rel_f1_scores.append(episode_result["rel_f1_mean"])
                success_rates.append(episode_result["success_rate"])
                entity_stdevs.append(episode_result["entity_f1_stdev"])
        
        if entity_f1_scores:
            overall_entity_f1 = statistics.mean(entity_f1_scores)
            overall_rel_f1 = statistics.mean(rel_f1_scores)
            overall_f1 = (overall_entity_f1 + overall_rel_f1) / 2
            overall_success = statistics.mean(success_rates)
            consistency = 1 - statistics.mean(entity_stdevs)  # Lower stdev = higher consistency
            
            print(f"{temp:<6.1f} {overall_entity_f1:<12.2%} {overall_rel_f1:<12.2%} {overall_f1:<12.2%} {overall_success:<8.2%} {consistency:<.3f}")
            
            if overall_f1 > best_overall_f1:
                best_overall_f1 = overall_f1
                best_temp = temp
        else:
            print(f"{temp:<6.1f} {'FAILED':<12} {'FAILED':<12} {'FAILED':<12} {'0.00%':<8} {'N/A'}")
    
    if best_temp is not None:
        print(f"\n🎯 Optimal Temperature: {best_temp}")
        print(f"🎯 Best Overall F1 Score: {best_overall_f1:.2%}")
    else:
        print(f"\n❌ No successful configurations found")
        print(f"🔍 All temperature values resulted in failures")
    
    # Save detailed results
    final_results = {
        "timestamp": datetime.now().isoformat(),
        "model": "qwen-3-coder-480b",
        "hyperparameter_sweep": "temperature",
        "temperature_values": TEMPERATURE_VALUES,
        "iterations_per_config": ITERATIONS_PER_CONFIG,
        "best_temperature": best_temp,
        "best_overall_f1": best_overall_f1,
        "detailed_results": all_results
    }
    
    filename = f"cerebras_temperature_sweep_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, "w") as f:
        json.dump(final_results, f, indent=2)
    
    print(f"\n💾 Detailed results saved to {filename}")
    
    # Recommendations
    print(f"\n💡 Recommendations:")
    if best_temp is None:
        print("  • Schema validation errors occurred - need to fix JSON schema")
        print("  • Consider using simpler schema without strict validation")
        print("  • Test with JSON mode instead of structured outputs")
    elif best_temp == 0.0:
        print("  • Current temperature (0.0) is optimal for deterministic extraction")
        print("  • Consider keeping temperature at 0.0 for production")
    elif best_temp <= 0.2:
        print(f"  • Temperature {best_temp} provides good balance of quality and consistency")
        print(f"  • Update production LLMConfig to use temperature={best_temp}")
    else:
        print(f"  • Temperature {best_temp} shows best F1 but may have higher variance")
        print(f"  • Consider testing top_p values with temperature {best_temp}")
        print(f"  • Monitor consistency in production")
    
    print("=" * 80)
    
    return best_temp, best_overall_f1

if __name__ == "__main__":
    asyncio.run(run_hyperparameter_sweep())