# src/nixos_manager/__init__.py

"""
nixos_manager

Local AI agent for managing NixOS flake configurations.
"""

from importlib.metadata import version, PackageNotFoundError

# ---- Version ----
try:
    __version__ = version("nixos-manager")
except PackageNotFoundError:  # during development
    __version__ = "0.0.0"

# ---- Public API ----
# Keep this minimal to avoid slow imports

__all__ = [
    "__version__",
]