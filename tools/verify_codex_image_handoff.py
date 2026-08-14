#!/usr/bin/env python3
"""Thin project entry for the packaged Codex image handoff verifier."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CLI_SRC = ROOT / "cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from redbeacon.services.codex_image_handoff import main  # noqa: E402


if __name__ == "__main__":
    main()
