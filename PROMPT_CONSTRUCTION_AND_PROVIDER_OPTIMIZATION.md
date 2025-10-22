# Graphiti Prompt Construction and Provider Optimization Guide

## Overview

This document details how prompts are constructed in the Graphiti system and identifies opportunities for per-provider optimizations to improve performance across different LLM providers (OpenAI, Anthropic, Ollama, Cerebras, Chutes AI, etc.).

## Current Prompt Construction System

### 1. Prompt Library Architecture

**Location**: `graphiti_core/prompts/lib.py`

The prompt system is organized around a centralized library with versioned prompts:

```python
PROMPT_LIBRARY_IMPL: PromptLibraryImpl = {
    'extract_nodes': extract_nodes_versions,
    'dedupe_nodes': dedupe_nodes_versions,
    'extract_edges': extract_edges_versions,
    'dedupe_edges': dedupe_edges_versions,
    'invalidate_edges': invalidate_edges_versions,
    'extract_edge_dates': extract_edge_dates_versions,
    'summarize_nodes': summarize_nodes_versions,
    'eval': eval_versions,
}
```

### 2. Prompt Execution Flow

**Key Files**:
- `graphiti_core/utils/maintenance/node_operations.py` - Node extraction execution
- `graphiti_core/utils/maintenance/edge_operations.py` - Edge extraction execution
- `graphiti_core/llm_client/client.py` - Base LLM client with prompt processing

**Execution Pattern**:
```python
# 1. Prepare context
context = {
    'episode_content': episode.content,
    'previous_episodes': [ep.content for ep in previous_episodes],
    'nodes': existing_nodes,
    'entity_types': entity_types,
    'custom_prompt': custom_instructions
}

# 2. Get prompt from library
messages = prompt_library.extract_nodes.extract_message(context)

# 3. Execute with LLM client
llm_response = await llm_client.generate_response(
    messages, 
    response_model=ExtractedEntities
)
```

### 3. Current Provider Support

**Supported Providers** (via `graphiti_core/client_factory.py`):
1. **Cerebras** - Priority 1 (qwen-3-coder-480b)
2. **Chutes AI** - Priority 2 (GLM-4.5-FP8)
3. **Ollama** - Priority 3 (local models)
4. **OpenAI** - Standard API
5. **Anthropic** - Claude models
6. **Gemini** - Google models

## Current Prompt Patterns

### 1. Standard Structure
Most prompts follow this XML-based pattern:
```xml
<PREVIOUS_MESSAGES>
{previous_episodes}
</PREVIOUS_MESSAGES>
<CURRENT_MESSAGE>
{episode_content}
</CURRENT_MESSAGE>
<ENTITIES>
{existing_entities}
</ENTITIES>
```

### 2. No Few-Shot Examples
**Current State**: The prompts do NOT include few-shot examples or demonstrations.
- All prompts rely on zero-shot instruction following
- No example inputs/outputs are provided
- No demonstration of desired format beyond schema descriptions

### 3. Provider-Agnostic Design
Currently, all providers receive identical prompts with only these modifications:
- Unicode handling: `DO_NOT_ESCAPE_UNICODE` added to system messages
- Multilingual support: `MULTILINGUAL_EXTRACTION_RESPONSES` added

## Opportunities for Provider-Specific Optimization

### 1. **Prompt Enhancement System** (Recommended Implementation)

**Location**: Create `graphiti_core/prompts/provider_optimizer.py`

```python
class ProviderPromptOptimizer:
    def optimize_for_provider(self, 
                            messages: list[Message], 
                            provider: str, 
                            task_type: str) -> list[Message]:
        """Optimize prompts based on provider capabilities"""
        
        if provider == "ollama":
            return self._optimize_for_ollama(messages, task_type)
        elif provider == "anthropic":
            return self._optimize_for_anthropic(messages, task_type)
        elif provider == "openai":
            return self._optimize_for_openai(messages, task_type)
        # ... etc
        
        return messages  # Default: no optimization
```

### 2. **Provider-Specific Modifications Needed**

#### A. **Ollama/Local Models**
**Issues**: Tend to be verbose, struggle with complex JSON schemas
**Optimizations**:
- Add explicit length constraints: "Be concise. Limit response to essential information."
- Simplify JSON schemas for complex extractions
- Add few-shot examples for better format adherence
- Break complex tasks into smaller steps

#### B. **Anthropic Claude**
**Strengths**: Excellent instruction following, good with structured output
**Optimizations**:
- Leverage Claude's strong reasoning with more detailed reasoning instructions
- Use Claude's preference for explicit step-by-step instructions
- Optimize for Claude's tool-use capabilities (already implemented)

#### C. **OpenAI GPT Models**
**Strengths**: Good JSON generation, reliable structured output
**Optimizations**:
- Leverage function calling for structured outputs
- Use more concise instructions (GPT handles implicit context well)
- Optimize token usage with shorter prompts

#### D. **Cerebras/Chutes AI**
**Characteristics**: High-performance inference, may have different instruction preferences
**Optimizations**:
- Test and optimize for specific model architectures
- May benefit from more explicit formatting instructions
- Consider token efficiency optimizations

### 3. **Implementation Points for Provider Optimization**

#### A. **Prompt Library Wrapper Enhancement**
**File**: `graphiti_core/prompts/lib.py`

Modify `VersionWrapper` to include provider awareness:
```python
class VersionWrapper:
    def __init__(self, func: PromptFunction, optimizer: ProviderPromptOptimizer = None):
        self.func = func
        self.optimizer = optimizer

    def __call__(self, context: dict[str, Any], provider: str = None) -> list[Message]:
        messages = self.func(context)
        
        # Apply provider-specific optimizations
        if self.optimizer and provider:
            messages = self.optimizer.optimize_for_provider(messages, provider, context.get('task_type'))
        
        # Apply existing modifications
        for message in messages:
            message.content += DO_NOT_ESCAPE_UNICODE if message.role == 'system' else ''
        
        return messages
```

#### B. **LLM Client Integration**
**Files**: 
- `graphiti_core/llm_client/client.py`
- `graphiti_core/llm_client/openai_base_client.py`
- `graphiti_core/llm_client/anthropic_client.py`

Add provider detection and prompt optimization:
```python
async def generate_response(self, messages: list[Message], ...):
    # Detect provider type
    provider_type = self._get_provider_type()
    
    # Apply provider-specific prompt optimizations
    optimized_messages = self.prompt_optimizer.optimize_for_provider(
        messages, provider_type, task_type
    )
    
    # Continue with existing flow...
```

#### C. **Configuration-Based Optimization**
**File**: `graphiti_core/llm_client/config.py`

Add provider-specific settings:
```python
class LLMConfig:
    def __init__(self, ...):
        # ... existing fields ...
        self.provider_optimizations: dict[str, Any] = {}
        self.enable_few_shot_examples: bool = False
        self.max_context_length: int = None
        self.prefer_concise_prompts: bool = False
```

## Specific Optimization Strategies

### 1. **Few-Shot Examples** (High Impact)
Add example-based learning for providers that benefit:
- **Target**: Ollama, smaller local models
- **Implementation**: Create example banks for each prompt type
- **Location**: `graphiti_core/prompts/examples/`

### 2. **Token Length Optimization** (Medium Impact)
Implement dynamic prompt truncation:
- **Target**: All providers with token limits
- **Strategy**: Prioritize recent context, summarize older episodes
- **Implementation**: Context window management in prompt construction

### 3. **Format Simplification** (Medium Impact)
Simplify complex JSON schemas for struggling models:
- **Target**: Ollama, local models
- **Strategy**: Break complex extractions into multiple simpler calls
- **Implementation**: Multi-step extraction workflows

### 4. **Provider-Specific Instructions** (Low-Medium Impact)
Tailor instruction style to provider strengths:
- **Anthropic**: More reasoning-focused instructions
- **OpenAI**: More direct, function-oriented instructions
- **Ollama**: More explicit, step-by-step instructions

## Next Steps for Implementation

1. **Create Provider Detection System** - Identify which provider is being used
2. **Implement ProviderPromptOptimizer Class** - Central optimization logic
3. **Add Few-Shot Example System** - Example banks for each prompt type
4. **Integrate with Existing Prompt Library** - Modify wrappers to use optimizer
5. **Add Configuration Options** - Allow users to enable/disable optimizations
6. **Performance Testing** - Benchmark optimizations across providers

## Files to Modify

### Core Implementation:
- `graphiti_core/prompts/lib.py` - Add provider awareness to wrappers
- `graphiti_core/prompts/provider_optimizer.py` - New optimization engine
- `graphiti_core/llm_client/config.py` - Add optimization settings
- `graphiti_core/llm_client/client.py` - Integrate optimization calls

### Provider-Specific Clients:
- `graphiti_core/llm_client/openai_base_client.py`
- `graphiti_core/llm_client/anthropic_client.py`
- `graphiti_core/llm_client/openai_generic_client.py`
- `graphiti_core/llm_client/gemini_client.py`

### Examples and Configuration:
- `graphiti_core/prompts/examples/` - New directory for few-shot examples
- `graphiti_core/client_factory.py` - Add optimization configuration

This system would allow Graphiti to automatically optimize prompts for different providers while maintaining backward compatibility and allowing users to disable optimizations if needed.
