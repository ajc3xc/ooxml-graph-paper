import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import count_meridian_docs_tools as c  # noqa: E402

SERVER = '''
@mcp.tool()
def insert_table(): ...
@mcp.tool
def locate_anchor(): ...
def not_a_tool(): ...
@other.tool()
def also_not(): ...
'''


def test_registered_tools_finds_only_mcp_tool_decorators():
    assert c.registered_tools(SERVER) == ["insert_table", "locate_anchor"]


def test_classify_counts_editing_and_anchoredit():
    result = c.classify(sorted(c.ANCHOREDIT | {"locate_anchor", "edit_caption"}))
    assert result["counts"]["total"] == 13
    assert result["counts"]["editing"] == 12
    assert result["counts"]["anchoredit"] == 11
    assert result["tools"]["locate_anchor"] == {"class": "discovery", "anchoredit": False}


def test_every_anchoredit_tool_is_an_editing_tool():
    assert all(c.CLASSES[t] == "editing" for t in c.ANCHOREDIT)


def test_classify_rejects_an_unclassified_tool():
    with pytest.raises(SystemExit, match="unclassified"):
        c.classify(sorted(c.ANCHOREDIT | {"brand_new_tool"}))
