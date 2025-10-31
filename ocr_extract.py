"""CLI helper to run OCR on PDF forms using EasyOCR and PyMuPDF."""

from __future__ import annotations

import argparse
import json
import sys
from io import BytesIO
from pathlib import Path
from typing import List, Sequence, Optional

import easyocr
import fitz  # PyMuPDF
import numpy as np
from PIL import Image


def _load_page_as_array(page: fitz.Page, dpi: int) -> np.ndarray:
    """Render a PDF page at the desired DPI and return an RGB numpy array."""
    zoom = dpi / 72.0  # 72 DPI is the default PDF resolution
    pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)

    # Converting through PNG ensures we always end up with an RGB image.
    with BytesIO(pixmap.tobytes("png")) as buffer:
        image = Image.open(buffer).convert("RGB")
        return np.array(image)


def _extract_page_text(
    reader: easyocr.Reader,
    image_array: np.ndarray,
    min_confidence: float,
) -> List[dict]:
    """Run OCR on a numpy image and collect results above the confidence threshold.

    Ensures outputs are JSON‑serializable by casting numeric types to built‑in
    Python types (e.g., float, int) and normalizing bounding boxes to
    `[[x, y], ...]` with float coordinates.
    """
    results: List[dict] = []
    for bbox, text, confidence in reader.readtext(image_array):
        try:
            conf_f = float(confidence)
        except Exception:
            conf_f = float(confidence.item()) if hasattr(confidence, "item") else 0.0
        if conf_f < min_confidence or not str(text).strip():
            continue

        # bbox from EasyOCR is a list of 4 points; ensure pure Python floats
        py_bbox = []
        try:
            for pt in bbox:
                x, y = pt
                py_bbox.append([float(x), float(y)])
        except Exception:
            # Fallback: coerce anything iterable to float list
            py_bbox = [[float(p) for p in (pt if hasattr(pt, "__iter__") else [pt])] for pt in bbox]

        results.append(
            {
                "text": str(text).strip(),
                "confidence": conf_f,
                "bbox": py_bbox,
            }
        )
    return results


def extract_pdf_text(
    pdf_path: Path,
    languages: Sequence[str],
    dpi: int,
    min_confidence: float,
    use_gpu: bool,
    reader: Optional[easyocr.Reader] = None,
) -> List[dict]:
    """Iterate through pages in a PDF and run OCR, returning structured data.

    If ``reader`` is provided, reuse it; otherwise create a new Reader using
    ``languages`` and ``use_gpu``.
    """
    reader = reader or easyocr.Reader(list(languages), gpu=use_gpu)
    pages_output = []

    with fitz.open(pdf_path) as document:
        for page_index, page in enumerate(document, start=1):
            image_array = _load_page_as_array(page, dpi)
            entries = _extract_page_text(reader, image_array, min_confidence)
            pages_output.append(
                {
                    "page": page_index,
                    "items": entries,
                }
            )
    return pages_output


def _parse_languages(value: str) -> List[str]:
    languages = [lang.strip() for lang in value.split(",") if lang.strip()]
    if not languages:
        raise argparse.ArgumentTypeError("At least one language code must be provided.")
    return languages


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run OCR on a PDF file using EasyOCR and export the results.",
    )
    parser.add_argument("pdf", type=Path, help="Path to the input PDF file.")
    parser.add_argument(
        "--languages",
        type=_parse_languages,
        default=["en"],
        help="Comma-separated EasyOCR language codes (default: en).",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="DPI used when rasterizing the PDF pages (default: 300).",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.2,
        help="Minimum OCR confidence (0-1) required to keep a detection (default: 0.2).",
    )
    parser.add_argument(
        "--gpu",
        action="store_true",
        help="Enable GPU inference if CUDA is available.",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        help="Optional path to save OCR output as JSON. Prints to stdout if omitted.",
    )
    return parser


def main(args: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    options = parser.parse_args(args)

    if not options.pdf.exists():
        parser.error(f"PDF not found: {options.pdf}")

    pages_output = extract_pdf_text(
        pdf_path=options.pdf,
        languages=options.languages,
        dpi=options.dpi,
        min_confidence=options.min_confidence,
        use_gpu=options.gpu,
    )

    if options.json_out:
        options.json_out.parent.mkdir(parents=True, exist_ok=True)
        options.json_out.write_text(json.dumps(pages_output, indent=2), encoding="utf-8")
    else:
        print(json.dumps(pages_output, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
