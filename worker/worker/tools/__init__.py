from .base import BaseTool

TOOL_REGISTRY: dict[str, BaseTool] = {}
# Maps OpenAI-safe api_name (underscores) back to internal dot-name
API_NAME_MAP: dict[str, str] = {}


def register(tool: BaseTool) -> None:
    TOOL_REGISTRY[tool.name] = tool
    if tool.api_name != tool.name:
        API_NAME_MAP[tool.api_name] = tool.name


def get_tools(names: list[str]) -> list[BaseTool]:
    return [TOOL_REGISTRY[n] for n in names if n in TOOL_REGISTRY]
