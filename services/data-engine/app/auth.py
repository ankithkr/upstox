"""Reads the Upstox access token cached by the existing OAuth login flow.

The token file is produced by the legacy `upstox_auth.py` login flow
(preserved on the `legacy/pre-rebuild` branch) and expires daily - this
module only reads it, it does not refresh it. See the root README's
"operational risk" note on daily re-auth.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def load_access_token() -> str:
    path = Path(os.environ.get("UPSTOX_TOKEN_FILE", "token.json"))
    if not path.exists():
        raise RuntimeError(
            f"Upstox token file not found at {path}. Run the login flow "
            "(upstox_auth.py on legacy/pre-rebuild) to create it."
        )
    data = json.loads(path.read_text())
    token = data.get("access_token")
    if not token:
        raise RuntimeError(f"{path} has no 'access_token' field")
    return token
