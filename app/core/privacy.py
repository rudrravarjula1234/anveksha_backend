"""PHI / PII protection helpers.

Three product rules enforced at the service layer (the wire shapes stay
identical — only the VALUES are masked, so no client change is needed):

1. Interviewers never see candidate identity. Queue rows, pending
   reports and report details present the candidate's dossier ID
   (ANV-XXXX), never their name.
2. Companies see candidates by alias until they pay to unlock.
3. Candidates never see which verifier they're paired with at booking
   time (post-session attribution on published reports is fine).

Seeded personas map to their canonical dossier ids; unknown names get a
stable hash-derived id so the mapping is deterministic across calls.
"""

import hashlib

# Canonical dossier ids for seeded personas (mirrors the prototype's
# privacy-aware screens).
_KNOWN_DOSSIERS: dict[str, str] = {
    "Aarav Rao": "ANV-2481",
    "Priya Nair": "ANV-3902",
    "Omar Haddad": "ANV-7714",
    "Li Wei": "ANV-5509",
    "Maya Iyer": "ANV-7104",
    "Dr. Suresh Mehra": "ANV-8801",
    "Rohit Verma": "ANV-4419",
}

# Stable aliases for the company-facing pool (mirrors the prototype's
# LockedCandidate cards).
CANDIDATE_ALIASES: dict[str, str] = {
    "cand_001": "Candidate A",
    "cand_002": "Candidate B",
    "cand_003": "Candidate C",
    "cand_004": "Candidate D",
}

MASKED_VERIFIER = "Anveksha Verifier"


def candidate_anon_id(name: str) -> str:
    """Deterministic candidate reference for interviewer-facing surfaces."""
    if name in _KNOWN_DOSSIERS:
        return _KNOWN_DOSSIERS[name]
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:4].upper()
    return f"ANV-{digest}"


def candidate_alias(candidate_id: str) -> str:
    """Company-facing alias for a locked candidate.

    Derived from the candidate id alone, so a candidate keeps the same
    alias on every page, under every filter and in chat (a position-based
    letter changed whenever the list did, and repeated after 26 rows).
    """
    if candidate_id in CANDIDATE_ALIASES:
        return CANDIDATE_ALIASES[candidate_id]
    digest = hashlib.sha256(candidate_id.encode("utf-8")).hexdigest()[:4].upper()
    return f"Candidate {digest}"


def mask_initials() -> str:
    """Initial-avatar replacement for anonymised people."""
    return "•"
