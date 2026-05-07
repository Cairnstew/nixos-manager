{ lib, ... }:
{
  options.project = with lib; {
    name                 = mkOption { type = types.str; };
    version              = mkOption { type = types.str; };
    description          = mkOption { type = types.str; };
    readme               = mkOption { type = types.str; default = "README.md"; };
    requiresPython       = mkOption { type = types.str; default = ">=3.12"; };
    dependencies         = mkOption { type = types.listOf types.str; default = []; };
    optionalDependencies = mkOption { type = types.attrsOf (types.listOf types.str); default = {}; };
    scripts              = mkOption { type = types.attrsOf types.str; default = {}; };
    devDependencies      = mkOption { type = types.listOf types.str; default = []; };
    shellEnv             = mkOption { type = types.attrsOf types.str; default = {}; };
    shellHints           = mkOption { type = types.listOf types.str; default = []; };
  };

  config.project = {
    name        = "nixos-manager";
    version     = "0.1.0";
    description = "Local AI agent for managing NixOS flake configurations";

    dependencies = [
      "qwen-agent[code-interpreter,gui,mcp,rag]>=0.0.3"
      "soundfile>=0.13.1"
    ];

    optionalDependencies.dev = [
      "pytest>=8.0"
      "pytest-cov>=5.0"
      "ruff>=0.4"
    ];

    scripts = {
      nixos-manager = "nixos_manager.agent:main";
      searchix      = "searchix.cli:main";
    };

    devDependencies = [
      "pytest>=8.0"
      "pytest-cov>=5.0"
      "ruff>=0.4"
      "pytest-asyncio>=1.3.0"
    ];

    shellEnv = {
      NIXMGR_MODEL   = "gemma4:e4b";
      NIXMGR_SERVER  = "http://localhost:11434/v1";
      NIXMGR_API_KEY = "ollama";
    };

    shellHints = [
      "python agent.py          # terminal REPL"
      "python agent.py --gui    # Gradio web UI"
      "pytest -v                # run tests"
      "uv add <pkg>             # add a dependency"
    ];
  };
}