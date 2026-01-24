"""
Unit tests for entity filtering logic: blocklist, timestamp regex, and path normalization.
"""

import pytest

from graphiti_core.utils.maintenance.node_operations import (
    ENTITY_NAME_BLOCKLIST,
    TIMESTAMP_PATTERN,
    is_garbage_entity,
    normalize_entity_name,
)


class TestEntityBlocklist:
    def test_tool_names_blocked(self):
        tool_names = ['bash', 'read', 'edit', 'write', 'grep', 'git', 'npm', 'docker', 'curl']
        for tool in tool_names:
            assert is_garbage_entity(tool), f"Tool '{tool}' should be blocked"
            assert is_garbage_entity(tool.upper()), f"Tool '{tool.upper()}' should be blocked"

    def test_opencode_metadata_blocked(self):
        metadata = [
            'opencode session',
            'opencode_session',
            'session',
            'session started',
            'session ended',
        ]
        for meta in metadata:
            assert is_garbage_entity(meta), f"Metadata '{meta}' should be blocked"

    def test_generic_terms_blocked(self):
        generic = ['the tool', 'the command', 'the script', 'the system', 'the project']
        for term in generic:
            assert is_garbage_entity(term), f"Generic term '{term}' should be blocked"

    def test_null_variants_blocked(self):
        nulls = ['unknown', 'null', 'none', 'undefined']
        for null in nulls:
            assert is_garbage_entity(null), f"Null variant '{null}' should be blocked"

    def test_valid_entities_not_blocked(self):
        valid = [
            'Docker Hub',
            'Git repository',
            'Bash script tutorial',
            'npm package manager',
            'Session Manager',
            'Project Alpha',
        ]
        for entity in valid:
            assert not is_garbage_entity(entity), f"Valid entity '{entity}' should NOT be blocked"

    def test_partial_matches_not_blocked(self):
        partial = ['reading', 'editor', 'bashful', 'gitignore', 'dockerize']
        for entity in partial:
            assert not is_garbage_entity(entity), f"Partial match '{entity}' should NOT be blocked"


class TestTimestampFiltering:
    def test_iso_date_filtered(self):
        timestamps = ['2025-01-24', '2025_01_24', '2024-12-31']
        for ts in timestamps:
            assert is_garbage_entity(ts), f"ISO date '{ts}' should be filtered"

    def test_iso_datetime_filtered(self):
        timestamps = ['2025-01-24T18:30:00Z', 'T18:30:00', '2025_01_24t183000']
        for ts in timestamps:
            assert is_garbage_entity(ts), f"ISO datetime '{ts}' should be filtered"

    def test_time_only_filtered(self):
        times = ['18:30:00', '00:00:00', '23:59:59']
        for t in times:
            assert is_garbage_entity(t), f"Time '{t}' should be filtered"

    def test_valid_entities_with_numbers_not_filtered(self):
        valid = ['Version 2025', 'Q1 2025 Report', 'Python 3.11', 'RFC 7231']
        for entity in valid:
            assert not is_garbage_entity(entity), f"Valid entity '{entity}' should NOT be filtered"


class TestPathNormalization:
    def test_absolute_path_preserved(self):
        path = '/opt/stacks/graphiti/file.py'
        assert normalize_entity_name(path) == path

    def test_path_with_trailing_slash_stripped(self):
        assert normalize_entity_name('/opt/stacks/graphiti/') == '/opt/stacks/graphiti'

    def test_backslashes_normalized(self):
        assert normalize_entity_name('C:\\Users\\file.py') == 'C:/Users/file.py'

    def test_mixed_slashes_normalized(self):
        assert (
            normalize_entity_name('/opt\\stacks/graphiti\\file.py')
            == '/opt/stacks/graphiti/file.py'
        )

    def test_relative_path_preserved(self):
        path = 'graphiti/core/nodes.py'
        assert normalize_entity_name(path) == path

    def test_non_path_normalized(self):
        assert normalize_entity_name('Some Entity') == 'some_entity'
        assert normalize_entity_name('Claude-3.5-Sonnet') == 'claude_3_5_sonnet'

    def test_empty_string_unchanged(self):
        assert normalize_entity_name('') == ''
        assert normalize_entity_name('   ') == '   '

    def test_windows_path_detected(self):
        path = 'C:/Users/Documents/file.txt'
        assert normalize_entity_name(path) == path


class TestBlocklistContents:
    def test_blocklist_is_frozenset(self):
        assert isinstance(ENTITY_NAME_BLOCKLIST, frozenset)

    def test_blocklist_all_lowercase(self):
        for item in ENTITY_NAME_BLOCKLIST:
            assert item == item.lower(), f"Blocklist item '{item}' should be lowercase"

    def test_timestamp_pattern_compiled(self):
        assert TIMESTAMP_PATTERN is not None
        assert hasattr(TIMESTAMP_PATTERN, 'search')
