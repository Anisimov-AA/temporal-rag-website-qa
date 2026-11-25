import json
import re
from collections import Counter
from pathlib import Path

from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parents[2]
PARSER = MarkdownIt("commonmark").enable(["table", "strikethrough"])
GROUPS = [
    ("carries meaning: keep", ["text", "paragraph", "heading", "bullet_list", "ordered_list", "blockquote", "table"]),
    ("meaning inside, the wrapper is noise: drop the wrapper", ["link", "strong", "em", "s", "code_inline", "fence"]),
    ("no meaning: drop", ["softbreak", "hardbreak", "image", "hr", "html_inline", "html_block"]),
]
NAMES = {
    "text": "plain text piece", "paragraph": "paragraph", "heading": "heading", "bullet_list": "bullet list",
    "ordered_list": "numbered list", "blockquote": "quote", "table": "table", "link": "link", "strong": "bold",
    "em": "italic", "s": "strikethrough", "code_inline": "inline code", "fence": "code block",
    "softbreak": "line break in a paragraph", "hardbreak": "forced line break", "image": "image", "hr": "divider",
    "html_inline": "html tag", "html_block": "html block",
}
SKIP = {"inline", "list_item", "thead", "tbody", "tr", "th", "td"}


INSIDE = {
    "strong": re.compile(r"\*\*[^*\n]+\*\*|__[^_\n]+__"),
    "em": re.compile(r"(?<![*\w])\*[^*\n]+\*(?!\*)|(?<![_\w])_[^_\n]+_(?![_\w])"),
    "softbreak": re.compile(r"\S{0,20}\n\S{0,20}"),
    "hardbreak": re.compile(r"\S{0,20}(?:  |\\)\n\S{0,20}"),
}


def walk(tokens, parent=""):
    for token in tokens:
        if token.type.endswith("_close"):
            continue
        yield token, parent
        if token.children:
            yield from walk(token.children, token.content)


def example(token, parent, lines):
    kind = token.type.removesuffix("_open")
    if token.type == "image":
        return f"![{token.content}]({token.attrGet('src')})"
    if token.type == "link_open":
        return f"[...]({token.attrGet('href')})"
    if kind in INSIDE:
        found = INSIDE[kind].search(parent)
        return found.group(0).replace("\n", " ⏎ ") if found else ""
    if token.map:
        return lines[token.map[0]].strip()
    return token.content.strip()


def main():
    counts, pages, examples, total = Counter(), Counter(), {}, 0
    for folder in sorted(p for p in (ROOT / "snapshots").iterdir() if (p / "manifest.json").exists()):
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        for entry in manifest["pages"]:
            text = (folder / entry["file"]).read_text(encoding="utf-8")
            lines, seen = text.splitlines(), set()
            total += 1
            for token, parent in walk(PARSER.parse(text)):
                kind = token.type.removesuffix("_open")
                if kind in SKIP:
                    continue
                counts[kind] += 1
                seen.add(kind)
                if not examples.get(kind):
                    examples[kind] = example(token, parent, lines)
            pages.update(seen)
    print(f"markdown-it on {total} raw pages, all 5 downloads\n")
    for title, kinds in GROUPS:
        print(title)
        for kind in kinds:
            print(f"  {NAMES[kind]:28} {counts[kind]:>8} times {pages[kind]:>5} pages   {examples.get(kind, '')[:50]!r}")
        print()
    other = [kind for kind in counts if not any(kind in kinds for _, kinds in GROUPS)]
    if other:
        print("not in a group yet:", other)


if __name__ == "__main__":
    main()
