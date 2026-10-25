import re
from pathlib import Path

DOCS_DIR = Path(__file__).parent / "knowledge"
MIN_SCORE = 4      # below this, a note is not relevant enough
MAX_RESULTS = 1    # how many notes we give to the AI

# Common words that don't help matching
STOP_WORDS = {
    "the", "and", "for", "with", "that", "this", "from", "have", "are", "was",
    "you", "your", "why", "how", "what", "when", "can", "not", "get", "getting",
    "error", "line", "file", "at", "in", "on", "of", "to", "is", "it", "am", "i",
}


def tokenize(text: str) -> list[str]:
    """Lowercases text, splits it into words, and drops stop words."""
    words = re.findall(r"[a-z0-9_]+", text.lower())
    return [w for w in words if len(w) > 1 and w not in STOP_WORDS]


def parse_doc(raw: str, file_name: str) -> dict:
    """Reads the Title / Source / Keywords lines at the top, then the body."""
    lines = raw.splitlines()
    meta = {}
    i = 0
    while i < len(lines):
        match = re.match(r"^(Title|Source|Keywords):\s*(.*)$", lines[i], re.IGNORECASE)
        if not match:
            break
        meta[match.group(1).lower()] = match.group(2).strip()
        i += 1

    body = "\n".join(lines[i:]).strip()
    phrases = [p.strip().lower() for p in meta.get("keywords", "").split(",") if p.strip()]

    return {
        "file": file_name,
        "title": meta.get("title", file_name),
        "url": meta.get("source", ""),
        "phrases": phrases,
        "keyword_tokens": set(tokenize(" ".join(phrases))),
        "title_tokens": set(tokenize(meta.get("title", ""))),
        "body_tokens": set(tokenize(body)),
        "body": body[:1500],
    }


def load_docs() -> list[dict]:
    """Reads every .md and .txt note in the knowledge folder."""
    if not DOCS_DIR.exists():
        print("No knowledge folder found. Retrieval is off.")
        return []

    docs = []
    for path in sorted(DOCS_DIR.iterdir()):
        if path.suffix.lower() in (".md", ".txt"):
            raw = path.read_text(encoding="utf-8-sig", errors="replace")
            docs.append(parse_doc(raw, path.name))
    return docs


def score_doc(doc: dict, query_lower: str, query_tokens: set[str]) -> int:
    score = 0

    # Strongest signal: a whole keyword phrase appears in the user's text
    for phrase in doc["phrases"]:
        if phrase in query_lower:
            score += 5

    # Weaker signals: single words matching keywords, title, or body
    for token in query_tokens:
        if token in doc["keyword_tokens"]:
            score += 2
        if token in doc["title_tokens"]:
            score += 2
        if token in doc["body_tokens"]:
            score += 1

    return score


def retrieve(query: str) -> list[dict]:
    """Returns up to MAX_RESULTS notes, best first. Returns [] if nothing matches."""
    docs = load_docs()  # re-read each time, so edits to notes apply immediately
    query_lower = query.lower()
    query_tokens = set(tokenize(query))

    scored = [(score_doc(d, query_lower, query_tokens), d) for d in docs]
    scored = [(s, d) for s, d in scored if s >= MIN_SCORE]
    scored.sort(key=lambda pair: pair[0], reverse=True)

    results = []
    for score, doc in scored[:MAX_RESULTS]:
        print(f"Matched note: {doc['title']} (score {score})")
        results.append(doc)
    return results


def list_topics() -> list[str]:
    """Titles of everything the bot knows about."""
    return [d["title"] for d in load_docs()]