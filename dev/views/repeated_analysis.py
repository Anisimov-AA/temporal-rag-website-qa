import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(ROOT / "solution"))
from run_eval import load_snapshots  # noqa: E402
from indexing.clean_pages import clean_pages as clean  # noqa: E402
from indexing.load_pages import load_pages as to_documents  # noqa: E402

BEFORE = ["images", "links", "markdown_noise", "html_noise"]
SHARE, LEAST, BLOCK_SHARE, MAX_BLOCK = 0.10, 3, 0.8, 40
NUMBER = re.compile(r"\d+")
HEADING = re.compile(r"^#{1,6}\s")
DATE = re.compile(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.? 0, 0$")


def shape(line):
    return NUMBER.sub("0", line.strip())


def main():
    table, followers, sizes = defaultdict(dict), defaultdict(Counter), {}
    for snapshot in load_snapshots(ROOT / "snapshots"):
        docs = clean(to_documents(snapshot), BEFORE)
        day = snapshot.taken_on[5:]
        sizes[day] = len(docs)
        counts = Counter(s for doc in docs for s in {shape(line) for line in doc.page_content.splitlines()})
        least = max(LEAST, SHARE * len(docs))
        repeated = {s for s, n in counts.items() if s and not s.startswith("|") and n >= least}
        for s in repeated:
            table[s][day] = counts[s]
        for doc in docs:
            lines = doc.page_content.splitlines()
            for i, line in enumerate(lines):
                if shape(line) in repeated and HEADING.match(line.strip()):
                    after = range(i + 1, min(len(lines), i + 1 + MAX_BLOCK))
                    end = next((shape(lines[k]) for k in after if shape(lines[k]) in repeated), None)
                    followers[shape(line)][end] += 1
    ends = {}
    for start, seen in followers.items():
        end, n = seen.most_common(1)[0]
        ends[start] = end if end and n >= BLOCK_SHARE * sum(seen.values()) else "the next heading of its level"
    kinds = defaultdict(list)
    for s in table:
        if DATE.match(s):
            kinds["date: keep, it is information"].append(s)
        elif s in ends:
            kinds["block start: drop the block"].append(s)
        elif s in ends.values():
            kinds["block end"].append(s)
        else:
            kinds["line: drop"].append(s)
    days = list(sizes)
    print(f"a line shape (numbers → 0) on {SHARE:.0%} of the pages of a download, at least {LEAST}")
    print("pages per download: " + ", ".join(f"{d} {n}" for d, n in sizes.items()) + "\n")
    print(f"{'':52}" + "".join(f"{d:>7}" for d in days))
    for kind, shapes in kinds.items():
        print(kind)
        for s in sorted(shapes, key=lambda s: -max(table[s].values())):
            row = "".join(f"{table[s].get(d, 0):>7}" for d in days)
            tail = f"   → until {ends[s]}" if s in ends else ""
            print(f"  {s[:50]:50}{row}{tail}")
        print()


if __name__ == "__main__":
    main()
