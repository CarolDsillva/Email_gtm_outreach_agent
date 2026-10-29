"""Thin adapters around the external services.

The pipeline depends only on the two small protocols below, so it can be run
against fakes in tests and swapped to other providers without touching the
pipeline logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Protocol, Type, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class Doc:
    url: str
    title: str
    text: str


class SearchClient(Protocol):
    def search(self, query: str, *, num_results: int = 5,
               category: Optional[str] = None,
               include_domains: Optional[List[str]] = None,
               max_chars: int = 1500) -> List[Doc]: ...


class LLMClient(Protocol):
    model: str

    def structured(self, system: str, user: str, schema: Type[T]) -> T: ...


class ExaSearch:
    """Web search + page contents via Exa."""

    def __init__(self, api_key: str):
        from exa_py import Exa

        self._exa = Exa(api_key)

    def search(self, query: str, *, num_results: int = 5,
               category: Optional[str] = None,
               include_domains: Optional[List[str]] = None,
               max_chars: int = 1500) -> List[Doc]:
        kwargs = {"num_results": num_results,
                  "text": {"max_characters": max_chars}}
        if category:
            kwargs["category"] = category
        if include_domains:
            kwargs["include_domains"] = include_domains
        response = self._exa.search_and_contents(query, **kwargs)
        return [Doc(url=r.url, title=r.title or "", text=(r.text or "")[:max_chars])
                for r in response.results]


class OpenAILLM:
    """OpenAI chat model with Pydantic structured outputs."""

    def __init__(self, api_key: str, model: str = "gpt-5-mini"):
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key, max_retries=3)
        self.model = model

    def structured(self, system: str, user: str, schema: Type[T]) -> T:
        completion = self._client.chat.completions.parse(
            model=self.model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            response_format=schema,
        )
        message = completion.choices[0].message
        if message.refusal:
            raise RuntimeError(f"Model refused: {message.refusal}")
        if message.parsed is None:
            raise RuntimeError("Model returned no structured output")
        return message.parsed
