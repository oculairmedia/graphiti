"""
Prompt templates for OpenEvolve evolution.

This module provides:
- Initial prompt templates that OpenEvolve will evolve
- Utilities for loading/saving evolved prompts
- Injection mechanisms to use evolved prompts in DSPy modules
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PromptTemplate:
    """
    A prompt template that can be evolved by OpenEvolve.

    Attributes:
        name: Template identifier (e.g., 'entity_extraction')
        instruction: The main instruction text to evolve
        examples: Few-shot examples (optional)
        constraints: Hard constraints that should not be violated
        metadata: Additional metadata
    """
    name: str
    instruction: str
    examples: list[dict[str, Any]] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_python_code(self) -> str:
        """
        Convert to Python code that OpenEvolve can evolve.

        Returns executable Python that defines the instruction and examples.
        """
        code = f'''"""
Evolved prompt template: {self.name}
Generated: {datetime.now(timezone.utc).isoformat()}

This file is evolved by OpenEvolve. The EXTRACTION_INSTRUCTION variable
contains the optimized prompt that will be injected into DSPy modules.
"""

# The main instruction to be evolved
# OpenEvolve will modify this to improve extraction quality
{self.name.upper()}_INSTRUCTION = """
{self.instruction}
"""

# Alias for compatibility
instruction = {self.name.upper()}_INSTRUCTION

# Constraints (do not modify during evolution)
CONSTRAINTS = {json.dumps(self.constraints, indent=4)}

# Few-shot examples (can be evolved)
EXAMPLES = {json.dumps(self.examples, indent=4)}

# Metadata
METADATA = {json.dumps(self.metadata, indent=4)}
'''
        return code

    def save(self, path: str | Path) -> None:
        """Save template as Python file for OpenEvolve."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_python_code())
        logger.info(f'Saved prompt template to {path}')

    @classmethod
    def from_python_file(cls, path: str | Path) -> 'PromptTemplate':
        """Load template from evolved Python file."""
        path = Path(path)
        code = path.read_text()

        local_ns: dict[str, Any] = {}
        exec(code, {'__builtins__': __builtins__}, local_ns)

        # Try to find the instruction
        instruction = ''
        for key in local_ns:
            if key.endswith('_INSTRUCTION'):
                instruction = local_ns[key]
                break
        if not instruction:
            instruction = local_ns.get('instruction', '')

        return cls(
            name=path.stem,
            instruction=instruction,
            examples=local_ns.get('EXAMPLES', []),
            constraints=local_ns.get('CONSTRAINTS', []),
            metadata=local_ns.get('METADATA', {}),
        )


def load_prompt_template(path: str | Path) -> PromptTemplate:
    """Load a prompt template from file."""
    return PromptTemplate.from_python_file(path)


def save_prompt_template(template: PromptTemplate, path: str | Path) -> None:
    """Save a prompt template to file."""
    template.save(path)


def inject_evolved_prompt(
    module: Any,
    evolved_instruction: str,
    field_name: str = 'custom_instructions',
) -> None:
    """
    Inject an evolved prompt instruction into a DSPy module.

    This modifies the module to use the evolved instruction
    in place of or in addition to its default prompts.
    """
    if hasattr(module, field_name):
        setattr(module, field_name, evolved_instruction)
    elif hasattr(module, '_evolved_instruction'):
        module._evolved_instruction = evolved_instruction
    else:
        # Store on module for later retrieval
        module._evolved_instruction = evolved_instruction
    logger.debug(f'Injected evolved prompt into {type(module).__name__}')


# =============================================================================
# Initial Prompt Templates
# =============================================================================

ENTITY_EXTRACTION_TEMPLATE = PromptTemplate(
    name='entity_extraction',
    instruction='''Extract all named entities from the text. For each entity:
1. Identify the entity name exactly as it appears in the text
2. Classify the entity type from the provided types
3. Consider context from previous messages if available

Focus on:
- People (names, titles, roles)
- Organizations (companies, institutions, teams)
- Locations (places, addresses, regions)
- Products (technologies, tools, services)
- Events (meetings, incidents, milestones)
- Concepts (abstract ideas, theories, methodologies)

Be precise: only extract entities that are clearly identifiable.
Avoid extracting generic terms or pronouns.''',
    constraints=[
        'Entity names must appear in the source text',
        'Each entity must have exactly one type',
        'Do not extract pronouns or generic references',
    ],
    examples=[
        {
            'input': 'Alice from Anthropic met with Bob at the AI conference in San Francisco.',
            'entities': [
                {'name': 'Alice', 'type': 'Person'},
                {'name': 'Anthropic', 'type': 'Organization'},
                {'name': 'Bob', 'type': 'Person'},
                {'name': 'AI conference', 'type': 'Event'},
                {'name': 'San Francisco', 'type': 'Location'},
            ],
        },
    ],
    metadata={
        'version': '1.0.0',
        'target_metric': 'extraction_f1',
    },
)


EDGE_EXTRACTION_TEMPLATE = PromptTemplate(
    name='edge_extraction',
    instruction='''Extract relationships (edges) between entities. For each relationship:
1. Identify the source entity (subject)
2. Identify the target entity (object)
3. Determine the relationship type that connects them
4. Extract temporal information (when the relationship is valid)

Relationship types to consider:
- WORKS_AT: employment or affiliation
- LOCATED_IN: physical location
- CREATED: authorship or invention
- PART_OF: membership or component
- KNOWS: personal acquaintance
- COLLABORATES_WITH: working together
- MANAGES: supervisory relationship
- ATTENDED: participation in events
- USES: utilization of tools/products

For temporal information:
- valid_at: when the relationship became true
- invalid_at: when the relationship ended (if applicable)

Only extract relationships that are explicitly stated or strongly implied.''',
    constraints=[
        'Source and target must be entities from the extraction',
        'Relationship must be stated or clearly implied in text',
        'Temporal data should use ISO 8601 format',
    ],
    examples=[
        {
            'input': 'Alice joined Anthropic in 2023 as a research scientist.',
            'entities': [
                {'id': 0, 'name': 'Alice', 'type': 'Person'},
                {'id': 1, 'name': 'Anthropic', 'type': 'Organization'},
            ],
            'edges': [
                {
                    'source_entity_id': 0,
                    'target_entity_id': 1,
                    'relation_type': 'WORKS_AT',
                    'fact': 'Alice works at Anthropic as a research scientist',
                    'valid_at': '2023-01-01',
                    'invalid_at': None,
                },
            ],
        },
    ],
    metadata={
        'version': '1.0.0',
        'target_metric': 'edge_f1',
    },
)


RESOLUTION_TEMPLATE = PromptTemplate(
    name='resolution',
    instruction='''Resolve extracted entities against existing entities in the knowledge graph.

For each extracted entity, determine:
1. Is this a NEW entity not seen before?
2. Is this a DUPLICATE of an existing entity?

Indicators of duplication:
- Same name (exact or with minor variations)
- Same type
- Similar context/description
- Aliases or abbreviations (e.g., "IBM" = "International Business Machines")
- Name variations (e.g., "Bob Smith" = "Robert Smith")

Return:
- duplicate_idx: index of matching existing entity (-1 if new)
- confidence: how certain you are (0.0 to 1.0)

Be conservative: only merge entities if you're confident they're the same.
When in doubt, treat as a new entity.''',
    constraints=[
        'duplicate_idx must be -1 (new) or valid existing entity index',
        'Do not merge entities of different types',
        'Preserve entity uniqueness when uncertain',
    ],
    examples=[
        {
            'extracted': {'id': 0, 'name': 'Bob', 'type': 'Person'},
            'existing': [
                {'idx': 0, 'name': 'Robert Smith', 'type': 'Person', 'summary': 'Software engineer'},
                {'idx': 1, 'name': 'Alice', 'type': 'Person', 'summary': 'Data scientist'},
            ],
            'context': 'Bob Smith presented the new architecture.',
            'resolution': {
                'id': 0,
                'name': 'Bob',
                'duplicate_idx': 0,  # Matches "Robert Smith" based on context
            },
        },
    ],
    metadata={
        'version': '1.0.0',
        'target_metric': 'resolution_accuracy',
    },
)


SUMMARY_GENERATION_TEMPLATE = PromptTemplate(
    name='summary_generation',
    instruction='''Generate a concise summary for an entity based on available information.

Guidelines:
1. Summarize in 1-3 sentences (max 150 words)
2. Include key identifying information
3. Mention relationships to other entities if relevant
4. Use factual, neutral language
5. If updating an existing summary, integrate new information

The summary should answer:
- What/who is this entity?
- What is their primary role/function?
- What key relationships or attributes define them?

Avoid:
- Speculation or assumptions
- Redundant information
- Overly generic descriptions''',
    constraints=[
        'Maximum 150 words',
        'Must be factually grounded in source text',
        'Should integrate with existing summary if present',
    ],
    examples=[
        {
            'entity_name': 'Alice Chen',
            'context': 'Alice Chen, a senior researcher at Anthropic, published a paper on constitutional AI.',
            'existing_summary': '',
            'generated_summary': 'Alice Chen is a senior researcher at Anthropic, specializing in AI safety and alignment research. She has contributed to work on constitutional AI.',
        },
    ],
    metadata={
        'version': '1.0.0',
        'target_metric': 'summary_quality',
    },
)


def get_initial_templates() -> dict[str, PromptTemplate]:
    """Get all initial prompt templates."""
    return {
        'entity_extraction': ENTITY_EXTRACTION_TEMPLATE,
        'edge_extraction': EDGE_EXTRACTION_TEMPLATE,
        'resolution': RESOLUTION_TEMPLATE,
        'summary_generation': SUMMARY_GENERATION_TEMPLATE,
    }


def create_evolution_seeds(output_dir: str | Path) -> dict[str, Path]:
    """
    Create initial Python files for OpenEvolve to evolve.

    Args:
        output_dir: Directory to write seed files

    Returns:
        Dict mapping template name to file path
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = {}
    for name, template in get_initial_templates().items():
        path = output_dir / f'{name}_prompt.py'
        template.save(path)
        paths[name] = path

    logger.info(f'Created {len(paths)} evolution seed files in {output_dir}')
    return paths
