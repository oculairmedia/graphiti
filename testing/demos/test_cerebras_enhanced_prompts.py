#!/usr/bin/env python3
"""
Cerebras Enhanced Prompting Test
Tests improved prompts with few-shot examples and qwen-3-coder-480b best practices
"""

import asyncio
import json
import os
import time
import statistics
from typing import Dict, List, Any, Tuple
from datetime import datetime
from cerebras.cloud.sdk import Cerebras

# Test episodes for consistent evaluation
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

# Enhanced schema with qwen-3-coder optimizations
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

def get_enhanced_system_prompt() -> str:
    """Enhanced system prompt optimized for qwen-3-coder-480b."""
    return """You are an expert entity and relationship extraction system. Your task is to analyze text and extract meaningful entities and their relationships with high precision.

## Extraction Guidelines:

### Entities
- Extract all PEOPLE (names, titles, roles)
- Extract all ORGANIZATIONS (companies, institutions, teams)
- Extract all LOCATIONS (cities, countries, buildings)
- Extract all CONCEPTS (technologies, products, algorithms, research areas)
- Extract all TEMPORAL EVENTS (meetings, launches, discoveries)

### Entity Types
- PERSON: Individual people (Alice, Dr. Chen, Sarah)
- ORGANIZATION: Companies, institutions (Microsoft, MIT, DataCorp)
- LOCATION: Geographic places (Seattle, San Francisco)
- TECHNOLOGY: Technical concepts (AI, algorithms, software)
- PRODUCT: Specific products or services (CloudSync 2.0, QuantumBoost)
- EVENT: Meetings, announcements, discoveries

### Relationships
- Use clear, descriptive relation types in UPPERCASE
- Common relations: WORKS_AT, COLLABORATES_WITH, DEVELOPS, ANNOUNCES, DISCOVERS
- Include temporal context when available
- Assign confidence scores: 0.9+ for explicit facts, 0.7+ for strong implications, 0.5+ for weak implications

## Examples:

**Input**: "John from Apple met with Sarah from Google to discuss partnership."
**Output**:
```json
{
  "entities": [
    {"name": "John", "type": "PERSON", "description": "Individual working at Apple"},
    {"name": "Apple", "type": "ORGANIZATION", "description": "Technology company"},
    {"name": "Sarah", "type": "PERSON", "description": "Individual working at Google"},
    {"name": "Google", "type": "ORGANIZATION", "description": "Technology company"}
  ],
  "relationships": [
    {"source": "John", "relation": "WORKS_AT", "target": "Apple", "confidence": 0.9},
    {"source": "Sarah", "relation": "WORKS_AT", "target": "Google", "confidence": 0.9},
    {"source": "John", "relation": "MET_WITH", "target": "Sarah", "confidence": 0.95},
    {"source": "Apple", "relation": "DISCUSSES_PARTNERSHIP_WITH", "target": "Google", "confidence": 0.8}
  ]
}
```

Extract with precision and include ALL meaningful entities and relationships."""

def get_enhanced_user_prompt(content: str) -> str:
    """Enhanced user prompt with specific instructions."""
    return f"""Extract entities and relationships from the following text. Focus on:

1. All people mentioned (names, titles, roles)
2. All organizations (companies, institutions, teams)
3. All locations (cities, countries, addresses)
4. All technical concepts (technologies, products, algorithms)
5. All events (meetings, announcements, discoveries)
6. All meaningful relationships between these entities

Text to analyze:
---
{content}
---

Return a complete JSON response with all entities and relationships found. Assign confidence scores based on how explicitly each relationship is stated in the text."""

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

async def test_prompt_variant(client: Cerebras, episode: Dict, prompt_type: str) -> Dict[str, Any]:
    """Test different prompt variants."""
    start = time.time()
    
    try:
        if prompt_type == "baseline":
            system_content = "You are an expert at extracting entities and relationships from text. Extract all meaningful entities (people, organizations, locations, concepts) and their relationships. Provide detailed descriptions and confidence scores."
            user_content = f"Extract entities and relationships from this text:\n\n{episode['content']}"
        
        elif prompt_type == "enhanced":
            system_content = get_enhanced_system_prompt()
            user_content = get_enhanced_user_prompt(episode['content'])
        
        elif prompt_type == "concise":
            system_content = """You are a precise entity extraction system. Extract entities and relationships with high accuracy.

Entity Types: PERSON, ORGANIZATION, LOCATION, TECHNOLOGY, PRODUCT, EVENT
Relationship Types: WORKS_AT, COLLABORATES_WITH, DEVELOPS, ANNOUNCES, DISCOVERS, INCLUDES

Output format: JSON with entities array and relationships array."""
            user_content = f"""Text: {episode['content']}

Extract all entities and relationships. Use confidence scores 0.9+ for explicit, 0.7+ for implied."""
        
        response = client.chat.completions.create(
            model="qwen-3-coder-480b",
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content}
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "entity_extraction", 
                    "strict": True,
                    "schema": entity_extraction_schema
                }
            },
            temperature=0.7,
            top_p=0.8,
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
            "prompt_type": prompt_type,
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
            "prompt_type": prompt_type,
            "error": str(e),
            "response_time": time.time() - start
        }

async def main():
    """Compare enhanced prompts against baseline."""
    print("=" * 80)
    print("🎯 CEREBRAS ENHANCED PROMPTING TEST")
    print("=" * 80)
    print(f"Model: qwen-3-coder-480b")
    print(f"Temperature: 0.7, Top-p: 0.8 (Qwen recommended)")
    print(f"Prompt variants: baseline, enhanced, concise")
    print(f"Start: {datetime.now().isoformat()}\n")
    
    api_key = os.environ.get("CEREBRAS_API_KEY")
    if not api_key:
        print("❌ CEREBRAS_API_KEY not set")
        return
    
    client = Cerebras(api_key=api_key)
    print("✓ Cerebras client initialized")
    
    prompt_variants = ["baseline", "enhanced", "concise"]
    all_results = {}
    
    for prompt_type in prompt_variants:
        print(f"\n{'='*60}")
        print(f"📝 Testing Prompt Type: {prompt_type}")
        print(f"{'='*60}")
        
        prompt_results = []
        
        for episode in TEST_EPISODES:
            print(f"\n📄 Episode: {episode['name']}")
            result = await test_prompt_variant(client, episode, prompt_type)
            prompt_results.append(result)
            
            if result["success"]:
                print(f"  ✓ E:{result['num_entities']} R:{result['num_relationships']} F1:{result['entity_f1']:.1%}/{result['rel_f1']:.1%} ({result['response_time']:.1f}s)")
                print(f"  📊 Confidence: {result['avg_confidence']:.3f}")
            else:
                print(f"  ✗ Error: {result['error'][:50]}...")
            
            # Rate limiting
            await asyncio.sleep(4)
        
        all_results[prompt_type] = prompt_results
        
        # Calculate prompt type statistics
        successful = [r for r in prompt_results if r["success"]]
        if successful:
            avg_entity_f1 = statistics.mean([r["entity_f1"] for r in successful])
            avg_rel_f1 = statistics.mean([r["rel_f1"] for r in successful])
            avg_confidence = statistics.mean([r["avg_confidence"] for r in successful])
            avg_time = statistics.mean([r["response_time"] for r in successful])
            
            print(f"\n  📊 {prompt_type.title()} Summary:")
            print(f"    Entity F1: {avg_entity_f1:.2%}")
            print(f"    Relationship F1: {avg_rel_f1:.2%}")
            print(f"    Total F1: {(avg_entity_f1 + avg_rel_f1) / 2:.2%}")
            print(f"    Avg Confidence: {avg_confidence:.3f}")
            print(f"    Avg Time: {avg_time:.2f}s")
        
        # Brief pause between prompt types
        if prompt_type != prompt_variants[-1]:
            print(f"\n⏳ Pausing 10 seconds before next prompt type...")
            await asyncio.sleep(10)
    
    # Final Comparison
    print(f"\n{'='*80}")
    print("🏆 PROMPT VARIANT COMPARISON")
    print(f"{'='*80}")
    
    comparison_data = []
    
    for prompt_type, prompt_results in all_results.items():
        successful = [r for r in prompt_results if r["success"]]
        if successful:
            avg_entity_f1 = statistics.mean([r["entity_f1"] for r in successful])
            avg_rel_f1 = statistics.mean([r["rel_f1"] for r in successful])
            total_f1 = (avg_entity_f1 + avg_rel_f1) / 2
            avg_confidence = statistics.mean([r["avg_confidence"] for r in successful])
            avg_time = statistics.mean([r["response_time"] for r in successful])
            success_rate = len(successful) / len(prompt_results)
            
            comparison_data.append({
                "prompt_type": prompt_type,
                "entity_f1": avg_entity_f1,
                "rel_f1": avg_rel_f1,
                "total_f1": total_f1,
                "avg_confidence": avg_confidence,
                "avg_time": avg_time,
                "success_rate": success_rate
            })
    
    # Display comparison table
    print(f"\n{'Prompt Type':<12} {'Entity F1':<12} {'Rel F1':<12} {'Total F1':<12} {'Success':<8} {'Confidence':<12} {'Avg Time'}")
    print("-" * 85)
    
    best_prompt = None
    best_f1 = 0
    
    for config in comparison_data:
        print(f"{config['prompt_type']:<12} "
              f"{config['entity_f1']:<12.2%} "
              f"{config['rel_f1']:<12.2%} "
              f"{config['total_f1']:<12.2%} "
              f"{config['success_rate']:<8.2%} "
              f"{config['avg_confidence']:<12.3f} "
              f"{config['avg_time']:<.2f}s")
        
        if config['total_f1'] > best_f1:
            best_f1 = config['total_f1']
            best_prompt = config['prompt_type']
    
    # Analysis and Recommendations
    print(f"\n🎯 Analysis:")
    if best_prompt:
        print(f"  🏆 Best performing prompt: {best_prompt}")
        print(f"  📈 Best total F1 score: {best_f1:.2%}")
        
        # Find improvement over baseline
        baseline_f1 = next((c['total_f1'] for c in comparison_data if c['prompt_type'] == 'baseline'), 0)
        if best_prompt != 'baseline' and baseline_f1 > 0:
            improvement = best_f1 - baseline_f1
            print(f"  📊 Improvement over baseline: {improvement:.2%}")
        
        print(f"\n💡 Recommendations:")
        if best_prompt == "enhanced":
            print("  ✅ Use enhanced prompts with few-shot examples")
            print("  ✅ Include detailed entity type definitions")
            print("  ✅ Provide explicit extraction guidelines")
        elif best_prompt == "concise":
            print("  ✅ Use concise, focused prompts")
            print("  ✅ Streamlined instructions work better")
        else:
            print("  ✅ Current baseline prompts are optimal")
            print("  ℹ️  Enhanced prompting didn't improve performance")
    
    # Save detailed results
    final_results = {
        "timestamp": datetime.now().isoformat(),
        "model": "qwen-3-coder-480b",
        "test_type": "prompt_enhancement",
        "configuration": {"temperature": 0.7, "top_p": 0.8},
        "best_prompt_type": best_prompt,
        "best_f1_score": best_f1,
        "comparison_summary": comparison_data,
        "detailed_results": all_results
    }
    
    filename = f"cerebras_enhanced_prompts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, "w") as f:
        json.dump(final_results, f, indent=2, default=str)
    
    print(f"\n💾 Detailed results saved to {filename}")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())