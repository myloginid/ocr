"""Flask web UI to upload PDFs and view OCR results.

Routes:
- GET /                — upload form
- POST /upload         — upload a PDF and run OCR
- GET /view/<uid>      — view PDF and recognized text
- GET /pdf/<uid>       — download the original PDF
- GET /ocr/<uid>.json  — download OCR output JSON
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import List

from flask import (
    Flask,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from werkzeug.utils import secure_filename

# Import OCR functionality lazily inside the upload route to keep startup fast


BASE_DIR = Path(__file__).resolve().parent
UPLOADS_DIR = BASE_DIR / "uploads"

app = Flask(__name__, static_folder="static", template_folder="templates")

# Will be set by run_flask.py at startup when available
PRELOADED_READER = None  # type: ignore


def _default_form_values() -> dict:
    return {
        "default_langs": "en",
        "default_dpi": 300,
        "default_min_conf": 0.2,
    }


def _parse_languages(raw: str | None) -> List[str]:
    value = (raw or "en").strip()
    langs = [p.strip() for p in value.split(",") if p.strip()]
    return langs or ["en"]


@app.get("/")
def index():
    return render_template("index.html", **_default_form_values())


@app.post("/upload")
def upload():
    file = request.files.get("pdf")
    if not file:
        abort(400, "Missing PDF upload under field 'pdf'.")

    # Parse options
    languages = _parse_languages(request.form.get("languages"))
    try:
        dpi = int(request.form.get("dpi", 300))
    except Exception:
        dpi = 300
    try:
        min_conf = float(request.form.get("min_conf", 0.2))
    except Exception:
        min_conf = 0.2

    # Workspace for this job
    uid = uuid.uuid4().hex[:12]
    job_dir = UPLOADS_DIR / uid
    job_dir.mkdir(parents=True, exist_ok=True)

    # Persist PDF
    filename = secure_filename(file.filename or "document.pdf") or "document.pdf"
    pdf_path = job_dir / "document.pdf"
    file.save(pdf_path)

    # Run OCR in a background thread and immediately redirect to the view page.
    # The view page will show a processing indicator until OCR is complete.
    def _worker(pdf: Path, out_dir: Path, langs: List[str], dpi_: int, min_c: float):
        try:
            from ocr_extract import extract_pdf_text

            # Reuse preloaded reader only for the same language set; else fall back
            # to a new reader (keeps correctness if user changes languages).
            use_preloaded = False
            reader = None
            try:
                pre = globals().get("PRELOADED_READER")
                if pre is not None:
                    # Best-effort: use preloaded reader if the request only asks for 'en'
                    if set(langs) == {"en"}:
                        reader = pre
                        use_preloaded = True
            except Exception:
                reader = None

            pages = extract_pdf_text(
                pdf_path=pdf,
                languages=langs,
                dpi=dpi_,
                min_confidence=min_c,
                use_gpu=False,
                reader=reader,
            )

            (out_dir / "ocr.json").write_text(
                json.dumps(pages, indent=2), encoding="utf-8"
            )
        except Exception as e:  # Write error to a file for UI to pick up
            (out_dir / "error.txt").write_text(str(e), encoding="utf-8")

    import threading

    t = threading.Thread(
        target=_worker, args=(pdf_path, job_dir, languages, dpi, min_conf), daemon=True
    )
    t.start()

    return redirect(url_for("view", uid=uid))


@app.get("/view/<uid>")
def view(uid: str):
    job_dir = UPLOADS_DIR / secure_filename(uid)
    pdf_path = job_dir / "document.pdf"
    json_path = job_dir / "ocr.json"
    if not pdf_path.exists():
        abort(404)

    if not json_path.exists():
        # If processing is ongoing, render a processing page with auto-refresh.
        err_path = job_dir / "error.txt"
        error_msg = err_path.read_text(encoding="utf-8") if err_path.exists() else None
        return render_template("processing.html", uid=uid, error=error_msg), 202

    pages = json.loads(json_path.read_text(encoding="utf-8"))
    flat_text = "\n".join(
        item.get("text", "")
        for page in pages
        for item in page.get("items", [])
        if item.get("text")
    )

    return render_template(
        "view.html",
        uid=uid,
        pages=pages,
        flat_text=flat_text,
    )


@app.get("/pdf/<uid>")
def get_pdf(uid: str):
    job_dir = UPLOADS_DIR / secure_filename(uid)
    pdf_path = job_dir / "document.pdf"
    if not pdf_path.exists():
        abort(404)
    return send_file(pdf_path, mimetype="application/pdf", as_attachment=False)


@app.get("/ocr/<uid>.json")
def get_ocr_json(uid: str):
    job_dir = UPLOADS_DIR / secure_filename(uid)
    json_path = job_dir / "ocr.json"
    if not json_path.exists():
        abort(404)
    return send_file(json_path, mimetype="application/json", as_attachment=False)


# Basic health endpoint for quick checks
@app.get("/healthz")
def healthz():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    # Local dev convenience: run on 127.0.0.1 with a default port
    host = "127.0.0.1"
    port = int(os.environ.get("PORT", "8080"))
    app.run(host=host, port=port, debug=False)
