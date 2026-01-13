"""
Evolved prompt template: entity_extraction
Generated: 2026-01-10T18:45:21.755917+00:00

This file is evolved by OpenEvolve. The EXTRACTION_INSTRUCTION variable
contains the optimized prompt that will be injected into DSPy modules.
"""

# The main instruction to be evolved
# OpenEvolve will modify this to improve extraction quality
ENTITY_EXTRACTION_INSTRUCTION = """
Extract all named entities from the text. For each entity:
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
Avoid extracting generic terms or pronouns.
"""

# Alias for compatibility
instruction = ENTITY_EXTRACTION_INSTRUCTION

# Constraints (do not modify during evolution)
CONSTRAINTS = [
    "Entity names must appear in the source text",
    "Each entity must have exactly one type",
    "Do not extract pronouns or generic references"
]

# Few-shot examples (can be evolved)
EXAMPLES = [
    {
        "input": "Alice from Anthropic met with Bob at the AI conference in San Francisco.",
        "entities": [
            {
                "name": "Alice",
                "type": "Person"
            },
            {
                "name": "Anthropic",
                "type": "Organization"
            },
            {
                "name": "Bob",
                "type": "Person"
            },
            {
                "name": "AI conference",
                "type": "Event"
            },
            {
                "name": "San Francisco",
                "type": "Location"
            }
        ]
    }
]

# Metadata
METADATA = {
    "version": "1.0.0",
    "target_metric": "extraction_f1"
}
