{ lib, config, pkgs, inputs, ... }:
let
  cfg    = config.project;
  pyEnv  = config.pythonEnv;
  pf     = config.pyproject;

  prodEnv  = pyEnv.basePythonSets.mkVirtualEnv "${cfg.name}-env"  pyEnv.workspace.deps.default;
  testEnv  = pyEnv.basePythonSets.mkVirtualEnv "${cfg.name}-test" pyEnv.workspace.deps.all;
  searchixPkg = inputs.searchix.packages.${pkgs.system}.default;

in
{
  imports = [ ./project.nix ./python-env.nix ./pyproject.nix ];

  perSystem = { pkgs, ... }: {
    packages.default = prodEnv;

    apps.default = {
      type = "app";
      program = pkgs.lib.getExe (pkgs.writeShellApplication {
        name = cfg.name;
        runtimeInputs = [ prodEnv pkgs.git searchixPkg ];
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
      name             = "${cfg.name}-tests";
      src              = ./.;
      nativeBuildInputs = [ testEnv ];
      buildPhase       = "true";
      checkPhase       = ''
        export NIXOS_REPO_PATH="$(mktemp -d)"
        export HOME="$(mktemp -d)"
        pytest --tb=short -q
      '';
      installPhase     = "mkdir -p $out";
      doCheck          = true;
    };
  };
}