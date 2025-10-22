#!/usr/bin/env python3
"""
Debug script to test the query wrapping logic.
"""
import re

def debug_wrap_vector_params():
    """Debug the vector parameter wrapping."""

    # Test query that should trigger the wrapping
    test_query = """
    UNWIND $edges AS edge
    MATCH (n:Entity {uuid: edge.source_node_uuid})-[e:RELATES_TO {group_id: edge.group_id}]-(m:Entity {uuid: edge.target_node_uuid})
    WITH e, edge, (2 - vec.cosineDistance(e.fact_embedding, edge.fact_embedding))/2 AS score
    WHERE score > $min_score
    RETURN edge.uuid AS search_edge_uuid
    """

    test_params = {
        'edges': [
            {
                'uuid': 'test-edge-1',
                'source_node_uuid': 'node-1',
                'target_node_uuid': 'node-2',
                'group_id': 'test_group',
                'fact_embedding': [0.1, 0.2, 0.3, 0.4, 0.5]
            }
        ],
        'min_score': 0.5
    }

    print("🔍 Original query:")
    print(test_query)
    print("\n" + "="*50)

    def _wrap_unwind_vectors(query_text: str) -> str:
        import re

        print("📋 Testing regex patterns...")

        # Pattern to match UNWIND parameter vectors in vector operations
        # Matches: edge.fact_embedding, node.name_embedding, etc. when used in vec.cosineDistance
        unwind_vector_patterns = [
            r'\b(edge\.(?:fact_)?embedding)\b',
            r'\b(node\.(?:name_|summary_)?embedding)\b',
            r'\b(entity\.(?:name_|summary_)?embedding)\b',
            r'\b(item\.(?:name_|summary_)?embedding)\b',
        ]

        for i, pattern in enumerate(unwind_vector_patterns):
            print(f"\n🔎 Pattern {i+1}: {pattern}")

            # Find all matches of the pattern
            matches = list(re.finditer(pattern, query_text))
            print(f"   Found {len(matches)} matches")

            for match in matches:
                print(f"   - Match: '{match.group(1)}' at position {match.span()}")

        # Use the first pattern for edge.fact_embedding
        pattern = unwind_vector_patterns[0]
        matches = re.finditer(pattern, query_text)
        replacements = []

        for match in matches:
            original = match.group(1)
            start, end = match.span(1)

            print(f"\n🔍 Processing match: '{original}'")
            print(f"   Position: {start}-{end}")

            # Check if this vector is used in a vector operation (vec.cosineDistance)
            # Look ahead and behind to see if it's in a vector context
            context_start = max(0, start - 50)
            context_end = min(len(query_text), end + 50)
            context = query_text[context_start:context_end]

            print(f"   Context: '{context.strip()}'")

            # If it's in a vector operation context and not already wrapped
            has_vector_op = 'vec.cosineDistance' in context or 'vector.similarity' in context
            already_wrapped = f'vecf32({original})' in context

            print(f"   Has vector operation: {has_vector_op}")
            print(f"   Already wrapped: {already_wrapped}")

            if has_vector_op and not already_wrapped:
                print(f"   ✅ Will wrap: {original} -> vecf32({original})")
                replacements.append((start, end, f'vecf32({original})'))
            else:
                print(f"   ❌ Will NOT wrap: {original}")

        # Apply replacements in reverse order to maintain indices
        print(f"\n🔧 Applying {len(replacements)} replacements...")
        for start, end, replacement in reversed(replacements):
            print(f"   {start}-{end}: {query_text[start:end]} -> {replacement}")
            query_text = query_text[:start] + replacement + query_text[end:]

        return query_text

    # Test the wrapping
    wrapped_query = _wrap_unwind_vectors(test_query)

    print("\n🎯 Final result:")
    print("="*50)
    print(wrapped_query)

    # Check results
    has_wrapped_edge = 'vecf32(edge.fact_embedding)' in wrapped_query
    has_unwrapped_graph = 'e.fact_embedding' in wrapped_query and 'vecf32(e.fact_embedding)' not in wrapped_query

    print(f"\n📊 Results:")
    print(f"   edge.fact_embedding wrapped: {has_wrapped_edge}")
    print(f"   e.fact_embedding untouched: {has_unwrapped_graph}")

    return has_wrapped_edge and has_unwrapped_graph

if __name__ == '__main__':
    success = debug_wrap_vector_params()
    print(f"\n🎉 Test {'PASSED' if success else 'FAILED'}")