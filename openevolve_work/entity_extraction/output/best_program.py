"""
Evolved prompt template: entity_extraction
Generated: 2026-01-10T17:05:41.389642+00:00

This file is evolved by OpenEvolve. The EXTRACTION_INSTRUCTION variable
contains the optimized prompt that will be injected into DSPy modules.
"""

# The main instruction to be evolved
# OpenEvolve will modify this to improve extraction quality
ENTITY_EXTRACTION_INSTRUCTION = """
Extract unique named entities with high precision, strict span fidelity, and atomic granularity.

### Core Extraction Rules:
1. **Span Integrity**: The 'name' must be a verbatim substring from the text. 
   - **Clean Boundaries**: Exclude leading/trailing punctuation (commas, periods, quotes) and possessive markers (e.g., extract "Apple" from "Apple's").
   - **Full Names**: Include formal titles (e.g., "Dr. Elena Garcia") and specific versions (e.g., "Python 3.11").
2. **Taxonomy Selection**: Assign exactly one type per entity:
    - **Person**: Named individuals and their formal titles.
    - **Organization**: Companies, agencies, institutions, or formal groups.
    - **Location**: Specific geographic places, facilities, or regions.
    - **Product**: Branded goods, specific software, hardware, or tools.
    - **Event**: Named occurrences, conferences, or time-bound meetings.
    - **Concept**: Specific named theories, protocols, or methodologies (e.g., "Zero Trust").
3. **Atomic Decomposition**: 
    - Break down nested references. For "the London office," extract "London" (Location). 
    - For "Google's BERT model," extract "Google" (Organization) and "BERT" (Product/Concept).
4. **Temporal Context**: Extract entities involved in temporal events, but do not include temporal markers (e.g., "2023," "Monday") in the entity name unless they are part of a formal title.
5. **Exclusions**: Strictly ignore pronouns, generic nouns (e.g., "the project"), and transient states.
"""

# Alias for compatibility
instruction = ENTITY_EXTRACTION_INSTRUCTION

# Constraints (do not modify during evolution)
CONSTRAINTS = [
    "Entity names must appear in the source text",
    "Each entity must have exactly one type",
    "Do not extract pronouns or generic references",
    "Exclude trailing punctuation and possessive markers from entity names"
]

# Few-shot examples (can be evolved)
EXAMPLES = [
    {
        "input": "Alice from Anthropic met with Bob at the AI conference in San Francisco.",
        "entities": [
            {"name": "Alice", "type": "Person"},
            {"name": "Anthropic", "type": "Organization"},
            {"name": "Bob", "type": "Person"},
            {"name": "AI conference", "type": "Event"},
            {"name": "San Francisco", "type": "Location"}
        ]
    },
    {
        "input": "During the 2024 Lisbon Summit, Dr. Elena Garcia unveiled Google's Aegis framework that NATO cyber units will pilot.",
        "entities": [
            {"name": "Lisbon Summit", "type": "Event"},
            {"name": "Dr. Elena Garcia", "type": "Person"},
            {"name": "Google", "type": "Organization"},
            {"name": "Aegis framework", "type": "Concept"},
            {"name": "NATO", "type": "Organization"}
        ]
    },
    {
        "input": "We are migrating our workflow to the Zero Trust Architecture using Python 3.11 at the Berlin office.",
        "entities": [
            {"name": "Zero Trust Architecture", "type": "Concept"},
            {"name": "Python 3.11", "type": "Product"},
            {"name": "Berlin", "type": "Location"}
        ]
    }
]

# Metadata
METADATA = {
    "version": "1.0.0",
    "target_metric": "extraction_f1"
}
