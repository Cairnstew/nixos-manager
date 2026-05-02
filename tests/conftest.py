import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Make sure the project root is importable
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Smart Stubbing: Only stub qwen_agent if it's NOT installed.
# This allows live tests to use the real library while unit tests stay light.
# ---------------------------------------------------------------------------
try:
    import qwen_agent
    HAS_QWEN = True
except ImportError:
    HAS_QWEN = False
    
    class _FakeBaseTool:
        """Minimal BaseTool stand-in so tools can be instantiated in tests."""
        name: str = ""
        description: str = ""
        parameters: list = []
        def call(self, params, **kwargs) -> str:
            raise NotImplementedError

    def _fake_register_tool(name: str):
        def decorator(cls):
            return cls
        return decorator

    # Patch the modules so the project can at least import them
    qwen_mock = MagicMock()
    qwen_mock.tools.base.BaseTool = _FakeBaseTool
    qwen_mock.tools.base.register_tool = _fake_register_tool
    sys.modules.setdefault("qwen_agent", qwen_mock)
    sys.modules.setdefault("qwen_agent.tools", qwen_mock.tools)
    sys.modules.setdefault("qwen_agent.tools.base", qwen_mock.tools.base)
    sys.modules.setdefault("qwen_agent.agents", MagicMock())
    sys.modules.setdefault("qwen_agent.llm", MagicMock())
    sys.modules.setdefault("qwen_agent.gui", MagicMock())


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """
    A temporary directory acting as a fake NixOS repo.
    Patches NIXOS_REPO_PATH in settings and any modules that already imported it.
    """
    # Patch the central settings
    monkeypatch.setattr("config.settings.NIXOS_REPO_PATH", tmp_path)

    # Force update any tool modules that might have cached the old path
    tool_mods = [
        "tools.repo_reader",
        "tools.repo_writer",
        "tools.nix_ops",
    ]
    for mod_name in tool_mods:
        if mod_name in sys.modules:
            mod = sys.modules[mod_name]
            if hasattr(mod, "NIXOS_REPO_PATH"):
                monkeypatch.setattr(mod, "NIXOS_REPO_PATH", tmp_path)

    return tmp_path


@pytest.fixture()
def nix_file(repo: Path) -> Path:
    """Create a sample configuration.nix."""
    f = repo / "configuration.nix"
    f.write_text('{ config, pkgs, ... }:\n{\n  networking.hostName = "myhost";\n}\n')
    return f


@pytest.fixture()
def nested_nix_files(repo: Path) -> list[Path]:
    """Create a directory structure for testing recursion."""
    files = [
        repo / "flake.nix",
        repo / "hosts" / "desktop.nix",
        repo / "modules" / "programs" / "neovim.nix",
    ]
    for f in files:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("# placeholder\n")
    return files

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def call_tool(tool_cls, params: dict) -> str:
    """Instantiate a tool and call it, returning the string result."""
    instance = tool_cls()
    return instance.call(params)


def call_tool_json(tool_cls, params: dict) -> str:
    """Same as call_tool but passes params as a JSON string."""
    instance = tool_cls()
    return instance.call(json.dumps(params))