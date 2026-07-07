"""Container healthcheck: probe /health over HTTPS (self-signed OK) then HTTP.

Exits 0 if the app responds, 1 otherwise. Works whether SSL_ENABLED is true
(default, self-signed) or false (plain HTTP).
"""

import os
import ssl
import sys
import urllib.request

port = os.getenv("UVICORN_PORT", "8000")
unverified = ssl._create_unverified_context()

for scheme in ("https", "http"):
    try:
        urllib.request.urlopen(
            f"{scheme}://127.0.0.1:{port}/health",
            context=unverified if scheme == "https" else None,
            timeout=4,
        )
        sys.exit(0)
    except Exception:
        continue

sys.exit(1)
