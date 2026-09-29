"""
Semantic memory — knowledge base with embeddings for similarity search.

Uses TF-IDF + cosine similarity for retrieval (no external embedding models
required). For higher quality, can be upgraded to sentence-transformers
when the model is available.

Stores:
  - Knowledge chunks (text + metadata + embedding)
  - Embeddings as numpy arrays (persisted)
  - Cosine similarity search

Used by:
  - Reasoning engine (finds relevant past knowledge)
  - Reflect node (looks at similar past episodes)
  - World model (provides context)
"""
import re
import math
import json
import time
import pickle
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from collections import Counter
from datetime import datetime, timezone


SEMANTIC_DIR = Path("/workspace/ai-empire/empire_data/semantic")
SEMANTIC_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class Chunk:
    id: str
    text: str
    embedding: List[float]
    metadata: Dict[str, Any] = field(default_factory=dict)
    source: str = ""          # where it came from (skill, episode, dataset, manual)
    source_id: str = ""       # reference to original
    tenant: str = "default"
    created_at: str = ""


class TFIDFVectorizer:
    """Lightweight TF-IDF vectorizer. No external deps."""

    def __init__(self):
        self.vocab: Dict[str, int] = {}
        self.idf: Dict[str, float] = {}

    def fit(self, documents: List[str]):
        # Build vocabulary
        df: Counter = Counter()
        n = len(documents)
        for doc in documents:
            terms = set(self._tokenize(doc))
            for term in terms:
                df[term] += 1
        self.vocab = {term: i for i, term in enumerate(sorted(df.keys()))}
        # IDF
        self.idf = {term: math.log((n + 1) / (count + 1)) + 1
                     for term, count in df.items()}
        return self

    def transform(self, document: str) -> List[float]:
        """Convert document to TF-IDF vector."""
        terms = self._tokenize(document)
        tf: Counter = Counter(terms)
        total = sum(tf.values()) or 1
        vec = [0.0] * len(self.vocab)
        for term, count in tf.items():
            if term in self.vocab:
                idx = self.vocab[term]
                vec[idx] = (count / total) * self.idf.get(term, 1.0)
        return vec

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """Lowercase + split + strip accents + filter."""
        text = text.lower()
        # Strip accents
        import unicodedata
        text = "".join(c for c in unicodedata.normalize("NFD", text)
                       if unicodedata.category(c) != "Mn")
        # Split by non-alphanumeric
        tokens = re.findall(r"\b[a-z0-9]{2,}\b", text)
        # Stopwords (Portuguese + English)
        STOP = {"the", "and", "for", "are", "but", "not", "you", "all",
                "can", "her", "was", "one", "our", "out", "day", "get",
                "use", "has", "him", "his", "how", "man", "new", "now",
                "old", "see", "two", "way", "who", "boy", "did", "its",
                "let", "put", "say", "she", "too", "que", "com", "nao",
                "para", "uma", "sao", "mas", "por", "tem", "the", "and"}
        return [t for t in tokens if t not in STOP and len(t) > 2]

    @staticmethod
    def cosine(v1: List[float], v2: List[float]) -> float:
        """Cosine similarity between two equal-length vectors."""
        if len(v1) != len(v2) or not v1:
            return 0.0
        dot = sum(a * b for a, b in zip(v1, v2))
        n1 = math.sqrt(sum(a * a for a in v1))
        n2 = math.sqrt(sum(b * b for b in v2))
        if n1 == 0 or n2 == 0:
            return 0.0
        return dot / (n1 * n2)


class SemanticMemory:
    """Vector-store-backed semantic memory."""

    def __init__(self, store_dir: Path = None):
        self.store_dir = store_dir or SEMANTIC_DIR
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self.chunks: Dict[str, Chunk] = {}
        self.vectorizer = TFIDFVectorizer()
        self._load()

    def _load(self):
        chunks_file = self.store_dir / "chunks.json"
        vocab_file = self.store_dir / "vocab.pkl"
        if chunks_file.exists():
            try:
                data = json.loads(chunks_file.read_text())
                for c in data.get("chunks", []):
                    self.chunks[c["id"]] = Chunk(
                        id=c["id"], text=c["text"], embedding=c["embedding"],
                        metadata=c.get("metadata", {}),
                        source=c.get("source", ""),
                        source_id=c.get("source_id", ""),
                        tenant=c.get("tenant", "default"),
                        created_at=c.get("created_at", ""),
                    )
            except Exception as e:
                print(f"[semantic] failed to load chunks: {e}")
        if vocab_file.exists():
            try:
                saved = pickle.loads(vocab_file.read_bytes())
                self.vectorizer.vocab = saved["vocab"]
                self.vectorizer.idf = saved["idf"]
            except Exception as e:
                print(f"[semantic] failed to load vocab: {e}")

    def _save(self):
        chunks_file = self.store_dir / "chunks.json"
        vocab_file = self.store_dir / "vocab.pkl"
        chunks_file.write_text(json.dumps({
            "version": 1,
            "chunks": [asdict(c) for c in self.chunks.values()]
        }, default=str, indent=2))
        vocab_file.write_bytes(pickle.dumps({
            "vocab": self.vectorizer.vocab,
            "idf": self.vectorizer.idf,
        }))

    def add(self, text: str, *, metadata: Dict[str, Any] = None,
            source: str = "", source_id: str = "",
            tenant: str = "default") -> Chunk:
        """Add a chunk to semantic memory. Auto-embeddings + rebuilds index."""
        cid = f"ch-{hashlib.md5(text.encode()).hexdigest()[:12]}"
        if cid in self.chunks:
            return self.chunks[cid]
        # Rebuild vectorizer with all texts (cheap, fits in memory)
        all_texts = [c.text for c in self.chunks.values()] + [text]
        self.vectorizer.fit(all_texts)
        embedding = self.vectorizer.transform(text)
        chunk = Chunk(
            id=cid, text=text, embedding=embedding,
            metadata=metadata or {},
            source=source, source_id=source_id, tenant=tenant,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.chunks[cid] = chunk
        # Re-embed existing
        for c in self.chunks.values():
            if c.id != cid:
                c.embedding = self.vectorizer.transform(c.text)
        self._save()
        return chunk

    def add_many(self, texts: List[str], **kwargs) -> List[Chunk]:
        return [self.add(t, **kwargs) for t in texts]

    def search(self, query: str, *, k: int = 5,
               tenant: str = None, min_score: float = 0.05) -> List[Tuple[Chunk, float]]:
        """Top-k similar chunks. Returns [(chunk, score), ...]."""
        if not self.chunks:
            return []
        q_vec = self.vectorizer.transform(query)
        results = []
        for chunk in self.chunks.values():
            if tenant and chunk.tenant != tenant:
                continue
            score = self.vectorizer.cosine(q_vec, chunk.embedding)
            if score >= min_score:
                results.append((chunk, score))
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:k]

    def delete(self, chunk_id: str):
        if chunk_id in self.chunks:
            del self.chunks[chunk_id]
            self._save()

    def delete_by_source(self, source: str, source_id: str):
        to_delete = [cid for c in self.chunks.values()
                     if c.source == source and c.source_id == source_id]
        for cid in to_delete:
            del self.chunks[cid]
        if to_delete:
            self._save()

    def stats(self) -> Dict[str, Any]:
        return {
            "chunk_count": len(self.chunks),
            "vocab_size": len(self.vectorizer.vocab),
            "by_source": _count_by(self.chunks.values(), lambda c: c.source),
            "by_tenant": _count_by(self.chunks.values(), lambda c: c.tenant),
        }


def _count_by(items, key):
    counts: Dict[str, int] = {}
    for it in items:
        k = key(it)
        counts[k] = counts.get(k, 0) + 1
    return counts


_SEMANTIC: Optional[SemanticMemory] = None


def get_semantic() -> SemanticMemory:
    global _SEMANTIC
    if _SEMANTIC is None:
        _SEMANTIC = SemanticMemory()
    return _SEMANTIC
