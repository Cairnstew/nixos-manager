"""Allow ``python -m searchix`` to invoke the CLI."""
import sys
from .cli import main

sys.exit(main())