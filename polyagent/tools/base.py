"""Tool base class + result type + JSON-Schema auto-generation.

A ``Tool`` declares a pydantic ``args_model``; its OpenAI function-calling
schema is generated automatically — no hand-written JSON.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel, Field, ValidationError


class ToolResult(BaseModel):
    output: str
    error: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class Tool(ABC):
    name: ClassVar[str]
    description: ClassVar[str]
    args_model: ClassVar[type[BaseModel]]

    @abstractmethod
    async def run(self, args: BaseModel) -> ToolResult: ...

    @classmethod
    def schema(cls) -> dict[str, Any]:
        """OpenAI function-calling tool schema, derived from ``args_model``."""
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": cls.description,
                "parameters": cls.args_model.model_json_schema(),
            },
        }

    async def call(self, raw_args: dict[str, Any]) -> ToolResult:
        """Validate raw args via pydantic, then run."""
        try:
            parsed = self.args_model.model_validate(raw_args)
        except ValidationError as exc:
            return ToolResult(output=f"invalid arguments: {exc}", error=True)
        return await self.run(parsed)
