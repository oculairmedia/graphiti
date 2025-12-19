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

Unit tests for robust JSON parsing in OpenAIGenericClient.
"""

import json

import pytest  # type: ignore

from graphiti_core.llm_client.openai_generic_client import _testonly_robust_json_parse


def test_robust_json_parse_passes_through_plain_json():
    payload = {'summary': 'hello', 'foo': 123}
    result = _testonly_robust_json_parse(json.dumps(payload))
    assert result == payload


def test_robust_json_parse_extracts_top_level_data_from_schema_echo():
    content = json.dumps(
        {
            '$defs': {'Something': {'type': 'object'}},
            'properties': {'summary': {'type': 'string'}},
            'required': ['summary'],
            'summary': 'actual summary',
            'bar': 42,
        }
    )

    result = _testonly_robust_json_parse(content)
    assert result == {'summary': 'actual summary', 'bar': 42}


def test_robust_json_parse_extracts_properties_value_from_schema_echo():
    content = json.dumps(
        {
            'title': 'EntityAttributes',
            'type': 'object',
            'properties': {
                'summary': {
                    'type': 'string',
                    'description': '...',
                    'value': 'embedded summary',
                },
                'age': {'type': 'integer', 'value': 7},
            },
        }
    )

    result = _testonly_robust_json_parse(content)
    assert result == {'summary': 'embedded summary', 'age': 7}


def test_robust_json_parse_extracts_properties_default_when_value_missing():
    content = json.dumps(
        {
            'type': 'object',
            'properties': {
                'summary': {'type': 'string', 'default': 'default summary'},
                'age': {'type': 'integer', 'default': 99},
            },
        }
    )

    result = _testonly_robust_json_parse(content)
    assert result == {'summary': 'default summary', 'age': 99}


def test_robust_json_parse_handles_json_codeblock_with_schema_echo():
    schema_echo = {
        'type': 'object',
        'properties': {'summary': {'type': 'string', 'value': 'from codeblock'}},
    }

    content = """Here you go:

```json
%s
```
""" % json.dumps(schema_echo)

    result = _testonly_robust_json_parse(content)
    assert result == {'summary': 'from codeblock'}


@pytest.mark.parametrize(
    'content',
    [
        '{"summary": "first"}\n\n{"summary": "second"}',
        'prefix... {"summary": "first"} ... suffix {"summary": "second"}',
    ],
)
def test_robust_json_parse_returns_first_object_when_multiple_present(content: str):
    result = _testonly_robust_json_parse(content)
    assert result == {'summary': 'first'}


@pytest.mark.parametrize(
    'content',
    [
        '',
        '   \n\n\t  ',
        'not json at all',
        '<html><body>502 bad gateway</body></html>',
    ],
)
def test_robust_json_parse_raises_when_no_json_present(content: str):
    with pytest.raises(json.JSONDecodeError) as excinfo:
        _testonly_robust_json_parse(content)

    assert 'Could not extract valid JSON from response' in excinfo.value.msg
