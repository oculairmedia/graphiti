import copy

from graphiti_core.utils.prompt_utils import enforce_max_prompt_tokens


def _make_large_context() -> dict:
    return {
        'episode_content': 'A' * 6000,
        'previous_episodes': [
            'Episode alpha ' + 'x' * 3000,
            'Episode beta ' + 'y' * 3000,
            'Episode gamma ' + 'z' * 3000,
            'Episode delta ' + 'w' * 3000,
        ],
        'existing_nodes_text': 'Node data ' + 'n' * 4000,
        'extra_field': {'notes': 'Some metadata', 'count': 3},
    }


def test_enforce_max_prompt_tokens_records_debug_metadata():
    original = _make_large_context()
    original_copy = copy.deepcopy(original)

    result = enforce_max_prompt_tokens(original, max_tokens=800)

    assert original == original_copy
    debug_info = result['__prompt_debug__']
    assert debug_info['initial_tokens'] > 800
    assert debug_info['final_tokens'] <= debug_info['initial_tokens']
    assert debug_info['adjustments']
    adjustment_types = {entry['type'] for entry in debug_info['adjustments']}
    assert {'previous_episodes', 'episode_content', 'existing_nodes_text'} & adjustment_types


def test_enforce_max_prompt_tokens_unchanged_when_under_limit():
    context = {
        'episode_content': 'Short text',
        'previous_episodes': ['Tiny'],
    }

    result = enforce_max_prompt_tokens(context, max_tokens=2000)

    assert context['episode_content'] == 'Short text'
    debug_info = result['__prompt_debug__']
    assert debug_info['initial_tokens'] <= 2000
    assert debug_info['status'] == 'unchanged'
    assert not debug_info['adjustments']
