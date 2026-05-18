from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    name: str
    description: str
    parameters: dict[str, Any]

    @property
    def api_name(self) -> str:
        # OpenAI function names must match ^[a-zA-Z0-9_-]{1,64}$; dots are invalid
        return self.name.replace(".", "_")

    @abstractmethod
    async def execute(self, **kwargs: Any) -> str: ...

    def to_openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.api_name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
