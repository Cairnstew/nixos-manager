{
  description = "nixos-manager — local AI agent for NixOS config management";

  inputs = {
    nixpkgs.url             = "github:NixOS/nixpkgs/nixpkgs-unstable";
    flake-parts.url         = "github:hercules-ci/flake-parts";
    pyproject-nix           = { url = "github:pyproject-nix/pyproject.nix";      inputs.nixpkgs.follows = "nixpkgs"; };
    uv2nix                  = { url = "github:pyproject-nix/uv2nix";              inputs.pyproject-nix.follows = "pyproject-nix"; inputs.nixpkgs.follows = "nixpkgs"; };
    pyproject-build-systems = { url = "github:pyproject-nix/build-system-pkgs";  inputs.pyproject-nix.follows = "pyproject-nix"; inputs.uv2nix.follows = "uv2nix"; inputs.nixpkgs.follows = "nixpkgs"; };
    searchix.url            = "git+https://codeberg.org/alinnow/searchix";
  };

  outputs = inputs:
    inputs.flake-parts.lib.mkFlake { inherit inputs; } {
      systems = [ "x86_64-linux" "aarch64-linux" "aarch64-darwin" "x86_64-darwin" ];
      imports = [ ./modules/flake.nix ];
    };
}