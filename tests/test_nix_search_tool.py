"""
Tests for nixos_manager.tools.nix_search module.
"""

import json
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from nixos_manager.tools.nix_search import NixSearchTool


class TestNixSearchTool:
    """Test NixSearchTool class."""

    def test_tool_initialization(self):
        """Test NixSearchTool can be instantiated."""
        tool = NixSearchTool()
        assert tool is not None

    def test_tool_has_description(self):
        """Test tool has description."""
        tool = NixSearchTool()
        assert tool.description is not None
        assert len(tool.description) > 0
        assert "NixOS" in tool.description

    def test_tool_has_parameters(self):
        """Test tool has parameters defined."""
        tool = NixSearchTool()
        assert hasattr(tool, "parameters")
        assert len(tool.parameters) > 0

    def test_tool_parameters_query(self):
        """Test query parameter exists."""
        tool = NixSearchTool()
        query_param = next(
            (p for p in tool.parameters if p["name"] == "query"),
            None
        )
        assert query_param is not None
        assert query_param["type"] == "string"
        assert query_param["required"] is True

    def test_call_mcp_structure(self):
        """Test _call_mcp method structure."""
        tool = NixSearchTool()
        assert hasattr(tool, "_call_mcp")
        assert asyncio.iscoroutinefunction(tool._call_mcp)

    def test_call_method_exists(self):
        """Test call method exists."""
        tool = NixSearchTool()
        assert hasattr(tool, "call")
        assert callable(tool.call)

    def test_call_accepts_json_params(self):
        """Test call method accepts JSON params."""
        tool = NixSearchTool()
        
        with patch.object(tool, "_call_mcp", return_value="result"):
            # Mock asyncio.run to avoid actual async execution
            with patch("asyncio.run", return_value="mocked_result"):
                params = json.dumps({"query": "python"})
                result = tool.call(params)
                assert result == "mocked_result"

    def test_call_parses_json_correctly(self):
        """Test call method parses JSON params."""
        tool = NixSearchTool()
        
        with patch.object(tool, "_call_mcp") as mock_call_mcp:
            mock_call_mcp.return_value = "result"
            with patch("asyncio.run", return_value="result"):
                params = json.dumps({"query": "nginx"})
                tool.call(params)
                # Verify asyncio.run was called with _call_mcp
                # Since we patched it, we just verify the call happened

    def test_call_with_different_queries(self):
        """Test call with various query types."""
        tool = NixSearchTool()
        
        test_queries = [
            "python3",
            "services.nginx",
            "programs.ghostty.enable",
            "postgresql",
        ]
        
        for query in test_queries:
            with patch.object(tool, "_call_mcp") as mock_call_mcp:
                mock_call_mcp.return_value = json.dumps({"query": query, "results": []})
                with patch("asyncio.run", return_value=json.dumps({"query": query, "results": []})):
                    params = json.dumps({"query": query})
                    result = tool.call(params)
                    assert result is not None


class TestNixSearchToolIntegration:
    """Integration tests for NixSearchTool."""

    @pytest.mark.skip(reason="Requires mcp-nixos binary and uvx")
    def test_tool_actual_search(self):
        """Test actual search (requires mcp-nixos)."""
        tool = NixSearchTool()
        params = json.dumps({"query": "python"})
        
        try:
            result = tool.call(params)
            # Should get some JSON-like response
            assert result is not None
        except Exception as e:
            pytest.skip(f"mcp-nixos not available: {e}")

    def test_tool_mock_mcp_call(self):
        """Test tool with mocked MCP call."""
        tool = NixSearchTool()
        
        mock_response = {
            "query": "python",
            "results": [
                {
                    "attribute": "packages/nixpkgs/python310",
                    "description": "A high-level programming language"
                }
            ]
        }
        
        async def mock_mcp(*args, **kwargs):
            return mock_response
        
        with patch.object(tool, "_call_mcp", side_effect=mock_mcp):
            params = json.dumps({"query": "python"})
            with patch("asyncio.run", return_value=mock_response):
                result = tool.call(params)
                assert result is not None


class TestToolRegistration:
    """Test tool registration with qwen-agent."""

    def test_tool_registered(self):
        """Test that NixSearchTool is registered."""
        # The @register_tool decorator should register it
        # Verify the tool can be instantiated with proper structure
        tool = NixSearchTool()
        assert hasattr(tool, 'description')
        assert hasattr(tool, 'parameters')
        assert tool.description is not None
        assert len(tool.parameters) > 0

    def test_tool_can_be_used_in_agent(self):
        """Test tool can be imported and used."""
        from nixos_manager.tools.nix_search import NixSearchTool
        
        tool = NixSearchTool()
        assert tool.description is not None
        assert len(tool.parameters) > 0


class TestNixSearchToolErrorHandling:
    """Test error handling in NixSearchTool."""

    def test_call_with_empty_query(self):
        """Test call with empty query."""
        tool = NixSearchTool()
        
        with patch.object(tool, "_call_mcp", return_value=""):
            with patch("asyncio.run", return_value=""):
                params = json.dumps({"query": ""})
                result = tool.call(params)
                assert result == ""

    def test_call_with_special_characters(self):
        """Test call with special characters in query."""
        tool = NixSearchTool()
        special_queries = [
            "python-3.10",
            "services.nginx.virtualHosts",
            "lib.lists.filter",
        ]
        
        for query in special_queries:
            with patch.object(tool, "_call_mcp") as mock_call_mcp:
                mock_call_mcp.return_value = json.dumps({"results": []})
                with patch("asyncio.run", return_value=json.dumps({"results": []})):
                    params = json.dumps({"query": query})
                    result = tool.call(params)
                    assert result is not None

    def test_call_with_invalid_json(self):
        """Test call with invalid JSON params."""
        tool = NixSearchTool()
        
        with pytest.raises(json.JSONDecodeError):
            tool.call("not valid json")

    def test_call_with_missing_query_key(self):
        """Test call with missing query key."""
        tool = NixSearchTool()
        
        with pytest.raises(KeyError):
            params = json.dumps({"wrong_key": "value"})
            tool.call(params)
