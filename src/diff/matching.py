"""Matching scraped products to existing FMLV `product_id`s.

Per DESIGN.md §4.1, `product_id` is minted by the NCC website, not this application —
matching is how a freshly scraped product finds its way to the *right* existing
`product_id` (so a 2027 model update lands on the same row as its 2026 predecessor)
or is correctly recognised as new.

Exact string matching on `manufacturer_range`/`model` does not work. A manufacturer's
site names a configuration differently to the baseline export — Adria's site names a
configuration by layout code + trim (`"670 DC"` + `"Supreme Alde RHD"`), the baseline
export has `"Supreme 670 DC"` for the same product: same words, different order (see
docs/adapters/adria.md and the TODO.md note it links to). So matching is token-based:
normalise range+model text into a bag of words and score candidates by overlap, rather
than requiring an exact match.

Callers are expected to have already scoped both `scraped` and `baseline` to a single
manufacturer — a run is always per-manufacturer (DESIGN.md §5), so matching does not
check manufacturer identity itself.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from ..adapters.base import ExtractedMotorhome
from ..product_model.model import Motorhome

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")

#: Below this score a candidate isn't a match at all — the scraped product is treated
#: as new instead. Chosen against the Adria "670 DC Supreme Alde RHD" vs baseline
#: "Supreme 670 DC" case (see docs/adapters/adria.md), which scores well above this;
#: revisit once a second manufacturer's naming has been checked against it.
DEFAULT_THRESHOLD = 0.5


def _tokenize(text: str | None) -> frozenset[str]:
    if not text:
        return frozenset()
    return frozenset(_TOKEN_PATTERN.findall(text.lower()))


def _identity_tokens(manufacturer_range: str | None, model: str | None) -> frozenset[str]:
    return _tokenize(manufacturer_range) | _tokenize(model)


def token_similarity(left: Motorhome, right: Motorhome) -> float:
    """Jaccard similarity of the two products' range+model word bags, in [0, 1]."""
    left_tokens = _identity_tokens(left.manufacturer_range, left.model)
    right_tokens = _identity_tokens(right.manufacturer_range, right.model)
    if not left_tokens and not right_tokens:
        return 0.0
    union = left_tokens | right_tokens
    if not union:
        return 0.0
    return len(left_tokens & right_tokens) / len(union)


@dataclass(frozen=True)
class MatchResult:
    """The outcome of matching one scraped product against the baseline.

    `baseline is None` means no candidate reached the threshold — treat as new
    (DESIGN.md §4.1: a genuinely new product is submitted with `product_id` blank).
    """

    extracted: ExtractedMotorhome
    baseline: Motorhome | None
    baseline_index: int | None
    score: float
    method: str | None  # "exact" | "fuzzy" | None


def match_products(
    scraped: Iterable[ExtractedMotorhome],
    baseline: Iterable[Motorhome],
    *,
    threshold: float = DEFAULT_THRESHOLD,
) -> list[MatchResult]:
    """Match every scraped product to at most one baseline product, and vice versa.

    A greedy highest-score-first assignment: candidate (scraped, baseline) pairs are
    scored, sorted best-first, and each is accepted only if neither side has already
    been claimed by a better-scoring pair. This is a one-to-one matching, not a
    threshold-only lookup — it stops two similarly-named scraped products both
    claiming the same baseline row.
    """
    scraped_list = list(scraped)
    baseline_list = list(baseline)

    candidates: list[tuple[float, int, int]] = []
    for s_idx, extracted in enumerate(scraped_list):
        for b_idx, baseline_motorhome in enumerate(baseline_list):
            score = token_similarity(extracted.motorhome, baseline_motorhome)
            if score > 0:
                candidates.append((score, s_idx, b_idx))

    # Stable sort: ties keep insertion order (scraped-index then baseline-index
    # ascending), so results are deterministic run to run.
    candidates.sort(key=lambda candidate: candidate[0], reverse=True)

    matched_scraped: dict[int, tuple[int, float]] = {}
    used_baseline: set[int] = set()
    for score, s_idx, b_idx in candidates:
        if score < threshold:
            break
        if s_idx in matched_scraped or b_idx in used_baseline:
            continue
        matched_scraped[s_idx] = (b_idx, score)
        used_baseline.add(b_idx)

    results: list[MatchResult] = []
    for s_idx, extracted in enumerate(scraped_list):
        match = matched_scraped.get(s_idx)
        if match is None:
            results.append(
                MatchResult(
                    extracted=extracted,
                    baseline=None,
                    baseline_index=None,
                    score=0.0,
                    method=None,
                )
            )
            continue
        b_idx, score = match
        method = "exact" if score == 1.0 else "fuzzy"
        results.append(
            MatchResult(
                extracted=extracted,
                baseline=baseline_list[b_idx],
                baseline_index=b_idx,
                score=score,
                method=method,
            )
        )
    return results
