"""Tiny PDF writer for tests: pages of text lines plus an optional outline.

make_pdf(path, pages, outline)
  pages:   [["line", "line"], ["line"], ...]       text of each page
  outline: [("Title", page_index, [children])...]  children use the same shape
"""

from pathlib import Path


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(path, pages, outline=()):
    n = len(pages)
    first_page = 5  # 1 catalog, 2 pages, 3 outlines, 4 font, then 2 objects per page
    page_no = lambda i: first_page + 2 * i
    objs: dict[int, str] = {}
    counter = [first_page + 2 * n]

    def build(nodes, parent):
        nos = list(range(counter[0], counter[0] + len(nodes)))
        counter[0] += len(nodes)
        for k, (title, page, kids) in enumerate(nodes):
            kid_nos = build(kids, nos[k]) if kids else []
            d = f"<< /Title ({_esc(title)}) /Parent {parent} 0 R /Dest [{page_no(page)} 0 R /Fit]"
            if k > 0:
                d += f" /Prev {nos[k - 1]} 0 R"
            if k < len(nodes) - 1:
                d += f" /Next {nos[k + 1]} 0 R"
            if kid_nos:
                d += f" /First {kid_nos[0]} 0 R /Last {kid_nos[-1]} 0 R /Count {len(kid_nos)}"
            objs[nos[k]] = d + " >>"
        return nos

    top = build(list(outline), 3) if outline else []
    catalog = "<< /Type /Catalog /Pages 2 0 R"
    if top:
        catalog += " /Outlines 3 0 R /PageMode /UseOutlines"
        objs[3] = f"<< /Type /Outlines /First {top[0]} 0 R /Last {top[-1]} 0 R /Count {len(top)} >>"
    objs[1] = catalog + " >>"
    kids = " ".join(f"{page_no(i)} 0 R" for i in range(n))
    objs[2] = f"<< /Type /Pages /Kids [{kids}] /Count {n} >>"
    objs[4] = "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    for i, lines in enumerate(pages):
        ops = ["BT", "/F1 18 Tf", "50 780 Td"]
        for line in lines:
            ops += ["0 -24 Td", f"({_esc(line)}) Tj"]
        ops.append("ET")
        body = "\n".join(ops)
        objs[page_no(i)] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents {page_no(i) + 1} 0 R "
            f"/Resources << /Font << /F1 4 0 R >> >> >>"
        )
        objs[page_no(i) + 1] = f"<< /Length {len(body)} >>\nstream\n{body}\nendstream"

    out = bytearray(b"%PDF-1.4\n")
    offsets = {}
    last = max(objs)
    for no in range(1, last + 1):
        if no not in objs:  # e.g. object 3 without an outline: an empty placeholder
            objs[no] = "null"
        offsets[no] = len(out)
        out += f"{no} 0 obj\n{objs[no]}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {last + 1}\n0000000000 65535 f \n".encode()
    for no in range(1, last + 1):
        out += f"{offsets[no]:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {last + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    Path(path).write_bytes(bytes(out))
    return Path(path)
