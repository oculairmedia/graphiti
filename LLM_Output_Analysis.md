# Graphiti LLM Prompts Comprehensive Reference

This document contains all the prompts used to drive Graphiti's knowledge graph construction and maintenance.

## Table of Contents
1. [Entity Extraction Prompts](#entity-extraction-prompts)
2. [Edge Extraction Prompts](#edge-extraction-prompts)
3. [Deduplication Prompts](#deduplication-prompts)
4. [Summarization Prompts](#summarization-prompts)
5. [Temporal Processing Prompts](#temporal-processing-prompts)
6. [Evaluation Prompts](#evaluation-prompts)
7. [LLM Output Length Analysis](#llm-output-length-analysis)

---

## Entity Extraction Prompts

### 1. Extract Message Entities
**File:** `graphiti_core/prompts/extract_nodes.py`
**Function:** `extract_message()`

**System Prompt:**
```
You are an AI assistant that extracts entity nodes from conversational messages.
Your primary task is to extract and classify the speaker and other significant entities mentioned in the conversation.
```

**User Prompt Template:**
```
<PREVIOUS MESSAGES>
{previous_episodes}
</PREVIOUS MESSAGES>

<CURRENT MESSAGE>
{episode_content}
</CURRENT MESSAGE>

<ENTITY TYPES>
{entity_types}
</ENTITY TYPES>

Instructions:

You are given a conversation context and a CURRENT MESSAGE. Your task is to extract **entity nodes** mentioned **explicitly or implicitly** in the CURRENT MESSAGE.
Pronoun references such as he/she/they or this/that/those should be disambiguated to the names of the
reference entities.

1. **Speaker Extraction**: Always extract the speaker (the part before the colon `:` in each dialogue line) as the first entity node.
   - If the speaker is mentioned again in the message, treat both mentions as a **single entity**.

2. **Entity Identification**:
   - Extract all significant entities, concepts, or actors that are **explicitly or implicitly** mentioned in the CURRENT MESSAGE.
   - **Exclude** entities mentioned only in the PREVIOUS MESSAGES (they are for context only).

3. **Entity Classification**:
   - Use the descriptions in ENTITY TYPES to classify each extracted entity.
   - Assign the appropriate `entity_type_id` for each one.

4. **Exclusions**:
   - Do NOT extract entities representing relationships or actions.
   - Do NOT extract dates, times, or other temporal information—these will be handled separately.

5. **Formatting**:
   - Be **explicit and unambiguous** in naming entities (e.g., use full names when available).

{custom_prompt}
```

### 2. Extract Text Entities
**Function:** `extract_text()`

**System Prompt:**
```
You are an AI assistant that extracts entity nodes from text.
Your primary task is to extract and classify the speaker and other significant entities mentioned in the provided text.
```

**User Prompt Template:**
```
<TEXT>
{episode_content}
</TEXT>
<ENTITY TYPES>
{entity_types}
</ENTITY TYPES>

Given the above text, extract entities from the TEXT that are explicitly or implicitly mentioned.
For each entity extracted, also determine its entity type based on the provided ENTITY TYPES and their descriptions.
Indicate the classified entity type by providing its entity_type_id.

{custom_prompt}

Guidelines:
1. Extract significant entities, concepts, or actors mentioned in the conversation.
2. Avoid creating nodes for relationships or actions.
3. Avoid creating nodes for temporal information like dates, times or years (these will be added to edges later).
4. Be as explicit as possible in your node names, using full names and avoiding abbreviations.
```

### 3. Extract JSON Entities
**Function:** `extract_json()`

**System Prompt:**
```
You are an AI assistant that extracts entity nodes from JSON.
Your primary task is to extract and classify relevant entities from JSON files
```

**User Prompt Template:**
```
<SOURCE DESCRIPTION>:
{source_description}
</SOURCE DESCRIPTION>
<JSON>
{episode_content}
</JSON>
<ENTITY TYPES>
{entity_types}
</ENTITY TYPES>

{custom_prompt}

Given the above source description and JSON, extract relevant entities from the provided JSON.
For each entity extracted, also determine its entity type based on the provided ENTITY TYPES and their descriptions.
Indicate the classified entity type by providing its entity_type_id.

Guidelines:
1. Always try to extract an entities that the JSON represents. This will often be something like a "name" or "user field
2. Do NOT extract any properties that contain dates
```

### 4. Entity Reflexion (Missing Entities)
**Function:** `reflexion()`

**System Prompt:**
```
You are an AI assistant that determines which entities have not been extracted from the given context
```

**User Prompt Template:**
```
<PREVIOUS MESSAGES>
{previous_episodes}
</PREVIOUS MESSAGES>
<CURRENT MESSAGE>
{episode_content}
</CURRENT MESSAGE>

<EXTRACTED ENTITIES>
{extracted_entities}
</EXTRACTED ENTITIES>

Given the above previous messages, current message, and list of extracted entities; determine if any entities haven't been
extracted.
```

### 5. Classify Nodes
**Function:** `classify_nodes()`

**System Prompt:**
```
You are an AI assistant that classifies entity nodes given the context from which they were extracted
```

**User Prompt Template:**
```
<PREVIOUS MESSAGES>
{previous_episodes}
</PREVIOUS MESSAGES>
<CURRENT MESSAGE>
{episode_content}
</CURRENT MESSAGE>

<EXTRACTED ENTITIES>
{extracted_entities}
</EXTRACTED ENTITIES>

<ENTITY TYPES>
{entity_types}
</ENTITY TYPES>

Given the above conversation, extracted entities, and provided entity types and their descriptions, classify the extracted entities.

Guidelines:
1. Each entity must have exactly one type
2. Only use the provided ENTITY TYPES as types, do not use additional types to classify entities.
3. If none of the provided entity types accurately classify an extracted node, the type should be set to None
```

### 6. Extract Entity Attributes
**Function:** `extract_attributes()`

**System Prompt:**
```
You are a helpful assistant that extracts entity properties from the provided text.
```

**User Prompt Template:**
```
<MESSAGES>
{previous_episodes}
{episode_content}
</MESSAGES>

Given the above MESSAGES and the following ENTITY, update any of its attributes based on the information provided
in MESSAGES. Use the provided attribute descriptions to better understand how each attribute should be determined.

Guidelines:
1. Do not hallucinate entity property values if they cannot be found in the current context.
2. Only use the provided MESSAGES and ENTITY to set attribute values.
3. The summary attribute represents a summary of the ENTITY, and should be updated with new information about the Entity from the MESSAGES.
    Summaries must be no longer than 250 words.

<ENTITY>
{node}
</ENTITY>
```

---

## Edge Extraction Prompts

### 1. Extract Fact Edges
**File:** `graphiti_core/prompts/extract_edges.py`
**Function:** `edge()`

**System Prompt:**
```
You are an expert fact extractor that extracts fact triples from text.
1. Extracted fact triples should also be extracted with relevant date information.
2. Treat the CURRENT TIME as the time the CURRENT MESSAGE was sent. All temporal information should be extracted relative to this time.
```

**User Prompt Template:**
```
<PREVIOUS_MESSAGES>
{previous_episodes}
</PREVIOUS_MESSAGES>

<CURRENT_MESSAGE>
{episode_content}
</CURRENT_MESSAGE>

<ENTITIES>
{nodes}
</ENTITIES>

<REFERENCE_TIME>
{reference_time}  # ISO 8601 (UTC); used to resolve relative time mentions
</REFERENCE_TIME>

<FACT TYPES>
{edge_types}
</FACT TYPES>

# TASK
Extract all factual relationships between the given ENTITIES based on the CURRENT MESSAGE.
Only extract facts that:
- involve two DISTINCT ENTITIES from the ENTITIES list,
- are clearly stated or unambiguously implied in the CURRENT MESSAGE,
    and can be represented as edges in a knowledge graph.
- The FACT TYPES provide a list of the most important types of facts, make sure to extract facts of these types
- The FACT TYPES are not an exhaustive list, extract all facts from the message even if they do not fit into one
    of the FACT TYPES
- The FACT TYPES each contain their fact_type_signature which represents the source and target entity types.

You may use information from the PREVIOUS MESSAGES only to disambiguate references or support continuity.

{custom_prompt}

# EXTRACTION RULES

1. Only emit facts where both the subject and object match IDs in ENTITIES.
2. Each fact must involve two **distinct** entities.
3. Use a SCREAMING_SNAKE_CASE string as the `relation_type` (e.g., FOUNDED, WORKS_AT).
4. Do not emit duplicate or semantically redundant facts.
5. The `fact_text` should quote or closely paraphrase the original source sentence(s).
6. Use `REFERENCE_TIME` to resolve vague or relative temporal expressions (e.g., "last week").
7. Do **not** hallucinate or infer temporal bounds from unrelated events.

# DATETIME RULES

- Use ISO 8601 with "Z" suffix (UTC) (e.g., 2025-04-30T00:00:00Z).
- If the fact is ongoing (present tense), set `valid_at` to REFERENCE_TIME.
- If a change/termination is expressed, set `invalid_at` to the relevant timestamp.
- Leave both fields `null` if no explicit or resolvable time is stated.
- If only a date is mentioned (no time), assume 00:00:00.
- If only a year is mentioned, use January 1st at 00:00:00.
```

### 2. Edge Reflexion (Missing Facts)
**Function:** `reflexion()`

**System Prompt:**
```
You are an AI assistant that determines which facts have not been extracted from the given context
```

**User Prompt Template:**
```
<PREVIOUS MESSAGES>
{previous_episodes}
</PREVIOUS MESSAGES>
<CURRENT MESSAGE>
{episode_content}
</CURRENT MESSAGE>

<EXTRACTED ENTITIES>
{nodes}
</EXTRACTED ENTITIES>

<EXTRACTED FACTS>
{extracted_facts}
</EXTRACTED FACTS>

Given the above MESSAGES, list of EXTRACTED ENTITIES entities, and list of EXTRACTED FACTS;
determine if any facts haven't been extracted.
```

### 3. Extract Edge Attributes
**Function:** `extract_attributes()`

**System Prompt:**
```
You are a helpful assistant that extracts fact properties from the provided text.
```

**User Prompt Template:**
```
<MESSAGE>
{episode_content}
</MESSAGE>
<REFERENCE TIME>
{reference_time}
</REFERENCE TIME>

Given the above MESSAGE, its REFERENCE TIME, and the following FACT, update any of its attributes based on the information provided
in MESSAGE. Use the provided attribute descriptions to better understand how each attribute should be determined.

Guidelines:
1. Do not hallucinate entity property values if they cannot be found in the current context.
2. Only use the provided MESSAGES and FACT to set attribute values.

<FACT>
{fact}
</FACT>
```

---

## LLM Output Length Analysis

### Problem Summary
The error occurs during `extract_attributes_from_node` where the LLM generates responses exceeding the 8192 token limit:
```
Output length exceeded max tokens 8192: Could not parse response content as the length limit was reached
CompletionUsage(completion_tokens=4000, prompt_tokens=381, total_tokens=4381)
```

### Root Cause Analysis

## Deduplication Prompts

### 1. Dedupe Single Node
**File:** `graphiti_core/prompts/dedupe_nodes.py`
**Function:** `node()`

**System Prompt:**
```
You are a helpful assistant that determines whether or not a NEW ENTITY is a duplicate of any EXISTING ENTITIES.
```

**User Prompt Template:**
```
<PREVIOUS MESSAGES>
{previous_episodes}
</PREVIOUS MESSAGES>
<CURRENT MESSAGE>
{episode_content}
</CURRENT MESSAGE>
<NEW ENTITY>
{extracted_node}
</NEW ENTITY>
<ENTITY TYPE DESCRIPTION>
{entity_type_description}
</ENTITY TYPE DESCRIPTION>

<EXISTING ENTITIES>
{existing_nodes}
</EXISTING ENTITIES>

Given the above EXISTING ENTITIES and their attributes, MESSAGE, and PREVIOUS MESSAGES; Determine if the NEW ENTITY extracted from the conversation
is a duplicate entity of one of the EXISTING ENTITIES.

Entities should only be considered duplicates if they refer to the *same real-world object or concept*.
Semantic Equivalence: if a descriptive label in existing_entities clearly refers to a named entity in context, treat them as duplicates.

Do NOT mark entities as duplicates if:
- They are related but distinct.
- They have similar names or purposes but refer to separate instances or concepts.

 TASK:
 1. Compare `new_entity` against each item in `existing_entities`.
 2. If it refers to the same real‐world object or concept, collect its index.
 3. Let `duplicate_idx` = the *first* collected index, or –1 if none.
 4. Let `duplicates` = the list of *all* collected indices (empty list if none).

Also return the full name of the NEW ENTITY (whether it is the name of the NEW ENTITY, a node it
is a duplicate of, or a combination of the two).
```

### 2. Dedupe Multiple Nodes
**Function:** `nodes()`

**System Prompt:**
```
You are a helpful assistant that determines whether or not ENTITIES extracted from a conversation are duplicates of existing entities.
```

**User Prompt Template:**
```
<PREVIOUS MESSAGES>
{previous_episodes}
</PREVIOUS MESSAGES>
<CURRENT MESSAGE>
{episode_content}
</CURRENT MESSAGE>

Each of the following ENTITIES were extracted from the CURRENT MESSAGE.
Each entity in ENTITIES is represented as a JSON object with the following structure:
{
    id: integer id of the entity,
    name: "name of the entity",
    entity_type: "ontological classification of the entity",
    entity_type_description: "Description of what the entity type represents",
    duplication_candidates: [
        {
            idx: integer index of the candidate entity,
            name: "name of the candidate entity",
            entity_type: "ontological classification of the candidate entity",
            ...<additional attributes>
        }
    ]
}

<ENTITIES>
{extracted_nodes}
</ENTITIES>

<EXISTING ENTITIES>
{existing_nodes}
</EXISTING ENTITIES>

For each of the above ENTITIES, determine if the entity is a duplicate of any of the EXISTING ENTITIES.

Entities should only be considered duplicates if they refer to the *same real-world object or concept*.

Do NOT mark entities as duplicates if:
- They are related but distinct.
- They have similar names or purposes but refer to separate instances or concepts.

Task:
Your response will be a list called entity_resolutions which contains one entry for each entity.

For each entity, return the id of the entity as id, the name of the entity as name, and the duplicate_idx
as an integer.

- If an entity is a duplicate of one of the EXISTING ENTITIES, return the idx of the candidate it is a
duplicate of.
- If an entity is not a duplicate of one of the EXISTING ENTITIES, return the -1 as the duplication_idx
```

### 3. Dedupe Node List
**Function:** `node_list()`

**System Prompt:**
```
You are a helpful assistant that de-duplicates nodes from node lists.
```

**User Prompt Template:**
```
Given the following context, deduplicate a list of nodes:

Nodes:
{nodes}

Task:
1. Group nodes together such that all duplicate nodes are in the same list of uuids
2. All duplicate uuids should be grouped together in the same list
3. Also return a new summary that synthesizes the summary into a new short summary

Guidelines:
1. Each uuid from the list of nodes should appear EXACTLY once in your response
2. If a node has no duplicates, it should appear in the response in a list of only one uuid

Respond with a JSON object in the following format:
{
    "nodes": [
        {
            "uuids": ["5d643020624c42fa9de13f97b1b3fa39", "node that is a duplicate of 5d643020624c42fa9de13f97b1b3fa39"],
            "summary": "Brief summary of the node summaries that appear in the list of names."
        }
    ]
}
```

### 4. Dedupe Single Edge
**File:** `graphiti_core/prompts/dedupe_edges.py`
**Function:** `edge()`

**System Prompt:**
```
You are a helpful assistant that de-duplicates edges from edge lists.
```

**User Prompt Template:**
```
Given the following context, determine whether the New Edge represents any of the edges in the list of Existing Edges.

<EXISTING EDGES>
{related_edges}
</EXISTING EDGES>

<NEW EDGE>
{extracted_edges}
</NEW EDGE>

Task:
If the New Edges represents the same factual information as any edge in Existing Edges, return the id of the duplicate fact
    as part of the list of duplicate_facts.
If the NEW EDGE is not a duplicate of any of the EXISTING EDGES, return an empty list.

Guidelines:
1. The facts do not need to be completely identical to be duplicates, they just need to express the same information.
```

### 5. Dedupe Edge List
**Function:** `edge_list()`

**System Prompt:**
```
You are a helpful assistant that de-duplicates edges from edge lists.
```

**User Prompt Template:**
```
Given the following context, find all of the duplicates in a list of facts:

Facts:
{edges}

Task:
If any facts in Facts is a duplicate of another fact, return a new fact with one of their uuid's.

Guidelines:
1. identical or near identical facts are duplicates
2. Facts are also duplicates if they are represented by similar sentences
3. Facts will often discuss the same or similar relation between identical entities
4. The final list should have only unique facts. If 3 facts are all duplicates of each other, only one of their
    facts should be in the response
```

### 6. Resolve Edge Duplicates
**Function:** `resolve_edge()`

**System Prompt:**
```
You are a helpful assistant that de-duplicates facts from fact lists and determines which existing facts are contradicted by the new fact.
```

**User Prompt Template:**
```
<NEW FACT>
{new_edge}
</NEW FACT>

<EXISTING FACTS>
{existing_edges}
</EXISTING FACTS>
<FACT INVALIDATION CANDIDATES>
{edge_invalidation_candidates}
</FACT INVALIDATION CANDIDATES>

<FACT TYPES>
{edge_types}
</FACT TYPES>

Task:
If the NEW FACT represents identical factual information of one or more in EXISTING FACTS, return the idx of the duplicate facts.
Facts with similar information that contain key differences should not be marked as duplicates.
If the NEW FACT is not a duplicate of any of the EXISTING FACTS, return an empty list.

Given the predefined FACT TYPES, determine if the NEW FACT should be classified as one of these types.
Return the fact type as fact_type or DEFAULT if NEW FACT is not one of the FACT TYPES.

Based on the provided FACT INVALIDATION CANDIDATES and NEW FACT, determine which existing facts the new fact contradicts.
Return a list containing all idx's of the facts that are contradicted by the NEW FACT.
If there are no contradicted facts, return an empty list.

Guidelines:
1. Some facts may be very similar but will have key differences, particularly around numeric values in the facts.
    Do not mark these facts as duplicates.
```

---

## Summarization Prompts

### 1. Summarize Pair
**File:** `graphiti_core/prompts/summarize_nodes.py`
**Function:** `summarize_pair()`

**System Prompt:**
```
You are a helpful assistant that combines summaries.
```

**User Prompt Template:**
```
Synthesize the information from the following two summaries into a single succinct summary.

Summaries must be under 250 words.

Summaries:
{node_summaries}
```

### 2. Summarize Context
**Function:** `summarize_context()`

**System Prompt:**
```
You are a helpful assistant that extracts entity properties from the provided text.
```

**User Prompt Template:**
```
<MESSAGES>
{previous_episodes}
{episode_content}
</MESSAGES>

Given the above MESSAGES and the following ENTITY name, create a summary for the ENTITY. Your summary must only use
information from the provided MESSAGES. Your summary should also only contain information relevant to the
provided ENTITY. Summaries must be under 250 words.

In addition, extract any values for the provided entity properties based on their descriptions.
If the value of the entity property cannot be found in the current context, set the value of the property to the Python value None.

Guidelines:
1. Do not hallucinate entity property values if they cannot be found in the current context.
2. Only use the provided messages, entity, and entity context to set attribute values.

<ENTITY>
{node_name}
</ENTITY>

<ENTITY CONTEXT>
{node_summary}
</ENTITY CONTEXT>

<ATTRIBUTES>
{attributes}
</ATTRIBUTES>
```

### 3. Summary Description
**Function:** `summary_description()`

**System Prompt:**
```
You are a helpful assistant that describes provided contents in a single sentence.
```

**User Prompt Template:**
```
Create a short one sentence description of the summary that explains what kind of information is summarized.
Summaries must be under 250 words.

Summary:
{summary}
```

---

## Temporal Processing Prompts

### 1. Extract Edge Dates
**File:** `graphiti_core/prompts/extract_edge_dates.py`
**Function:** `v1()`

**System Prompt:**
```
You are an AI assistant that extracts datetime information for graph edges, focusing only on dates directly related to the establishment or change of the relationship described in the edge fact.
```

**User Prompt Template:**
```
<PREVIOUS MESSAGES>
{previous_episodes}
</PREVIOUS MESSAGES>
<CURRENT MESSAGE>
{current_episode}
</CURRENT MESSAGE>
<REFERENCE TIMESTAMP>
{reference_timestamp}
</REFERENCE TIMESTAMP>

<FACT>
{edge_fact}
</FACT>

IMPORTANT: Only extract time information if it is part of the provided fact. Otherwise ignore the time mentioned. Make sure to do your best to determine the dates if only the relative time is mentioned. (eg 10 years ago, 2 mins ago) based on the provided reference timestamp
If the relationship is not of spanning nature, but you are still able to determine the dates, set the valid_at only.
Definitions:
- valid_at: The date and time when the relationship described by the edge fact became true or was established.
- invalid_at: The date and time when the relationship described by the edge fact stopped being true or ended.

Task:
Analyze the conversation and determine if there are dates that are part of the edge fact. Only set dates if they explicitly relate to the formation or alteration of the relationship itself.

Guidelines:
1. Use ISO 8601 format (YYYY-MM-DDTHH:MM:SS.SSSSSSZ) for datetimes.
2. Use the reference timestamp as the current time when determining the valid_at and invalid_at dates.
3. If the fact is written in the present tense, use the Reference Timestamp for the valid_at date
4. If no temporal information is found that establishes or changes the relationship, leave the fields as null.
5. Do not infer dates from related events. Only use dates that are directly stated to establish or change the relationship.
6. For relative time mentions directly related to the relationship, calculate the actual datetime based on the reference timestamp.
7. If only a date is mentioned without a specific time, use 00:00:00 (midnight) for that date.
8. If only year is mentioned, use January 1st of that year at 00:00:00.
9. Always include the time zone offset (use Z for UTC if no specific time zone is mentioned).
10. A fact discussing that something is no longer true should have a valid_at according to when the negated fact became true.
```

### 2. Invalidate Edges V1
**File:** `graphiti_core/prompts/invalidate_edges.py`
**Function:** `v1()`

**System Prompt:**
```
You are an AI assistant that helps determine which relationships in a knowledge graph should be invalidated based solely on explicit contradictions in newer information.
```

**User Prompt Template:**
```
Based on the provided existing edges and new edges with their timestamps, determine which relationships, if any, should be marked as expired due to contradictions or updates in the newer edges.
Use the start and end dates of the edges to determine which edges are to be marked expired.
Only mark a relationship as invalid if there is clear evidence from other edges that the relationship is no longer true.
Do not invalidate relationships merely because they weren't mentioned in the episodes. You may use the current episode and previous episodes as well as the facts of each edge to understand the context of the relationships.

Previous Episodes:
{previous_episodes}

Current Episode:
{current_episode}

Existing Edges (sorted by timestamp, newest first):
{existing_edges}

New Edges:
{new_edges}

Each edge is formatted as: "UUID | SOURCE_NODE - EDGE_NAME - TARGET_NODE (fact: EDGE_FACT), START_DATE (END_DATE, optional))"
```

### 3. Invalidate Edges V2
**Function:** `v2()`

**System Prompt:**
```
You are an AI assistant that determines which facts contradict each other.
```

**User Prompt Template:**
```
Based on the provided EXISTING FACTS and a NEW FACT, determine which existing facts the new fact contradicts.
Return a list containing all ids of the facts that are contradicted by the NEW FACT.
If there are no contradicted facts, return an empty list.

<EXISTING FACTS>
{existing_edges}
</EXISTING FACTS>

<NEW FACT>
{new_edge}
</NEW FACT>
```

---

## Evaluation Prompts

### 1. Query Expansion
**File:** `graphiti_core/prompts/eval.py`
**Function:** `query_expansion()`

**System Prompt:**
```
You are an expert at rephrasing questions into queries used in a database retrieval system
```

**User Prompt Template:**
```
Bob is asking Alice a question, are you able to rephrase the question into a simpler one about Alice in the third person
that maintains the relevant context?
<QUESTION>
{query}
</QUESTION>
```

### 2. QA Prompt
**Function:** `qa_prompt()`

**System Prompt:**
```
You are Alice and should respond to all questions from the first person perspective of Alice
```

**User Prompt Template:**
```
Your task is to briefly answer the question in the way that you think Alice would answer the question.
You are given the following entity summaries and facts to help you determine the answer to your question.
<ENTITY_SUMMARIES>
{entity_summaries}
</ENTITY_SUMMARIES>
<FACTS>
{facts}
</FACTS>
<QUESTION>
{query}
</QUESTION>
```

### 3. Evaluation Prompt
**Function:** `eval_prompt()`

**System Prompt:**
```
You are a judge that determines if answers to questions match a gold standard answer
```

**User Prompt Template:**
```
Given the QUESTION and the gold standard ANSWER determine if the RESPONSE to the question is correct or incorrect.
Although the RESPONSE may be more verbose, mark it as correct as long as it references the same topic
as the gold standard ANSWER. Also include your reasoning for the grade.
<QUESTION>
{query}
</QUESTION>
<ANSWER>
{answer}
</ANSWER>
<RESPONSE>
{response}
</RESPONSE>
```

### 4. Evaluate Add Episode Results
**Function:** `eval_add_episode_results()`

**System Prompt:**
```
You are a judge that determines whether a baseline graph building result from a list of messages is better
than a candidate graph building result based on the same messages.
```

**User Prompt Template:**
```
Given the following PREVIOUS MESSAGES and MESSAGE, determine if the BASELINE graph data extracted from the
conversation is higher quality than the CANDIDATE graph data extracted from the conversation.

Return False if the BASELINE extraction is better, and True otherwise. If the CANDIDATE extraction and
BASELINE extraction are nearly identical in quality, return True. Add your reasoning for your decision to the reasoning field

<PREVIOUS MESSAGES>
{previous_messages}
</PREVIOUS MESSAGES>
<MESSAGE>
{message}
</MESSAGE>

<BASELINE>
{baseline}
</BASELINE>

<CANDIDATE>
{candidate}
</CANDIDATE>
```

---

### 1. Token Limit Configuration

**File: `graphiti_core/llm_client/config.py`**
<augment_code_snippet path="graphiti_core/llm_client/config.py" mode="EXCERPT">
````python
DEFAULT_MAX_TOKENS = 8192
DEFAULT_TEMPERATURE = 0

class LLMConfig:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,  # ← 8192 token limit
        small_model: str | None = None,
    ):
````
</augment_code_snippet>

### 2. The Problematic Function: `extract_attributes_from_node`

**File: `graphiti_core/utils/maintenance/node_operations.py`**
<augment_code_snippet path="graphiti_core/utils/maintenance/node_operations.py" mode="EXCERPT">
````python
async def extract_attributes_from_node(
    llm_client: LLMClient,
    node: EntityNode,
    episode: EpisodicNode | None = None,
    previous_episodes: list[EpisodicNode] | None = None,  # ← Can be very large
    entity_type: BaseModel | None = None,
) -> EntityNode:
    # Context includes ALL previous episodes
    summary_context: dict[str, Any] = {
        'node': node_context,
        'episode_content': episode.content if episode is not None else '',
        'previous_episodes': [ep.content for ep in previous_episodes]  # ← PROBLEM
        if previous_episodes is not None
        else [],
    }

    # Dynamic Pydantic model creation for structured output
    unique_model_name = f'EntityAttributes_{uuid4().hex}'
    entity_attributes_model = pydantic.create_model(unique_model_name, **attributes_definitions)

    llm_response = await llm_client.generate_response(
        prompt_library.extract_nodes.extract_attributes(summary_context),
        response_model=entity_attributes_model,  # ← Complex JSON schema
        model_size=ModelSize.small,
    )
````
</augment_code_snippet>

### 3. The Verbose Prompt Template

**File: `graphiti_core/prompts/extract_nodes.py`**
<augment_code_snippet path="graphiti_core/prompts/extract_nodes.py" mode="EXCERPT">
````python
def extract_attributes(context: dict[str, Any]) -> list[Message]:
    return [
        Message(
            role='system',
            content='You are a helpful assistant that extracts entity properties from the provided text.',
        ),
        Message(
            role='user',
            content=f"""
        <MESSAGES>
        {json.dumps(context['previous_episodes'], indent=2)}  # ← ALL previous episodes
        {json.dumps(context['episode_content'], indent=2)}   # ← Current episode
        </MESSAGES>

        Given the above MESSAGES and the following ENTITY, update any of its attributes based on the information provided
        in MESSAGES. Use the provided attribute descriptions to better understand how each attribute should be determined.

        Guidelines:
        1. Do not hallucinate entity property values if they cannot be found in the current context.
        2. Only use the provided MESSAGES and ENTITY to set attribute values.
        3. The summary attribute represents a summary of the ENTITY, and should be updated with new information about the Entity from the MESSAGES. 
            Summaries must be no longer than 250 words.
        
        <ENTITY>
        {context['node']}  # ← Full entity context
        </ENTITY>
        """,
        ),
    ]
````
</augment_code_snippet>

### 4. JSON Schema Injection

**File: `graphiti_core/llm_client/openai_generic_client.py`**
<augment_code_snippet path="graphiti_core/llm_client/openai_generic_client.py" mode="EXCERPT">
````python
async def generate_response(
    self,
    messages: list[Message],
    response_model: type[BaseModel] | None = None,
    max_tokens: int | None = None,
    model_size: ModelSize = ModelSize.medium,
) -> dict[str, typing.Any]:
    if response_model is not None:
        serialized_model = json.dumps(response_model.model_json_schema())
        messages[-1].content += (
            f'\n\nRespond with a JSON object in the following format:\n\n{serialized_model}'  # ← Adds verbose schema
        )

    # Add multilingual extraction instructions
    messages[0].content += MULTILINGUAL_EXTRACTION_RESPONSES  # ← Additional text
````
</augment_code_snippet>

### 5. Multilingual Instructions Addition

**File: `graphiti_core/llm_client/client.py`**
<augment_code_snippet path="graphiti_core/llm_client/client.py" mode="EXCERPT">
````python
MULTILINGUAL_EXTRACTION_RESPONSES = (
    '\n\nAny extracted information should be returned in the same language as it was written in.'
)

# This gets added to EVERY prompt:
messages[0].content += MULTILINGUAL_EXTRACTION_RESPONSES
````
</augment_code_snippet>

### 6. Error Handling and Fallback

**File: `graphiti_core/llm_client/fallback_client.py`**
<augment_code_snippet path="graphiti_core/llm_client/fallback_client.py" mode="EXCERPT">
````python
class FallbackLLMClient(LLMClient):
    async def _generate_response(
        self,
        messages: list[Message],
        response_model: type[BaseModel] | None = None,
        max_tokens: int = 16384,  # ← Higher limit for fallback
        model_size: ModelSize = ModelSize.medium,
    ) -> dict[str, Any]:
        try:
            # Use fallback client
            result = await self.fallback_client._generate_response(
                messages, response_model, max_tokens, model_size
            )
            return result
        except Exception as e:
            logger.error(f"Fallback client also failed: {e}")  # ← This is the error we see
````
</augment_code_snippet>

### 7. Token Limit Exception Handling

**File: `graphiti_core/llm_client/openai_base_client.py`**
<augment_code_snippet path="graphiti_core/llm_client/openai_base_client.py" mode="EXCERPT">
````python
try:
    if response_model:
        response = await self._create_structured_completion(
            model=model,
            messages=openai_messages,
            temperature=self.temperature,
            max_tokens=max_tokens or self.max_tokens,
            response_model=response_model,
        )
        return self._handle_structured_response(response)

except openai.LengthFinishReasonError as e:
    raise Exception(f'Output length exceeded max tokens {self.max_tokens}: {e}') from e  # ← This error
````
</augment_code_snippet>

## Why the Output is So Long

### 1. **Large Input Context**
- `previous_episodes` can contain many episodes with full content
- Each episode content is JSON-dumped with `indent=2` (verbose formatting)
- Current episode content is also included in full

### 2. **Complex JSON Schema**
- Dynamic Pydantic model creation with `entity_attributes_model`
- Full JSON schema gets appended to the prompt
- Schema can be very detailed for complex entity types

### 3. **Verbose Model Behavior**
- Ollama `gemma3:12b` model tends to be chatty
- Model might generate explanations, reasoning, or repeated content
- Local models often less constrained than API models

### 4. **Cumulative Prompt Additions**
- Multilingual instructions added to system message
- JSON schema added to user message
- Guidelines and examples in the prompt template

## Solutions

### Immediate Fixes:
1. **Reduce context size**: Limit `previous_episodes` to most recent N episodes
2. **Increase token limit**: Set higher `max_tokens` for attribute extraction
3. **Simplify JSON schema**: Use simpler response models
4. **Truncate episode content**: Limit episode content length

### Long-term Improvements:
1. **Context windowing**: Implement sliding window for episode history
2. **Content summarization**: Summarize old episodes instead of including full content
3. **Model-specific tuning**: Adjust prompts for different model behaviors
4. **Streaming responses**: Handle partial responses for long outputs
