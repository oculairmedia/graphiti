import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERVER_ROOT = PROJECT_ROOT / "server"

for candidate in (PROJECT_ROOT, SERVER_ROOT):
    path_str = str(candidate)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from graph_service.dto.common import Message


def test_message_defaults_source_description():
    msg = Message(content="hello", role_type="user", role=None)
    assert msg.source_description == "unspecified"


def test_message_trims_source_description():
    msg = Message(
        content="hello",
        role_type="assistant",
        role="bot",
        source_description="  slack export  ",
    )
    assert msg.source_description == "slack export"
