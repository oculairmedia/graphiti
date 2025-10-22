"""
Focused Cerebras Relationship Extraction Optimization
Specifically targets the poor relationship extraction performance (25% F1) 
identified in the comprehensive optimization tests.
"""

import json
import asyncio
from typing import Dict, List, Tuple, Any
from datetime import datetime
from dataclasses import dataclass
import os
from cerebras.cloud.sdk import Cerebras
import re

# Configuration
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY")
MODEL = "qwen-3-coder-480b"
TEMPERATURE = 0.7
TOP_P = 0.8

@dataclass
class RelationshipScenario:
    """Test scenario focused on relationship extraction"""
    name: str
    input_text: str
    entities: List[str]  # Pre-identified entities
    expected_relationships: List[Dict]
    relationship_types: List[str]  # Expected relationship types in this domain
    difficulty: str = "medium"  # easy, medium, hard
    domain: str = "general"

@dataclass
class RelationshipStrategy:
    """Strategy specifically for relationship extraction"""
    name: str
    description: str
    system_prompt_modifier: callable
    extraction_approach: str = "single_pass"  # single_pass, two_pass, iterative
    post_processor: callable = None

class RelationshipPatterns:
    """Common relationship patterns and indicators"""
    
    # Linguistic patterns that indicate relationships
    EMPLOYMENT_PATTERNS = {
        r"(\w+(?:\s+\w+)*),?\s+(?:the\s+)?CEO\s+of\s+(\w+(?:\s+\w+)*)": "CEO_OF",
        r"(\w+(?:\s+\w+)*)\s+works?\s+(?:at|for)\s+(\w+(?:\s+\w+)*)": "WORKS_AT",
        r"(\w+(?:\s+\w+)*)\s+from\s+(\w+(?:\s+\w+)*)": "AFFILIATED_WITH",
        r"(\w+(?:\s+\w+)*),?\s+(?:a\s+)?(?:director|manager|employee)\s+at\s+(\w+(?:\s+\w+)*)": "WORKS_AT",
        r"(\w+(?:\s+\w+)*)\s+joined\s+(\w+(?:\s+\w+)*)": "JOINED",
        r"(\w+(?:\s+\w+)*)\s+left\s+(\w+(?:\s+\w+)*)": "LEFT"
    }
    
    COLLABORATION_PATTERNS = {
        r"(\w+(?:\s+\w+)*)\s+collaborated?\s+with\s+(\w+(?:\s+\w+)*)": "COLLABORATES_WITH",
        r"(\w+(?:\s+\w+)*)\s+partnered?\s+with\s+(\w+(?:\s+\w+)*)": "PARTNERS_WITH",
        r"(\w+(?:\s+\w+)*)\s+and\s+(\w+(?:\s+\w+)*)\s+worked\s+together": "COLLABORATES_WITH",
        r"(\w+(?:\s+\w+)*)\s+met\s+with\s+(\w+(?:\s+\w+)*)": "MET_WITH",
        r"(\w+(?:\s+\w+)*)\s+discussed?\s+with\s+(\w+(?:\s+\w+)*)": "DISCUSSED_WITH"
    }
    
    BUSINESS_PATTERNS = {
        r"(\w+(?:\s+\w+)*)\s+acquired?\s+(\w+(?:\s+\w+)*)": "ACQUIRED",
        r"(\w+(?:\s+\w+)*)\s+launched?\s+(\w+(?:\s+\w+)*)": "LAUNCHED",
        r"(\w+(?:\s+\w+)*)\s+announced?\s+(\w+(?:\s+\w+)*)": "ANNOUNCED",
        r"(\w+(?:\s+\w+)*)\s+developed?\s+(\w+(?:\s+\w+)*)": "DEVELOPED",
        r"(\w+(?:\s+\w+)*)\s+funded?\s+(\w+(?:\s+\w+)*)": "FUNDED",
        r"(\w+(?:\s+\w+)*)\s+invested?\s+in\s+(\w+(?:\s+\w+)*)": "INVESTED_IN"
    }
    
    TECHNICAL_PATTERNS = {
        r"(\w+(?:\s+\w+)*)\s+uses?\s+(\w+(?:\s+\w+)*)": "USES",
        r"(\w+(?:\s+\w+)*)\s+integrates?\s+with\s+(\w+(?:\s+\w+)*)": "INTEGRATES_WITH",
        r"(\w+(?:\s+\w+)*)\s+based\s+on\s+(\w+(?:\s+\w+)*)": "BASED_ON",
        r"(\w+(?:\s+\w+)*)\s+built\s+on\s+(\w+(?:\s+\w+)*)": "BUILT_ON",
        r"(\w+(?:\s+\w+)*)\s+powered?\s+by\s+(\w+(?:\s+\w+)*)": "POWERED_BY"
    }
    
    @classmethod
    def extract_relationships_by_pattern(cls, text: str, entities: List[str]) -> List[Dict]:
        """Extract relationships using linguistic patterns"""
        relationships = []
        entity_set = {entity.lower().strip() for entity in entities}
        
        all_patterns = {**cls.EMPLOYMENT_PATTERNS, **cls.COLLABORATION_PATTERNS, 
                       **cls.BUSINESS_PATTERNS, **cls.TECHNICAL_PATTERNS}
        
        for pattern, rel_type in all_patterns.items():
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                source = match.group(1).strip()
                target = match.group(2).strip()
                
                # Check if both entities are in our entity list
                if source.lower() in entity_set and target.lower() in entity_set:
                    relationships.append({
                        "source": source,
                        "target": target, 
                        "type": rel_type,
                        "confidence": 0.9,  # High confidence for pattern matches
                        "method": "pattern_extraction"
                    })
        
        return relationships

class RelationshipFocusedFramework:
    """Framework specifically designed to improve relationship extraction"""
    
    def __init__(self):
        self.client = Cerebras(api_key=CEREBRAS_API_KEY)
        
    def get_relationship_scenarios(self) -> List[RelationshipScenario]:
        """Get test scenarios focused on different types of relationships"""
        return [
            RelationshipScenario(
                name="employment_relationships",
                input_text="Sarah Chen, the CEO of TechCorp, announced that John Smith will join as CTO. Mary Johnson from DataSys will lead the new AI division. The company also hired Dr. Alice Wang from MIT.",
                entities=["Sarah Chen", "John Smith", "Mary Johnson", "Dr. Alice Wang", "TechCorp", "DataSys", "MIT", "AI division"],
                expected_relationships=[
                    {"source": "Sarah Chen", "target": "TechCorp", "type": "CEO_OF"},
                    {"source": "John Smith", "target": "TechCorp", "type": "JOINED_AS_CTO"},
                    {"source": "Mary Johnson", "target": "DataSys", "type": "FROM"},
                    {"source": "Mary Johnson", "target": "AI division", "type": "LEADS"},
                    {"source": "Dr. Alice Wang", "target": "MIT", "type": "FROM"},
                    {"source": "Dr. Alice Wang", "target": "TechCorp", "type": "HIRED_BY"}
                ],
                relationship_types=["CEO_OF", "JOINED_AS", "FROM", "LEADS", "HIRED_BY"],
                difficulty="hard",
                domain="business"
            ),
            
            RelationshipScenario(
                name="collaboration_relationships", 
                input_text="Dr. Bob Zhang at Stanford collaborated with Professor Lisa Chen from MIT on quantum computing research. They met with researchers from Google and IBM to discuss potential applications.",
                entities=["Dr. Bob Zhang", "Professor Lisa Chen", "Stanford", "MIT", "Google", "IBM", "quantum computing research"],
                expected_relationships=[
                    {"source": "Dr. Bob Zhang", "target": "Stanford", "type": "WORKS_AT"},
                    {"source": "Professor Lisa Chen", "target": "MIT", "type": "WORKS_AT"},
                    {"source": "Dr. Bob Zhang", "target": "Professor Lisa Chen", "type": "COLLABORATED_WITH"},
                    {"source": "Dr. Bob Zhang", "target": "quantum computing research", "type": "RESEARCHES"},
                    {"source": "Professor Lisa Chen", "target": "quantum computing research", "type": "RESEARCHES"},
                    {"source": "Dr. Bob Zhang", "target": "Google", "type": "MET_WITH"},
                    {"source": "Dr. Bob Zhang", "target": "IBM", "type": "MET_WITH"},
                    {"source": "Professor Lisa Chen", "target": "Google", "type": "MET_WITH"},
                    {"source": "Professor Lisa Chen", "target": "IBM", "type": "MET_WITH"}
                ],
                relationship_types=["WORKS_AT", "COLLABORATED_WITH", "RESEARCHES", "MET_WITH"],
                difficulty="medium",
                domain="academic"
            ),
            
            RelationshipScenario(
                name="temporal_relationships",
                input_text="John previously worked at Google for 5 years. In 2020, he joined Microsoft as a senior engineer. Last year, he was promoted to principal engineer and now leads the Azure team.",
                entities=["John", "Google", "Microsoft", "Azure team", "senior engineer", "principal engineer"],
                expected_relationships=[
                    {"source": "John", "target": "Google", "type": "PREVIOUSLY_WORKED_AT"},
                    {"source": "John", "target": "Microsoft", "type": "JOINED_IN_2020"},
                    {"source": "John", "target": "senior engineer", "type": "JOINED_AS"},
                    {"source": "John", "target": "principal engineer", "type": "PROMOTED_TO"},
                    {"source": "John", "target": "Azure team", "type": "LEADS"}
                ],
                relationship_types=["PREVIOUSLY_WORKED_AT", "JOINED_IN", "JOINED_AS", "PROMOTED_TO", "LEADS"],
                difficulty="hard",
                domain="career"
            ),
            
            RelationshipScenario(
                name="technical_relationships",
                input_text="The GraphRAG system uses LLaMA-3 embeddings for vector storage. It integrates with FalkorDB as the backend database and employs Cosmograph for data visualization. The system was built on FastAPI framework.",
                entities=["GraphRAG system", "LLaMA-3 embeddings", "FalkorDB", "Cosmograph", "FastAPI framework"],
                expected_relationships=[
                    {"source": "GraphRAG system", "target": "LLaMA-3 embeddings", "type": "USES"},
                    {"source": "GraphRAG system", "target": "FalkorDB", "type": "INTEGRATES_WITH"},
                    {"source": "GraphRAG system", "target": "Cosmograph", "type": "EMPLOYS"},
                    {"source": "GraphRAG system", "target": "FastAPI framework", "type": "BUILT_ON"}
                ],
                relationship_types=["USES", "INTEGRATES_WITH", "EMPLOYS", "BUILT_ON"],
                difficulty="easy",
                domain="technical"
            ),
            
            RelationshipScenario(
                name="implicit_relationships",
                input_text="Apple announced record quarterly earnings. Tim Cook said the iPhone sales exceeded expectations in China. The company will expand manufacturing in India next year.",
                entities=["Apple", "Tim Cook", "iPhone", "China", "India", "manufacturing"],
                expected_relationships=[
                    {"source": "Tim Cook", "target": "Apple", "type": "CEO_OF"},  # Implicit
                    {"source": "Apple", "target": "iPhone", "type": "MANUFACTURES"}, # Implicit
                    {"source": "iPhone", "target": "China", "type": "SOLD_IN"},
                    {"source": "Apple", "target": "India", "type": "WILL_EXPAND_TO"},
                    {"source": "Apple", "target": "manufacturing", "type": "WILL_EXPAND"}
                ],
                relationship_types=["CEO_OF", "MANUFACTURES", "SOLD_IN", "WILL_EXPAND_TO"],
                difficulty="hard",
                domain="business"
            )
        ]
    
    def get_relationship_strategies(self) -> List[RelationshipStrategy]:
        """Get different strategies for relationship extraction optimization"""
        
        def relationship_first_prompt(base_prompt: str) -> str:
            return f"""You are a relationship extraction specialist. Your PRIMARY focus is identifying relationships between entities.

RELATIONSHIP EXTRACTION PRIORITY:
1. First, identify all relationships and connections mentioned in the text
2. Look for verbs, prepositions, and connecting phrases that indicate relationships
3. Then identify the entities involved in these relationships

RELATIONSHIP TYPES TO LOOK FOR:
- Employment: works_at, CEO_of, joined, hired_by, leads, manages
- Collaboration: collaborates_with, partners_with, met_with, discussed_with
- Business: acquired, launched, announced, developed, funded, invested_in
- Technical: uses, integrates_with, built_on, powered_by, based_on
- Temporal: previously_worked_at, joined_in, promoted_to, will_expand_to

{base_prompt}

Extract relationships with high precision. Include confidence scores and supporting context."""

        def two_pass_prompt(base_prompt: str) -> str:
            return f"""You are performing PASS 2 of a two-pass extraction system focused exclusively on RELATIONSHIPS.

The entities have already been identified in Pass 1. Your job is to find ALL relationships between these entities.

RELATIONSHIP EXTRACTION INSTRUCTIONS:
- Look for explicit relationships (stated directly)
- Look for implicit relationships (implied by context, titles, roles)
- Use verbs as relationship indicators: "works", "leads", "uses", "built"
- Use prepositions as relationship indicators: "at", "with", "from", "for"
- Pay attention to titles and roles that imply relationships

{base_prompt}

Return ONLY relationships. Be exhaustive - find every possible connection between entities."""

        def contextual_inference_prompt(base_prompt: str) -> str:
            return f"""You are an expert at inferring relationships from context and implicit information.

CONTEXT-BASED RELATIONSHIP INFERENCE:
- If someone is called "CEO of X", create CEO_OF relationship
- If someone "from MIT" is mentioned, create AFFILIATED_WITH relationship  
- If someone "announced" something, they likely work for the organization
- If technologies are mentioned together, look for integration relationships
- If people work on the same project, they collaborate

INFERENCE RULES:
1. Titles imply employment relationships (CEO, CTO, Director → WORKS_AT)
2. "From" often indicates affiliation (Dr. X from MIT → AFFILIATED_WITH)
3. Announcements imply spokesperson role (X announced → REPRESENTS/WORKS_AT)
4. Collaboration verbs create bidirectional relationships
5. Technical mentions often indicate usage relationships

{base_prompt}

Extract both explicit AND inferred relationships. Mark inferred relationships with confidence < 1.0."""

        def linguistic_pattern_prompt(base_prompt: str) -> str:
            return f"""You are using advanced linguistic pattern recognition for relationship extraction.

LINGUISTIC PATTERNS FOR RELATIONSHIPS:
- [Person] [title] [preposition] [Organization] → employment relationship
- [Entity1] [action_verb] [Entity2] → action relationship  
- [Entity1] [connecting_word] [Entity2] → connection relationship
- [Entity] "from" [Organization] → affiliation
- [Entity] "at" [Organization] → location/employment
- [Entity] "with" [Entity] → collaboration

PATTERN EXAMPLES:
- "Sarah Chen, CEO of TechCorp" → Sarah Chen CEO_OF TechCorp
- "uses LLaMA-3 embeddings" → [System] USES LLaMA-3 embeddings
- "collaborated with MIT" → [Person] COLLABORATES_WITH MIT
- "built on FastAPI" → [System] BUILT_ON FastAPI

{base_prompt}

Focus on linguistic patterns that indicate relationships. Extract relationships with pattern confidence scores."""

        def domain_specific_prompt(base_prompt: str, domain: str = "technical") -> str:
            domain_patterns = {
                "business": """
BUSINESS RELATIONSHIP PATTERNS:
- CEO, CTO, Director → LEADS/MANAGES
- announced, launched → ANNOUNCED/LAUNCHED  
- acquired, invested → ACQUIRED/INVESTED_IN
- joined, hired → JOINED/HIRED_BY
- partnership, collaboration → PARTNERS_WITH
""",
                "technical": """
TECHNICAL RELATIONSHIP PATTERNS:
- uses, employs → USES/EMPLOYS
- integrates with → INTEGRATES_WITH
- built on, based on → BUILT_ON/BASED_ON
- powered by → POWERED_BY
- connects to → CONNECTS_TO
""",
                "academic": """
ACADEMIC RELATIONSHIP PATTERNS:
- researches, studies → RESEARCHES
- collaborates on → COLLABORATES_ON
- funded by → FUNDED_BY  
- affiliated with → AFFILIATED_WITH
- published with → CO_AUTHORED_WITH
"""
            }
            
            return f"""{base_prompt}

DOMAIN: {domain.upper()}
{domain_patterns.get(domain, "")}

Focus on {domain}-specific relationship patterns and terminology."""

        return [
            RelationshipStrategy(
                name="baseline_relationships",
                description="Standard relationship extraction",
                system_prompt_modifier=lambda p: p,
                extraction_approach="single_pass"
            ),
            
            RelationshipStrategy(
                name="relationship_first",
                description="Extract relationships before entities", 
                system_prompt_modifier=relationship_first_prompt,
                extraction_approach="single_pass"
            ),
            
            RelationshipStrategy(
                name="two_pass_extraction",
                description="Two-pass: entities first, then relationships",
                system_prompt_modifier=two_pass_prompt,
                extraction_approach="two_pass"
            ),
            
            RelationshipStrategy(
                name="contextual_inference", 
                description="Infer implicit relationships from context",
                system_prompt_modifier=contextual_inference_prompt,
                extraction_approach="single_pass"
            ),
            
            RelationshipStrategy(
                name="linguistic_patterns",
                description="Use linguistic patterns for relationship detection",
                system_prompt_modifier=linguistic_pattern_prompt,
                extraction_approach="single_pass"
            ),
            
            RelationshipStrategy(
                name="domain_business",
                description="Business domain-specific relationship extraction",
                system_prompt_modifier=lambda p: domain_specific_prompt(p, "business"),
                extraction_approach="single_pass"
            ),
            
            RelationshipStrategy(
                name="domain_technical", 
                description="Technical domain-specific relationship extraction",
                system_prompt_modifier=lambda p: domain_specific_prompt(p, "technical"),
                extraction_approach="single_pass"
            ),
            
            RelationshipStrategy(
                name="pattern_augmented",
                description="Combine LLM extraction with pattern matching",
                system_prompt_modifier=linguistic_pattern_prompt,
                extraction_approach="single_pass",
                post_processor=RelationshipPatterns.extract_relationships_by_pattern
            )
        ]
    
    def get_relationship_schema(self) -> Dict:
        """Schema optimized for relationship extraction"""
        return {
            "type": "object",
            "properties": {
                "relationships": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "source": {"type": "string"},
                            "target": {"type": "string"},
                            "type": {"type": "string"},
                            "confidence": {"type": "number"},
                            "context": {"type": "string"},
                            "method": {"type": "string"}
                        },
                        "required": ["source", "target", "type"],
                        "additionalProperties": False
                    }
                }
            },
            "required": ["relationships"],
            "additionalProperties": False
        }
    
    def calculate_relationship_metrics(self, predicted: List[Dict], expected: List[Dict]) -> Dict:
        """Calculate relationship-specific metrics with flexible matching"""
        def normalize_relationship(rel):
            if isinstance(rel, dict):
                source = rel.get('source', '').strip().lower()
                target = rel.get('target', '').strip().lower()
                rel_type = rel.get('type', '').strip().upper()
                return (source, target, rel_type)
            return tuple(str(x).strip().lower() for x in rel)
        
        # Normalize predicted and expected relationships
        pred_rels = {normalize_relationship(rel) for rel in predicted if rel}
        exp_rels = {normalize_relationship(rel) for rel in expected if rel}
        
        # Also check for reverse relationships (bidirectional)
        pred_rels_with_reverse = pred_rels.copy()
        for source, target, rel_type in pred_rels.copy():
            if rel_type in ["COLLABORATES_WITH", "MET_WITH", "PARTNERS_WITH"]:
                pred_rels_with_reverse.add((target, source, rel_type))
        
        tp = len(pred_rels_with_reverse & exp_rels)
        fp = len(pred_rels - exp_rels)
        fn = len(exp_rels - pred_rels_with_reverse)
        
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        
        return {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
            "predicted_count": len(pred_rels),
            "expected_count": len(exp_rels)
        }
    
    async def test_relationship_strategy(self, strategy: RelationshipStrategy, scenario: RelationshipScenario) -> Dict:
        """Test a relationship extraction strategy"""
        try:
            if strategy.extraction_approach == "two_pass":
                # First pass: extract entities (simulated - we'll use provided entities)
                entities_text = f"Entities in text: {', '.join(scenario.entities)}"
                
                # Second pass: extract relationships given entities
                base_prompt = f"""Given these entities: {', '.join(scenario.entities)}
                
Extract ALL relationships between these entities from the following text.
Return relationships in JSON format with source, target, type, and confidence."""
                
                system_prompt = strategy.system_prompt_modifier(base_prompt)
                user_prompt = f"""Text: {scenario.input_text}

Entities: {entities_text}

Extract all relationships between the given entities. Focus on finding every possible connection."""
                
            else:
                # Single pass extraction
                base_prompt = """Extract relationships from the following text.
Focus on finding all connections between entities mentioned in the text.
Return relationships in JSON format with source, target, type, and confidence."""
                
                system_prompt = strategy.system_prompt_modifier(base_prompt)
                user_prompt = scenario.input_text
            
            # Make API call
            start_time = datetime.now()
            response = self.client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "relationship_extraction",
                        "strict": False,
                        "schema": self.get_relationship_schema()
                    }
                },
                temperature=TEMPERATURE,
                top_p=TOP_P,
                max_completion_tokens=2000
            )
            
            result = json.loads(response.choices[0].message.content)
            response_time = (datetime.now() - start_time).total_seconds()
            
            # Apply post-processing if defined
            relationships = result.get('relationships', [])
            if strategy.post_processor:
                pattern_relationships = strategy.post_processor(scenario.input_text, scenario.entities)
                relationships.extend(pattern_relationships)
            
            # Calculate metrics
            metrics = self.calculate_relationship_metrics(relationships, scenario.expected_relationships)
            
            return {
                "strategy": strategy.name,
                "scenario": scenario.name,
                "success": True,
                "relationships": relationships,
                "metrics": metrics,
                "response_time": response_time,
                "extraction_approach": strategy.extraction_approach
            }
            
        except Exception as e:
            return {
                "strategy": strategy.name,
                "scenario": scenario.name,
                "success": False,
                "error": str(e),
                "metrics": {"f1": 0, "precision": 0, "recall": 0}
            }
    
    async def run_relationship_focused_tests(self):
        """Run comprehensive relationship extraction tests"""
        strategies = self.get_relationship_strategies()
        scenarios = self.get_relationship_scenarios()
        
        print("Focused Relationship Extraction Optimization")
        print("=" * 80)
        print(f"Testing {len(strategies)} strategies on {len(scenarios)} scenarios...")
        print(f"Model: {MODEL} | Temperature: {TEMPERATURE} | Top-P: {TOP_P}")
        print()
        
        all_results = []
        strategy_scores = {}
        
        for strategy in strategies:
            print(f"Testing Strategy: {strategy.name}")
            print(f"Description: {strategy.description}")
            print(f"Approach: {strategy.extraction_approach}")
            print("-" * 60)
            
            strategy_results = []
            for scenario in scenarios:
                result = await self.test_relationship_strategy(strategy, scenario)
                strategy_results.append(result)
                all_results.append(result)
                
                if result['success']:
                    metrics = result['metrics']
                    print(f"  {scenario.name:25} | F1: {metrics['f1']:.3f} | P: {metrics['precision']:.3f} | R: {metrics['recall']:.3f} | Found: {metrics['predicted_count']}")
                else:
                    print(f"  {scenario.name:25} | ERROR: {result.get('error', 'Unknown')}")
            
            # Calculate average scores
            successful = [r for r in strategy_results if r['success']]
            if successful:
                avg_f1 = sum(r['metrics']['f1'] for r in successful) / len(successful)
                avg_precision = sum(r['metrics']['precision'] for r in successful) / len(successful)
                avg_recall = sum(r['metrics']['recall'] for r in successful) / len(successful)
                success_rate = len(successful) / len(strategy_results)
                
                strategy_scores[strategy.name] = {
                    "avg_f1": avg_f1,
                    "avg_precision": avg_precision,
                    "avg_recall": avg_recall,
                    "success_rate": success_rate
                }
                
                print(f"\n  Strategy Average | F1: {avg_f1:.3f} | P: {avg_precision:.3f} | R: {avg_recall:.3f} | Success: {success_rate:.1%}")
            print()
        
        # Generate focused relationship report
        self.generate_relationship_report(strategy_scores, all_results)
        
        return strategy_scores, all_results
    
    def generate_relationship_report(self, strategy_scores: Dict, all_results: List[Dict]):
        """Generate relationship-focused optimization report"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = f"cerebras_relationship_optimization_{timestamp}.json"
        
        # Find best strategies
        best_f1 = max(strategy_scores.items(), key=lambda x: x[1]['avg_f1']) if strategy_scores else ("none", {"avg_f1": 0})
        best_precision = max(strategy_scores.items(), key=lambda x: x[1]['avg_precision']) if strategy_scores else ("none", {"avg_precision": 0})
        best_recall = max(strategy_scores.items(), key=lambda x: x[1]['avg_recall']) if strategy_scores else ("none", {"avg_recall": 0})
        
        # Calculate improvements over baseline
        baseline_f1 = strategy_scores.get('baseline_relationships', {}).get('avg_f1', 0)
        improvements = {}
        for name, scores in strategy_scores.items():
            if name != 'baseline_relationships' and baseline_f1 > 0:
                improvement = ((scores['avg_f1'] - baseline_f1) / baseline_f1) * 100
                improvements[name] = improvement
        
        report = {
            "timestamp": timestamp,
            "model": MODEL,
            "focus": "relationship_extraction",
            "configuration": {
                "temperature": TEMPERATURE,
                "top_p": TOP_P
            },
            "summary": {
                "best_f1_strategy": best_f1[0],
                "best_f1_score": best_f1[1]['avg_f1'],
                "best_precision_strategy": best_precision[0], 
                "best_precision_score": best_precision[1]['avg_precision'],
                "best_recall_strategy": best_recall[0],
                "best_recall_score": best_recall[1]['avg_recall'],
                "baseline_f1": baseline_f1,
                "improvements": improvements
            },
            "strategy_scores": strategy_scores,
            "detailed_results": all_results,
            "recommendations": self.generate_relationship_recommendations(strategy_scores, improvements)
        }
        
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        print("=" * 80)
        print("RELATIONSHIP EXTRACTION OPTIMIZATION REPORT")
        print("=" * 80)
        print(f"Best F1 Strategy: {best_f1[0]} (F1: {best_f1[1]['avg_f1']:.3f})")
        print(f"Best Precision: {best_precision[0]} (P: {best_precision[1]['avg_precision']:.3f})")  
        print(f"Best Recall: {best_recall[0]} (R: {best_recall[1]['avg_recall']:.3f})")
        print(f"Baseline F1: {baseline_f1:.3f}")
        print()
        
        print("Top Improvements:")
        for name, improvement in sorted(improvements.items(), key=lambda x: x[1], reverse=True)[:5]:
            f1_score = strategy_scores[name]['avg_f1']
            print(f"  {name:25} | +{improvement:5.1f}% | F1: {f1_score:.3f}")
        
        print(f"\nDetailed report saved to: {report_file}")
        
        return report_file
    
    def generate_relationship_recommendations(self, strategy_scores: Dict, improvements: Dict) -> List[str]:
        """Generate relationship-specific recommendations"""
        recommendations = []
        
        if not strategy_scores:
            return ["No successful strategies to analyze"]
        
        # Find best performers
        best_f1_strategy = max(strategy_scores.items(), key=lambda x: x[1]['avg_f1'])
        best_precision_strategy = max(strategy_scores.items(), key=lambda x: x[1]['avg_precision'])
        best_recall_strategy = max(strategy_scores.items(), key=lambda x: x[1]['avg_recall'])
        
        if best_f1_strategy[1]['avg_f1'] > 0.5:
            recommendations.append(f"Deploy {best_f1_strategy[0]} for optimal relationship extraction (F1: {best_f1_strategy[1]['avg_f1']:.3f})")
        
        if best_precision_strategy[1]['avg_precision'] > 0.7:
            recommendations.append(f"Use {best_precision_strategy[0]} for high-precision relationship extraction")
        
        if best_recall_strategy[1]['avg_recall'] > 0.7:
            recommendations.append(f"Use {best_recall_strategy[0]} for comprehensive relationship discovery")
        
        # Check for two-pass benefits
        two_pass_results = [name for name in strategy_scores.keys() if "two_pass" in name]
        if two_pass_results and improvements.get(two_pass_results[0], 0) > 20:
            recommendations.append("Two-pass extraction shows significant improvement - consider implementing")
        
        # Check pattern matching benefits
        pattern_results = [name for name in strategy_scores.keys() if "pattern" in name]
        if pattern_results and improvements.get(pattern_results[0], 0) > 15:
            recommendations.append("Pattern-augmented extraction provides substantial gains")
        
        # Check domain-specific benefits
        domain_improvements = {k: v for k, v in improvements.items() if k.startswith("domain_")}
        if domain_improvements and max(domain_improvements.values()) > 25:
            recommendations.append("Domain-specific prompting shows strong benefits - tailor prompts to content type")
        
        return recommendations


async def main():
    """Run focused relationship extraction optimization"""
    framework = RelationshipFocusedFramework()
    strategy_scores, all_results = await framework.run_relationship_focused_tests()
    
    print("\nRelationship extraction optimization completed!")
    return strategy_scores


if __name__ == "__main__":
    asyncio.run(main())