"""Tests for built-in tools."""

from __future__ import annotations

import os
import tempfile

import pytest

from ollama_agent.tools import (
    CalculatorTool, DateTimeTool, FileReaderTool, ShellTool, get_default_tools,
)


class TestCalculatorTool:
    def setup_method(self) -> None:
        self.tool = CalculatorTool()

    def test_basic_arithmetic(self) -> None:
        assert self.tool.forward("2 + 2") == "4"

    def test_multiplication(self) -> None:
        assert self.tool.forward("6 * 7") == "42"

    def test_power(self) -> None:
        assert self.tool.forward("2 ** 10") == "1024"

    def test_sqrt(self) -> None:
        assert float(self.tool.forward("sqrt(144)")) == pytest.approx(12.0)

    def test_float_result(self) -> None:
        assert float(self.tool.forward("1 / 3")) == pytest.approx(1 / 3, rel=1e-6)

    def test_invalid_expression_returns_error(self) -> None:
        assert self.tool.forward("import os; os.system('ls')").startswith("Error")

    def test_name_error_returns_error(self) -> None:
        assert self.tool.forward("undefined_var + 1").startswith("Error")

    def test_no_builtins_access(self) -> None:
        assert self.tool.forward("__import__('os').getcwd()").startswith("Error")

    def test_tool_metadata(self) -> None:
        assert self.tool.name == "calculator"


class TestDateTimeTool:
    def test_returns_iso_string(self) -> None:
        import datetime
        result = DateTimeTool().forward()
        dt = datetime.datetime.fromisoformat(result)
        assert dt.tzinfo is not None

    def test_tool_metadata(self) -> None:
        assert DateTimeTool().name == "datetime"


class TestShellTool:
    def setup_method(self) -> None:
        self.tool = ShellTool()

    def test_echo_command(self) -> None:
        assert "hello_world" in self.tool.forward("echo hello_world")

    def test_blocked_rm_rf(self) -> None:
        assert "Blocked" in self.tool.forward("rm -rf /")

    def test_blocked_fork_bomb(self) -> None:
        assert "Blocked" in self.tool.forward(":(){:|:&};:")

    def test_output_truncated(self) -> None:
        result = self.tool.forward("python3 -c \"print('x' * 8000)\"")
        assert len(result) <= 4000


class TestFileReaderTool:
    def setup_method(self) -> None:
        self.tool = FileReaderTool()

    def test_reads_file(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Hello, world!")
            path = f.name
        try:
            assert self.tool.forward(path) == "Hello, world!"
        finally:
            os.unlink(path)

    def test_max_chars_respected(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("A" * 1000)
            path = f.name
        try:
            assert len(self.tool.forward(path, max_chars=100)) == 100
        finally:
            os.unlink(path)

    def test_missing_file_returns_error(self) -> None:
        assert self.tool.forward("/nonexistent/file.txt").startswith("Error")


class TestGetDefaultTools:
    def test_contains_calculator_and_datetime(self) -> None:
        names = [t.name for t in get_default_tools()]
        assert "calculator" in names
        assert "datetime" in names

    def test_returns_new_instances(self) -> None:
        assert get_default_tools() is not get_default_tools()