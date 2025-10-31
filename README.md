# OCR Web UI and CLI

This project provides:

- CLI: `ocr_extract.py` to OCR PDFs using EasyOCR and PyMuPDF and export structured JSON.
- Web UI: Flask app (`webapp.py`) to upload a PDF and view the original side‑by‑side with extracted text.

No virtualenv is required in these instructions; use your current Python environment.

## GPU Requirement

EasyOCR runs on CPU or GPU. While CPU works for demos, a GPU is required for acceptable performance in production. Enable GPU by installing CUDA‑capable PyTorch in your environment and setting `EASYOCR_USE_GPU=1`. Without a GPU, the first request may take 1–2 minutes as models load and inference runs on CPU.

## Setup

Install dependencies:

```bash
pip install -r requirements.txt
```

First run will download EasyOCR model weights (and may fetch PyTorch assets) — this can take a few minutes and requires network access.

## Run the Web UI

### Option A: CML Application (recommended)
- Application script: `python run_flask.py`
- The app binds to `127.0.0.1` and uses the CML‑provided `CDSW_APP_PORT` automatically.
- Health check: `GET /healthz`

Preloading and processing UX:
- The app preloads a single EasyOCR `Reader` at startup to reduce first‑request latency. Configure via env:
  - `EASYOCR_LANGS`: comma‑separated language codes for the preloaded reader (default `en`).
  - `EASYOCR_USE_GPU`: set to `1/true/on` to enable GPU for the preloaded reader.
- When you upload a PDF, OCR runs in a background thread. While it runs, `/view/<uid>` shows a “processing…” page with an auto‑refresh. Once done, it automatically displays results.

### Option B: Local development

Helper script:
```bash
python run_flask.py
```

Or direct Flask:
```bash
python -m flask --app webapp:app run --host 127.0.0.1 --port 8080
```

Open http://127.0.0.1:8080 (adjust port if different).

In the UI:
- Choose a PDF, optionally set languages (comma‑separated, e.g., `en,es`), DPI, and minimum confidence.
- After upload, you’ll see the PDF on the left and recognized text on the right, plus a quick‑copy text box and a link to the raw JSON.

Routes provided by the app:
- `GET /` — upload form
- `POST /upload` — upload and OCR a PDF
- `GET /view/<uid>` — view PDF + extracted text
- `GET /pdf/<uid>` — download the original PDF
- `GET /ocr/<uid>.json` — download OCR JSON
- `GET /healthz` — basic health check

Background processing and storage:
- Each upload creates `uploads/<uid>/document.pdf` and later `uploads/<uid>/ocr.json`.
- If an error occurs during OCR, it is written to `uploads/<uid>/error.txt` and displayed on the processing page.

## Use the CLI

```bash
python ocr_extract.py path/to/input.pdf \
  --languages en \
  --json-out output/ocr.json
```

Notes:
- `--languages` uses comma‑separated EasyOCR codes (e.g., `en,es`).
- `--dpi` controls rasterization resolution (default: 300).
- `--min-confidence` (0–1, default: 0.2) filters low‑confidence detections.
- Add `--gpu` to enable GPU inference if CUDA is available.

## Storage and cleanup
- Each upload is stored under `uploads/<uid>/document.pdf`; OCR output is saved at `uploads/<uid>/ocr.json`.
- To remove previous runs locally, delete old subfolders under `uploads/`.

## Environment notes
- The web app reads `CDSW_APP_PORT` (or `PORT`) to choose the listening port; `run_flask.py` handles this automatically.
- Optional env:
  - `EASYOCR_LANGS` and `EASYOCR_USE_GPU` as described above.
- This project does not use OpenAI/LLM APIs.

## Project layout

- App entrypoint: `webapp.py`
- CLI helper: `ocr_extract.py`
- Templates: `templates/index.html`, `templates/view.html`
- Processing template: `templates/processing.html`
- Static styles: `static/styles.css`
- Upload workspace for each job: `uploads/<uid>/document.pdf` and `uploads/<uid>/ocr.json`
