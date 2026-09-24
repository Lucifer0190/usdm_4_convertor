"""Layout adapters: PyMuPDF always returns the synthetic SoA table's dims;
Docling/MinerU degrade to `[]` (not a crash) when their optional deps are absent.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "spikes"))
from make_soa_fixture import build, ground_truth

from usdm4_assure.layout import docling_adapter, mineru_adapter, pymupdf_adapter


def test_pymupdf_adapter_returns_synthetic_table_dims():
    pdf = build()
    gt = ground_truth()
    grids = pymupdf_adapter.extract_tables(pdf)
    assert grids
    g = grids[0]
    assert g.method == "pymupdf"
    assert g.page == 1
    # header rows (epoch, visit, timing) + one row per activity
    assert g.n_rows == 3 + len(gt["activities"])
    assert g.n_cols == 1 + len(gt["visits"])


def test_pymupdf_adapter_always_available():
    assert pymupdf_adapter.available()


def test_docling_adapter_degrades_to_empty_when_not_installed():
    if docling_adapter.available():
        return  # installed in this environment — nothing to assert about absence
    assert docling_adapter.extract_tables("irrelevant.pdf") == []


def test_mineru_adapter_degrades_to_empty_when_not_installed():
    if mineru_adapter.available():
        return
    assert mineru_adapter.extract_tables("irrelevant.pdf") == []


def test_text_grid_matches_cells_shape():
    pdf = build()
    g = pymupdf_adapter.extract_tables(pdf)[0]
    tg = g.text_grid()
    assert len(tg) == g.n_rows
    assert all(len(row) == g.n_cols for row in tg)
