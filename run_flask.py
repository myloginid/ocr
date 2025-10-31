#!/usr/bin/env python
"""Minimal launcher for the OCR Flask app.

- Binds to 127.0.0.1 for CML proxying
- Uses `CDSW_APP_PORT` (or `PORT`, else 8080)
- Exits if `CDSW_APP_PORT` is already in use
- Honors `FLASK_DEBUG` and caps uploads at 5 MB
"""

from __future__ import annotations

import os
import socket
import sys


def main() -> int:
    host = "127.0.0.1"
    env_port = os.getenv("CDSW_APP_PORT")
    port = int(env_port or os.getenv("PORT", "8080"))

    # If CML provided CDSW_APP_PORT, ensure the port is free before starting.
    if env_port:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.25)
            if s.connect_ex((host, port)) == 0:
                print(
                    f"Error: CDSW_APP_PORT {port} is already in use on {host}.",
                    file=sys.stderr,
                )
                return 98

    # Import the Flask app directly and tweak minimal runtime config
    from webapp import app  # lazy import keeps startup lean
    app.config.setdefault("MAX_CONTENT_LENGTH", 5 * 1024 * 1024)

    # Preload a global EasyOCR Reader and attach it to the webapp module so
    # request handlers can reuse it (avoids first-request latency).
    # Languages and GPU usage can be controlled via env vars.
    preload_langs = [p.strip() for p in os.getenv("EASYOCR_LANGS", "en").split(",") if p.strip()]
    use_gpu = os.getenv("EASYOCR_USE_GPU", "").strip().lower() in {"1", "true", "yes", "on"}
    try:
        import easyocr  # type: ignore
        import webapp as webapp_module

        print(
            f"Preloading EasyOCR Reader (langs={preload_langs}, gpu={use_gpu}) ...",
            flush=True,
        )
        webapp_module.PRELOADED_READER = easyocr.Reader(preload_langs, gpu=use_gpu)
        print("EasyOCR Reader preloaded.", flush=True)
    except Exception as e:  # pragma: no cover - best-effort preload
        print(f"Warning: failed to preload EasyOCR Reader: {e}", file=sys.stderr)

    debug = os.getenv("FLASK_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}
    print(f"Starting Flask on http://{host}:{port} ...", flush=True)
    app.run(host=host, port=port, debug=debug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
