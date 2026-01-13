"""
Copyright 2024, Zep Software, Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import json
from typing import Any, Protocol, TypedDict

from pydantic import BaseModel, Field

from ..utils.prompt_utils import enforce_max_prompt_tokens
from .models import Message, PromptFunction, PromptVersion


class ExtractedEntity(BaseModel):
    name: str = Field(..., description='Name of the extracted entity')
    entity_type_id: int = Field(
        description='ID of the classified entity type. '
        'Must be one of the provided entity_type_id integers.',
    )

    def __init__(self, **data):
        # Handle common LLM field name variations
        if 'entity_name' in data and 'name' not in data:
            data['name'] = data.pop('entity_name')
        if 'entityName' in data and 'name' not in data:
            data['name'] = data.pop('entityName')
        if 'entity_type' in data and 'entity_type_id' not in data:
            # Try to convert string type to id (default to 0)
            data['entity_type_id'] = 0
            data.pop('entity_type')
        super().__init__(**data)


class ExtractedEntities(BaseModel):
    extracted_entities: list[ExtractedEntity] = Field(..., description='List of extracted entities')


class MissedEntities(BaseModel):
    missed_entities: list[str] = Field(..., description="Names of entities that weren't extracted")


class EntityClassificationTriple(BaseModel):
    uuid: str = Field(description='UUID of the entity')
    name: str = Field(description='Name of the entity')
    entity_type: str | None = Field(
        default=None, description='Type of the entity. Must be one of the provided types or None'
    )


class EntityClassification(BaseModel):
    entity_classifications: list[EntityClassificationTriple] = Field(
        ..., description='List of entities classification triples.'
    )


class Prompt(Protocol):
    extract_message: PromptVersion
    extract_json: PromptVersion
    extract_text: PromptVersion
    reflexion: PromptVersion
    classify_nodes: PromptVersion
    extract_attributes: PromptVersion


class Versions(TypedDict):
    extract_message: PromptFunction
    extract_json: PromptFunction
    extract_text: PromptFunction
    reflexion: PromptFunction
    classify_nodes: PromptFunction
    extract_attributes: PromptFunction


def extract_message(context: dict[str, Any]) -> list[Message]:
    # Apply defensive prompt clipping (this already handles previous_episodes)
    context = enforce_max_prompt_tokens(context)

    sys_prompt = """You are an AI assistant that extracts entity nodes from conversational messages.
    Your primary task is to extract unique named entities with high precision, strict span fidelity, and atomic granularity."""

    # Import safe serializer for datetime handling
    from graphiti_core.utils.prompt_utils import safe_json_dumps

    user_prompt = f"""
<PREVIOUS MESSAGES>
{safe_json_dumps(context.get('previous_episodes', []))}
</PREVIOUS MESSAGES>

<CURRENT MESSAGE>
{context['episode_content']}
</CURRENT MESSAGE>

<ENTITY TYPES>
{context['entity_types']}
</ENTITY TYPES>

Instructions:

You are given a conversation context and a CURRENT MESSAGE. Your task is to extract **entity nodes** mentioned **explicitly or implicitly** in the CURRENT MESSAGE.
Pronoun references such as he/she/they or this/that/those should be disambiguated to the names of the reference entities.

### Core Extraction Rules:

1. **Speaker Extraction**: Always extract the speaker (the part before the colon `:` in each dialogue line) as the first entity node.
   - If the speaker is mentioned again in the message, treat both mentions as a **single entity**.

2. **Span Integrity**: The entity name must be a verbatim substring from the text.
   - **Clean Boundaries**: Exclude leading/trailing punctuation (commas, periods, quotes) and possessive markers (e.g., extract "Apple" from "Apple's").
   - **Full Names**: Include formal titles (e.g., "Dr. Elena Garcia") and specific versions (e.g., "Python 3.11").

3. **Entity Classification**:
   - Use the descriptions in ENTITY TYPES to classify each extracted entity.
   - Assign exactly one `entity_type_id` per entity.

4. **Atomic Decomposition**:
   - Break down nested references. For "the London office," extract "London" (Location).
   - For "Google's BERT model," extract "Google" (Organization) and "BERT" (Product/Concept) separately.

5. **Required Entity Names**:
   - **CRITICAL**: Every entity MUST have a clear, specific, non-empty name.
   - Do NOT extract entities that cannot be given a meaningful name.
   - Generic terms like "container", "service", "system" without specific identifiers should be avoided.

6. **Exclusions**:
   - Do NOT extract entities representing relationships or actions.
   - Do NOT extract dates, times, or other temporal information—these will be handled separately.
   - Do NOT extract pronouns, generic nouns (e.g., "the project"), or transient states.
   - **Exclude** entities mentioned only in the PREVIOUS MESSAGES (they are for context only).

{context['custom_prompt']}
"""
    return [
        Message(role='system', content=sys_prompt),
        Message(role='user', content=user_prompt),
    ]


def extract_json(context: dict[str, Any]) -> list[Message]:
    sys_prompt = """You are an AI assistant that extracts entity nodes from JSON.
    Your primary task is to extract and classify relevant entities from JSON files with high precision, strict span fidelity, and atomic granularity."""

    user_prompt = f"""
<SOURCE DESCRIPTION>:
{context['source_description']}
</SOURCE DESCRIPTION>
<JSON>
{context['episode_content']}
</JSON>
<ENTITY TYPES>
{context['entity_types']}
</ENTITY TYPES>

{context['custom_prompt']}

Given the above source description and JSON, extract relevant entities from the provided JSON.
For each entity extracted, also determine its entity type based on the provided ENTITY TYPES and their descriptions.
Indicate the classified entity type by providing its entity_type_id.

Guidelines:
1. Always try to extract entities that the JSON represents. This will often be something like a "name" or "user" field.
2. **Span Integrity**: The entity name must be a verbatim substring from the JSON values.
   - **Clean Boundaries**: Exclude leading/trailing punctuation (commas, periods, quotes) and possessive markers (e.g., extract "Apple" from "Apple's").
   - **Full Names**: Include formal titles (e.g., "Dr. Elena Garcia") and specific versions (e.g., "Python 3.11").
3. **Atomic Decomposition**:
   - Break down nested references. For "the London office," extract "London" (Location).
   - For "Google's BERT model," extract "Google" (Organization) and "BERT" (Product/Concept) separately.
4. Do NOT extract any properties that contain dates or temporal information.
5. **CRITICAL**: Every entity MUST have a clear, specific, non-empty name. Do NOT extract entities that cannot be given a meaningful name.
6. If you cannot determine a specific name for an entity, skip it entirely rather than using generic terms.
7. **Exclusions**: Do NOT extract pronouns, generic nouns (e.g., "the project"), or transient states.
"""
    return [
        Message(role='system', content=sys_prompt),
        Message(role='user', content=user_prompt),
    ]


def extract_text(context: dict[str, Any]) -> list[Message]:
    sys_prompt = """You are an AI assistant that extracts entity nodes from text.
    Your primary task is to extract and classify significant entities with high precision, strict span fidelity, and atomic granularity."""

    user_prompt = f"""
<TEXT>
{context['episode_content']}
</TEXT>
<ENTITY TYPES>
{context['entity_types']}
</ENTITY TYPES>

Given the above text, extract entities from the TEXT that are explicitly or implicitly mentioned.
For each entity extracted, also determine its entity type based on the provided ENTITY TYPES and their descriptions.
Indicate the classified entity type by providing its entity_type_id.

{context['custom_prompt']}

Guidelines:
1. Extract significant entities, concepts, or actors mentioned in the text.
2. **Span Integrity**: The entity name must be a verbatim substring from the text.
   - **Clean Boundaries**: Exclude leading/trailing punctuation (commas, periods, quotes) and possessive markers (e.g., extract "Apple" from "Apple's").
   - **Full Names**: Include formal titles (e.g., "Dr. Elena Garcia") and specific versions (e.g., "Python 3.11").
3. **Atomic Decomposition**:
   - Break down nested references. For "the London office," extract "London" (Location).
   - For "Google's BERT model," extract "Google" (Organization) and "BERT" (Product/Concept) separately.
4. Avoid creating nodes for relationships or actions.
5. Avoid creating nodes for temporal information like dates, times or years (these will be added to edges later).
6. Be as explicit as possible in your node names, using full names and avoiding abbreviations.
7. **CRITICAL**: Every entity MUST have a clear, specific, non-empty name. Do NOT extract entities that cannot be given a meaningful name.
8. If you cannot determine a specific name for an entity, skip it entirely rather than using generic terms.
9. **Exclusions**: Do NOT extract pronouns, generic nouns (e.g., "the project"), or transient states.
"""
    return [
        Message(role='system', content=sys_prompt),
        Message(role='user', content=user_prompt),
    ]


def reflexion(context: dict[str, Any]) -> list[Message]:
    sys_prompt = """You are an AI assistant that determines which entities have not been extracted from the given context"""

    user_prompt = f"""
<PREVIOUS MESSAGES>
{json.dumps([ep for ep in context['previous_episodes']], indent=2)}
</PREVIOUS MESSAGES>
<CURRENT MESSAGE>
{context['episode_content']}
</CURRENT MESSAGE>

<EXTRACTED ENTITIES>
{context['extracted_entities']}
</EXTRACTED ENTITIES>

Given the above previous messages, current message, and list of extracted entities; determine if any entities haven't been
extracted.
"""
    return [
        Message(role='system', content=sys_prompt),
        Message(role='user', content=user_prompt),
    ]


def classify_nodes(context: dict[str, Any]) -> list[Message]:
    sys_prompt = """You are an AI assistant that classifies entity nodes given the context from which they were extracted"""

    user_prompt = f"""
    <PREVIOUS MESSAGES>
    {json.dumps([ep for ep in context['previous_episodes']], indent=2)}
    </PREVIOUS MESSAGES>
    <CURRENT MESSAGE>
    {context['episode_content']}
    </CURRENT MESSAGE>
    
    <EXTRACTED ENTITIES>
    {context['extracted_entities']}
    </EXTRACTED ENTITIES>
    
    <ENTITY TYPES>
    {context['entity_types']}
    </ENTITY TYPES>
    
    Given the above conversation, extracted entities, and provided entity types and their descriptions, classify the extracted entities.
    
    Guidelines:
    1. Each entity must have exactly one type
    2. Only use the provided ENTITY TYPES as types, do not use additional types to classify entities.
    3. If none of the provided entity types accurately classify an extracted node, the type should be set to None
"""
    return [
        Message(role='system', content=sys_prompt),
        Message(role='user', content=user_prompt),
    ]


def extract_attributes(context: dict[str, Any]) -> list[Message]:
    # Import safe serializer for datetime handling
    from graphiti_core.utils.prompt_utils import safe_json_dumps

    return [
        Message(
            role='system',
            content="""You are a JSON extraction assistant. You MUST respond with ONLY a valid JSON object.

CRITICAL RULES:
- Output ONLY a single JSON object - no explanations, no markdown, no extra text
- Do not wrap the JSON in code blocks or backticks
- Do not output multiple JSON objects
- Do not include any text before or after the JSON
- The response must be parseable by json.loads() directly""",
        ),
        Message(
            role='user',
            content=f"""Extract entity properties from the provided text and return them as a JSON object.

<MESSAGES>
{safe_json_dumps(context['previous_episodes'])}
{safe_json_dumps(context['episode_content'])}
</MESSAGES>

Given the above MESSAGES and the following ENTITY, update any of its attributes based on the information provided
in MESSAGES. Use the provided attribute descriptions to better understand how each attribute should be determined.

Guidelines:
1. Do not hallucinate entity property values if they cannot be found in the current context.
2. Only use the provided MESSAGES and ENTITY to set attribute values.
3. The summary attribute represents a summary of the ENTITY, and should be updated with new information about the Entity from the MESSAGES.
    Summaries must be no longer than 250 words.
4. Return ONLY the JSON object with the extracted attributes - no other text.

<ENTITY>
{context['node']}
</ENTITY>
""",
        ),
    ]


versions: Versions = {
    'extract_message': extract_message,
    'extract_json': extract_json,
    'extract_text': extract_text,
    'reflexion': reflexion,
    'classify_nodes': classify_nodes,
    'extract_attributes': extract_attributes,
}
