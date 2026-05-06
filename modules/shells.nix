{ lib, config, pkgs, inputs, ... }:
let
  cfg     = config.project;
  pyEnv   = config.pythonEnv;
  pf      = config.pyproject;
  banner  = builtins.concatStringsSep "\n    " cfg.shellHints;

  pythonSet  = pyEnv.basePythonSets.overrideScope pyEnv.editableOverlay;
  virtualenv = pythonSet.mkVirtualEnv "${cfg.name}-dev" pyEnv.workspace.deps.all;
  searchixPkg = inputs.searchix.packages.${pkgs.system}.default;

in
{
  imports = [ ./project.nix ./python-env.nix ./pyproject.nix ];

  perSystem = { pkgs, ... }: {
    devShells.default = pkgs.mkShell {
      packages = [ virtualenv pkgs.uv searchixPkg ] ++ cfg.extraDevPackages pkgs;
      env = cfg.shellEnv // {
        UV_NO_SYNC          = "1";
        UV_PYTHON           = "${pyEnv.python.interpreter}";
        UV_PYTHON_DOWNLOADS = "never";
        LD_LIBRARY_PATH     = "${pkgs.stdenv.cc.cc.lib}/lib:$LD_LIBRARY_PATH";
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
  };
}