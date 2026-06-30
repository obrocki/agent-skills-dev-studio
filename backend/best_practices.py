"""Agent Skills authoring best-practice rule definitions.

Single source of truth for the compiled regexes, limits, weights, and
rating-band thresholds used to score a skill draft. The scoring engine in
``validate.py`` imports these definitions and applies them; keeping the rules
here lets the authoring guidelines evolve without touching the engine.
"""
import re

# Skill names must be lowercase kebab-case (e.g. pdf-extractor).
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
# Descriptions should be third person, so first/second person pronouns are flagged.
PERSON_RE = re.compile(r"\b(I|I'm|I'll|we|we're|you|you're|your|my|me|us)\b", re.IGNORECASE)
# YAML front matter is the leading `--- ... ---` block.
FRONTMATTER_RE = re.compile(r"^\ufeff?---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", re.DOTALL)
# Top-level front-matter keys (used to reject unsupported fields).
FM_KEY_RE = re.compile(r"^([A-Za-z0-9_-]+)[ \t]*:")
# Markdown link targets, for checking local references resolve under resource/.
LINK_RE = re.compile(r"\[[^\]]*\]\(\s*<?([^)\s>]+)")
# A Markdown table row.
TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$", re.MULTILINE)
# A Markdown table header-separator row (e.g. | --- | --- |).
TABLE_SEP_RE = re.compile(r"^[ \t]*\|?[ \t:|-]*-[ \t:|-]*$", re.MULTILINE)

# Front matter supports only these two fields.
ALLOWED_FM_KEYS = {"name", "description"}
# Name stays short enough to read at a glance.
MAX_NAME = 64
# Description fits a single concise paragraph.
MAX_DESC = 1024
# Body stays maintainable; longer detail belongs in references.
MAX_LINES = 500
# Body stays within a sensible token budget for progressive disclosure.
MAX_TOKENS = 5000
# Minimum characters of non-heading body content to count as a real body.
MIN_BODY = 60

# The body is the actual skill, so its substance checks outweigh
# metadata and lint checks.
WEIGHTS = {"body_present": 3, "body_length": 2, "body_tokens": 2}

# Rating bands: a score at or above each threshold earns the named rating.
RATING_EXCELLENT = 85
RATING_GOOD = 65
RATING_FAIR = 40
