{
  description = "nixos-manager — local AI agent for NixOS config management";

  inputs = {
    nixpkgs.url            = "github:NixOS/nixpkgs/nixpkgs-unstable";
    flake-parts.url        = "github:hercules-ci/flake-parts";
    pyproject-nix          = { url = "github:pyproject-nix/pyproject.nix";      inputs.nixpkgs.follows = "nixpkgs"; };
    uv2nix                 = { url = "github:pyproject-nix/uv2nix";              inputs.pyproject-nix.follows = "pyproject-nix"; inputs.nixpkgs.follows = "nixpkgs"; };
    pyproject-build-systems = { url = "github:pyproject-nix/build-system-pkgs"; inputs.pyproject-nix.follows = "pyproject-nix"; inputs.uv2nix.follows = "uv2nix"; inputs.nixpkgs.follows = "nixpkgs"; };
  };

  outputs = { self, nixpkgs, flake-parts, pyproject-nix, uv2nix, pyproject-build-systems, ... }@inputs:
  let
    projectConfig = {
      name        = "nixos-manager";
      version     = "0.1.0";
      description = "Local AI agent for managing NixOS flake configurations";
      readme      = "README.md";
      requiresPython = ">=3.12";

      dependencies = [
      ];

      optionalDependencies = {
        dev = [
          "pytest>=8.0"
          "pytest-cov>=5.0"
          "ruff>=0.4"
        ];
      };

      scripts = {
        nixos-manager = "agent:main";
      };

      buildSystem = {
        requires     = [ "hatchling" ];
        buildBackend = "hatchling.build";
      };

      hatchWheelPackages = [ "tools" "config" ];

      toolSettings = {
        uv.devDependencies = [
          "pytest>=8.0"
          "pytest-cov>=5.0"
          "ruff>=0.4"
        ];

        pytest.ini_options = {
          testpaths     = [ "tests" ];
          python_files  = [ "test_*.py" ];
          python_classes = [ "Test*" ];
          python_functions = [ "test_*" ];
          addopts = [ "-v" "--tb=short" "--strict-markers" "-p" "no:warnings" ];
          markers = [
            "integration: requires real binaries (git, nix) installed"
            "slow: takes more than a few seconds"
          ];
        };

        coverage = {
          run    = { source = [ "tools" "config" "agent" ]; omit = [ "tests/*" "*/conftest.py" ]; };
          report = { show_missing = true; skip_covered = false; };
        };

        ruff = {
          line-length  = 100;
          target-version = "py312";
          lint = { select = [ "E" "F" "I" "UP" ]; ignore = [ "E501" ]; };
        };
      };

      shellEnv = {
        NIXMGR_MODEL   = "qwen2.5:7b-instruct";
        NIXMGR_SERVER  = "http://localhost:11434/v1";
        NIXMGR_API_KEY = "ollama";
      };

      shellHints = [
        "python agent.py          # terminal REPL"
        "python agent.py --gui    # Gradio web UI"
        "pytest -v                # run tests"
        "uv add <pkg>             # add a dependency"
      ];

      extraDevPackages = pkgs: [ pkgs.git pkgs.ruff pkgs.stdenv.cc.cc.lib ];
    };

  in
  let
    mkPyprojectAttrs = cfg: {
      "build-system" = {
        requires      = cfg.buildSystem.requires;
        build-backend = cfg.buildSystem.buildBackend;
      };

      project = {
        name            = cfg.name;
        version         = cfg.version;
        description     = cfg.description;
        readme          = cfg.readme;
        requires-python = cfg.requiresPython;
        dependencies    = cfg.dependencies;
        scripts         = cfg.scripts;
        optional-dependencies = cfg.optionalDependencies;
      };

      "tool.hatch.metadata".allow-direct-references = true;

      "tool.hatch.build.targets.wheel".packages = cfg.hatchWheelPackages;

      "dependency-groups"."dev"   = cfg.toolSettings.uv.devDependencies;
      "tool.pytest.ini_options"        = cfg.toolSettings.pytest.ini_options;
      "tool.coverage.run"              = cfg.toolSettings.coverage.run;
      "tool.coverage.report"           = cfg.toolSettings.coverage.report;
      "tool.ruff"                      = builtins.removeAttrs cfg.toolSettings.ruff [ "lint" ];
      "tool.ruff.lint"                = cfg.toolSettings.ruff.lint;
    };

    # Store the Python writer as a plain file — avoids Nix string escaping issues.
    mkPyprojectWriter = pkgs: cfg:
      let
        jsonData = pkgs.writeText "pyproject-data.json"
                     (builtins.toJSON (mkPyprojectAttrs cfg));
        writerPy = pkgs.writeText "write-pyproject.py" ''
import json, sys

with open(sys.argv[1]) as f:
    data = json.load(f)

def to_toml_value(v):
    if isinstance(v, bool): return "true" if v else "false"
    elif isinstance(v, int): return str(v)
    elif isinstance(v, float): return str(v)
    elif isinstance(v, str): return json.dumps(v)
    elif isinstance(v, list):
        if all(isinstance(i, (str, bool, int, float)) for i in v):
            items = ", ".join(to_toml_value(i) for i in v)
            return "[" + items + "]"
        else:
            rows = ["["]
            for item in v:
                rows.append("    " + to_toml_value(item) + ",")
            rows.append("]")
            return "\n".join(rows)
    elif isinstance(v, dict): return None
    return json.dumps(str(v))

def write_section(out, key, value):
    if isinstance(value, dict):
        deferred = []
        out.append("\n[" + key + "]")
        for k, v in value.items():
            if isinstance(v, dict):
                deferred.append((k, v))
            else:
                tv = to_toml_value(v)
                if tv is not None:
                    out.append(k + " = " + tv)
        for k, v in deferred:
            write_section(out, key + "." + k, v)
    else:
        tv = to_toml_value(value)
        if tv is not None:
            out.append(key + " = " + tv)

lines = ["# This file is generated by flake.nix — edit projectConfig there."]
for section, value in data.items():
    write_section(lines, section, value)

with open(sys.argv[2], "w") as f:
    f.write("\n".join(lines) + "\n")
        '';
      in { inherit jsonData writerPy; };


    mkBuildSystemOverlay = final: prev:
      let
        inherit (final) resolveBuildSystem;
        buildSystemOverrides = {
          packaging.flit-core             = [ ];
          tomli.flit-core                  = [ ];
          pip         = { setuptools = [ ]; wheel = [ ]; };
          pluggy.setuptools                = [ ];
          trove-classifiers.setuptools     = [ ];
          coverage.setuptools              = [ ];
          blinker.setuptools               = [ ];
          certifi.setuptools               = [ ];
          charset-normalizer.setuptools    = [ ];
          requests.setuptools              = [ ];
          pysocks.setuptools               = [ ];
          pytest-cov.setuptools            = [ ];
          tqdm.setuptools                  = [ ];
          six.setuptools                   = [ ];
          platformdirs.hatchling           = [ ];
          colorama.setuptools              = [ ];
          wrapt.setuptools                 = [ ];
          deprecated.setuptools            = [ ];
          filelock.hatchling               = [ ];
          zipp.setuptools                  = [ ];
          jieba.setuptools                 = [ ];
          cffi.setuptools                  = [ ];
          soundfile.cffi                   = [ ];
          tiktoken    = { setuptools = [ ]; };
          easyocr     = { setuptools = [ ]; };
          decord      = { setuptools = [ ]; };
          urllib3     = { hatchling = [ ]; hatch-vcs = [ ]; };
          idna.flit-core                   = [ ];
          httpcore    = { hatchling = [ ]; };
          httpx       = { hatchling = [ ]; };
          attrs = { hatchling = [ ]; hatch-vcs = [ ]; hatch-fancy-pypi-readme = [ ]; };
          hatchling = { pathspec = [ ]; pluggy = [ ]; packaging = [ ]; trove-classifiers = [ ]; };
          pathspec.flit-core               = [ ];
          pytest-timeout.setuptools        = [ ];
          pytest-mock.setuptools           = [ ];
        };
      in
      builtins.mapAttrs (
        name: spec:
        if builtins.hasAttr name prev
        then prev.${name}.overrideAttrs (old: {
          nativeBuildInputs = (old.nativeBuildInputs or [ ]) ++ resolveBuildSystem spec;
        })
        else builtins.throw "buildSystemOverrides: package '${name}' not found in pythonSet"
      ) (builtins.intersectAttrs prev buildSystemOverrides);

  in
  flake-parts.lib.mkFlake { inherit inputs; } {
    systems = [ "x86_64-linux" "aarch64-linux" "aarch64-darwin" "x86_64-darwin" ];

    perSystem = { pkgs, system, ... }:
      let
        cfg    = projectConfig;
        python = pkgs.python312;
        workspace = uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ./.; };
        overlay = workspace.mkPyprojectOverlay { sourcePreference = "wheel"; };
        editableOverlay = workspace.mkEditablePyprojectOverlay { root = "$REPO_ROOT"; };

        # hatchling needs editables at build time for editable wheel support
        editablesOverlay = final: prev: {
          nixos-manager = prev.nixos-manager.overrideAttrs (old: {
            nativeBuildInputs = (old.nativeBuildInputs or [ ]) ++ [ final.editables ];
          });
        };

        pythonSets =
          (pkgs.callPackage pyproject-nix.build.packages { inherit python; }).overrideScope (
            pkgs.lib.composeManyExtensions [
              pyproject-build-systems.overlays.default
              overlay
              mkBuildSystemOverlay
              editablesOverlay
            ]
          );

        pyprojectFiles = mkPyprojectWriter pkgs cfg;

      in
      {
        devShells.default =
          let
            pythonSet = pythonSets.overrideScope editableOverlay;
            virtualenv = pythonSet.mkVirtualEnv "${cfg.name}-dev" workspace.deps.all;
            banner = builtins.concatStringsSep "\n    " cfg.shellHints;
          in
          pkgs.mkShell {
            packages = [ virtualenv pkgs.uv ] ++ cfg.extraDevPackages pkgs;
            env = cfg.shellEnv // {
              UV_NO_SYNC          = "1";
              UV_PYTHON           = "${python.interpreter}";
              UV_PYTHON_DOWNLOADS = "never";
              LD_LIBRARY_PATH="${pkgs.stdenv.cc.cc.lib}/lib:$LD_LIBRARY_PATH";
            };
            shellHook = ''
              export REPO_ROOT=$(git rev-parse --show-toplevel)
              unset PYTHONPATH
              echo ""
              echo "🔧 ${cfg.name} dev shell"
              echo "    ${banner}"
              echo ""
            '';
          };

        devShells.bootstrap = pkgs.mkShell {
          packages = [ pkgs.uv python ];
          shellHook = ''
            dest="$(git rev-parse --show-toplevel)/pyproject.toml"
            if [ ! -f "$dest" ]; then
              python3 ${pyprojectFiles.writerPy} ${pyprojectFiles.jsonData} "$dest"
              chmod 644 "$dest"
              echo "✔ generated pyproject.toml"
            fi
            echo "${cfg.name} bootstrap — run: uv sync  then  exit && nix develop"
            trap 'git add uv.lock pyproject.toml 2>/dev/null || true' EXIT
          '';
        };

        packages.default = pythonSets.mkVirtualEnv "${cfg.name}-env" workspace.deps.default;

        apps.default = {
          type = "app";
          program = pkgs.lib.getExe (pkgs.writeShellApplication {
            name = cfg.name;
            runtimeInputs = [
              (pythonSets.mkVirtualEnv "${cfg.name}-env" workspace.deps.default)
              pkgs.git
            ];
            text = ''
              export REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo ".")
              python -m agent "$@"
            '';
          });
        };

        checks.tests =
          let
            testEnv = pythonSets.mkVirtualEnv "${cfg.name}-test" workspace.deps.all;
          in
          pkgs.stdenv.mkDerivation {
            name         = "${cfg.name}-tests";
            src          = ./.;
            nativeBuildInputs = [ testEnv ];
            checkPhase   = ''
              export NIXOS_REPO_PATH="$(mktemp -d)"
              export HOME="$(mktemp -d)"
              pytest --tb=short -q
            '';
            buildPhase   = "true";
            installPhase = "mkdir -p $out";
            doCheck      = true;
          };

        # Force-regenerate pyproject.toml from projectConfig (resets any uv add changes).
        apps.sync-pyproject = {
          type = "app";
          program = pkgs.lib.getExe (pkgs.writeShellApplication {
            name = "sync-pyproject";
            runtimeInputs = [ pkgs.python3 ];
            text = ''
              dest="$(git rev-parse --show-toplevel)/pyproject.toml"
              python3 ${pyprojectFiles.writerPy} ${pyprojectFiles.jsonData} "$dest"
              chmod 644 "$dest"
              echo "✔ wrote $dest"
            '';
          });
        };
      };
  };
}