"""Tests for OllamaModel."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ollama_agent.models import OllamaModel


def _make_http_response(body: dict) -> MagicMock:
    r = MagicMock()
    r.json.return_value = body
    r.raise_for_status = MagicMock()
    return r


BASIC_COMPLETION = {
    "choices": [{"message": {"role": "assistant", "content": "Hello!", "tool_calls": None}}]
}

TOOL_CALL_COMPLETION = {
    "choices": [{"message": {
        "role": "assistant", "content": "",
        "tool_calls": [{
            "id": "call_1", "type": "function",
            "function": {"name": "calculator", "arguments": '{"expression": "2+2"}'},
        }],
    }}]
}

TAGS_RESPONSE = {"models": [{"name": "qwen2.5:7b"}, {"name": "gemma3:4b"}]}


class TestOllamaModelInit:
    def test_defaults(self) -> None:
        m = OllamaModel()
        assert m.model_id == "qwen2.5:7b"
        assert m.base_url == "http://localhost:11434"

    def test_trailing_slash_stripped(self) -> None:
        m = OllamaModel(base_url="http://localhost:11434/")
        assert not m.base_url.endswith("/")

    def test_repr(self) -> None:
        assert "gemma3:4b" in repr(OllamaModel(model_id="gemma3:4b"))


class TestOllamaModelCall:
    def test_basic_text_response(self) -> None:
        with patch("httpx.Client.post", return_value=_make_http_response(BASIC_COMPLETION)):
            msg = OllamaModel().generate([{"role": "user", "content": "hi"}])
        assert msg.content == "Hello!"
        assert msg.tool_calls is None

    def test_payload_contains_model(self) -> None:
        captured: list[dict] = []
        def fake_post(url, *, json, **kwargs):
            captured.append(json)
            return _make_http_response(BASIC_COMPLETION)
        with patch("httpx.Client.post", side_effect=fake_post):
            OllamaModel(model_id="gemma3:4b").generate([{"role": "user", "content": "hi"}])
        assert captured[0]["model"] == "gemma3:4b"

    def test_stop_sequences_forwarded(self) -> None:
        captured: list[dict] = []
        def fake_post(url, *, json, **kwargs):
            captured.append(json)
            return _make_http_response(BASIC_COMPLETION)
        with patch("httpx.Client.post", side_effect=fake_post):
            OllamaModel().generate([{"role": "user", "content": "hi"}], stop_sequences=["STOP"])
        assert captured[0]["stop"] == ["STOP"]

    def test_tool_call_response_parsed(self) -> None:
        with patch("httpx.Client.post", return_value=_make_http_response(TOOL_CALL_COMPLETION)):
            msg = OllamaModel().generate([{"role": "user", "content": "calculate 2+2"}])
        assert msg.tool_calls is not None
        tc = msg.tool_calls[0]
        assert tc.function.name == "calculator"
        assert tc.function.arguments["expression"] == "2+2"

    def test_tool_call_args_string_parsed_to_dict(self) -> None:
        completion = {"choices": [{"message": {"role": "assistant", "content": "",
            "tool_calls": [{"id": "c1", "type": "function",
                "function": {"name": "calculator", "arguments": '{"expression": "3*3"}'}}]}}]}
        with patch("httpx.Client.post", return_value=_make_http_response(completion)):
            msg = OllamaModel().generate([{"role": "user", "content": "hi"}])
        args = msg.tool_calls[0].function.arguments
        assert isinstance(args, dict)
        assert args["expression"] == "3*3"


class TestOllamaModelConnection:
    def test_check_connection_success(self) -> None:
        with patch("httpx.Client.get", return_value=_make_http_response(TAGS_RESPONSE)):
            assert OllamaModel(model_id="qwen2.5:7b").check_connection() is True

    def test_check_connection_model_missing(self) -> None:
        with patch("httpx.Client.get", return_value=_make_http_response({"models": []})):
            assert OllamaModel(model_id="unknown:7b").check_connection() is False

    def test_check_connection_server_down(self) -> None:
        with patch("httpx.Client.get", side_effect=Exception("refused")):
            assert OllamaModel().check_connection() is False

    def test_list_models(self) -> None:
        with patch("httpx.Client.get", return_value=_make_http_response(TAGS_RESPONSE)):
            models = OllamaModel().list_models()
        assert "qwen2.5:7b" in models


class TestBuildToolSchemas:
    def _make_tool(self, name, description, inputs):
        t = MagicMock()
        t.name = name
        t.description = description
        t.inputs = inputs
        return t

    def test_basic_schema(self) -> None:
        tool = self._make_tool("calculator", "Evaluate math",
                               {"expression": {"type": "string", "description": "Math expr"}})
        schemas = OllamaModel._build_tool_schemas([tool])
        fn = schemas[0]["function"]
        assert fn["name"] == "calculator"
        assert "expression" in fn["parameters"]["required"]

    def test_nullable_field_not_required(self) -> None:
        tool = self._make_tool("reader", "Read file",
                               {"path": {"type": "string"},
                                "max_chars": {"type": "integer", "nullable": True}})
        required = OllamaModel._build_tool_schemas([tool])[0]["function"]["parameters"]["required"]
        assert "path" in required
        assert "max_chars" not in required

    def test_malformed_tool_skipped(self) -> None:
        assert OllamaModel._build_tool_schemas([MagicMock(spec=[])]) == []