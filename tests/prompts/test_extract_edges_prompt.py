import types

import pytest
from graphiti_core.prompts import extract_edges as extract_edges_module
from graphiti_core.utils.prompt_utils import enforce_max_prompt_tokens


@pytest.fixture(autouse=True)
def sample_context():
    return {
        'episode_content': 'Alice met Bob at the park.',
        'previous_episodes': ['Earlier, Alice mentioned Bob.'],
        'nodes': [{'id': 0, 'name': 'Alice', 'entity_types': ['Person']}],
        'reference_time': '2025-01-01T00:00:00Z',
        'edge_types': [],
        'custom_prompt': '',
        'extracted_facts': [],
        'fact': 'Alice introduced Bob to Charlie.',
    }


def _install_tracking_hook(monkeypatch):
    tracker = types.SimpleNamespace(called=False)

    def _wrapped(context):
        tracker.called = True
        return context

    monkeypatch.setattr(
        extract_edges_module,
        'enforce_max_prompt_tokens',
        _wrapped,
        raising=False,
    )
    return tracker


def test_edge_prompt_enforces_token_limit(sample_context, monkeypatch):
    tracker = _install_tracking_hook(monkeypatch)

    extract_edges_module.edge(dict(sample_context))

    assert tracker.called, 'edge() should clip prompts via enforce_max_prompt_tokens'


def test_reflexion_prompt_enforces_token_limit(sample_context, monkeypatch):
    tracker = _install_tracking_hook(monkeypatch)

    extract_edges_module.reflexion(dict(sample_context))

    assert tracker.called, 'reflexion() should clip prompts via enforce_max_prompt_tokens'


def test_extract_attributes_prompt_enforces_token_limit(sample_context, monkeypatch):
    tracker = _install_tracking_hook(monkeypatch)

    extract_edges_module.extract_attributes(dict(sample_context))

    assert tracker.called, 'extract_attributes() should clip prompts via enforce_max_prompt_tokens'
