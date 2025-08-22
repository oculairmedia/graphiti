"""
Quality Control Demo for Parallel Ingestion Pipeline

This script validates that parallel processing produces equivalent results
to sequential processing, ensuring we don't sacrifice accuracy for speed.

Key Quality Control Checks:
1. Entity completeness - Are all entities found in both methods?
2. Entity consistency - Are entity names and types the same?
3. Deduplication effectiveness - Are duplicates handled properly?
4. Reflexion quality - Does parallel reflexion miss important entities?
"""

import asyncio
import time
import logging
from typing import List, Dict, Any, Set
from dataclasses import dataclass
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class EntityResult:
    """Represents an extracted entity"""
    name: str
    entity_type_id: int
    confidence: float = 1.0

    def __hash__(self):
        return hash((self.name.lower(), self.entity_type_id))

    def __eq__(self, other):
        if not isinstance(other, EntityResult):
            return False
        return (self.name.lower() == other.name.lower() and
                self.entity_type_id == other.entity_type_id)


@dataclass
class QualityMetrics:
    """Quality control metrics comparing sequential vs parallel results"""
    method_name: str
    total_entities: int
    unique_entities: int
    entity_names: Set[str]
    entity_types: Set[int]
    processing_time: float
    completeness_score: float = 0.0  # How many entities found vs expected
    consistency_score: float = 0.0  # How consistent with sequential baseline


class MockLLMClient:
    """Mock LLM client with deterministic responses for quality testing"""

    def __init__(self):
        self.call_count = 0
        # Predefined entities that should be found in the test content
        self.expected_entities = {
            "alice johnson": EntityResult("Alice Johnson", 0, 0.95),
            "bob smith": EntityResult("Bob Smith", 0, 0.92),
            "marketing team": EntityResult("Marketing Team", 0, 0.88),
            "q4 strategy": EntityResult("Q4 Strategy", 0, 0.91),
            "new product launch": EntityResult("New Product Launch", 0, 0.89),
            "charlie wilson": EntityResult("Charlie Wilson", 0, 0.85),  # Should be found in reflexion
            "engineering team": EntityResult("Engineering Team", 0, 0.82),
            "sales department": EntityResult("Sales Department", 0, 0.87),
            "david brown": EntityResult("David Brown", 0, 0.90),
            "emma davis": EntityResult("Emma Davis", 0, 0.93),
            "frank miller": EntityResult("Frank Miller", 0, 0.86),
            "budget requirements": EntityResult("Budget Requirements", 0, 0.84),
            "supply chain": EntityResult("Supply Chain", 0, 0.81),
            "user interface": EntityResult("User Interface", 0, 0.88),
            "api integration": EntityResult("API Integration", 0, 0.85)
        }

    async def generate_response(self, prompt: Any, response_model=None) -> Dict[str, Any]:
        """Generate deterministic responses for quality testing"""
        self.call_count += 1
        call_id = self.call_count

        start_time = time.time()
        # Simulate realistic timing
        await asyncio.sleep(0.1)  # Much faster for testing
        actual_duration = time.time() - start_time

        logger.info(f"LLM Call {call_id}: {actual_duration:.3f}s")

        # Determine what entities to return based on prompt content
        content = str(prompt).lower()
        found_entities = []

        # Initial extraction - return core entities
        if "extract entities" in content and "initial" in content:
            found_entities = [
                {"name": "Alice Johnson", "entity_type_id": 0},
                {"name": "Bob Smith", "entity_type_id": 0},
                {"name": "Marketing Team", "entity_type_id": 0},
                {"name": "Q4 Strategy", "entity_type_id": 0},
                {"name": "New Product Launch", "entity_type_id": 0}
            ]

        # Reflexion - return missed entities
        elif "missed entities" in content or "reflexion" in content:
            found_entities = [
                {"name": "Charlie Wilson", "entity_type_id": 0},
                {"name": "Sales Department", "entity_type_id": 0}
            ]

        # Chunk-specific responses for parallel processing
        elif "chunk 0" in content:
            found_entities = [
                {"name": "Alice Johnson", "entity_type_id": 0},
                {"name": "Marketing Team", "entity_type_id": 0},
                {"name": "Q4 Strategy", "entity_type_id": 0}
            ]
        elif "chunk 1" in content:
            found_entities = [
                {"name": "Bob Smith", "entity_type_id": 0},
                {"name": "New Product Launch", "entity_type_id": 0},
                {"name": "Charlie Wilson", "entity_type_id": 0}
            ]
        elif "chunk 2" in content:
            found_entities = [
                {"name": "Sales Department", "entity_type_id": 0},
                {"name": "David Brown", "entity_type_id": 0}
            ]

        # Batch responses
        elif "batch" in content:
            batch_id = content.split("batch")[-1].strip().split()[0] if "batch" in content else "0"
            batch_entities = [
                {"name": f"Batch Entity {batch_id}", "entity_type_id": 0},
                {"name": "Alice Johnson", "entity_type_id": 0},
                {"name": "Bob Smith", "entity_type_id": 0}
            ]
            found_entities = batch_entities

        return {"extracted_entities": found_entities}


class QualityControlledExtractor:
    """Entity extractor with quality control validation"""

    def __init__(self):
        self.client = MockLLMClient()
        self.expected_entities = self.client.expected_entities

    async def extract_entities_sequential(self, episode_content: str) -> QualityMetrics:
        """Sequential extraction (baseline for quality comparison)"""
        start_time = time.time()

        logger.info("🔍 Starting SEQUENTIAL extraction (quality baseline)...")

        # Reset client for consistent testing
        self.client.call_count = 0

        # Initial extraction
        initial_response = await self.client.generate_response(
            f"Initial extract entities from: {episode_content[:500]}"
        )

        entities = []
        for entity_data in initial_response.get('extracted_entities', []):
            entities.append(EntityResult(
                name=entity_data['name'],
                entity_type_id=entity_data['entity_type_id']
            ))

        # Reflexion
        reflexion_response = await self.client.generate_response(
            f"Find missed entities from: {episode_content[:500]}"
        )

        for entity_data in reflexion_response.get('extracted_entities', []):
            entities.append(EntityResult(
                name=entity_data['name'],
                entity_type_id=entity_data['entity_type_id']
            ))

        total_time = time.time() - start_time

        # Calculate quality metrics
        entity_names = {e.name.lower() for e in entities}
        entity_types = {e.entity_type_id for e in entities}
        expected_names = {name.lower() for name in self.expected_entities.keys()}

        completeness_score = len(entity_names & expected_names) / len(expected_names)
        consistency_score = 1.0  # Baseline method

        logger.info(f"✅ Sequential found {len(entities)} entities ({completeness_score:.1%} complete)")

        return QualityMetrics(
            method_name="Sequential",
            total_entities=len(entities),
            unique_entities=len(set(entities)),
            entity_names=entity_names,
            entity_types=entity_types,
            processing_time=total_time,
            completeness_score=completeness_score,
            consistency_score=consistency_score
        )

    async def extract_entities_parallel(self, episode_content: str, max_concurrent: int = 3) -> QualityMetrics:
        """Parallel extraction with quality validation"""
        start_time = time.time()

        logger.info(f"⚡ Starting PARALLEL extraction (quality controlled, {max_concurrent} concurrent)...")

        # Reset client
        self.client.call_count = 0

        # Split content into chunks
        content_chunks = self._split_content(episode_content, max_concurrent)

        # Create parallel extraction tasks
        extraction_tasks = []
        for i, chunk in enumerate(content_chunks):
            task = asyncio.create_task(
                self.client.generate_response(
                    f"Extract entities from chunk {i}: {chunk}"
                )
            )
            extraction_tasks.append(task)

        # Wait for all extractions
        extraction_results = await asyncio.gather(*extraction_tasks, return_exceptions=True)

        entities = []
        for result in extraction_results:
            if isinstance(result, Exception):
                logger.error(f"❌ Extraction failed: {result}")
                continue

            for entity_data in result.get('extracted_entities', []):
                entities.append(EntityResult(
                    name=entity_data['name'],
                    entity_type_id=entity_data['entity_type_id']
                ))

        # Parallel reflexion
        reflexion_tasks = []
        for i, chunk in enumerate(content_chunks):
            task = asyncio.create_task(
                self.client.generate_response(
                    f"Find missed entities from chunk {i}: {chunk}"
                )
            )
            reflexion_tasks.append(task)

        reflexion_results = await asyncio.gather(*reflexion_tasks, return_exceptions=True)

        for result in reflexion_results:
            if isinstance(result, Exception):
                logger.error(f"❌ Reflexion failed: {result}")
                continue

            for entity_data in result.get('extracted_entities', []):
                entities.append(EntityResult(
                    name=entity_data['name'],
                    entity_type_id=entity_data['entity_type_id']
                ))

        total_time = time.time() - start_time

        # Remove duplicates
        unique_entities = list(set(entities))

        # Calculate quality metrics
        entity_names = {e.name.lower() for e in unique_entities}
        entity_types = {e.entity_type_id for e in unique_entities}
        expected_names = {name.lower() for name in self.expected_entities.keys()}

        completeness_score = len(entity_names & expected_names) / len(expected_names)

        logger.info(f"✅ Parallel found {len(unique_entities)} unique entities ({completeness_score:.1%} complete)")

        return QualityMetrics(
            method_name="Parallel",
            total_entities=len(unique_entities),
            unique_entities=len(unique_entities),
            entity_names=entity_names,
            entity_types=entity_types,
            processing_time=total_time,
            completeness_score=completeness_score,
            consistency_score=1.0  # Will be calculated relative to sequential
        )

    def _split_content(self, content: str, num_chunks: int) -> List[str]:
        """Split content into chunks for parallel processing"""
        words = content.split()
        chunk_size = len(words) // num_chunks
        chunks = []

        for i in range(num_chunks):
            start = i * chunk_size
            end = start + chunk_size if i < num_chunks - 1 else len(words)
            chunk = " ".join(words[start:end])
            chunks.append(chunk)

        return chunks


class QualityControlDemo:
    """Main demo class for quality control validation"""

    def __init__(self):
        self.test_content = self._generate_test_content()
        self.extractor = QualityControlledExtractor()

    def _generate_test_content(self) -> str:
        """Generate test content with known entities"""
        return """
        In today's team meeting, Alice Johnson from marketing presented the Q4 strategy update.
        She discussed the new product launch timeline with Bob Smith, the engineering lead.
        Charlie Wilson from sales provided insights about customer feedback and market trends.
        The team also discussed integration with the new API developed by David Brown and his team.
        Emma Davis suggested improvements to the user interface based on recent user testing.
        Frank Miller outlined the budget requirements for the next quarter's initiatives.
        The meeting concluded with action items assigned to various team members including
        follow-ups with stakeholders and preparation for the upcoming conference in New York.
        Additional topics included supply chain optimization and partnership opportunities with
        several technology vendors including Microsoft, Google, and Amazon Web Services.
        """

    async def run_quality_comparison(self):
        """Run quality comparison between sequential and parallel processing"""
        print("🔍 QUALITY CONTROL DEMO: Parallel vs Sequential Entity Extraction")
        print("=" * 75)
        print(f"Test content: {len(self.test_content)} characters")
        print(f"Expected entities: {len(self.extractor.expected_entities)}")
        print()

        # Run sequential (baseline)
        print("📊 Running Sequential Processing (Quality Baseline)")
        sequential_metrics = await self.extractor.extract_entities_sequential()
        self._print_quality_metrics(sequential_metrics)
        print()

        # Run parallel with different concurrency levels
        parallel_results = []
        for concurrency in [2, 3, 4]:
            print(f"⚡ Running Parallel Processing ({concurrency} concurrent) - Quality Validation")
            parallel_metrics = await self.extractor.extract_entities_parallel(
                self.test_content, max_concurrent=concurrency
            )

            # Calculate consistency score relative to sequential
            if sequential_metrics.entity_names:
                consistency_score = len(parallel_metrics.entity_names & sequential_metrics.entity_names) / len(sequential_metrics.entity_names)
            else:
                consistency_score = 0.0
            parallel_metrics.consistency_score = consistency_score

            parallel_results.append(parallel_metrics)
            self._print_quality_metrics(parallel_metrics)
            print()

        # Quality analysis
        self._print_quality_analysis(sequential_metrics, parallel_results)

    def _print_quality_metrics(self, metrics: QualityMetrics):
        """Print quality metrics"""
        print(f"  Method: {metrics.method_name}")
        print(".3f")
        print(f"  Total Entities: {metrics.total_entities}")
        print(f"  Unique Entities: {metrics.unique_entities}")
        print(".1%")
        print(".1%")
        print(f"  Entity Types Found: {len(metrics.entity_types)}")
        print(f"  LLM Calls Made: {self.extractor.client.call_count}")

        if metrics.entity_names:
            print(f"  Sample Entities: {list(metrics.entity_names)[:5]}")

    def _print_quality_analysis(self, sequential: QualityMetrics, parallel_results: List[QualityMetrics]):
        """Print comprehensive quality analysis"""
        print("🎯 QUALITY ANALYSIS REPORT")
        print("=" * 75)

        print("<15")
        print("-" * 75)

        print("<15"
              "<12d"
              "<10.1%"
              "<10.1%"
              "<8.3f")

        for result in parallel_results:
            print("<15"
                  "<12d"
                  "<10.1%"
                  "<10.1%"
                  "<8.3f")

        print()
        print("🔍 QUALITY CONTROL INSIGHTS:")
        print()

        # Check for quality degradation
        quality_issues = []
        for result in parallel_results:
            if result.completeness_score < 0.8:
                quality_issues.append(f"{result.method_name}: Low completeness ({result.completeness_score:.1%})")
            if result.consistency_score < 0.9:
                quality_issues.append(f"{result.method_name}: Low consistency ({result.consistency_score:.1%})")

        if quality_issues:
            print("⚠️  QUALITY ISSUES DETECTED:")
            for issue in quality_issues:
                print(f"   • {issue}")
            print()
            print("💡 RECOMMENDATIONS:")
            print("   • Implement entity deduplication across chunks")
            print("   • Use content-aware chunking to preserve context")
            print("   • Add overlap between chunks to prevent missed entities")
            print("   • Implement result consolidation logic")
        else:
            print("✅ ALL METHODS PASSED QUALITY THRESHOLDS:")
            print("   • Completeness: >80% of expected entities found")
            print("   • Consistency: >90% overlap with sequential baseline")
            print()
            print("🚀 SAFE TO PROCEED WITH PARALLEL PROCESSING")

        print()
        print("📋 IMPLEMENTATION RECOMMENDATIONS:")
        print("   1. Add entity deduplication logic for parallel results")
        print("   2. Implement chunk overlap to preserve context boundaries")
        print("   3. Add quality validation in production")
        print("   4. Monitor entity completeness and consistency")
        print("   5. Consider fallback to sequential for critical content")


async def main():
    """Main entry point"""
    print("🔍 Quality Control Demo for Parallel Ingestion Pipeline")
    print("   Validating that parallel processing maintains output quality")
    print()

    # Run the quality control demo
    demo = QualityControlDemo()
    await demo.run_quality_comparison()

    print("\n✨ Quality control demo completed!")
    print("   Results show whether parallel processing maintains accuracy.")


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())