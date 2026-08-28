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

A bag of words alone is not enough, because a model *code* is not a word. Sunlight's
price list prints `V 60`, the baseline export holds `V60` — the same layout, but
tokenised as `{v, 60}` and `{v60}`, which share nothing at all. The overlap then rests
entirely on the range name, and when the range has *also* been renamed (Sunlight's MY27
`Van Adventure Edition` → `Van Adventure`) the score collapses far enough that eleven
products FMLV already held were proposed as new, while the same run raised disappearance
notices against the rows they duplicated. See docs/adapters/sunlight.md.

So code fragments are glued back together before scoring: a run of adjacent tokens that
can only be parts of a code — single letters and digit-leading tokens — is joined into
one, so `V 60`, `V60`, `I 67S`/`I67S` and `V 67 S`/`V 67S` all tokenise alike. The rule
is deliberately narrow. It leaves a multi-letter token such as Adria's `DC` alone, so
`"670 DC"` still scores as before, and it keeps `CLIFF 540 V` (`{cliff, 540v}`) distinct
from `CLIFF 540` (`{cliff, 540}`) — the collision sunlight.py's run-based parser exists
to avoid, which a blanket "strip the spaces" normalisation would have reintroduced here.

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

#: Only whitespace may sit between two tokens for them to count as one code. A comma or
#: a slash separates *fields*, so "Matrix, 670" must not glue into "matrix670".
_WHITESPACE_ONLY = re.compile(r"\s*\Z")

#: Below this score a candidate isn't a match at all — the scraped product is treated
#: as new instead. Chosen against the Adria "670 DC Supreme Alde RHD" vs baseline
#: "Supreme 670 DC" case (see docs/adapters/adria.md), which scores well above this;
#: revisit once a second manufacturer's naming has been checked against it.
DEFAULT_THRESHOLD = 0.5


def _is_code_fragment(token: str) -> bool:
    """True for a token that can only be part of a model code, never a word.

    A lone letter (`V`, `T`, the `S` of `V 67 S`) or anything starting with a digit
    (`60`, `67S`, `7433Q`). A multi-letter run like `DC` or `RHD` is deliberately
    excluded: it is just as likely to be a trim name, and gluing it to its neighbour
    would break Adria's `"670 DC"` (docs/adapters/adria.md).
    """
    return (len(token) == 1 and token.isalpha()) or token[0].isdigit()


def _tokenize(text: str | None) -> frozenset[str]:
    """Word-bag of `text`, with adjacent model-code fragments joined into one token.

    Runs of code fragments separated by nothing but whitespace are joined, so `V 60`
    and `V60` — and `V 67 S` and `V 67S` — all yield the same token. A run is only
    joined when it carries a digit somewhere: `A Class` stays two tokens, since `A` on
    its own would otherwise swallow the word after it.
    """
    if not text:
        return frozenset()
    lowered = text.lower()
    matches = list(_TOKEN_PATTERN.finditer(lowered))

    tokens: list[str] = []
    run: list[re.Match[str]] = []

    def flush() -> None:
        if len(run) > 1 and any(match.group()[0].isdigit() for match in run):
            tokens.append("".join(match.group() for match in run))
        else:
            tokens.extend(match.group() for match in run)
        run.clear()

    for match in matches:
        adjacent = bool(run) and bool(
            _WHITESPACE_ONLY.match(lowered, run[-1].end(), match.start())
        )
        if not _is_code_fragment(match.group()):
            flush()
            tokens.append(match.group())
            continue
        if not adjacent:
            flush()
        run.append(match)
    flush()

    return frozenset(tokens)


def _identity_tokens(manufacturer_range: str | None, model: str | None) -> frozenset[str]:
    return _tokenize(manufacturer_range) | _tokenize(model)


def _codes(tokens: frozenset[str]) -> frozenset[str]:
    """The layout codes in a token bag — the tokens carrying a digit."""
    return frozenset(token for token in tokens if any(char.isdigit() for char in token))


def token_similarity(left: Motorhome, right: Motorhome) -> float:
    """Jaccard similarity of the two products' range+model word bags, in [0, 1].

    Zero when both sides name a layout code and none of the codes agree. Word overlap
    alone is too generous here: `Low Profiles T65` and `Low Profiles T 66S` share their
    whole range name, which on a two-word range is already half the bag — enough to
    reach the threshold on the strength of being siblings. But a layout code is the one
    part of a product's name that is *meant* to be unique within its range, so two
    products whose codes disagree are two products, however alike the rest reads.
    """
    left_tokens = _identity_tokens(left.manufacturer_range, left.model)
    right_tokens = _identity_tokens(right.manufacturer_range, right.model)
    if not left_tokens and not right_tokens:
        return 0.0
    union = left_tokens | right_tokens
    if not union:
        return 0.0

    left_codes, right_codes = _codes(left_tokens), _codes(right_tokens)
    if left_codes and right_codes and not (left_codes & right_codes):
        return 0.0

    return len(left_tokens & right_tokens) / len(union)


def _tie_break(baseline: Motorhome) -> tuple[int, int]:
    """Sort key preferring the *live, current* row when several score identically.

    An FMLV export holds a manufacturer's history, not just its current line-up: the
    Sunlight baseline carries `Coachbuilts A60` twice, as archived 2022 product 3524 and
    live 2026 product 6562. Both are the same layout and both score identically against
    a scraped `Coachbuilts Root A 60`, so without a tie-break the winner is whichever
    the export happened to list first — and a model-year update would land on the dead
    row while the live one drifted out of date.

    Sorted ascending, so lower is better: not-archived before archived, then the newest
    year first.
    """
    return (1 if baseline.archived else 0, -(baseline.year or 0))


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

    Equal scores are broken by `_tie_break`: an export routinely holds the same layout
    more than once, and the live row is the one an update belongs on.
    """
    scraped_list = list(scraped)
    baseline_list = list(baseline)

    candidates: list[tuple[float, tuple[int, int], int, int]] = []
    for s_idx, extracted in enumerate(scraped_list):
        for b_idx, baseline_motorhome in enumerate(baseline_list):
            score = token_similarity(extracted.motorhome, baseline_motorhome)
            if score > 0:
                candidates.append((score, _tie_break(baseline_motorhome), s_idx, b_idx))

    # Best score first, then the tie-break, then insertion order (scraped-index then
    # baseline-index ascending) so results are deterministic run to run.
    candidates.sort(
        key=lambda candidate: (-candidate[0], candidate[1], candidate[2], candidate[3])
    )

    matched_scraped: dict[int, tuple[int, float]] = {}
    used_baseline: set[int] = set()
    for score, _tie, s_idx, b_idx in candidates:
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
