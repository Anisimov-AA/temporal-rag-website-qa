import difflib
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTDIR = Path(__file__).resolve().parent / "out"
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(ROOT / "solution"))
from run_eval import load_snapshots  # noqa: E402
from indexing.clean_pages import CLEANERS  # noqa: E402
from indexing.clean_pages.blocks import FIELD, find_blocks, find_calculators, find_forms, find_locators  # noqa: E402
from indexing.load_pages import load_pages as to_documents  # noqa: E402

STEPS = [
    "images",
    "links",
    "markdown_noise",
    "html_noise",
    "blocks",
    "repeated_lines",
    "tidy",
    "head",
    "app_pages",
    "empty_pages",
    "copies",
]
FEATURED = [
    "https://www.dupaco.com",
    "https://www.dupaco.com/rates",
    "https://www.dupaco.com/personal/loans/auto-motorcycle-loans",
    "https://www.dupaco.com/about/member-services",
    "https://www.dupaco.com/learn/blog/savings-interest-calculator",
    "https://www.dupaco.com/contact",
    "https://www.dupaco.com/calculators/personal-loan",
]
OUT = OUTDIR / "view_clean.html"
PAGE_DIR = OUTDIR / "view_clean_pages"
TOKEN = re.compile(r"\s+|[^\s]+")


def pieces(text, level):
    if level == 0:
        return text.splitlines(keepends=True)
    if level == 1:
        return TOKEN.findall(text)
    return list(text)


def mark(a, b, level):
    left, right = [], []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(
        None, a, b, autojunk=False
    ).get_opcodes():
        old, new = "".join(a[i1:i2]), "".join(b[j1:j2])
        if op == "equal":
            anchor = f'<a data-k="{len(left)}"></a>' if level == 0 else ""
            left.append(anchor + html.escape(old))
            right.append(anchor + html.escape(old))
        elif op == "replace" and level < 2:
            inner_left, inner_right = mark(
                pieces(old, level + 1), pieces(new, level + 1), level + 1
            )
            left.append(inner_left)
            right.append(inner_right)
        else:
            if old:
                left.append(f"<del>{html.escape(old)}</del>")
            right.append(html.escape(new))
    return "".join(left), "".join(right)


def diff(before, after):
    return mark(pieces(before, 0), pieces(after, 0), 0)


def blocks_view(before):
    lines = before.splitlines()
    block, orange = {}, set()
    spans = find_blocks(lines) + find_locators(lines) + find_calculators(lines) + find_forms(lines)
    for n, (first, last) in enumerate(sorted(spans)):
        for k in range(first, last + 1):
            block.setdefault(k, n)
    for first, last in find_forms(lines):
        field = next(k for k in range(first, last + 1) if FIELD.match(lines[k].strip()))
        orange.update(range(first, field))
    left, right, open_block = [], [], None
    for k, line in enumerate(lines):
        text = html.escape(line) + "\n"
        if block.get(k) != open_block and open_block is not None:
            left.append("</del>")
            open_block = None
        if k in block:
            if open_block is None:
                left.append('<del class="blk">')
                open_block = block[k]
            left.append(f'<span class="intro">{text}</span>' if k in orange else text)
        else:
            anchor = f'<a data-k="{k}"></a>'
            left.append(anchor + text)
            right.append(anchor + text)
    if open_block is not None:
        left.append("</del>")
    return "".join(left), "".join(right)


def by_url(docs):
    return {doc.metadata["url"]: doc.page_content for doc in docs}


def views(docs):
    texts = by_url(docs)
    pages = {url: [] for url in texts}
    for name in STEPS:
        docs = CLEANERS[name](docs)
        after = by_url(docs)
        published = {doc.metadata["url"]: doc.metadata.get("published") for doc in docs}
        for url in pages:
            before = texts.get(url)
            if before is None:
                pages[url].append(
                    {"step": name, "note": "dropped earlier", "left": "", "right": ""}
                )
            elif url not in after:
                pages[url].append(
                    {
                        "step": name,
                        "note": "this step drops the page",
                        "left": f"<del>{html.escape(before)}</del>",
                        "right": "",
                    }
                )
            else:
                left, right = (
                    blocks_view(before)
                    if name == "blocks"
                    else diff(before, after[url])
                )
                note = f"{len(before):,} → {len(after[url]):,} chars, {len(before) - len(after[url]):,} removed"
                if name == "head":
                    note += f" · published: {published[url]}"
                pages[url].append(
                    {"step": name, "note": note, "left": left, "right": right}
                )
        texts = after
    return pages


PAGE = """<!doctype html><meta charset="utf-8"><title>Clean viewer</title>
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
pre { position: relative; flex: 1; overflow-y: auto; margin: 0; padding: 0 16px 50vh; white-space: pre-wrap; overflow-wrap: anywhere; font: 13px/1.6 Consolas, monospace; }
del { background: #f6d5dc; color: #a0446a; }
del.intro { background: #f9e3c4; color: #b5651d; }
del.blk { display: block; margin: 0 0 1.6em; padding: 2px 4px; border-radius: 4px; }
del.blk .intro { display: block; margin: -2px -4px 0; padding: 2px 4px; background: #f9e3c4; color: #b5651d; border-radius: 4px 4px 0 0; }
</style>
<header><div id="pages"></div><div id="steps"></div></header>
<main><section><h2>before this step · removed in red · orange = a form's heading and intro</h2><pre id="left"></pre></section>
<section><h2>after this step</h2><pre id="right"></pre></section></main>
<script>
const INDEX = __INDEX__, FEATURED = __FEATURED__, LOADED = {};
const left = document.getElementById("left"), right = document.getElementById("right");
let page = FEATURED[0], step = 0, busy = false;
function pageLoaded(i, views) { LOADED[i] = views; if (i == page) show(); }
function openPage(i) {
  page = i;
  if (LOADED[i]) return show();
  const s = document.createElement("script");
  s.src = `view_clean_pages/${i}.js`;
  document.body.appendChild(s);
}
function show() {
  const buttons = FEATURED.map(i => `<button class="${i == page ? "on" : ""}" onclick="openPage(${i})">${INDEX[i]}</button>`);
  buttons.push(`<button onclick="openPage(Math.floor(Math.random() * INDEX.length))">random</button>`);
  document.getElementById("pages").innerHTML = buttons.join("") + `<span id="name">${INDEX[page]}</span>`;
  const v = LOADED[page];
  document.getElementById("steps").innerHTML = v.map((s, i) => `<button class="${i == step ? "on" : ""}" onclick="step=${i};show()">${i + 1}. ${s.step}</button>`).join("") + `<span id="note">${v[step].note}</span>`;
  left.innerHTML = v[step].left;
  right.innerHTML = v[step].right;
  left.scrollTop = right.scrollTop = 0;
}
function follow(from, to) {
  if (busy) { busy = false; return; }
  const marks = [...from.querySelectorAll("a[data-k]")];
  let top = marks[0];
  for (const m of marks) { if (m.offsetTop <= from.scrollTop) top = m; else break; }
  if (!top) return;
  const twin = to.querySelector(`a[data-k="${top.dataset.k}"]`);
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
    pages = views(to_documents(load_snapshots(ROOT / "snapshots")[-1]))
    urls = list(pages)
    PAGE_DIR.mkdir(parents=True, exist_ok=True)
    for old in PAGE_DIR.glob("*.js"):
        old.unlink()
    for i, url in enumerate(urls):
        (PAGE_DIR / f"{i}.js").write_text(
            f"pageLoaded({i}, {json.dumps(pages[url])});", encoding="utf-8"
        )
    page = PAGE.replace("__INDEX__", json.dumps([name(url) for url in urls]))
    page = page.replace(
        "__FEATURED__", json.dumps([urls.index(url) for url in FEATURED])
    )
    OUT.write_text(page, encoding="utf-8")
    print("saved", OUT, "and", len(urls), "pages in", PAGE_DIR)


if __name__ == "__main__":
    main()
