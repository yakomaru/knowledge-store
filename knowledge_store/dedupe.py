"""Content similarity.

Token-set Jaccard over normalized words. Cheap, dependency-free, and good enough
to catch the case that actually matters: an agent re-writing something the store
already holds, in slightly different words.
"""

from __future__ import annotations

import re
from functools import lru_cache

_WORD = re.compile(r"[a-z0-9]+")

#: Dropped before comparison so two passages aren't called similar on glue words.
_STOPWORDS = frozenset("""
a an the and or but if then than that this these those of in on at to for from by
with without is are was were be been being it its as we you they i he she them us
our your their not no do does did done have has had will would can could should
over under also so such via per into onto out up down about
""".split())

_SUFFIXES = ("ization", "isation", "ating", "ation", "ingly", "edly", "ing", "ies",
             "ied", "ies", "ers", "er", "ed", "es", "ly", "s")


def _stem(word: str) -> str:
    """Crude suffix stripping, to agree with the FTS porter tokenizer.

    It does not need to be linguistically correct, only consistent: its whole job
    is to stop ``owns``/``owning`` and ``serves``/``served`` from reading as
    unrelated tokens when comparing two passages.
    """
    if len(word) <= 4:
        return word
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            base = word[: -len(suffix)]
            if suffix in ("ies", "ied"):
                return base + "y"
            # Collapse a doubled final consonant: "running" -> "run".
            if len(base) > 3 and base[-1] == base[-2] and base[-1] not in "aeiou":
                base = base[:-1]
            return base
    return word


def tokens(text: str) -> frozenset[str]:
    """Normalized content words, as a set."""
    return frozenset(
        _stem(w) for w in _WORD.findall(text.lower())
        if w not in _STOPWORDS and len(w) > 1
    )


@lru_cache(maxsize=2048)
def _cached_tokens(text: str) -> frozenset[str]:
    return tokens(text)


#: Below this many tokens, containment is not meaningful -- a very short passage
#: sits inside a long one by accident.
_MIN_CONTAINMENT_TOKENS = 4


def similarity(a: str, b: str) -> float:
    """How much of the smaller passage is already said by the larger one, 0.0 - 1.0.

    The maximum of two measures, because they catch different failures:

    * **Jaccard** (``|A&B| / |A|B||``) catches restatement -- the same fact in
      different words.
    * **Containment** (``|A&B| / min(|A|,|B|)``) catches elaboration -- an entry
      that repeats a stored fact and appends detail. Jaccard scores that pair
      *low* precisely because the new detail inflates the union, which would let
      redundant supersets into the store unchallenged.
    """
    ta, tb = _cached_tokens(a), _cached_tokens(b)
    if not ta or not tb:
        return 0.0
    intersection = len(ta & tb)
    if not intersection:
        return 0.0
    jaccard = intersection / len(ta | tb)
    smaller = min(len(ta), len(tb))
    if smaller < _MIN_CONTAINMENT_TOKENS:
        return jaccard
    return max(jaccard, intersection / smaller)


def looks_like_chatter(content: str, markers: tuple[str, ...]) -> str | None:
    """Return the marker that makes this look like session narration, if any."""
    lowered = content.lower()
    for marker in markers:
        if marker in lowered:
            return marker.strip()
    return None


def fts_query_from(content: str, max_terms: int = 24) -> str:
    """Build a safe FTS5 MATCH query from free text.

    Every term is quoted, so punctuation in the source can't be read as FTS
    operators (``NEAR``, ``*``, ``-``, ``"``) and turn a write into a syntax error.
    """
    terms = [t for t in tokens(content)][:max_terms]
    if not terms:
        return ""
    return " OR ".join(f'"{t}"' for t in terms)
