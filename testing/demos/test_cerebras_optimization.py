#!/usr/bin/env python3
"""
Cerebras Advanced Structured Output Optimization
Tests advanced schema features: $ref/$defs, union types, Pydantic integration, nested structures
"""

import asyncio
import json
import os
import time
import statistics
from typing import Dict, List, Any, Tuple, Union, Optional
from datetime import datetime
from cerebras.cloud.sdk import Cerebras
from pydantic import BaseModel, Field
from enum import Enum

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

# Pydantic Models for Type Safety
class EntityType(str, Enum):
    PERSON = "PERSON"
    ORGANIZATION = "ORGANIZATION"
    LOCATION = "LOCATION"
    TECHNOLOGY = "TECHNOLOGY"
    PRODUCT = "PRODUCT"
    EVENT = "EVENT"
    CONCEPT = "CONCEPT"

class RelationType(str, Enum):
    WORKS_AT = "WORKS_AT"
    COLLABORATES_WITH = "COLLABORATES_WITH"
    DEVELOPS = "DEVELOPS"
    ANNOUNCES = "ANNOUNCES"
    DISCOVERS = "DISCOVERS"
    INCLUDES = "INCLUDES"
    INTERESTED_IN = "INTERESTED_IN"
    MET_WITH = "MET_WITH"
    LAUNCHES = "LAUNCHES"
    NAMED = "NAMED"

class ConfidenceLevel(str, Enum):
    HIGH = "HIGH"      # 0.9+
    MEDIUM = "MEDIUM"  # 0.7-0.89
    LOW = "LOW"        # 0.5-0.69

class Entity(BaseModel):
    name: str = Field(..., description="Name of the entity")
    type: EntityType = Field(..., description="Type classification of the entity")
    description: str = Field(..., description="Brief description of the entity")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score for entity extraction")

class Relationship(BaseModel):
    source: str = Field(..., description="Source entity name")
    relation: RelationType = Field(..., description="Type of relationship")
    target: str = Field(..., description="Target entity name")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score for relationship")
    confidence_level: ConfidenceLevel = Field(..., description="Categorical confidence level")
    context: Optional[str] = Field(None, description="Supporting context from text")

class ExtractionResult(BaseModel):
    entities: List[Entity] = Field(..., description="List of extracted entities")
    relationships: List[Relationship] = Field(..., description="List of extracted relationships")

# Advanced schema with $ref and $defs
def get_advanced_schema_with_refs():
    """Schema using $ref and $defs for reusable components."""
    return {
        "type": "object",
        "properties": {
            "entities": {
                "type": "array",
                "items": {"$ref": "#/$defs/entity"}
            },
            "relationships": {
                "type": "array",
                "items": {"$ref": "#/$defs/relationship"}
            }
        },
        "required": ["entities", "relationships"],
        "additionalProperties": False,
        "$defs": {
            "entity": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "type": {
                        "type": "string",
                        "enum": ["PERSON", "ORGANIZATION", "LOCATION", "TECHNOLOGY", "PRODUCT", "EVENT", "CONCEPT"]
                    },
                    "description": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0}
                },
                "required": ["name", "type", "description", "confidence"],
                "additionalProperties": False
            },
            "relationship": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "relation": {
                        "type": "string",
                        "enum": ["WORKS_AT", "COLLABORATES_WITH", "DEVELOPS", "ANNOUNCES", "DISCOVERS", "INCLUDES", "INTERESTED_IN", "MET_WITH", "LAUNCHES", "NAMED"]
                    },
                    "target": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "confidence_level": {
                        "type": "string",
                        "enum": ["HIGH", "MEDIUM", "LOW"]
                    },
                    "context": {"type": "string"}
                },
                "required": ["source", "relation", "target", "confidence", "confidence_level"],
                "additionalProperties": False
            }
        }
    }

# Union types schema with anyOf
def get_union_types_schema():
    """Schema with union types for flexible entity definitions."""
    return {
        "type": "object",
        "properties": {
            "entities": {
                "type": "array",
                "items": {
                    "anyOf": [
                        {"$ref": "#/$defs/person_entity"},
                        {"$ref": "#/$defs/organization_entity"},
                        {"$ref": "#/$defs/technical_entity"}
                    ]
                }
            },
            "relationships": {
                "type": "array",
                "items": {"$ref": "#/$defs/relationship"}
            }
        },
        "required": ["entities", "relationships"],
        "additionalProperties": False,
        "$defs": {
            "person_entity": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "type": {"type": "string", "enum": ["PERSON"]},
                    "title": {"type": "string"},
                    "organization": {"type": "string"},
                    "confidence": {"type": "number"}
                },
                "required": ["name", "type", "confidence"],
                "additionalProperties": False
            },
            "organization_entity": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "type": {"type": "string", "enum": ["ORGANIZATION"]},
                    "industry": {"type": "string"},
                    "size": {"type": "string"},
                    "confidence": {"type": "number"}
                },
                "required": ["name", "type", "confidence"],
                "additionalProperties": False
            },
            "technical_entity": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "type": {"type": "string", "enum": ["TECHNOLOGY", "PRODUCT", "CONCEPT"]},
                    "category": {"type": "string"},
                    "description": {"type": "string"},
                    "confidence": {"type": "number"}
                },
                "required": ["name", "type", "confidence"],
                "additionalProperties": False
            },
            "relationship": {
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

async def test_schema_variant(client: Cerebras, episode: Dict, variant: str) -> Dict[str, Any]:
    """Test different schema optimization variants."""
    start = time.time()
    
    # Enhanced system prompt for all variants
    system_prompt = """You are an advanced entity and relationship extraction system with strict adherence to schema validation.

Extract entities and relationships with maximum precision. For each entity, determine:
- Exact name (no abbreviations unless in source)
- Precise type classification using provided enums
- Descriptive context
- Confidence score based on text clarity

For relationships:
- Use standard relation types from the enum
- Assign confidence levels: HIGH (0.9+), MEDIUM (0.7-0.89), LOW (0.5-0.69)
- Include supporting context where available

Focus on accuracy over quantity. Only extract what is clearly supported by the text."""

    user_prompt = f"""Analyze this text and extract all entities and relationships with high precision:

TEXT: {episode['content']}

Requirements:
1. Extract ALL meaningful entities with proper type classification
2. Identify ALL relationships with appropriate confidence scoring
3. Ensure all confidence scores reflect actual text support
4. Use enum values exactly as specified in schema"""

    try:
        if variant == "pydantic":
            # Use Pydantic model schema
            schema = ExtractionResult.model_json_schema()
        elif variant == "refs_defs":
            # Use $ref and $defs schema
            schema = get_advanced_schema_with_refs()
        elif variant == "union_types":
            # Use union types with anyOf
            schema = get_union_types_schema()
        elif variant == "strict_false":
            # Use basic schema with strict=False
            schema = ExtractionResult.model_json_schema()
        else:  # baseline
            # Basic schema
            schema = {
                "type": "object",
                "properties": {
                    "entities": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "type": {"type": "string"},
                                "description": {"type": "string"},
                                "confidence": {"type": "number"}
                            },
                            "required": ["name", "type", "description", "confidence"],
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
        
        # Configure strict mode
        strict_mode = variant != "strict_false"
        
        response = client.chat.completions.create(
            model="qwen-3-coder-480b",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "extraction_result",
                    "strict": strict_mode,
                    "schema": schema
                }
            },
            temperature=0.7,
            top_p=0.8,
            max_completion_tokens=3000
        )
        
        end_time = time.time()
        result = json.loads(response.choices[0].message.content)
        
        # Extract entities and relationships for analysis
        entities = []
        relationships = []
        
        if variant == "union_types":
            # Handle union type structure
            entities = [entity["name"] for entity in result.get("entities", [])]
            relationships = [(rel["source"], rel["relation"], rel["target"]) for rel in result.get("relationships", [])]
        else:
            # Standard structure
            entities = [entity["name"] for entity in result.get("entities", [])]
            relationships = [(rel["source"], rel["relation"], rel["target"]) for rel in result.get("relationships", [])]
        
        # Calculate metrics
        entity_precision, entity_recall, entity_f1 = calculate_precision_recall(entities, episode['expected_entities'])
        rel_precision, rel_recall, rel_f1 = calculate_relationship_f1(relationships, episode['expected_relationships'])
        
        # Calculate confidence scores
        rel_confidences = []
        for rel in result.get("relationships", []):
            if isinstance(rel.get("confidence"), (int, float)):
                rel_confidences.append(rel["confidence"])
        
        avg_confidence = statistics.mean(rel_confidences) if rel_confidences else 0.0
        
        # Schema complexity metrics
        schema_size = len(json.dumps(schema))
        has_enums = "enum" in json.dumps(schema)
        has_refs = "$ref" in json.dumps(schema)
        has_unions = "anyOf" in json.dumps(schema)
        
        return {
            "success": True,
            "variant": variant,
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
            "schema_features": {
                "size": schema_size,
                "has_enums": has_enums,
                "has_refs": has_refs,
                "has_unions": has_unions,
                "strict_mode": strict_mode
            },
            "raw_result": result
        }
        
    except Exception as e:
        return {
            "success": False,
            "variant": variant,
            "error": str(e),
            "response_time": time.time() - start
        }

async def main():
    """Test advanced schema optimization techniques."""
    print("=" * 80)
    print("🔧 CEREBRAS STRUCTURED OUTPUT OPTIMIZATION")
    print("=" * 80)
    print(f"Model: qwen-3-coder-480b")
    print(f"Configuration: temperature=0.7, top_p=0.8 (Qwen optimal)")
    print(f"Schema variants: baseline, pydantic, refs_defs, union_types, strict_false")
    print(f"Start: {datetime.now().isoformat()}\n")
    
    api_key = os.environ.get("CEREBRAS_API_KEY")
    if not api_key:
        print("❌ CEREBRAS_API_KEY not set")
        return
    
    client = Cerebras(api_key=api_key)
    print("✓ Cerebras client initialized")
    
    schema_variants = ["baseline", "pydantic", "refs_defs", "union_types", "strict_false"]
    all_results = {}
    
    for variant in schema_variants:
        print(f"\n{'='*60}")
        print(f"🔬 Testing Schema Variant: {variant}")
        print(f"{'='*60}")
        
        variant_results = []
        
        for episode in TEST_EPISODES:
            print(f"\n📄 Episode: {episode['name']}")
            result = await test_schema_variant(client, episode, variant)
            variant_results.append(result)
            
            if result["success"]:
                print(f"  ✓ E:{result['num_entities']} R:{result['num_relationships']} F1:{result['entity_f1']:.1%}/{result['rel_f1']:.1%} ({result['response_time']:.1f}s)")
                print(f"  📊 Confidence: {result['avg_confidence']:.3f}")
                
                # Show schema features
                features = result['schema_features']
                feature_str = []
                if features['has_enums']: feature_str.append("enums")
                if features['has_refs']: feature_str.append("$refs")
                if features['has_unions']: feature_str.append("unions")
                if features['strict_mode']: feature_str.append("strict")
                
                print(f"  🔧 Schema: {features['size']} bytes, {', '.join(feature_str)}")
            else:
                print(f"  ✗ Error: {result['error'][:50]}...")
            
            # Rate limiting
            await asyncio.sleep(4)
        
        all_results[variant] = variant_results
        
        # Brief pause between variants
        if variant != schema_variants[-1]:
            print(f"\n⏳ Pausing 10 seconds before next variant...")
            await asyncio.sleep(10)
    
    # Final Comparison
    print(f"\n{'='*80}")
    print("🏆 SCHEMA OPTIMIZATION COMPARISON")
    print(f"{'='*80}")
    
    comparison_data = []
    
    for variant, variant_results in all_results.items():
        successful = [r for r in variant_results if r["success"]]
        if successful:
            avg_entity_f1 = statistics.mean([r["entity_f1"] for r in successful])
            avg_rel_f1 = statistics.mean([r["rel_f1"] for r in successful])
            total_f1 = (avg_entity_f1 + avg_rel_f1) / 2
            avg_confidence = statistics.mean([r["avg_confidence"] for r in successful])
            avg_time = statistics.mean([r["response_time"] for r in successful])
            success_rate = len(successful) / len(variant_results)
            avg_schema_size = statistics.mean([r["schema_features"]["size"] for r in successful])
            
            comparison_data.append({
                "variant": variant,
                "entity_f1": avg_entity_f1,
                "rel_f1": avg_rel_f1,
                "total_f1": total_f1,
                "avg_confidence": avg_confidence,
                "avg_time": avg_time,
                "success_rate": success_rate,
                "schema_size": avg_schema_size
            })
    
    # Display comparison table
    print(f"\n{'Variant':<12} {'Entity F1':<10} {'Rel F1':<10} {'Total F1':<10} {'Success':<8} {'Confidence':<11} {'Time':<6} {'Schema'}")
    print("-" * 85)
    
    best_variant = None
    best_f1 = 0
    
    for config in comparison_data:
        print(f"{config['variant']:<12} "
              f"{config['entity_f1']:<10.2%} "
              f"{config['rel_f1']:<10.2%} "
              f"{config['total_f1']:<10.2%} "
              f"{config['success_rate']:<8.2%} "
              f"{config['avg_confidence']:<11.3f} "
              f"{config['avg_time']:<6.2f}s "
              f"{config['schema_size']:<.0f}b")
        
        if config['total_f1'] > best_f1:
            best_f1 = config['total_f1']
            best_variant = config['variant']
    
    # Analysis and Recommendations
    print(f"\n🎯 Optimization Analysis:")
    if best_variant:
        print(f"  🏆 Best schema variant: {best_variant}")
        print(f"  📈 Best total F1 score: {best_f1:.2%}")
        
        # Find improvement over baseline
        baseline_f1 = next((c['total_f1'] for c in comparison_data if c['variant'] == 'baseline'), 0)
        if best_variant != 'baseline' and baseline_f1 > 0:
            improvement = best_f1 - baseline_f1
            print(f"  📊 Improvement over baseline: {improvement:.2%}")
        
        print(f"\n💡 Schema Optimization Recommendations:")
        if best_variant == "pydantic":
            print("  ✅ Use Pydantic models for type safety and validation")
            print("  ✅ Automatic schema generation reduces errors")
            print("  ✅ Better integration with Python applications")
        elif best_variant == "refs_defs":
            print("  ✅ Use $ref and $defs for reusable schema components")
            print("  ✅ Reduces schema size and improves maintainability")
            print("  ✅ Better organization of complex structures")
        elif best_variant == "union_types":
            print("  ✅ Use union types (anyOf) for flexible entity definitions")
            print("  ✅ Allows specialized entity structures by type")
            print("  ✅ More precise validation per entity category")
        elif best_variant == "strict_false":
            print("  ✅ Use strict=false for more flexibility")
            print("  ✅ Allows additional fields not in schema")
            print("  ✅ Better for exploratory extraction")
        else:
            print("  ✅ Current baseline schema is optimal")
            print("  ℹ️  Advanced features didn't improve performance")
    
    # Save detailed results
    final_results = {
        "timestamp": datetime.now().isoformat(),
        "model": "qwen-3-coder-480b",
        "test_type": "schema_optimization",
        "configuration": {"temperature": 0.7, "top_p": 0.8},
        "best_variant": best_variant,
        "best_f1_score": best_f1,
        "comparison_summary": comparison_data,
        "detailed_results": all_results
    }
    
    filename = f"cerebras_optimization_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, "w") as f:
        json.dump(final_results, f, indent=2, default=str)
    
    print(f"\n💾 Detailed results saved to {filename}")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())