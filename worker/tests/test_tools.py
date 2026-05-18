# pyright: reportPrivateUsage=false, reportUnusedImport=false
"""Tests for tool base class, registry, and bus static tools."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from worker.tools import TOOL_REGISTRY, get_tools, register
from worker.tools.base import BaseTool

# ── P6.4-01: BaseTool + Registry ─────────────────────────────────────────────


class DummyTool(BaseTool):
    name = "dummy.test"
    description = "A dummy tool for testing"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {"msg": {"type": "string"}},
        "required": ["msg"],
    }

    async def execute(self, **kwargs: Any) -> str:
        return f"echo: {kwargs.get('msg', '')}"


def test_register_and_get() -> None:
    tool = DummyTool()
    register(tool)
    assert "dummy.test" in TOOL_REGISTRY
    found = get_tools(["dummy.test"])
    assert len(found) == 1
    assert found[0].name == "dummy.test"


def test_get_tools_missing_name() -> None:
    result = get_tools(["does.not.exist"])
    assert result == []


def test_to_openai_schema() -> None:
    tool = DummyTool()
    schema = tool.to_openai_schema()
    assert schema["type"] == "function"
    fn = schema["function"]
    assert fn["name"] == "dummy.test"
    assert fn["description"] == "A dummy tool for testing"
    assert fn["parameters"]["type"] == "object"
    assert "msg" in fn["parameters"]["properties"]


@pytest.mark.asyncio
async def test_execute() -> None:
    tool = DummyTool()
    result = await tool.execute(msg="hello")
    assert result == "echo: hello"


# ── P6.4-05: Bus static tools (mock DB) ──────────────────────────────────────


@pytest.mark.asyncio
async def test_search_stops_returns_results() -> None:
    """bus.search_stops finds stops by name."""
    import worker.tools.bus as bus_module

    mock_stop = MagicMock()
    mock_stop.uid = "YUN298841"
    mock_stop.nameZh = "斗六火車站"
    mock_stop.city = "YunlinCounty"

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_stop]

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    rows = await bus_module._search_stops(mock_db, "斗六", None, 5)
    assert len(rows) == 1
    assert rows[0]["nameZh"] == "斗六火車站"


@pytest.mark.asyncio
async def test_search_stops_no_results() -> None:
    """bus.search_stops returns empty list when nothing found."""
    import worker.tools.bus as bus_module

    empty_result = MagicMock()
    empty_result.scalars.return_value.all.return_value = []

    mock_db = AsyncMock()
    # First call (ILIKE) returns empty; second call (trigram fallback) raises
    mock_db.execute = AsyncMock(
        side_effect=[empty_result, Exception("no pg_trgm")]
    )

    rows = await bus_module._search_stops(mock_db, "不存在的站", None, 5)
    assert rows == []


@pytest.mark.asyncio
async def test_list_stops_not_found() -> None:
    """bus.list_stops returns error string when route not found."""
    import worker.tools.bus as bus_module

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    text, stops = await bus_module._list_stops(mock_db, "不存在路線", 0)
    assert "找不到路線" in text
    assert stops == []


@pytest.mark.asyncio
async def test_next_departures_no_stops() -> None:
    """bus.next_departures returns error string when stop not found."""
    import worker.tools.bus as bus_module

    empty_result = MagicMock()
    empty_result.scalars.return_value.all.return_value = []

    mock_db = AsyncMock()
    # _search_stops: first call (ILIKE) empty, second call (trigram) fails → []
    mock_db.execute = AsyncMock(
        side_effect=[empty_result, Exception("no pg_trgm")]
    )

    result = await bus_module._next_departures(mock_db, "不存在的站", None, 1, 3)
    assert "找不到" in result


def test_bus_tools_registered() -> None:
    """Bus tools are in TOOL_REGISTRY after importing bus module."""
    import worker.tools.bus  # noqa: F401

    expected = [
        "bus.search_stops",
        "bus.find_routes",
        "bus.list_stops",
        "bus.next_departures",
    ]
    for name in expected:
        assert name in TOOL_REGISTRY, f"{name} not in registry"


def test_tdx_tool_registered() -> None:
    """TDX tool is in TOOL_REGISTRY after importing tdx_realtime module."""
    import worker.tools.tdx_realtime  # noqa: F401

    assert "tdx.bus_arrival" in TOOL_REGISTRY
