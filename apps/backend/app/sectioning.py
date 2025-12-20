import re
from typing import List, Tuple

def _norm(line: str) -> str:
    line = (line or "").strip()
    line = re.sub(r"\s+", " ", line)
    return line

# Universal heading patterns (doc-agnostic)
UNIVERSAL_PATTERNS: List[Tuple[str, str]] = [
    ("overview", r"^(abstract|summary|overview|about|background|purpose|introduction)\b.*$"),
    ("how_to", r"^(how to|procedure|procedures|steps|setup|installation|configuration|usage|examples|workflow)\b.*$"),
    ("reference", r"^(reference|specification|specifications|api|schema|fields|parameters|commands|glossary|definitions)\b.*$"),
    ("policies", r"^(policy|policies|rules|requirements|compliance|guidelines|standards)\b.*$"),
    ("troubleshooting", r"^(troubleshooting|faq|common issues|errors|known issues|fixes)\b.*$"),
    ("impact", r"^(limitations|considerations|security|privacy|ethics|risk|safety|responsible)\b.*$"),
]

# Extra patterns that often appear in research papers (optional but harmless)
PAPER_EXTRA_PATTERNS: List[Tuple[str, str]] = [
    ("overview", r"^(1\.\s*)?introduction\b.*$"),
    ("how_to", r"^(methods|materials and methods|methodology|experimental setup)\b.*$"),
    ("reference", r"^(results|experiments|evaluation|tables?|figures?)\b.*$"),
    ("impact", r"^(broader impact|societal impact)\b.*$"),
    ("overview", r"^(discussion|conclusion|conclusions)\b.*$"),  # often summary-ish
]

def detect_section_from_page_text(
    page_text: str,
    current_section: str = "other",
    enable_paper_patterns: bool = True,
) -> str:
    """
    Detect section based on header-like lines on the page.
    Keeps the previous section if nothing matches (sticky section).
    """
    if not page_text:
        return current_section

    patterns = UNIVERSAL_PATTERNS + (PAPER_EXTRA_PATTERNS if enable_paper_patterns else [])

    # Candidate header lines: short-ish lines
    lines = [_norm(l) for l in page_text.split("\n")]
    candidates = [l for l in lines if 0 < len(l) <= 80]

    for line in candidates:
        for section, pat in patterns:
            if re.match(pat, line, flags=re.IGNORECASE):
                return section

    return current_section
