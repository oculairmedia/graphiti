#!/usr/bin/env python3
"""
Complex DSPy extraction tests with entity reuse and deduplication.

Tests realistic scenarios where:
- Entities appear across multiple episodes
- Same entity referenced by different names/aliases
- Relationships evolve over time
- Context from previous episodes affects extraction

Run with: CHUTES_API_KEY=your-key python3 test_dspy_complex_scenarios.py
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone, timedelta

sys.path.insert(0, '/opt/stacks/graphiti')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def setup():
    """Configure DSPy."""
    from graphiti_core.dspy.config import configure_lm
    api_key = os.environ.get('CHUTES_API_KEY')
    if not api_key:
        print('ERROR: CHUTES_API_KEY not set')
        sys.exit(1)
    configure_lm(api_key=api_key)


# =============================================================================
# Test Scenarios
# =============================================================================

def test_multi_episode_entity_tracking():
    """
    Test entity tracking across multiple episodes.

    Scenario: A project discussion spanning 3 messages where entities
    are introduced and then referenced again.
    """
    print('\n' + '=' * 70)
    print('TEST: Multi-Episode Entity Tracking')
    print('=' * 70)

    from graphiti_core.dspy.modules import NodeExtractor, NodeResolver

    extractor = NodeExtractor()
    resolver = NodeResolver()

    entity_types = [
        {'id': 0, 'name': 'Person', 'description': 'A human individual'},
        {'id': 1, 'name': 'Organization', 'description': 'A company or team'},
        {'id': 2, 'name': 'Project', 'description': 'A software project or initiative'},
        {'id': 3, 'name': 'Technology', 'description': 'A programming language, framework, or tool'},
    ]

    # Episode 1: Introduction
    episode1 = "Sarah: Hey team, I'm starting a new project called DataFlow. We'll be using Python and PostgreSQL."

    # Episode 2: Reference existing entities + new ones
    episode2 = "Mike: That sounds great Sarah! I've used Postgres before. Should we also consider Redis for caching in DataFlow?"

    # Episode 3: More references with aliases
    episode3 = "Sarah: Good idea Mike. Let's add Redis to the tech stack. I'll talk to Dr. Chen about the ML components for the project."

    print('\n--- Episode 1 ---')
    print(f'Content: {episode1}')

    result1 = extractor(
        current_message=episode1,
        entity_types=entity_types,
    )

    print(f'Extracted: {[e.name for e in result1.extracted_entities]}')

    # Build existing entities for episode 2
    existing_entities = []
    for i, entity in enumerate(result1.extracted_entities):
        existing_entities.append({
            'idx': i,
            'name': entity.name,
            'type': entity_types[entity.entity_type_id]['name'],
        })

    print('\n--- Episode 2 ---')
    print(f'Content: {episode2}')
    print(f'Existing entities: {[e["name"] for e in existing_entities]}')

    result2 = extractor(
        current_message=episode2,
        entity_types=entity_types,
        previous_messages=[{'content': episode1}],
    )

    print(f'New extractions: {[e.name for e in result2.extracted_entities]}')

    # Resolve against existing
    extracted_for_resolution = [
        {'id': i, 'name': e.name, 'type': entity_types[e.entity_type_id]['name']}
        for i, e in enumerate(result2.extracted_entities)
    ]

    resolution2 = resolver(
        current_message=episode2,
        extracted_entities=extracted_for_resolution,
        existing_entities=existing_entities,
        previous_messages=[{'content': episode1}],
    )

    print('Resolutions:')
    for res in resolution2.entity_resolutions:
        if res.duplicate_idx >= 0:
            print(f'  - "{res.name}" -> DUPLICATE of "{existing_entities[res.duplicate_idx]["name"]}"')
        else:
            print(f'  - "{res.name}" -> NEW ENTITY')

    # Update existing entities with new ones
    for res in resolution2.entity_resolutions:
        if res.duplicate_idx < 0:  # New entity
            existing_entities.append({
                'idx': len(existing_entities),
                'name': res.name,
                'type': 'Unknown',
            })

    print('\n--- Episode 3 ---')
    print(f'Content: {episode3}')
    print(f'Existing entities: {[e["name"] for e in existing_entities]}')

    result3 = extractor(
        current_message=episode3,
        entity_types=entity_types,
        previous_messages=[{'content': episode1}, {'content': episode2}],
    )

    print(f'New extractions: {[e.name for e in result3.extracted_entities]}')

    extracted_for_resolution3 = [
        {'id': i, 'name': e.name, 'type': entity_types[e.entity_type_id]['name']}
        for i, e in enumerate(result3.extracted_entities)
    ]

    resolution3 = resolver(
        current_message=episode3,
        extracted_entities=extracted_for_resolution3,
        existing_entities=existing_entities,
        previous_messages=[{'content': episode1}, {'content': episode2}],
    )

    print('Resolutions:')
    for res in resolution3.entity_resolutions:
        if res.duplicate_idx >= 0:
            print(f'  - "{res.name}" -> DUPLICATE of "{existing_entities[res.duplicate_idx]["name"]}"')
        else:
            print(f'  - "{res.name}" -> NEW ENTITY')

    return True


def test_alias_and_nickname_resolution():
    """
    Test resolution of entities with different names/aliases.

    Scenario: Same person referred to by full name, nickname, and title.
    """
    print('\n' + '=' * 70)
    print('TEST: Alias and Nickname Resolution')
    print('=' * 70)

    from graphiti_core.dspy.modules import NodeExtractor, NodeResolver

    extractor = NodeExtractor()
    resolver = NodeResolver()

    entity_types = [
        {'id': 0, 'name': 'Person', 'description': 'A human individual'},
        {'id': 1, 'name': 'Organization', 'description': 'A company'},
    ]

    # Build up existing entities representing people with different names
    existing_entities = [
        {
            'idx': 0,
            'name': 'Robert Johnson',
            'type': 'Person',
            'summary': 'CEO of TechCorp, also known as Bob'
        },
        {
            'idx': 1,
            'name': 'Elizabeth Chen',
            'type': 'Person',
            'summary': 'CTO of TechCorp, Dr. Chen, Liz'
        },
        {
            'idx': 2,
            'name': 'TechCorp',
            'type': 'Organization',
            'summary': 'A technology company'
        },
    ]

    # Test messages with various aliases
    test_cases = [
        ("Bob called a meeting for tomorrow.", "Robert Johnson"),
        ("Dr. Chen will present the technical roadmap.", "Elizabeth Chen"),
        ("The CEO wants to discuss Q4 targets.", "Robert Johnson"),
        ("Liz mentioned the new ML pipeline.", "Elizabeth Chen"),
        ("Mr. Johnson approved the budget.", "Robert Johnson"),
    ]

    print(f'\nExisting entities:')
    for e in existing_entities:
        print(f'  - {e["name"]}: {e.get("summary", "")}')

    results = []
    for message, expected_match in test_cases:
        print(f'\n--- Testing: "{message}" ---')
        print(f'Expected to match: {expected_match}')

        extracted = extractor(
            current_message=message,
            entity_types=entity_types,
        )

        if not extracted.extracted_entities:
            print('  No entities extracted')
            results.append(False)
            continue

        extracted_for_resolution = [
            {'id': i, 'name': e.name, 'type': entity_types[e.entity_type_id]['name']}
            for i, e in enumerate(extracted.extracted_entities)
        ]

        resolution = resolver(
            current_message=message,
            extracted_entities=extracted_for_resolution,
            existing_entities=existing_entities,
        )

        matched = False
        for res in resolution.entity_resolutions:
            if res.duplicate_idx >= 0:
                matched_name = existing_entities[res.duplicate_idx]['name']
                print(f'  "{res.name}" -> matched "{matched_name}"')
                if matched_name == expected_match:
                    matched = True
            else:
                print(f'  "{res.name}" -> NO MATCH (new entity)')

        results.append(matched)
        print(f'  Result: {"PASS" if matched else "FAIL"}')

    passed = sum(results)
    print(f'\n--- Summary: {passed}/{len(results)} alias resolutions correct ---')
    return passed >= len(results) * 0.6  # 60% threshold


def test_evolving_relationships():
    """
    Test extraction of relationships that change over time.

    Scenario: Employment history with temporal information.
    """
    print('\n' + '=' * 70)
    print('TEST: Evolving Relationships Over Time')
    print('=' * 70)

    from graphiti_core.dspy.modules import NodeExtractor, EdgeExtractor

    extractor = NodeExtractor()
    edge_extractor = EdgeExtractor()

    entity_types = [
        {'id': 0, 'name': 'Person', 'description': 'A human individual'},
        {'id': 1, 'name': 'Organization', 'description': 'A company'},
        {'id': 2, 'name': 'Role', 'description': 'A job title or position'},
    ]

    # Career progression narrative
    episodes = [
        {
            'content': "John started his career at Google as a junior engineer in 2015.",
            'time': '2015-06-01T00:00:00Z',
        },
        {
            'content': "In 2018, John was promoted to senior engineer at Google.",
            'time': '2018-03-01T00:00:00Z',
        },
        {
            'content': "John left Google in 2020 to join Microsoft as a principal engineer.",
            'time': '2020-09-01T00:00:00Z',
        },
        {
            'content': "Recently, John became the engineering director at Microsoft.",
            'time': '2023-01-15T00:00:00Z',
        },
    ]

    all_entities = []
    previous_messages = []

    for episode in episodes:
        print(f'\n--- Episode ({episode["time"][:10]}) ---')
        print(f'Content: {episode["content"]}')

        # Extract entities
        extracted = extractor(
            current_message=episode['content'],
            entity_types=entity_types,
            previous_messages=previous_messages,
        )

        # Build entity list for edge extraction
        entities_for_edges = []
        for i, e in enumerate(extracted.extracted_entities):
            entity_dict = {
                'id': len(all_entities) + i,
                'name': e.name,
                'type': entity_types[e.entity_type_id]['name'],
            }
            entities_for_edges.append(entity_dict)

            # Check if already exists
            if not any(existing['name'].lower() == e.name.lower() for existing in all_entities):
                all_entities.append(entity_dict)

        print(f'Entities: {[e["name"] for e in entities_for_edges]}')

        # Extract edges with temporal info
        if len(entities_for_edges) >= 2:
            edges = edge_extractor(
                current_message=episode['content'],
                entities=entities_for_edges,
                reference_time=episode['time'],
                previous_messages=previous_messages,
            )

            print('Relationships:')
            for edge in edges.edges:
                src_id = edge.source_entity_id
                tgt_id = edge.target_entity_id
                src_name = entities_for_edges[src_id]['name'] if src_id < len(entities_for_edges) else f'id:{src_id}'
                tgt_name = entities_for_edges[tgt_id]['name'] if tgt_id < len(entities_for_edges) else f'id:{tgt_id}'

                temporal = ''
                if edge.valid_at:
                    temporal += f' [started: {edge.valid_at[:10]}]'
                if edge.invalid_at:
                    temporal += f' [ended: {edge.invalid_at[:10]}]'

                print(f'  {src_name} --[{edge.relation_type}]--> {tgt_name}{temporal}')
                print(f'    Fact: {edge.fact}')

        previous_messages.append({'content': episode['content']})

    print(f'\n--- All tracked entities: {[e["name"] for e in all_entities]} ---')
    return True


def test_complex_organizational_structure():
    """
    Test extraction from complex organizational relationships.

    Scenario: Company hierarchy with multiple relationships.
    """
    print('\n' + '=' * 70)
    print('TEST: Complex Organizational Structure')
    print('=' * 70)

    from graphiti_core.dspy.modules import NodeExtractor, EdgeExtractor, NodeResolver

    extractor = NodeExtractor()
    edge_extractor = EdgeExtractor()
    resolver = NodeResolver()

    entity_types = [
        {'id': 0, 'name': 'Person', 'description': 'A human individual'},
        {'id': 1, 'name': 'Organization', 'description': 'A company, department, or team'},
        {'id': 2, 'name': 'Project', 'description': 'A project or initiative'},
    ]

    # Complex organizational message
    message = """
    The AI Division at TechCorp is led by Dr. Sarah Chen, who reports directly to CEO Michael Torres.
    Sarah oversees three teams: the NLP Team headed by James Wilson, the Computer Vision Team led by Maria Garcia,
    and the MLOps Team managed by David Kim. James's team is working on Project ChatAssist, while Maria's team
    is developing Project ImageAI. Both projects report progress to Sarah weekly. Michael recently announced
    that TechCorp will be acquiring StartupML, which will merge with the AI Division.
    """

    reference_time = datetime.now(timezone.utc).isoformat()

    print(f'Input message:\n{message.strip()}\n')

    # Extract entities
    extracted = extractor(
        current_message=message,
        entity_types=entity_types,
    )

    print(f'Extracted {len(extracted.extracted_entities)} entities:')
    entities_for_edges = []
    for i, e in enumerate(extracted.extracted_entities):
        type_name = entity_types[e.entity_type_id]['name']
        print(f'  {i}: {e.name} ({type_name})')
        entities_for_edges.append({
            'id': i,
            'name': e.name,
            'type': type_name,
        })

    # Extract relationships
    edges = edge_extractor(
        current_message=message,
        entities=entities_for_edges,
        reference_time=reference_time,
    )

    print(f'\nExtracted {len(edges.edges)} relationships:')
    for edge in edges.edges:
        src = entities_for_edges[edge.source_entity_id]['name'] if edge.source_entity_id < len(entities_for_edges) else f'?{edge.source_entity_id}'
        tgt = entities_for_edges[edge.target_entity_id]['name'] if edge.target_entity_id < len(entities_for_edges) else f'?{edge.target_entity_id}'
        print(f'  {src} --[{edge.relation_type}]--> {tgt}')

    # Expected relationships to find
    expected_relations = [
        ('REPORTS_TO', 'LEADS', 'MANAGES', 'HEADED_BY', 'LED_BY'),  # Hierarchy relations
        ('WORKS_ON', 'DEVELOPING', 'WORKING_ON'),  # Project relations
        ('ACQUIRING', 'MERGING', 'MERGE_WITH'),  # M&A relations
    ]

    found_categories = set()
    for edge in edges.edges:
        for i, category in enumerate(expected_relations):
            if edge.relation_type in category or any(c in edge.relation_type for c in category):
                found_categories.add(i)

    print(f'\n--- Found {len(found_categories)}/3 relationship categories ---')
    print(f'  Hierarchy: {"YES" if 0 in found_categories else "NO"}')
    print(f'  Projects: {"YES" if 1 in found_categories else "NO"}')
    print(f'  M&A: {"YES" if 2 in found_categories else "NO"}')

    return len(edges.edges) >= 5 and len(found_categories) >= 2


def main():
    """Run all complex scenario tests."""
    print('=' * 70)
    print('DSPy Complex Scenario Tests')
    print('=' * 70)
    print(f'Time: {datetime.now().isoformat()}')

    setup()

    results = {}

    try:
        results['multi_episode'] = test_multi_episode_entity_tracking()
    except Exception as e:
        print(f'FAIL: {e}')
        import traceback
        traceback.print_exc()
        results['multi_episode'] = False

    try:
        results['alias_resolution'] = test_alias_and_nickname_resolution()
    except Exception as e:
        print(f'FAIL: {e}')
        import traceback
        traceback.print_exc()
        results['alias_resolution'] = False

    try:
        results['evolving_relations'] = test_evolving_relationships()
    except Exception as e:
        print(f'FAIL: {e}')
        import traceback
        traceback.print_exc()
        results['evolving_relations'] = False

    try:
        results['org_structure'] = test_complex_organizational_structure()
    except Exception as e:
        print(f'FAIL: {e}')
        import traceback
        traceback.print_exc()
        results['org_structure'] = False

    # Summary
    print('\n' + '=' * 70)
    print('TEST SUMMARY')
    print('=' * 70)
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print(f'Passed: {passed}/{total}')
    for name, result in results.items():
        status = 'PASS' if result else 'FAIL'
        print(f'  {name}: {status}')

    return 0 if passed == total else 1


if __name__ == '__main__':
    sys.exit(main())
