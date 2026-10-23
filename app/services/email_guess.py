"""Best-effort email discovery for cold outreach.

Two parts:
  - extract_people(): pull likely owner/founder names out of site text.
  - guess_emails(): generate common email patterns from a first/last name + domain.

Guessed addresses MUST be verified (MillionVerifier) before sending —
sending to a guessed address that bounces will kill your domain reputation.
"""
import re

# role keywords that usually precede/follow a person's name on an "about"/"team" page
_ROLE = (
    r"(?i:founder|co-founder|cofounder|ceo|owner|president|director|principal|"
    r"managing partner|partner|manager)"
)

# "Founder & CEO John Smith", "Owner: Jane Doe", "John Smith, Founder"
_PATTERNS = [
    re.compile(
        r"(?P<role>" + _ROLE + r")[\s,&:]*\b(?P<name>[A-Z][a-z]+(?:\s+[A-Z][a-zA-Z]*){1,2})"
    ),
    re.compile(
        r"(?P<name>[A-Z][a-z]+(?:\s+[A-Z][a-zA-Z]*){1,2})[\s,]+(?P<role>" + _ROLE + r")"
    ),
]

_STOPWORDS = {"the", "and", "our", "for", "a", "an", "of", "is", "was"}


def extract_people(text: str) -> list[dict]:
    """Return [{'name': 'John Smith', 'role': 'founder'}] in first-seen order."""
    if not text:
        return []
    people: list[dict] = []
    seen: set[str] = set()
    for pat in _PATTERNS:
        for m in pat.finditer(text):
            name = " ".join(m.group("name").split()).title()
            role = m.group("role").lower()
            first = name.split(" ")[0].lower()
            if first in _STOPWORDS or len(name) < 5:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            people.append({"name": name, "role": role})
    return people[:10]


def _split(name: str) -> tuple[str, str]:
    parts = name.split()
    if not parts:
        return "", ""
    return parts[0].lower(), (parts[-1].lower() if len(parts) > 1 else "")


def guess_emails(domain: str, first: str, last: str) -> list[str]:
    """Generate the common first/last patterns for a given name + domain."""
    if not domain or not first:
        return []
    domain = domain.strip().lower().removeprefix("www.")
    f = first
    l = last
    fi = f[0]
    li = l[0] if l else ""
    patterns = [
        f"{f}@{domain}",
        f"{f}.{l}@{domain}",
        f"{f}{l}@{domain}",
        f"{fi}{l}@{domain}",
        f"{f}_{l}@{domain}",
        f"{f}{li}@{domain}",
    ]
    if l:
        patterns.append(f"{l}@{domain}")
    # dedupe, preserve order
    return list(dict.fromkeys(p for p in patterns if "@" in p))
