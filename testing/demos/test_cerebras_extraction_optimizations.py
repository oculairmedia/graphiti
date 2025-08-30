"""
Comprehensive test framework for Cerebras extraction optimizations.
Tests relationship inference, entity filtering, and advanced extraction strategies.
"""

import json
import asyncio
from typing import Dict, List, Tuple, Any
from datetime import datetime
from dataclasses import dataclass, asdict
import os
from cerebras.cloud.sdk import Cerebras

# Configuration
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY")
MODEL = "qwen-3-coder-480b"
TEMPERATURE = 0.7
TOP_P = 0.8

@dataclass
class TestScenario:
    """Test scenario with input text and expected outputs"""
    name: str
    input_text: str
    expected_entities: List[Dict]
    expected_relationships: List[Dict]
    context: str = ""
    domain: str = "general"

@dataclass
class OptimizationStrategy:
    """Optimization strategy configuration"""
    name: str
    description: str
    prompt_modifier: callable
    schema_modifier: callable = None
    post_processor: callable = None

class RelationshipInferenceRules:
    """Rules for inferring implicit relationships from context"""
    
    EMPLOYMENT_INDICATORS = {
        "announced": "WORKS_AT",
        "said": "AFFILIATED_WITH",
        "CEO": "LEADS",
        "founder": "FOUNDED",
        "employee": "WORKS_AT",
        "director": "DIRECTS",
        "manager": "MANAGES",
        "spokesperson": "REPRESENTS"
    }
    
    LOCATION_INDICATORS = {
        "based in": "LOCATED_IN",
        "headquartered": "HEADQUARTERED_IN",
        "office in": "HAS_OFFICE_IN",
        "from": "ORIGINATES_FROM"
    }
    
    TEMPORAL_INDICATORS = {
        "previously": "FORMERLY",
        "will": "FUTURE",
        "since": "STARTED",
        "until": "ENDED"
    }
    
    @classmethod
    def infer_relationships(cls, text: str, entities: List[Dict]) -> List[Dict]:
        """Infer implicit relationships from text and entities"""
        inferred = []
        
        # Check for employment relationships
        for entity in entities:
            if entity['type'] == 'PERSON':
                for org in entities:
                    if org['type'] == 'ORGANIZATION':
                        # Check if person is mentioned with role near organization
                        for indicator, rel_type in cls.EMPLOYMENT_INDICATORS.items():
                            if indicator in text.lower():
                                context = text[max(0, text.lower().find(entity['name'].lower())-50):
                                             min(len(text), text.lower().find(entity['name'].lower())+50)]
                                if org['name'] in context:
                                    inferred.append({
                                        'source': entity['name'],
                                        'target': org['name'],
                                        'type': rel_type,
                                        'confidence': 0.7,
                                        'inferred': True
                                    })
        
        return inferred

class EntityFilter:
    """Filter to reduce over-extraction of non-entities"""
    
    BLACKLIST_PATTERNS = [
        r'^\d+$',  # Pure numbers
        r'^\$[\d,]+$',  # Currency amounts
        r'^\d{4}-\d{2}-\d{2}$',  # Dates
        r'^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)$',  # Days
        r'^(January|February|March|April|May|June|July|August|September|October|November|December)$'  # Months
    ]
    
    MIN_ENTITY_LENGTH = 2
    MAX_ENTITY_LENGTH = 100
    
    @classmethod
    def filter_entities(cls, entities: List[Dict]) -> List[Dict]:
        """Filter out likely non-entities"""
        import re
        filtered = []
        
        for entity in entities:
            name = entity.get('name', '')
            
            # Check length constraints
            if len(name) < cls.MIN_ENTITY_LENGTH or len(name) > cls.MAX_ENTITY_LENGTH:
                continue
            
            # Check blacklist patterns
            blacklisted = False
            for pattern in cls.BLACKLIST_PATTERNS:
                if re.match(pattern, name, re.IGNORECASE):
                    blacklisted = True
                    break
            
            if not blacklisted:
                filtered.append(entity)
        
        return filtered

class TestFramework:
    """Main test framework for extraction optimizations"""
    
    def __init__(self):
        self.client = Cerebras(api_key=CEREBRAS_API_KEY)
        self.results = []
        
    def get_base_schema(self) -> Dict:
        """Get base extraction schema"""
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
            "strict": False  # Best performing configuration
        }
    
    def get_test_scenarios(self) -> List[TestScenario]:
        """Get comprehensive test scenarios"""
        return [
            TestScenario(
                name="implicit_employment",
                input_text="Sarah Chen, the CEO of TechCorp, announced record profits. She said the company will expand to Europe next year.",
                expected_entities=[
                    {"name": "Sarah Chen", "type": "PERSON"},
                    {"name": "TechCorp", "type": "ORGANIZATION"},
                    {"name": "Europe", "type": "LOCATION"}
                ],
                expected_relationships=[
                    {"source": "Sarah Chen", "target": "TechCorp", "type": "CEO_OF"},
                    {"source": "TechCorp", "target": "Europe", "type": "EXPANSION_TO"}
                ],
                domain="business"
            ),
            TestScenario(
                name="research_collaboration",
                input_text="Dr. Alice Wang from MIT collaborated with Professor Bob Zhang at Stanford on quantum computing research funded by NSF.",
                expected_entities=[
                    {"name": "Dr. Alice Wang", "type": "PERSON"},
                    {"name": "MIT", "type": "ORGANIZATION"},
                    {"name": "Professor Bob Zhang", "type": "PERSON"},
                    {"name": "Stanford", "type": "ORGANIZATION"},
                    {"name": "NSF", "type": "ORGANIZATION"}
                ],
                expected_relationships=[
                    {"source": "Dr. Alice Wang", "target": "MIT", "type": "WORKS_AT"},
                    {"source": "Professor Bob Zhang", "target": "Stanford", "type": "WORKS_AT"},
                    {"source": "Dr. Alice Wang", "target": "Professor Bob Zhang", "type": "COLLABORATES_WITH"},
                    {"source": "NSF", "target": "Dr. Alice Wang", "type": "FUNDS"}
                ],
                domain="academic"
            ),
            TestScenario(
                name="temporal_relationships",
                input_text="John Smith previously worked at Google. He joined Microsoft in 2020 and became CTO in 2022.",
                expected_entities=[
                    {"name": "John Smith", "type": "PERSON"},
                    {"name": "Google", "type": "ORGANIZATION"},
                    {"name": "Microsoft", "type": "ORGANIZATION"}
                ],
                expected_relationships=[
                    {"source": "John Smith", "target": "Google", "type": "FORMERLY_WORKED_AT"},
                    {"source": "John Smith", "target": "Microsoft", "type": "WORKS_AT"},
                    {"source": "John Smith", "target": "Microsoft", "type": "IS_CTO_OF"}
                ],
                domain="career"
            ),
            TestScenario(
                name="complex_technical",
                input_text="The GraphRAG system developed by Anthropic uses LLaMA-3 embeddings. It integrates with FalkorDB for storage and Cosmograph for visualization.",
                expected_entities=[
                    {"name": "GraphRAG", "type": "SYSTEM"},
                    {"name": "Anthropic", "type": "ORGANIZATION"},
                    {"name": "LLaMA-3", "type": "MODEL"},
                    {"name": "FalkorDB", "type": "DATABASE"},
                    {"name": "Cosmograph", "type": "LIBRARY"}
                ],
                expected_relationships=[
                    {"source": "GraphRAG", "target": "Anthropic", "type": "DEVELOPED_BY"},
                    {"source": "GraphRAG", "target": "LLaMA-3", "type": "USES"},
                    {"source": "GraphRAG", "target": "FalkorDB", "type": "INTEGRATES_WITH"},
                    {"source": "GraphRAG", "target": "Cosmograph", "type": "INTEGRATES_WITH"}
                ],
                domain="technical"
            )
        ]
    
    def get_optimization_strategies(self) -> List[OptimizationStrategy]:
        """Get all optimization strategies to test"""
        
        def relationship_first_prompt(base_prompt: str) -> str:
            """Modify prompt to extract relationships first"""
            return f"""
{base_prompt}

EXTRACTION ORDER:
1. First, identify all relationships between entities in the text
2. Then, extract the entities involved in those relationships
3. This approach ensures we don't miss implicit relationships

Focus on relationship extraction accuracy over entity extraction.
"""
        
        def entity_filtering_prompt(base_prompt: str) -> str:
            """Add entity filtering rules to prompt"""
            return f"""
{base_prompt}

ENTITY FILTERING RULES:
- Do NOT extract: dates, times, currency amounts, pure numbers
- Do NOT extract: generic terms like "company", "person", "system"
- DO extract: Named entities (people, organizations, places, products)
- Minimum entity length: 2 characters
- Maximum entity length: 100 characters
"""
        
        def domain_specific_prompt(base_prompt: str, domain: str = "technical") -> str:
            """Add domain-specific examples"""
            domain_examples = {
                "technical": """
Example extraction for technical domain:
Input: "PyTorch uses CUDA for GPU acceleration"
Entities: [{"name": "PyTorch", "type": "FRAMEWORK"}, {"name": "CUDA", "type": "TECHNOLOGY"}]
Relationships: [{"source": "PyTorch", "target": "CUDA", "type": "USES"}]
""",
                "business": """
Example extraction for business domain:
Input: "Apple acquired Beats for $3 billion"
Entities: [{"name": "Apple", "type": "COMPANY"}, {"name": "Beats", "type": "COMPANY"}]
Relationships: [{"source": "Apple", "target": "Beats", "type": "ACQUIRED"}]
"""
            }
            return f"{base_prompt}\n\nDOMAIN: {domain}\n{domain_examples.get(domain, '')}"
        
        def confidence_scoring_prompt(base_prompt: str) -> str:
            """Add confidence scoring to extractions"""
            return f"""
{base_prompt}

Add confidence scores (0.0-1.0) to each extraction:
- 1.0: Explicitly stated in text
- 0.8-0.9: Strongly implied
- 0.6-0.7: Reasonably inferred
- Below 0.6: Uncertain (do not extract)
"""
        
        return [
            OptimizationStrategy(
                name="baseline",
                description="Standard extraction without optimizations",
                prompt_modifier=lambda p: p
            ),
            OptimizationStrategy(
                name="relationship_first",
                description="Extract relationships before entities",
                prompt_modifier=relationship_first_prompt
            ),
            OptimizationStrategy(
                name="entity_filtering",
                description="Apply strict entity filtering rules",
                prompt_modifier=entity_filtering_prompt,
                post_processor=EntityFilter.filter_entities
            ),
            OptimizationStrategy(
                name="inference_rules",
                description="Apply relationship inference rules",
                prompt_modifier=lambda p: p,
                post_processor=RelationshipInferenceRules.infer_relationships
            ),
            OptimizationStrategy(
                name="domain_specific",
                description="Use domain-specific prompts and examples",
                prompt_modifier=lambda p: domain_specific_prompt(p, "technical")
            ),
            OptimizationStrategy(
                name="confidence_scoring",
                description="Add confidence scores to filter uncertain extractions",
                prompt_modifier=confidence_scoring_prompt
            ),
            OptimizationStrategy(
                name="combined_optimizations",
                description="Combine all effective optimizations",
                prompt_modifier=lambda p: confidence_scoring_prompt(
                    entity_filtering_prompt(
                        relationship_first_prompt(p)
                    )
                ),
                post_processor=lambda e, r, t: (
                    EntityFilter.filter_entities(e),
                    RelationshipInferenceRules.infer_relationships(t, e) + r
                )
            )
        ]
    
    def calculate_metrics(self, predicted: Dict, expected: Dict) -> Dict:
        """Calculate precision, recall, and F1 scores with flexible matching"""
        def normalize_entity(item):
            """Normalize entity for comparison"""
            if isinstance(item, dict):
                name = item.get('name', '').strip().lower()
                entity_type = item.get('type', '').strip().upper()
                return (name, entity_type)
            return (str(item).strip().lower(), '')
        
        def normalize_relationship(item):
            """Normalize relationship for comparison"""
            if isinstance(item, dict):
                source = item.get('source', '').strip().lower()
                target = item.get('target', '').strip().lower() 
                rel_type = item.get('type', '').strip().upper()
                return (source, target, rel_type)
            elif isinstance(item, (list, tuple)) and len(item) >= 3:
                return (str(item[0]).strip().lower(), str(item[2]).strip().lower(), str(item[1]).strip().upper())
            return tuple(str(x).strip().lower() for x in item) if item else ()
        
        # Entity metrics with normalization
        pred_entities = set()
        for entity in predicted.get('entities', []):
            normalized = normalize_entity(entity)
            if normalized[0]:  # Only add if name is not empty
                pred_entities.add(normalized)
        
        exp_entities = set()
        for entity in expected.get('entities', []):
            normalized = normalize_entity(entity)
            if normalized[0]:  # Only add if name is not empty
                exp_entities.add(normalized)
        
        entity_tp = len(pred_entities & exp_entities)
        entity_fp = len(pred_entities - exp_entities)
        entity_fn = len(exp_entities - pred_entities)
        
        # Relationship metrics with normalization
        pred_rels = set()
        for rel in predicted.get('relationships', []):
            normalized = normalize_relationship(rel)
            if len(normalized) >= 3 and normalized[0] and normalized[1]:  # Only add valid relationships
                pred_rels.add(normalized)
        
        exp_rels = set()
        for rel in expected.get('relationships', []):
            normalized = normalize_relationship(rel)
            if len(normalized) >= 3 and normalized[0] and normalized[1]:  # Only add valid relationships
                exp_rels.add(normalized)
        
        rel_tp = len(pred_rels & exp_rels)
        rel_fp = len(pred_rels - exp_rels)
        rel_fn = len(exp_rels - pred_rels)
        
        # Calculate scores
        def calc_scores(tp, fp, fn):
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
            return {"precision": precision, "recall": recall, "f1": f1}
        
        entity_scores = calc_scores(entity_tp, entity_fp, entity_fn)
        rel_scores = calc_scores(rel_tp, rel_fp, rel_fn)
        
        return {
            "entities": entity_scores,
            "relationships": rel_scores,
            "overall_f1": (entity_scores['f1'] + rel_scores['f1']) / 2
        }
    
    async def test_strategy(self, strategy: OptimizationStrategy, scenario: TestScenario) -> Dict:
        """Test a single optimization strategy on a scenario"""
        try:
            # Prepare prompt
            base_prompt = "Extract entities and relationships from the following text."
            prompt = strategy.prompt_modifier(base_prompt)
            
            # Prepare schema
            schema = self.get_base_schema()
            if strategy.schema_modifier:
                schema = strategy.schema_modifier(schema)
            
            # Make API call
            start_time = datetime.now()
            response = self.client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": scenario.input_text}
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "extraction",
                        "strict": False,  # Use strict=False for better performance
                        "schema": schema
                    }
                },
                temperature=TEMPERATURE,
                top_p=TOP_P,
                max_completion_tokens=2000
            )
            
            extraction = json.loads(response.choices[0].message.content)
            response_time = (datetime.now() - start_time).total_seconds()
            
            # Apply post-processing if defined
            if strategy.post_processor:
                if strategy.name == "combined_optimizations":
                    entities, relationships = strategy.post_processor(
                        extraction['entities'],
                        extraction['relationships'],
                        scenario.input_text
                    )
                    extraction = {"entities": entities, "relationships": relationships}
                elif strategy.name == "inference_rules":
                    # Infer additional relationships
                    inferred_rels = strategy.post_processor(scenario.input_text, extraction['entities'])
                    extraction['relationships'].extend(inferred_rels)
                else:
                    extraction['entities'] = strategy.post_processor(extraction['entities'])
            
            # Calculate metrics
            expected = {
                "entities": scenario.expected_entities,
                "relationships": scenario.expected_relationships
            }
            metrics = self.calculate_metrics(extraction, expected)
            
            return {
                "strategy": strategy.name,
                "scenario": scenario.name,
                "success": True,
                "extraction": extraction,
                "metrics": metrics,
                "response_time": response_time
            }
            
        except Exception as e:
            return {
                "strategy": strategy.name,
                "scenario": scenario.name,
                "success": False,
                "error": str(e),
                "metrics": {"overall_f1": 0}
            }
    
    async def run_comprehensive_test(self):
        """Run all strategies on all scenarios"""
        strategies = self.get_optimization_strategies()
        scenarios = self.get_test_scenarios()
        
        print(f"Testing {len(strategies)} strategies on {len(scenarios)} scenarios...")
        print("=" * 80)
        
        all_results = []
        strategy_scores = {}
        
        for strategy in strategies:
            print(f"\nTesting strategy: {strategy.name}")
            print(f"Description: {strategy.description}")
            print("-" * 40)
            
            strategy_results = []
            for scenario in scenarios:
                result = await self.test_strategy(strategy, scenario)
                strategy_results.append(result)
                all_results.append(result)
                
                if result['success']:
                    print(f"  {scenario.name}: F1={result['metrics']['overall_f1']:.3f}")
                else:
                    print(f"  {scenario.name}: ERROR - {result.get('error', 'Unknown')}")
            
            # Calculate average scores for strategy
            successful = [r for r in strategy_results if r['success']]
            if successful:
                avg_f1 = sum(r['metrics']['overall_f1'] for r in successful) / len(successful)
                avg_entity_f1 = sum(r['metrics']['entities']['f1'] for r in successful) / len(successful)
                avg_rel_f1 = sum(r['metrics']['relationships']['f1'] for r in successful) / len(successful)
                
                strategy_scores[strategy.name] = {
                    "avg_f1": avg_f1,
                    "avg_entity_f1": avg_entity_f1,
                    "avg_rel_f1": avg_rel_f1,
                    "success_rate": len(successful) / len(strategy_results)
                }
                
                print(f"\n  Average F1: {avg_f1:.3f}")
                print(f"  Entity F1: {avg_entity_f1:.3f}")
                print(f"  Relationship F1: {avg_rel_f1:.3f}")
                print(f"  Success Rate: {strategy_scores[strategy.name]['success_rate']:.1%}")
        
        # Generate report
        self.generate_report(strategy_scores, all_results)
        
        return strategy_scores, all_results
    
    def generate_report(self, strategy_scores: Dict, all_results: List[Dict]):
        """Generate comprehensive test report"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = f"cerebras_optimization_report_{timestamp}.json"
        
        # Find best strategy
        best_strategy = max(strategy_scores.items(), key=lambda x: x[1]['avg_f1'])
        
        # Calculate improvements over baseline
        baseline_f1 = strategy_scores.get('baseline', {}).get('avg_f1', 0)
        improvements = {}
        for name, scores in strategy_scores.items():
            if name != 'baseline' and baseline_f1 > 0:
                improvement = ((scores['avg_f1'] - baseline_f1) / baseline_f1) * 100
                improvements[name] = improvement
        
        report = {
            "timestamp": timestamp,
            "model": MODEL,
            "configuration": {
                "temperature": TEMPERATURE,
                "top_p": TOP_P
            },
            "summary": {
                "best_strategy": best_strategy[0],
                "best_f1": best_strategy[1]['avg_f1'],
                "baseline_f1": baseline_f1,
                "improvements": improvements
            },
            "strategy_scores": strategy_scores,
            "detailed_results": all_results,
            "recommendations": self.generate_recommendations(strategy_scores, improvements)
        }
        
        # Save report
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        print("\n" + "=" * 80)
        print("FINAL REPORT")
        print("=" * 80)
        print(f"Best Strategy: {best_strategy[0]}")
        print(f"Best F1 Score: {best_strategy[1]['avg_f1']:.3f}")
        print(f"Improvement over baseline: {improvements.get(best_strategy[0], 0):.1f}%")
        print(f"\nTop Improvements:")
        for name, improvement in sorted(improvements.items(), key=lambda x: x[1], reverse=True)[:3]:
            print(f"  {name}: +{improvement:.1f}%")
        print(f"\nReport saved to: {report_file}")
    
    def generate_recommendations(self, strategy_scores: Dict, improvements: Dict) -> List[str]:
        """Generate actionable recommendations based on results"""
        recommendations = []
        
        # Check if relationship-first helps
        if improvements.get('relationship_first', 0) > 5:
            recommendations.append("Implement relationship-first extraction in production")
        
        # Check if entity filtering helps
        if improvements.get('entity_filtering', 0) > 5:
            recommendations.append("Add entity filtering rules to reduce over-extraction")
        
        # Check if inference rules help
        if improvements.get('inference_rules', 0) > 10:
            recommendations.append("Implement relationship inference rules for implicit relationships")
        
        # Check if combined approach is best
        if 'combined_optimizations' in improvements and improvements['combined_optimizations'] > 15:
            recommendations.append("Deploy combined optimization strategy for maximum improvement")
        
        # Check relationship extraction quality
        avg_rel_f1 = sum(s.get('avg_rel_f1', 0) for s in strategy_scores.values()) / len(strategy_scores)
        if avg_rel_f1 < 0.6:
            recommendations.append("Focus on improving relationship extraction prompts")
        
        return recommendations


async def main():
    """Main execution function"""
    print("Cerebras Extraction Optimization Test Framework")
    print("=" * 80)
    
    framework = TestFramework()
    strategy_scores, all_results = await framework.run_comprehensive_test()
    
    print("\nTest completed successfully!")
    return strategy_scores


if __name__ == "__main__":
    asyncio.run(main())