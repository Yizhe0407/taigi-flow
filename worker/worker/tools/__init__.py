from .base import BaseTool

TOOL_REGISTRY: dict[str, BaseTool] = {}


def register(tool: BaseTool) -> None:
    TOOL_REGISTRY[tool.name] = tool


def get_tools(names: list[str]) -> list[BaseTool]:
    return [TOOL_REGISTRY[n] for n in names if n in TOOL_REGISTRY]
