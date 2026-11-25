import sys
from pathlib import Path

from ollama import Client

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "harness"))
from contract import Answer, Snapshot  # noqa: E402
from find_conflicts import find_conflicts, prose_rates, rate_table  # noqa: E402
from generation.ask_the_llm import GAPS, LLMS, ask_the_llm  # noqa: E402
from generation.check_the_answer import check_the_answer  # noqa: E402
from generation.cite_the_sources import cite_the_sources  # noqa: E402
from generation.write_the_prompt import FORMATS, RETRY, write_the_prompt  # noqa: E402
from indexing.clean_pages import clean_pages  # noqa: E402
from indexing.index_chunks import EMBEDDINGS, QUERY_EMBEDDINGS, Keywords, build_index, fingerprint, index_docs, index_is_ready, open_index  # noqa: E402
from indexing.load_pages import load_pages  # noqa: E402
from indexing.split_into_chunks import split_into_chunks  # noqa: E402
from retrieval.drop_old_versions import drop_old_versions  # noqa: E402
from retrieval.keep_top_k import keep_top_k  # noqa: E402
from retrieval.reorder_by_date import reorder_by_date  # noqa: E402
from retrieval.rerank_chunks import rerank_chunks  # noqa: E402
from retrieval.retrieve_chunks import retrieve_chunks  # noqa: E402

INDEX_DIR = Path(__file__).resolve().parents[1] / "index"
DONT_KNOW = "I don't know. The Dupaco website does not say this. Please contact Dupaco and a member services rep can help."
CONFIG = {
    "clean": [
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
    ],
    "chunk_size": 4000,
    "embedding": "bge-m3",
    "search": "vectors + bm25 + rerank",
    "candidates": 20,
    "top_k": 5,
    "dates": "newest effective first",
    "prompt": "json_known",
    "llm": "gcp:gemma4:26b",
}


class Knowledge:
    def __init__(self, config=None):
        self.config = config or CONFIG
        self.embeddings = EMBEDDINGS[self.config["embedding"]]()
        self.query_embeddings = QUERY_EMBEDDINGS[self.config["embedding"]]()
        self.llm = LLMS[self.config["llm"]]()
        self.stores = {}
        self.keywords = {}
        self.dates = {}
        self.rates = []
        self.prose = []

    def ingest(self, snapshot: Snapshot):
        c = self.config
        pages = load_pages(snapshot)
        self.rates += rate_table(pages)
        self.prose += prose_rates(pages)
        cleaned = clean_pages(pages, c["clean"])
        chunks = split_into_chunks(cleaned, c["chunk_size"])
        docs = index_docs(chunks)
        name = f"{snapshot.snapshot_id}__{c['embedding']}__{fingerprint(docs)}"
        if not index_is_ready(docs, name, self.embeddings, INDEX_DIR):
            self.free_the_gpu()
        _, how = build_index(docs, name, self.embeddings, INDEX_DIR)
        store = open_index(name, self.query_embeddings, INDEX_DIR)
        self.stores[snapshot.snapshot_id] = store
        self.keywords[snapshot.snapshot_id] = Keywords(docs)
        self.dates[snapshot.snapshot_id] = snapshot.taken_on
        print(
            f"{snapshot.snapshot_id}: {len(pages)} pages loaded, "
            f"{len(cleaned)} after cleaning, {len(chunks)} chunks, index {how}"
        )
        self.warm_up(store, docs)

    def free_the_gpu(self):
        Client(host=self.llm.base_url).generate(model=self.llm.model, keep_alive=0)

    def warm_up(self, store, docs):
        store.similarity_search("warm up", k=1)
        rerank_chunks("warm up", docs[:2])
        self.llm.invoke("Reply OK")

    def pick(self, as_of):
        days = {sid: day for sid, day in self.dates.items() if as_of is None or day <= as_of}
        return max(days, key=days.get) if days else min(self.dates, key=self.dates.get)

    def search(self, question, snapshot_id):
        c = self.config
        chunks = retrieve_chunks(self.stores[snapshot_id], self.keywords[snapshot_id], question, c["candidates"], c["search"])
        if "rerank" in c["search"]:
            chunks = rerank_chunks(question, chunks)
        if c.get("old_versions") == "drop":
            chunks = drop_old_versions(chunks)
        chunks = keep_top_k(chunks, c["top_k"])
        if c["dates"] == "newest effective first":
            chunks = reorder_by_date(chunks)
        return chunks

    def answer(self, question, as_of=None):
        c = self.config
        snapshot_id = self.pick(as_of)
        chunks = self.search(question, snapshot_id)
        today = (as_of or self.dates[snapshot_id]) if c.get("today") else None
        prompt = write_the_prompt(c["prompt"], question, chunks, today, c.get("url_in_body", False))
        reply = ask_the_llm(self.llm, GAPS[c["llm"]], prompt, FORMATS[c["prompt"]])
        if c.get("retry") and not reply.known:
            reply = ask_the_llm(self.llm, GAPS[c["llm"]], prompt + RETRY, FORMATS[c["prompt"]])
        reply = check_the_answer(question, reply)
        if not reply.known:
            return Answer(text=DONT_KNOW, confident=False)
        return Answer(text=reply.answer, sources=cite_the_sources(chunks, reply.pages))

    def conflicts(self):
        return find_conflicts(self.rates, self.prose)


def build(config=None):
    return Knowledge(config)
