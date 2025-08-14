#!/bin/bash

# Graphiti Quick Search Hook
# Searches Graphiti when specific keywords are detected

# Read JSON input from stdin
input=$(cat)

# Extract hook event and relevant data
hook_event=$(echo "$input" | jq -r '.hook_event_name')
prompt=$(echo "$input" | jq -r '.prompt // ""')
tool_name=$(echo "$input" | jq -r '.tool_name // ""')

# Only process UserPromptSubmit events
if [ "$hook_event" != "UserPromptSubmit" ]; then
    exit 0
fi

# Check if prompt contains Graphiti-related keywords
if echo "$prompt" | grep -qiE "(graphiti|knowledge graph|remember|recall|previous context|what did|earlier|history of)"; then
    
    # Extract search terms (remove common words)
    search_query=$(echo "$prompt" | sed -E 's/\b(what|how|when|where|who|why|is|are|was|were|the|a|an|in|on|at|to|for)\b//gi' | tr -s ' ')
    
    # Call Graphiti API
    response=$(curl -s -X POST "http://localhost:8003/search" \
        -H "Content-Type: application/json" \
        -d "{\"query\": \"$search_query\", \"limit\": 5}" \
        --max-time 5 2>/dev/null)
    
    if [ $? -eq 0 ] && [ -n "$response" ]; then
        # Format the response as context
        context="<!-- Graphiti Knowledge Graph Context -->\n"
        context+="<graphiti-results>\n"
        
        # Extract and format entities
        entities=$(echo "$response" | jq -r '.entities[]? | "- \(.name // "Unknown"): \(.content // "" | .[0:100])"' 2>/dev/null)
        if [ -n "$entities" ]; then
            context+="## Relevant Entities:\n$entities\n"
        fi
        
        # Extract and format relationships
        edges=$(echo "$response" | jq -r '.edges[]? | "- \(.source_name // "?") --[\(.relationship_type // "?"")]--> \(.target_name // "?")"' 2>/dev/null)
        if [ -n "$edges" ]; then
            context+="\n## Relationships:\n$edges\n"
        fi
        
        context+="</graphiti-results>\n"
        
        # Output as additional context
        jq -n --arg context "$context" '{
            hookSpecificOutput: {
                hookEventName: "UserPromptSubmit",
                additionalContext: $context
            }
        }'
        exit 0
    fi
fi

# No context to add
exit 0