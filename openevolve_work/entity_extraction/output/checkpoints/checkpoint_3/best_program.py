"""
Evolved prompt template: entity_extraction
Generated: 2026-01-10T17:05:41.389642+00:00

This file is evolved by OpenEvolve. The EXTRACTION_INSTRUCTION variable
contains the optimized prompt that will be injected into DSPy modules.
"""

# The main instruction to be evolved
# OpenEvolve will modify this to improve extraction quality
ENTITY_EXTRACTION_INSTRUCTION = """
You are an entity extraction specialist. Given any text (single utterance or conversation):
1. Read the entire passage before extracting.
2. Copy each explicit named entity exactly as written in the text.
3. Assign exactly one type chosen from [Person, Organization, Location, Product, Event, Concept].
4. Prefer the most specific supported type (e.g., "AI Summit" -> Event, "Northwind Research Lab" -> Organization).
5. When multiple mentions describe the same entity, output one object using the most complete surface form.
6. Ignore pronouns, vague mentions ("the team", "our office"), code names without expansion, or entities not fully spelled out.
7. Return the answer as valid JSON: [{"name": "...", "type": "..."}]. Use [] if no entities qualify.
8. Use prior messages only to disambiguate what was stated, never to invent new entities.

Focus on:
- People (names, honorifics, name + title combinations)
- Organizations (companies, institutions, coalitions, teams)
- Locations (geographic areas, facilities with proper names)
- Products (software, hardware, named services)
- Events (scheduled happenings, initiatives, incidents)
- Concepts (recognized theories, methodologies, frameworks)

Quality checklist:
- Surface form must appear verbatim.
- Keep multi-word entities intact unless the text splits them.
- Maintain the order of first appearance.
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
    },
    {
        "input": "Yesterday, Dr. Maria Lopez briefed the NASA Artemis task force while visiting the Kennedy Space Center in Florida.",
        "entities": [
            {
                "name": "Dr. Maria Lopez",
                "type": "Person"
            },
            {
                "name": "NASA",
                "type": "Organization"
            },
            {
                "name": "Artemis task force",
                "type": "Organization"
            },
            {
                "name": "Kennedy Space Center",
                "type": "Location"
            },
            {
                "name": "Florida",
                "type": "Location"
            }
        ]
    },
    {
        "input": "Q: Did you send the proposal to Delta Analytics in Berlin? A: Yes, I emailed it to Delta Analytics and cc'd Prof. Erik Voss.",
        "entities": [
            {
                "name": "Delta Analytics",
                "type": "Organization"
            },
            {
                "name": "Berlin",
                "type": "Location"
            },
            {
                "name": "Prof. Erik Voss",
                "type": "Person"
            }
        ]
    }
]

# Metadata
METADATA = {
    "version": "1.0.0",
    "target_metric": "extraction_f1"
}
