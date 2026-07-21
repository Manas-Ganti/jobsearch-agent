"""LLMBackend protocol + implementations.

Pipeline code never learns which of these it is talking to. Structured output is
part of the protocol, not a caller concern: `schema` means the backend must use
JSON-constrained decoding, so parsing cannot break on malformed output.
"""

from __future__ import annotations

import json
import logging
from typing import Protocol, TypeVar, runtime_checkable

import httpx
from pydantic import BaseModel, ValidationError

from ..registry import Registry

log = logging.getLogger(__name__)

LLM_BACKENDS: Registry["LLMBackend"] = Registry("llm backend")

M = TypeVar("M", bound=BaseModel)


@runtime_checkable
class LLMBackend(Protocol):
    model: str

    def complete(
        self, prompt: str, *, system: str | None = None, schema: dict | None = None
    ) -> str:
        """Return raw completion text. If `schema` is given the text is JSON
        matching that schema, produced by constrained decoding."""


def complete_model(
    backend: LLMBackend,
    prompt: str,
    model_cls: type[M],
    *,
    system: str | None = None,
    retries: int = 1,
) -> M | None:
    """Constrained-decode into a pydantic model. Returns None if it never parses."""
    schema = model_cls.model_json_schema()
    for attempt in range(retries + 1):
        text = backend.complete(prompt, system=system, schema=schema)
        try:
            return model_cls.model_validate_json(text)
        except (ValidationError, ValueError) as exc:
            log.warning(
                "LLM output failed %s validation (attempt %d): %s",
                model_cls.__name__,
                attempt + 1,
                exc,
            )
    return None


@LLM_BACKENDS.register("ollama")
class OllamaLLM:
    """Local default. Uses Ollama's `format` field for JSON-schema decoding."""

    def __init__(
        self,
        model: str = "qwen2.5:7b-instruct",
        base_url: str = "http://localhost:11434",
        options: dict | None = None,
        timeout: float = 180.0,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.options = {"temperature": 0.0, **(options or {})}
        self._client = httpx.Client(timeout=timeout)

    def complete(
        self, prompt: str, *, system: str | None = None, schema: dict | None = None
    ) -> str:
        payload: dict = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": self.options,
        }
        if system:
            payload["system"] = system
        if schema is not None:
            payload["format"] = schema
        resp = self._client.post(f"{self.base_url}/api/generate", json=payload)
        resp.raise_for_status()
        return resp.json().get("response", "")


@LLM_BACKENDS.register("vllm")
class VLLMChat:
    """OpenAI-compatible server (vLLM, llama.cpp, TGI). Guided decoding via
    `response_format: json_schema`."""

    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:8000/v1",
        options: dict | None = None,
        api_key: str = "EMPTY",
        timeout: float = 180.0,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.options = {"temperature": 0.0, **(options or {})}
        self._client = httpx.Client(
            timeout=timeout, headers={"Authorization": f"Bearer {api_key}"}
        )

    def complete(
        self, prompt: str, *, system: str | None = None, schema: dict | None = None
    ) -> str:
        messages = ([{"role": "system", "content": system}] if system else []) + [
            {"role": "user", "content": prompt}
        ]
        payload: dict = {"model": self.model, "messages": messages, **self.options}
        if schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "output", "schema": schema, "strict": True},
            }
        resp = self._client.post(f"{self.base_url}/chat/completions", json=payload)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"] or ""


@LLM_BACKENDS.register("stub")
class StubLLM:
    """Offline backend for smoke runs and tests. Emits schema-shaped defaults."""

    def __init__(self, model: str = "stub", **_: object) -> None:
        self.model = model

    def complete(
        self, prompt: str, *, system: str | None = None, schema: dict | None = None
    ) -> str:
        if schema is None:
            return ""
        return json.dumps(_default_for(schema))


def _default_for(schema: dict) -> object:
    defs = schema.get("$defs", {})

    def build(node: dict) -> object:
        if "$ref" in node:
            return build(defs.get(node["$ref"].rsplit("/", 1)[-1], {}))
        for key in ("anyOf", "oneOf"):
            if key in node:
                return build(node[key][0])
        kind = node.get("type")
        if kind == "object":
            props = node.get("properties", {})
            required = node.get("required", list(props))
            return {k: build(v) for k, v in props.items() if k in required}
        if kind == "array":
            return []
        if kind in ("number", "integer"):
            return 0
        if kind == "boolean":
            return False
        if kind == "null":
            return None
        return ""

    return build(schema)


def build_llm(cfg) -> LLMBackend:
    LLM_BACKENDS.discover(__package__)
    return LLM_BACKENDS.create(
        cfg.backend, model=cfg.model, base_url=cfg.base_url, options=cfg.options
    )
