import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTDIR = Path(__file__).resolve().parent / "out"
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(ROOT / "solution"))
from run_eval import load_snapshots  # noqa: E402
from solution import CONFIG  # noqa: E402

CHUNK_SIZE, CLEAN_STEPS = CONFIG["chunk_size"], CONFIG["clean"]
from indexing.clean_pages import clean_pages as clean  # noqa: E402
from indexing.load_pages import load_pages as to_documents  # noqa: E402
from langchain_core.documents import Document  # noqa: E402
from indexing.split_into_chunks import (  # noqa: E402
    QUESTION,
    SUBHEADING,
    TABLE_LINE,
    TABLE_ROW,
    TINY,
    cut_long_unit,
    glue_tiny,
    split_by_headings,
    split_into_units,
)

FEATURED = [
    "https://www.dupaco.com/personal/loans/auto-motorcycle-loans",
    "https://www.dupaco.com/rates",
    "https://www.dupaco.com/personal/credit-cards",
    "https://www.dupaco.com/contact",
    "https://www.dupaco.com/hubfs/Dupaco-2025-Impact-Report.pdf",
]
OUT = OUTDIR / "view_chunks.html"
PAGE_DIR = OUTDIR / "view_chunks_pages"


def esc(text):
    return html.escape(text)


def path_of(section):
    m = section.metadata
    return " › ".join(x for x in (m.get("h1"), m.get("h2")) if x) or "(above the first heading)"


def box(label, body, cls=""):
    return f'<div class="box {cls}"><div class="lab">{esc(label)}</div><div class="txt">{body}</div></div>'


def eyebrow_html(text):
    lines = text.splitlines()
    k = 0
    while k < len(lines) and (not lines[k].strip() or SUBHEADING.match(lines[k])):
        k += 1
    if k and k < len(lines):
        return f'<mark class="eyebrow">{esc(chr(10).join(lines[:k]))}</mark>\n{esc(chr(10).join(lines[k:]))}'
    return esc(text)


def unit_kind(unit):
    rows = [line.strip() for line in unit.splitlines() if line.strip() and not SUBHEADING.match(line.strip())]
    if rows and QUESTION.match(rows[0]):
        return "a question and its answer"
    if any(TABLE_ROW.match(line) for line in unit.splitlines()):
        return "a table with its caption and notes"
    if any(SUBHEADING.match(line) for line in unit.splitlines()):
        return "a ### part"
    return "text"


def header_html(piece, first):
    lines = piece.splitlines()
    table = next((i for i, line in enumerate(lines) if TABLE_ROW.match(line)), None)
    if first or table is None or table != 0:
        return esc(piece)
    n = 2 if len(lines) > 1 and TABLE_LINE.match(lines[1]) else 1
    return f'<mark class="header">{esc(chr(10).join(lines[:n]))}</mark>\n{esc(chr(10).join(lines[n:]))}'


def views(doc, size):
    sections = split_by_headings(doc)
    long = [i for i, s in enumerate(sections) if len(s.page_content) > size]
    moved = sum(1 for s in sections if SUBHEADING.match(s.page_content.splitlines()[0]))
    text = doc.page_content
    left, at = "", 0
    for i, s in enumerate(sections):
        start = text.find(s.page_content[:40], at)
        start = at if start < 0 else start
        left += esc(text[at:start]) + f'<a data-k="s{i}"></a>'
        at = start
    left = f'<div class="raw">{left}{esc(text[at:])}</div>'
    right = "".join(
        f'<a data-k="s{i}"></a>'
        + box(f"section {i + 1} · {len(s.page_content):,} chars · {path_of(s)}" + (f" · over {size}: goes to step 2" if i in long else " · one chunk"), eyebrow_html(s.page_content), "long" if i in long else "")
        for i, s in enumerate(sections)
    )
    one = {"step": "1. split by # and ##", "note": f"{len(sections)} sections · {len(long)} over {size} chars · {moved} start with a small heading moved down from the section above (yellow)", "left": left, "right": right}

    units = []
    for i, s in enumerate(sections):
        if i in long:
            units += [(i, u, unit_kind(u)) for u in split_into_units(s.page_content)]
        else:
            units.append((i, s.page_content, "a short section: one chunk"))
    right2 = ""
    for n, (i, u, kind) in enumerate(units):
        first = n == 0 or units[n - 1][0] != i
        right2 += (f'<a data-k="s{i}"></a>' if first else "") + f'<a data-k="u{n}"></a>' + box(f"unit {n + 1} · {len(u):,} chars · {kind}" + (f" · over {size}: goes to step 3" if len(u) > size else ""), esc(u), "long" if len(u) > size else ("cut" if i in long else ""))
    kinds = {}
    for i, u, kind in units:
        if i in long:
            kinds[kind] = kinds.get(kind, 0) + 1
    two = {"step": "2. long sections → units", "note": f"{len(long)} long sections → " + (", ".join(f"{v} × {k}" for k, v in kinds.items()) or "nothing to do"), "left": right, "right": right2}

    right3, count, cuts, flat = "", 0, 0, []
    for n, (i, u, kind) in enumerate(units):
        pieces = cut_long_unit(u, size) if len(u) > size else [u]
        cuts += len(pieces) > 1
        for p, piece in enumerate(pieces):
            count += 1
            anchor = (f'<a data-k="u{n}"></a>' if p == 0 else "") + f'<a data-k="c{count}"></a>'
            label = f"chunk {count} · {len(piece):,} chars" + (f" · piece {p + 1} of {len(pieces)}" if len(pieces) > 1 else "")
            right3 += anchor + box(label, header_html(piece, p == 0), "cut" if len(pieces) > 1 else "")
            flat.append(piece)
    left3 = right2
    three = {"step": "3. cut units over the size", "note": f"{cuts} units over {size} cut: tables between rows with the header again (blue), text between paragraphs · {count} chunks", "left": left3, "right": right3}

    final = glue_tiny([Document(page_content=p, metadata={"url": doc.metadata["url"]}) for p in flat])
    right4, k, glued = "", 0, 0
    for c, chunk in enumerate(final):
        parts = [k]
        while "\n\n".join(flat[j] for j in parts) != chunk.page_content:
            parts.append(parts[-1] + 1)
        k = parts[-1] + 1
        body = "\n\n".join(f'<mark class="tiny">{esc(flat[j])}</mark>' if len(flat[j]) < TINY and len(parts) > 1 else esc(flat[j]) for j in parts)
        anchors = "".join(f'<a data-k="c{j + 1}"></a>' for j in parts[:1])
        glued += len(parts) > 1
        label = f"chunk {c + 1} · {len(chunk.page_content):,} chars" + (f" · a tiny chunk glued on" if len(parts) > 1 else "")
        right4 += anchors + box(label, body, "glued" if len(parts) > 1 else "")
    four = {"step": "4. glue tiny chunks", "note": f"chunks under {TINY} chars join the next chunk of the page (the last one joins the one before) · {glued} glued · {len(final)} chunks", "left": right3, "right": right4}
    return [one, two, three, four]


PAGE = """<!doctype html><meta charset="utf-8"><title>Chunk viewer</title>
<style>
body { margin: 0; height: 100vh; display: flex; flex-direction: column; font: 14px/1.5 Lexend, Verdana, sans-serif; color: #2b3137; background: #fbfaf6; }
header { padding: 10px 16px; border-bottom: 1px solid #c9cfd4; }
button { font: inherit; margin: 2px; padding: 4px 10px; border: 1px solid #c9cfd4; border-radius: 6px; background: #fff; cursor: pointer; }
button.on { background: #2b3137; color: #fff; }
#name { font-weight: 700; margin-left: 8px; }
#note { color: #6b7680; margin-left: 8px; }
main { flex: 1; display: grid; grid-template-columns: 1fr 1fr; min-height: 0; }
section { display: flex; flex-direction: column; min-height: 0; }
section + section { border-left: 1px solid #c9cfd4; }
h2 { margin: 0; padding: 6px 16px; font-size: 12px; color: #6b7680; text-transform: uppercase; letter-spacing: .06em; }
.pane { position: relative; flex: 1; overflow-y: auto; padding: 0 16px 50vh; font: 13px/1.6 Consolas, monospace; }
.raw, .txt { white-space: pre-wrap; overflow-wrap: anywhere; }
.box { border: 1px solid #c9cfd4; border-radius: 6px; margin: 8px 0; background: #fff; }
.box.long { border-color: #b5651d; background: #fdf3e6; }
.box.cut { border-left: 4px solid #1f7a8c; }
.box.glued { border-left: 4px solid #3d8b5a; }
.lab { font: 11px Lexend, Verdana, sans-serif; color: #6b7680; padding: 3px 8px; border-bottom: 1px solid #e3e6e8; }
.txt { padding: 4px 8px; }
mark.header { background: #d6e9ee; color: #1f5f6d; }
mark.eyebrow { background: #f7ecb5; color: #7a6212; }
mark.tiny { background: #e6dcf3; color: #5b3f86; }
hr.seam { border: 0; border-top: 1px dashed #3d8b5a; margin: 4px 0; }
</style>
<header><div id="pages"></div><div id="steps"></div></header>
<main><section><h2>before this step</h2><div class="pane" id="left"></div></section>
<section><h2>after · orange = over the size · yellow = a small heading moved down · blue = the table header again · violet = a tiny chunk glued on</h2><div class="pane" id="right"></div></section></main>
<script>
const INDEX = __INDEX__, FEATURED = __FEATURED__, LOADED = {};
const left = document.getElementById("left"), right = document.getElementById("right");
let page = FEATURED[0], step = 0, busy = false;
function pageLoaded(i, views) { LOADED[i] = views; if (i == page) show(); }
function openPage(i) {
  page = i;
  if (LOADED[i]) return show();
  const s = document.createElement("script");
  s.src = `view_chunks_pages/${i}.js`;
  document.body.appendChild(s);
}
function show() {
  const buttons = FEATURED.map(i => `<button class="${i == page ? "on" : ""}" onclick="openPage(${i})">${INDEX[i]}</button>`);
  buttons.push(`<button onclick="openPage(Math.floor(Math.random() * INDEX.length))">random</button>`);
  document.getElementById("pages").innerHTML = buttons.join("") + `<span id="name">${INDEX[page]}</span>`;
  const v = LOADED[page];
  document.getElementById("steps").innerHTML = v.map((s, i) => `<button class="${i == step ? "on" : ""}" onclick="step=${i};show()">${s.step}</button>`).join("") + `<span id="note">${v[step].note}</span>`;
  left.innerHTML = v[step].left;
  right.innerHTML = v[step].right;
  left.scrollTop = right.scrollTop = 0;
}
function follow(from, to) {
  if (busy) { busy = false; return; }
  const marks = [...from.querySelectorAll("a[data-k]")];
  let top = null;
  for (const m of marks) { if (m.offsetTop <= from.scrollTop + 4) top = m; else break; }
  if (!top) { busy = true; to.scrollTop = from.scrollTop; return; }
  const twin = to.querySelector(`a[data-k="${top.dataset.k}"]`);
  if (!twin) return;
  busy = true;
  to.scrollTop = twin.offsetTop + (from.scrollTop - top.offsetTop);
}
left.onscroll = () => follow(left, right);
right.onscroll = () => follow(right, left);
openPage(page);
</script>"""


def name(url):
    return url.split("dupaco.com")[1] or "/"


def main():
    docs = clean(to_documents(load_snapshots(ROOT / "snapshots")[-1]), CLEAN_STEPS)
    PAGE_DIR.mkdir(parents=True, exist_ok=True)
    for old in PAGE_DIR.glob("*.js"):
        old.unlink()
    urls = [doc.metadata["url"] for doc in docs]
    for i, doc in enumerate(docs):
        (PAGE_DIR / f"{i}.js").write_text(
            f"pageLoaded({i}, {json.dumps(views(doc, CHUNK_SIZE))});", encoding="utf-8"
        )
    page = PAGE.replace("__INDEX__", json.dumps([name(url) for url in urls]))
    page = page.replace("__FEATURED__", json.dumps([urls.index(url) for url in FEATURED if url in urls]))
    OUT.write_text(page, encoding="utf-8")
    print("saved", OUT, "and", len(urls), "pages in", PAGE_DIR, "· size", CHUNK_SIZE)


if __name__ == "__main__":
    main()
