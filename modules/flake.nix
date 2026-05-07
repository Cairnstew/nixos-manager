{ inputs, ... }:
{
  imports = [ ./project.nix ];

  perSystem = { pkgs, system, ... }:
    let
      cfg = (pkgs.lib.evalModules {
        modules = [ ./project.nix ];
        specialArgs = { inherit (pkgs) lib; };
        }).config.project;
      pyEnv      = import ./python-env.nix { inherit pkgs inputs; };
      pf         = import ./pyproject.nix  { inherit pkgs cfg; };
      searchix   = inputs.searchix.packages.${system}.default;
      extraDev   = [ pkgs.git pkgs.ruff pkgs.stdenv.cc.cc.lib ];
      banner     = builtins.concatStringsSep "\n    " cfg.shellHints;

      prodEnv = pyEnv.basePythonSets.mkVirtualEnv "${cfg.name}-env"  pyEnv.workspace.deps.default;
      testEnv = pyEnv.basePythonSets.mkVirtualEnv "${cfg.name}-test" pyEnv.workspace.deps.all;
      devEnv  = pyEnv.devEnv.mkVirtualEnv          "${cfg.name}-dev"  pyEnv.workspace.deps.all;
    in
    {
      devShells.default = pkgs.mkShell {
        packages = [ devEnv pkgs.uv searchix pkgs.libsndfile] ++ extraDev;
        env = cfg.shellEnv // {
          UV_NO_SYNC          = "1";
          UV_PYTHON           = "${pyEnv.python.interpreter}";
          UV_PYTHON_DOWNLOADS = "never";
          LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath [
            pkgs.stdenv.cc.cc.lib
            pkgs.libsndfile
          ];
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
        packages = [ pkgs.uv pyEnv.python ];
        shellHook = ''
          dest="$(git rev-parse --show-toplevel)/pyproject.toml"
          if [ ! -f "$dest" ]; then
            python3 ${pf.writerPy} ${pf.jsonData} "$dest"
            chmod 644 "$dest"
            echo "✔ generated pyproject.toml"
          fi
          echo "${cfg.name} bootstrap — run: uv sync  then  exit && nix develop"
          trap 'git add uv.lock pyproject.toml 2>/dev/null || true' EXIT
        '';
      };

      packages.default = prodEnv;

      apps.default = {
        type = "app";
        program = pkgs.lib.getExe (pkgs.writeShellApplication {
          name = cfg.name;
          runtimeInputs = [ prodEnv pkgs.git searchix ];
          text = ''
            export REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo ".")
            python -m agent "$@"
          '';
        });
      };

      apps.sync-pyproject = {
        type = "app";
        program = pkgs.lib.getExe (pkgs.writeShellApplication {
          name = "sync-pyproject";
          runtimeInputs = [ pkgs.python3 ];
          text = ''
            dest="$(git rev-parse --show-toplevel)/pyproject.toml"
            python3 ${pf.writerPy} ${pf.jsonData} "$dest"
            chmod 644 "$dest"
            echo "✔ wrote $dest"
          '';
        });
      };

      checks.tests = pkgs.stdenv.mkDerivation {
        name              = "${cfg.name}-tests";
        src               = ../.;
        nativeBuildInputs = [ testEnv ];
        buildPhase        = "true";
        checkPhase        = ''
          export NIXOS_REPO_PATH="$(mktemp -d)"
          export HOME="$(mktemp -d)"
          pytest --tb=short -q
        '';
        installPhase      = "mkdir -p $out";
        doCheck           = true;
      };
    };
}