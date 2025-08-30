"""
Multi-model consensus testing for Cerebras extraction.
Tests ensemble approaches and consensus strategies for improved accuracy.
"""

import json
import asyncio
from typing import Dict, List, Tuple, Any, Optional
from datetime import datetime
from dataclasses import dataclass, field
import os
import numpy as np
from cerebras.cloud.sdk import Cerebras
from collections import Counter, defaultdict

# Configuration
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY")
MODEL = "qwen-3-coder-480b"

@dataclass
class ConsensusConfig:
    """Configuration for consensus strategy"""
    name: str
    num_samples: int = 3
    temperature_range: Tuple[float, float] = (0.3, 0.7)
    top_p_range: Tuple[float, float] = (0.7, 0.9)
    voting_threshold: float = 0.5
    aggregation_method: str = "majority"  # majority, weighted, union, intersection
    confidence_weighting: bool = False

@dataclass
class ExtractionResult:
    """Single extraction result with metadata"""
    entities: List[Dict]
    relationships: List[Dict]
    temperature: float
    top_p: float
    response_time: float
    confidence: float = 1.0
    prompt_variant: str = "standard"

class ConsensusStrategies:
    """Different consensus strategies for multi-model outputs"""
    
    @staticmethod
    def majority_voting(results: List[ExtractionResult], threshold: float = 0.5) -> Dict:
        """Simple majority voting on entities and relationships"""
        entity_counts = Counter()
        relationship_counts = Counter()
        
        for result in results:
            for entity in result.entities:
                key = (entity['name'], entity['type'])
                entity_counts[key] += 1
            
            for rel in result.relationships:
                key = (rel['source'], rel['target'], rel['type'])
                relationship_counts[key] += 1
        
        min_votes = int(len(results) * threshold)
        
        consensus_entities = [
            {"name": name, "type": etype}
            for (name, etype), count in entity_counts.items()
            if count >= min_votes
        ]
        
        consensus_relationships = [
            {"source": src, "target": tgt, "type": rtype}
            for (src, tgt, rtype), count in relationship_counts.items()
            if count >= min_votes
        ]
        
        return {
            "entities": consensus_entities,
            "relationships": consensus_relationships,
            "consensus_method": "majority_voting",
            "threshold": threshold
        }
    
    @staticmethod
    def weighted_consensus(results: List[ExtractionResult]) -> Dict:
        """Weighted voting based on confidence scores"""
        entity_weights = defaultdict(float)
        relationship_weights = defaultdict(float)
        
        for result in results:
            weight = result.confidence
            
            for entity in result.entities:
                key = (entity['name'], entity['type'])
                entity_weights[key] += weight
            
            for rel in result.relationships:
                key = (rel['source'], rel['target'], rel['type'])
                relationship_weights[key] += weight
        
        # Normalize weights
        max_weight = len(results)
        threshold = max_weight * 0.5
        
        consensus_entities = [
            {"name": name, "type": etype}
            for (name, etype), weight in entity_weights.items()
            if weight >= threshold
        ]
        
        consensus_relationships = [
            {"source": src, "target": tgt, "type": rtype}
            for (src, tgt, rtype), weight in relationship_weights.items()
            if weight >= threshold
        ]
        
        return {
            "entities": consensus_entities,
            "relationships": consensus_relationships,
            "consensus_method": "weighted",
            "avg_confidence": np.mean([r.confidence for r in results])
        }
    
    @staticmethod
    def union_consensus(results: List[ExtractionResult]) -> Dict:
        """Union of all extractions (high recall)"""
        all_entities = set()
        all_relationships = set()
        
        for result in results:
            for entity in result.entities:
                all_entities.add((entity['name'], entity['type']))
            
            for rel in result.relationships:
                all_relationships.add((rel['source'], rel['target'], rel['type']))
        
        return {
            "entities": [
                {"name": name, "type": etype}
                for name, etype in all_entities
            ],
            "relationships": [
                {"source": src, "target": tgt, "type": rtype}
                for src, tgt, rtype in all_relationships
            ],
            "consensus_method": "union"
        }
    
    @staticmethod
    def intersection_consensus(results: List[ExtractionResult]) -> Dict:
        """Intersection of all extractions (high precision)"""
        if not results:
            return {"entities": [], "relationships": [], "consensus_method": "intersection"}
        
        # Initialize with first result
        common_entities = {(e['name'], e['type']) for e in results[0].entities}
        common_relationships = {(r['source'], r['target'], r['type']) for r in results[0].relationships}
        
        # Find intersection with remaining results
        for result in results[1:]:
            result_entities = {(e['name'], e['type']) for e in result.entities}
            result_relationships = {(r['source'], r['target'], r['type']) for r in result.relationships}
            
            common_entities &= result_entities
            common_relationships &= result_relationships
        
        return {
            "entities": [
                {"name": name, "type": etype}
                for name, etype in common_entities
            ],
            "relationships": [
                {"source": src, "target": tgt, "type": rtype}
                for src, tgt, rtype in common_relationships
            ],
            "consensus_method": "intersection"
        }
    
    @staticmethod
    def ranked_consensus(results: List[ExtractionResult]) -> Dict:
        """Rank-based consensus with confidence scores"""
        entity_scores = defaultdict(list)
        relationship_scores = defaultdict(list)
        
        for result in results:
            # Score based on temperature (lower = more confident)
            temp_score = 1.0 - (result.temperature / 1.0)
            
            for entity in result.entities:
                key = (entity['name'], entity['type'])
                entity_scores[key].append(temp_score * result.confidence)
            
            for rel in result.relationships:
                key = (rel['source'], rel['target'], rel['type'])
                relationship_scores[key].append(temp_score * result.confidence)
        
        # Calculate average scores and rank
        ranked_entities = []
        for key, scores in entity_scores.items():
            avg_score = np.mean(scores)
            occurrence_rate = len(scores) / len(results)
            final_score = avg_score * occurrence_rate
            
            if final_score > 0.5:  # Threshold
                ranked_entities.append({
                    "name": key[0],
                    "type": key[1],
                    "confidence": final_score
                })
        
        ranked_relationships = []
        for key, scores in relationship_scores.items():
            avg_score = np.mean(scores)
            occurrence_rate = len(scores) / len(results)
            final_score = avg_score * occurrence_rate
            
            if final_score > 0.4:  # Lower threshold for relationships
                ranked_relationships.append({
                    "source": key[0],
                    "target": key[1],
                    "type": key[2],
                    "confidence": final_score
                })
        
        # Sort by confidence
        ranked_entities.sort(key=lambda x: x.get('confidence', 0), reverse=True)
        ranked_relationships.sort(key=lambda x: x.get('confidence', 0), reverse=True)
        
        return {
            "entities": ranked_entities,
            "relationships": ranked_relationships,
            "consensus_method": "ranked"
        }

class PromptVariants:
    """Different prompt variants for diversity"""
    
    @staticmethod
    def get_variants() -> List[Tuple[str, str]]:
        """Get different prompt variants for ensemble diversity"""
        return [
            ("standard", "Extract all entities and relationships from the text."),
            ("detailed", """Carefully analyze the text and extract:
1. All named entities (people, organizations, locations, systems)
2. All relationships between these entities
Be thorough and include implicit relationships."""),
            ("structured", """Task: Entity and Relationship Extraction
Instructions:
- Identify all entities with their types
- Extract all relationships with source, target, and type
- Include both explicit and implicit relationships"""),
            ("concise", "Find entities and their relationships."),
            ("analytical", """Perform deep analysis to extract:
- Entities: Focus on proper nouns and named concepts
- Relationships: Look for verbs and prepositions indicating connections
Consider context and implied connections.""")
        ]

class MultiModelConsensus:
    """Main framework for multi-model consensus testing"""
    
    def __init__(self):
        self.client = Cerebras(api_key=CEREBRAS_API_KEY)
        self.prompt_variants = PromptVariants.get_variants()
        
    def get_schema(self, strict: bool = False) -> Dict:
        """Get extraction schema"""
        return {
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
                            "target": {"type": "string"},
                            "type": {"type": "string"}
                        },
                        "required": ["source", "target", "type"],
                        "additionalProperties": False
                    }
                }
            },
            "required": ["entities", "relationships"],
            "additionalProperties": False,
            "strict": strict
        }
    
    async def single_extraction(
        self,
        text: str,
        temperature: float,
        top_p: float,
        prompt_variant: Tuple[str, str]
    ) -> Optional[ExtractionResult]:
        """Perform a single extraction with given parameters"""
        try:
            variant_name, prompt = prompt_variant
            
            start_time = datetime.now()
            response = self.client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": text}
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "extraction",
                        "strict": False,
                        "schema": self.get_schema(strict=False)
                    }
                },
                temperature=temperature,
                top_p=top_p,
                max_completion_tokens=2000
            )
            
            result = json.loads(response.choices[0].message.content)
            response_time = (datetime.now() - start_time).total_seconds()
            
            # Calculate confidence based on temperature
            confidence = 1.0 - (temperature * 0.5)  # Lower temperature = higher confidence
            
            return ExtractionResult(
                entities=result.get('entities', []),
                relationships=result.get('relationships', []),
                temperature=temperature,
                top_p=top_p,
                response_time=response_time,
                confidence=confidence,
                prompt_variant=variant_name
            )
            
        except Exception as e:
            print(f"Extraction failed: {e}")
            return None
    
    async def ensemble_extraction(
        self,
        text: str,
        config: ConsensusConfig
    ) -> Tuple[List[ExtractionResult], Dict]:
        """Perform ensemble extraction with multiple configurations"""
        tasks = []
        
        # Generate diverse parameter combinations
        for i in range(config.num_samples):
            # Vary temperature
            temp_range = config.temperature_range[1] - config.temperature_range[0]
            temperature = config.temperature_range[0] + (temp_range * i / max(1, config.num_samples - 1))
            
            # Vary top_p
            top_p_range = config.top_p_range[1] - config.top_p_range[0]
            top_p = config.top_p_range[0] + (top_p_range * i / max(1, config.num_samples - 1))
            
            # Vary prompt variant
            prompt_variant = self.prompt_variants[i % len(self.prompt_variants)]
            
            tasks.append(self.single_extraction(text, temperature, top_p, prompt_variant))
        
        # Execute all extractions in parallel
        results = await asyncio.gather(*tasks)
        
        # Filter out failed extractions
        valid_results = [r for r in results if r is not None]
        
        if not valid_results:
            return [], {"error": "All extractions failed"}
        
        # Apply consensus strategy
        if config.aggregation_method == "majority":
            consensus = ConsensusStrategies.majority_voting(valid_results, config.voting_threshold)
        elif config.aggregation_method == "weighted":
            consensus = ConsensusStrategies.weighted_consensus(valid_results)
        elif config.aggregation_method == "union":
            consensus = ConsensusStrategies.union_consensus(valid_results)
        elif config.aggregation_method == "intersection":
            consensus = ConsensusStrategies.intersection_consensus(valid_results)
        elif config.aggregation_method == "ranked":
            consensus = ConsensusStrategies.ranked_consensus(valid_results)
        else:
            consensus = ConsensusStrategies.majority_voting(valid_results)
        
        return valid_results, consensus
    
    def analyze_variance(self, results: List[ExtractionResult]) -> Dict:
        """Analyze variance across multiple extractions"""
        if not results:
            return {"error": "No results to analyze"}
        
        # Entity variance
        all_entities = []
        for r in results:
            all_entities.extend([(e['name'], e['type']) for e in r.entities])
        
        entity_counter = Counter(all_entities)
        unique_entities = len(set(all_entities))
        total_entities = len(all_entities)
        
        # Relationship variance
        all_relationships = []
        for r in results:
            all_relationships.extend([(rel['source'], rel['target'], rel['type']) for rel in r.relationships])
        
        rel_counter = Counter(all_relationships)
        unique_relationships = len(set(all_relationships))
        total_relationships = len(all_relationships)
        
        # Agreement metrics
        entity_agreement = []
        for entity, count in entity_counter.items():
            agreement_rate = count / len(results)
            entity_agreement.append(agreement_rate)
        
        rel_agreement = []
        for rel, count in rel_counter.items():
            agreement_rate = count / len(results)
            rel_agreement.append(agreement_rate)
        
        return {
            "num_samples": len(results),
            "entity_variance": {
                "unique": unique_entities,
                "total": total_entities,
                "avg_per_sample": total_entities / len(results),
                "avg_agreement": np.mean(entity_agreement) if entity_agreement else 0,
                "std_agreement": np.std(entity_agreement) if entity_agreement else 0
            },
            "relationship_variance": {
                "unique": unique_relationships,
                "total": total_relationships,
                "avg_per_sample": total_relationships / len(results),
                "avg_agreement": np.mean(rel_agreement) if rel_agreement else 0,
                "std_agreement": np.std(rel_agreement) if rel_agreement else 0
            },
            "timing": {
                "avg_response_time": np.mean([r.response_time for r in results]),
                "std_response_time": np.std([r.response_time for r in results])
            }
        }
    
    async def test_consensus_strategies(self, test_text: str):
        """Test all consensus strategies on the same text"""
        print("Testing Multi-Model Consensus Strategies")
        print("=" * 80)
        print(f"Test text: {test_text[:100]}...")
        print()
        
        strategies = [
            ConsensusConfig(name="Majority Voting", num_samples=5, aggregation_method="majority"),
            ConsensusConfig(name="Weighted Consensus", num_samples=5, aggregation_method="weighted", confidence_weighting=True),
            ConsensusConfig(name="Union (High Recall)", num_samples=3, aggregation_method="union"),
            ConsensusConfig(name="Intersection (High Precision)", num_samples=3, aggregation_method="intersection"),
            ConsensusConfig(name="Ranked Consensus", num_samples=5, aggregation_method="ranked"),
            ConsensusConfig(name="Diverse Ensemble", num_samples=7, temperature_range=(0.0, 0.9), aggregation_method="majority"),
            ConsensusConfig(name="Conservative", num_samples=3, temperature_range=(0.0, 0.3), aggregation_method="intersection"),
            ConsensusConfig(name="Aggressive", num_samples=5, temperature_range=(0.5, 0.9), aggregation_method="union")
        ]
        
        results_summary = []
        
        for config in strategies:
            print(f"\nTesting: {config.name}")
            print("-" * 40)
            
            # Run ensemble extraction
            results, consensus = await self.ensemble_extraction(test_text, config)
            
            if results:
                # Analyze variance
                variance = self.analyze_variance(results)
                
                print(f"  Samples: {len(results)}")
                print(f"  Entities found: {len(consensus.get('entities', []))}")
                print(f"  Relationships found: {len(consensus.get('relationships', []))}")
                print(f"  Avg agreement (entities): {variance['entity_variance']['avg_agreement']:.2f}")
                print(f"  Avg agreement (relationships): {variance['relationship_variance']['avg_agreement']:.2f}")
                print(f"  Avg response time: {variance['timing']['avg_response_time']:.2f}s")
                
                results_summary.append({
                    "strategy": config.name,
                    "config": config,
                    "consensus": consensus,
                    "variance": variance,
                    "num_entities": len(consensus.get('entities', [])),
                    "num_relationships": len(consensus.get('relationships', []))
                })
            else:
                print("  ERROR: All extractions failed")
        
        # Generate comparison report
        self.generate_comparison_report(results_summary)
        
        return results_summary
    
    def generate_comparison_report(self, results: List[Dict]):
        """Generate comparison report for different strategies"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = f"consensus_strategies_comparison_{timestamp}.json"
        
        # Find best strategies by different metrics
        most_entities = max(results, key=lambda x: x['num_entities']) if results else None
        most_relationships = max(results, key=lambda x: x['num_relationships']) if results else None
        best_agreement = max(results, key=lambda x: x['variance']['entity_variance']['avg_agreement']) if results else None
        
        report = {
            "timestamp": timestamp,
            "model": MODEL,
            "summary": {
                "strategies_tested": len(results),
                "most_entities": most_entities['strategy'] if most_entities else None,
                "most_relationships": most_relationships['strategy'] if most_relationships else None,
                "best_agreement": best_agreement['strategy'] if best_agreement else None
            },
            "detailed_results": results,
            "recommendations": self.generate_consensus_recommendations(results)
        }
        
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        print("\n" + "=" * 80)
        print("CONSENSUS STRATEGY COMPARISON")
        print("=" * 80)
        if most_entities:
            print(f"Most Entities: {most_entities['strategy']} ({most_entities['num_entities']})")
        if most_relationships:
            print(f"Most Relationships: {most_relationships['strategy']} ({most_relationships['num_relationships']})")
        if best_agreement:
            print(f"Best Agreement: {best_agreement['strategy']} ({best_agreement['variance']['entity_variance']['avg_agreement']:.2f})")
        print(f"\nReport saved to: {report_file}")
    
    def generate_consensus_recommendations(self, results: List[Dict]) -> List[str]:
        """Generate recommendations based on consensus testing"""
        recommendations = []
        
        if not results:
            return ["No successful consensus strategies to analyze"]
        
        # Analyze trade-offs
        union_result = next((r for r in results if "Union" in r['strategy']), None)
        intersection_result = next((r for r in results if "Intersection" in r['strategy']), None)
        
        if union_result and intersection_result:
            if union_result['num_entities'] > intersection_result['num_entities'] * 1.5:
                recommendations.append("Consider union strategy for exploratory analysis (high recall)")
            if intersection_result['variance']['entity_variance']['avg_agreement'] > 0.8:
                recommendations.append("Use intersection strategy for high-confidence extractions")
        
        # Check ensemble benefits
        diverse_result = next((r for r in results if "Diverse" in r['strategy']), None)
        if diverse_result and diverse_result['variance']['entity_variance']['avg_agreement'] > 0.7:
            recommendations.append("Diverse ensemble with majority voting provides good balance")
        
        # Check if conservative approach works
        conservative_result = next((r for r in results if "Conservative" in r['strategy']), None)
        if conservative_result and conservative_result['variance']['entity_variance']['avg_agreement'] > 0.85:
            recommendations.append("Conservative approach (low temperature + intersection) for production")
        
        return recommendations


async def main():
    """Main execution function"""
    consensus_tester = MultiModelConsensus()
    
    # Test text with various entity types and relationships
    test_text = """
    Dr. Sarah Chen, CEO of QuantumTech Industries, announced a breakthrough in quantum computing 
    at the International Tech Summit in San Francisco. The new QPU-500 processor, developed in 
    collaboration with MIT's Quantum Lab led by Professor John Williams, achieves 500 qubits 
    with 99.9% fidelity. Google and IBM have expressed interest in licensing the technology. 
    The development was funded by a $50 million grant from the NSF.
    """
    
    # Run consensus strategy testing
    results = await consensus_tester.test_consensus_strategies(test_text)
    
    print("\nConsensus testing completed!")
    return results


if __name__ == "__main__":
    asyncio.run(main())