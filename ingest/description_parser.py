"""
Parse a pasted YouTube description or comment into setlist lines for the
contribute-tab prefill.

Builds on the line tokenizer and token classifier in populate_db.py and adds
steps that only make sense when looking at a whole description at once:

  1. Pre-clean noise such as "(2 Kalai)" and "(Kriti is unavailable)".
  2. Classify each line, optionally against database names (CatalogLookups).
  3. Infer the column order most lines share (e.g. raga - piece - talam -
     composer) and use it to read the lines the classifier could not.
  4. Fold alapana lines into the song that follows in the same raga.
  5. Canonicalize kinds.
  6. Collapse "Ragam" / "Tanam" / "Pallavi" lines into a single RTP item.
"""

import re
from collections import Counter
from dataclasses import replace

from ingest.populate_db import (
    PHONETIC_MIN_LEN,
    CatalogLookups,
    ClassifiedLine,
    _is_setlist_line,
    _score_confidence,
    classify_tokens,
    detect_kind,
    normalize_for_match,
    phonetic_key,
    tokenize_line,
)

# A template needs this many confidently-parsed lines before it is trusted.
MIN_TEMPLATE_SUPPORT = 2

# ---------------------------------------------------------------------------
# 1. Pre-clean
# ---------------------------------------------------------------------------

_NOISE_PATTERNS = (
    re.compile(r"\(\s*\d+\s*kala[im]?\s*\)", re.IGNORECASE),    # (2 Kalai)
    re.compile(r"\([^)]*\bunavailable\b[^)]*\)", re.IGNORECASE),  # (Kriti is unavailable)
    re.compile(r"(?<!\S)\*+(?!\S)"),                              # stray asterisks
)


def clean_line(line: str) -> str:
    for pattern in _NOISE_PATTERNS:
        line = pattern.sub(" ", line)
    return re.sub(r"[ \t]+", " ", line).strip()


# ---------------------------------------------------------------------------
# 3. Format inference
# ---------------------------------------------------------------------------

_PLACEHOLDER_RE = re.compile(
    r"^(?:unknown|unidentified|none|n/?a|\?+)"
    r"(?:\s+(?:composer|raga|ragam|talam|tala))?$",
    re.IGNORECASE,
)


def _line_shape(line: ClassifiedLine) -> tuple[str, ...] | None:
    """Role sequence of a line the classifier read confidently, else None.

    Confident means: at least three tokens, nothing skipped, and exactly one
    token left unrecognized (which must be the piece name).
    """
    if line.is_rtp or len(line.tokens) < 3 or "skip" in line.roles:
        return None
    if sum(1 for role in line.roles if role is None) != 1:
        return None
    return tuple("piece" if role is None else role for role in line.roles)


def infer_template(lines: list[ClassifiedLine]) -> tuple[str, ...] | None:
    """Most common role sequence among confidently parsed lines."""
    counts = Counter(shape for shape in map(_line_shape, lines) if shape)
    if not counts:
        return None
    template, support = counts.most_common(1)[0]
    return template if support >= MIN_TEMPLATE_SUPPORT else None


def apply_template(line: ClassifiedLine, template: tuple[str, ...] | None) -> ClassifiedLine:
    """Read a line's unrecognized tokens according to the description's template.

    Leaves the line untouched unless it is consistent with the template: no more
    tokens than the template has columns, and every token the classifier did
    recognize sits in the column the template gives that role.
    """
    if template is None or line.is_rtp or "skip" in line.roles:
        return line
    unknown = [i for i, role in enumerate(line.roles) if role is None]
    if not unknown or len(line.tokens) > len(template):
        return line
    for i, role in enumerate(line.roles):
        if role is not None and role != template[i]:
            return line

    assigned = {"raga": line.raga, "talam": line.talam, "composer": line.composer}
    piece = None
    for i in unknown:
        role = template[i]
        token = line.tokens[i]
        if role == "piece":
            piece = token
        elif assigned[role] is None:
            assigned[role] = None if _PLACEHOLDER_RE.match(token) else token

    if not piece:
        return line

    kind = line.kind or detect_kind(piece)
    return replace(
        line,
        piece_name=piece,
        raga=assigned["raga"],
        talam=assigned["talam"],
        composer=assigned["composer"],
        kind=kind,
        confidence=_score_confidence(
            piece, assigned["raga"], assigned["talam"], assigned["composer"],
            kind, line.is_rtp,
        ),
    )


# ---------------------------------------------------------------------------
# 5. Kinds
# ---------------------------------------------------------------------------

# Kinds offered by the contribute form's dropdown.
ALLOWED_KINDS = {
    "krithi", "varnam", "javali", "padam", "tillana", "viruttam", "slokam",
    "mangalam", "bhajan", "tiruppavai", "tiruppugazh", "rtp", "alapana",
}

_KIND_SYNONYMS = {
    "thiruppugazh": "tiruppugazh",
    "thiruppavai": "tiruppavai",
    "thillana": "tillana",
    "varna": "varnam",
    "sloka": "slokam",
    "viruttham": "viruttam",
    "kriti": "krithi",
    "kirtanam": "krithi",
}


def canonical_kind(kind: str | None) -> str | None:
    if not kind:
        return None
    norm = normalize_for_match(kind)
    norm = _KIND_SYNONYMS.get(norm, norm)
    if norm in ALLOWED_KINDS:
        return norm
    return detect_kind(kind) or kind.lower()


# ---------------------------------------------------------------------------
# 4. Alapana
# ---------------------------------------------------------------------------

_ALAPANA_RE = re.compile(r"\bala+panai?\b", re.IGNORECASE)  # alapana, alaapana


def _is_alapana(line: ClassifiedLine) -> bool:
    return bool(line.piece_name) and bool(_ALAPANA_RE.search(line.piece_name))


def _same_raga(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    norm_a, norm_b = normalize_for_match(a), normalize_for_match(b)
    if norm_a == norm_b:
        return True
    key_a, key_b = phonetic_key(norm_a), phonetic_key(norm_b)
    return len(key_a) >= PHONETIC_MIN_LEN and key_a == key_b


def merge_alapanas(lines: list[ClassifiedLine]) -> list[ClassifiedLine]:
    """Fold an alapana into the song right after it when both are in one raga.

    The song takes the alapana's timestamp, since the alapana is where that
    rendition starts. An alapana with no matching song after it stays as its
    own raga-only item.
    """
    lines = list(lines)
    merged: list[ClassifiedLine] = []
    for i, line in enumerate(lines):
        if _is_alapana(line) and line.timestamp_seconds is not None:
            following = lines[i + 1] if i + 1 < len(lines) else None
            if (
                following is not None
                and not _is_alapana(following)
                and _same_raga(line.raga, following.raga)
            ):
                lines[i + 1] = replace(following, timestamp_seconds=line.timestamp_seconds)
                continue
            merged.append(replace(line, piece_name="Alapana", kind="alapana"))
        else:
            merged.append(line)
    return merged


# ---------------------------------------------------------------------------
# 6. RTP sections
# ---------------------------------------------------------------------------

# Bare section names, matched on diacritic-free lowercase: ragam, tanam, pallavi.
_RTP_PART_RE = re.compile(r"^(?:ra+gam|th?a+nam|pall?avi)$")


def _is_rtp_part(line: ClassifiedLine) -> bool:
    return (
        not line.is_rtp
        and bool(line.piece_name)
        and bool(_RTP_PART_RE.match(normalize_for_match(line.piece_name)))
    )


def _raga_compatible(a: str | None, b: str | None) -> bool:
    return not a or not b or _same_raga(a, b)


def _combine_rtp(rtp: ClassifiedLine, part: ClassifiedLine | None = None) -> ClassifiedLine:
    """Make `rtp` an RTP item, taking any missing details from `part`."""
    raga = rtp.raga or (part.raga if part else None)
    talam = rtp.talam or (part.talam if part else None)
    # Only a composer the classifier recognized is kept: in a pallavi line the
    # trailing text is the pallavi lyric, not a composer.
    composer = rtp.composer or (part.composer if part else None)
    timestamp = rtp.timestamp_seconds
    if timestamp is None and part is not None:
        timestamp = part.timestamp_seconds
    return replace(
        rtp,
        piece_name="RTP",
        kind="rtp",
        is_rtp=True,
        raga=raga,
        talam=talam,
        composer=composer,
        timestamp_seconds=timestamp,
        has_thani=rtp.has_thani or bool(part and part.has_thani),
        confidence=_score_confidence("RTP", raga, talam, composer, "rtp", True),
    )


def merge_rtp_parts(lines: list[ClassifiedLine]) -> list[ClassifiedLine]:
    """Collapse consecutive Ragam / Tanam / Pallavi lines into one RTP item.

    The item starts at the first part's timestamp. A part that follows an
    existing RTP line in the same raga is folded into it as well.
    """
    merged: list[ClassifiedLine] = []
    for line in lines:
        if not _is_rtp_part(line):
            merged.append(line)
            continue
        previous = merged[-1] if merged else None
        if previous is not None and previous.is_rtp and _raga_compatible(previous.raga, line.raga):
            merged[-1] = _combine_rtp(previous, line)
        else:
            merged.append(_combine_rtp(line))
    return merged


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_description(
    text: str,
    catalog: CatalogLookups | None = None,
) -> list[ClassifiedLine]:
    """Classify setlist-like lines pasted from a video description or comment."""
    classified = []
    for raw in text.splitlines():
        line = clean_line(raw)
        if _is_setlist_line(line):
            classified.append(classify_tokens(tokenize_line(line), catalog))

    classified = merge_rtp_parts(classified)

    template = infer_template(classified)
    lines = [apply_template(line, template) for line in classified]
    lines = [replace(line, kind=canonical_kind(line.kind)) for line in lines]
    return merge_alapanas(lines)
