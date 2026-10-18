import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "probe" / "python"))

from pdf_export import build_pdf


def test_build_pdf_has_matching_xref_offsets():
    pdf = build_pdf("Title", "A short body paragraph.", [("Zone", "B"), ("Heat", "0.10")])
    assert pdf.startswith(b"%PDF-1.4")
    assert pdf.endswith(b"%%EOF")

    xref_start = int(pdf.rsplit(b"startxref\n", 1)[1].split(b"\n", 1)[0])
    xref_block = pdf[xref_start:].split(b"trailer")[0]
    offsets = [int(line.split()[0]) for line in xref_block.splitlines()[3:]]
    for i, offset in enumerate(offsets, start=1):
        assert pdf[offset:offset + len(f"{i} 0 obj".encode())] == f"{i} 0 obj".encode()


def test_build_pdf_stream_length_matches_declared_length():
    pdf = build_pdf("Title", "Body text here.", [("Key", "Value")])
    length = int(pdf.split(b"/Length ", 1)[1].split(b">>", 1)[0])
    stream = pdf.split(b"stream\n", 1)[1].split(b"\nendstream", 1)[0]
    assert len(stream) == length


if __name__ == "__main__":
    test_build_pdf_has_matching_xref_offsets()
    test_build_pdf_stream_length_matches_declared_length()
    print("ok")
