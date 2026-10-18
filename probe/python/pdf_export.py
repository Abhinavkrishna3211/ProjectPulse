"""Minimal single-page text PDF writer, stdlib only - no new dependency to
install on the board before the deadline. Good enough for a short report or
guard note: a title, a wrapped paragraph, and a measurement table.
"""

import textwrap

PAGE_WIDTH = 612
PAGE_HEIGHT = 792
MARGIN = 50
WRAP_CHARS = 90


def _escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _content_stream(title: str, body: str, rows: list[tuple[str, str]]) -> str:
    y = PAGE_HEIGHT - MARGIN
    lines = [
        "BT",
        f"/F2 16 Tf",
        f"{MARGIN} {y} Td",
        f"({_escape(title)}) Tj",
        "ET",
    ]
    y -= 30
    lines += ["BT", "/F1 11 Tf", f"{MARGIN} {y} Td", "14 TL"]
    for para_line in textwrap.wrap(body, WRAP_CHARS) or [""]:
        lines.append(f"({_escape(para_line)}) Tj")
        lines.append("T*")
    lines.append("ET")
    y -= 14 * (len(textwrap.wrap(body, WRAP_CHARS) or [""]) + 2)
    lines += ["BT", "/F1 10 Tf", f"{MARGIN} {y} Td", "14 TL"]
    for key, value in rows:
        lines.append(f"({_escape(key)}: {_escape(value)}) Tj")
        lines.append("T*")
    lines.append("ET")
    return "\n".join(lines)


def build_pdf(title: str, body: str, rows: list[tuple[str, str]]) -> bytes:
    """A4-ish single-page PDF with a title, a wrapped paragraph and a
    key/value table. Returns raw PDF bytes, no temp files."""
    content = _content_stream(title, body, rows).encode("latin-1", "replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            f"<< /Type /Page /Parent 2 0 R /Resources "
            f"<< /Font << /F1 4 0 R /F2 5 0 R >> >> "
            f"/MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] /Contents 6 0 R >>"
        ).encode("latin-1"),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode("latin-1")
        out += obj
        out += b"\nendobj\n"

    xref_start = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode("latin-1")
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += f"{off:010d} 00000 n \n".encode("latin-1")
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_start}\n%%EOF"
    ).encode("latin-1")
    return bytes(out)
