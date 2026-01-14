import pytest

from graphiti_core.dspy.signatures import ExtractedEdges, NodeResolutions
from graphiti_core.prompts.extract_nodes import ExtractedEntities, ExtractedEntity


def test_extracted_entities_accepts_bare_list():
    data = [{'name': 'Graphiti', 'entity_type_id': 0}]
    model = ExtractedEntities.model_validate(data)
    assert len(model.extracted_entities) == 1
    assert model.extracted_entities[0].name == 'Graphiti'


def test_extracted_entities_accepts_wrapped_dict():
    data = {'extracted_entities': [{'name': 'Graphiti', 'entity_type_id': 0}]}
    model = ExtractedEntities.model_validate(data)
    assert len(model.extracted_entities) == 1


def test_extracted_entity_normalizes_field_names():
    entity = ExtractedEntity.model_validate({'entity_name': 'Alpha', 'entity_type_id': 1})
    assert entity.name == 'Alpha'
    entity = ExtractedEntity.model_validate({'entityName': 'Beta', 'entity_type_id': 2})
    assert entity.name == 'Beta'
    entity = ExtractedEntity.model_validate({'name': 'Gamma', 'entity_type': 'Person'})
    assert entity.name == 'Gamma'
    assert entity.entity_type_id == 0


def test_extracted_edges_accepts_bare_list():
    data = [
        {
            'relation_type': 'WORKS_AT',
            'source_entity_id': 0,
            'target_entity_id': 1,
            'fact': 'Alice works at TechCorp',
            'valid_at': None,
            'invalid_at': None,
        }
    ]
    model = ExtractedEdges.model_validate(data)
    assert len(model.edges) == 1
    assert model.edges[0].relation_type == 'WORKS_AT'


def test_node_resolutions_accepts_bare_list():
    data = [
        {
            'id': 0,
            'duplicate_idx': -1,
            'name': 'Graphiti',
            'duplicates': [],
        }
    ]
    model = NodeResolutions.model_validate(data)
    assert len(model.entity_resolutions) == 1
    assert model.entity_resolutions[0].name == 'Graphiti'
