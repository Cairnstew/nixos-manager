{ pkgs, inputs }:
let
  python    = pkgs.python312;
  workspace = inputs.uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ../.; };

  overlay         = workspace.mkPyprojectOverlay { sourcePreference = "wheel"; };
  editableOverlay = workspace.mkEditablePyprojectOverlay { root = "$REPO_ROOT"; };

  editablesOverlay = final: prev: {
    nixos-manager = prev.nixos-manager.overrideAttrs (old: {
      nativeBuildInputs = (old.nativeBuildInputs or [ ]) ++ [ final.editables ];
    });
  };

  buildSystemOverrides = {
    packaging.flit-core           = [ ];
    tomli.flit-core               = [ ];
    pip                           = { setuptools = [ ]; wheel = [ ]; };
    pluggy.setuptools             = [ ];
    trove-classifiers.setuptools  = [ ];
    coverage.setuptools           = [ ];
    blinker.setuptools            = [ ];
    certifi.setuptools            = [ ];
    charset-normalizer.setuptools = [ ];
    requests.setuptools           = [ ];
    pysocks.setuptools            = [ ];
    pytest-cov.setuptools         = [ ];
    tqdm.setuptools               = [ ];
    six.setuptools                = [ ];
    platformdirs.hatchling        = [ ];
    colorama.setuptools           = [ ];
    wrapt.setuptools              = [ ];
    deprecated.setuptools         = [ ];
    filelock.hatchling            = [ ];
    zipp.setuptools               = [ ];
    jieba.setuptools              = [ ];
    cffi.setuptools               = [ ];
    soundfile.cffi                = [ ];
    tiktoken                      = { setuptools = [ ]; };
    easyocr                       = { setuptools = [ ]; };
    decord                        = { setuptools = [ ]; };
    urllib3                       = { hatchling = [ ]; hatch-vcs = [ ]; };
    idna.flit-core                = [ ];
    httpcore                      = { hatchling = [ ]; };
    httpx                         = { hatchling = [ ]; };
    attrs                         = { hatchling = [ ]; hatch-vcs = [ ]; hatch-fancy-pypi-readme = [ ]; };
    hatchling                     = { pathspec = [ ]; pluggy = [ ]; packaging = [ ]; trove-classifiers = [ ]; };
    pathspec.flit-core            = [ ];
    pytest-timeout.setuptools     = [ ];
    pytest-mock.setuptools        = [ ];
  };

  mkBuildSystemOverlay = final: prev:
    builtins.mapAttrs (name: spec:
      if builtins.hasAttr name prev
      then prev.${name}.overrideAttrs (old: {
        nativeBuildInputs = (old.nativeBuildInputs or [ ]) ++ final.resolveBuildSystem spec;
      })
      else builtins.throw "buildSystemOverrides: package '${name}' not found"
    ) (builtins.intersectAttrs prev buildSystemOverrides);

  basePythonSets =
    (pkgs.callPackage inputs.pyproject-nix.build.packages { inherit python; }).overrideScope (
      pkgs.lib.composeManyExtensions [
        inputs.pyproject-build-systems.overlays.default
        overlay
        mkBuildSystemOverlay
        editablesOverlay
      ]
    );

in
{
  inherit python workspace basePythonSets editableOverlay;
  devEnv  = basePythonSets.overrideScope editableOverlay;
}