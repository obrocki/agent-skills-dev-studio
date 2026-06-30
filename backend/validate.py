"""Best-practices validation for Agent Skill drafts.

Scores a skill's name, description, and Markdown body against Agent Skills
authoring guidelines and returns a 0-100 score with per-check results so the
UI can render a red-to-green rating bar.
"""
import re

from backend import best_practices


def _person_hits(text: str) -> int:
    """Count first/second person pronouns that hurt skill discovery."""
    return len(best_practices.PERSON_RE.findall(text or ""))


def _frontmatter_keys(content: str) -> list[str] | None:
    """Return top-level YAML front-matter keys, or None when no block is present."""
    match = best_practices.FRONTMATTER_RE.match(content or "")
    if not match:
        return None
    keys: list[str] = []
    for line in match.group(1).splitlines():
        if not line or line[0] in " \t-#":
            continue  # skip nested mappings, list items, comments, and blanks
        key_match = best_practices.FM_KEY_RE.match(line)
        if key_match:
            keys.append(key_match.group(1))
    return keys


def _estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 characters per token) for length budgeting."""
    return (len(text) + 3) // 4


def _unresolved_references(content: str) -> list[str]:
    """Return local Markdown link targets that do not resolve under ``resource/``."""
    bad: list[str] = []
    for target in best_practices.LINK_RE.findall(content or ""):
        ref = target.strip().split("#", 1)[0]
        if not ref:
            continue
        low = ref.lower()
        if low.startswith(("http://", "https://", "mailto:", "//", "data:", "tel:")):
            continue  # external links are out of scope
        norm = ref.lstrip("./")
        if not (norm.startswith("resource/") or norm.startswith("resources/")):
            bad.append(ref)
    return bad


def validate_skill(name: str, description: str, content: str) -> dict:
    """Score a skill draft against authoring best practices.

    Args:
        name: The skill name.
        description: The skill description.
        content: The Markdown body.

    Returns:
        dict: ``score`` (0-100), ``rating``, ``color`` (HSL red->green), and a
        ``checks`` list of ``{id, label, status, detail}`` entries.
    """
    name = (name or "").strip()
    description = (description or "").strip()
    content = content or ""
    checks: list[dict] = []

    def add(check_id: str, label: str, status: str, detail: str = "") -> None:
        checks.append({"id": check_id, "label": label, "status": status, "detail": detail})

    # --- Metadata: name ---
    if name:
        add("name_present", "Name is set", "pass")
    else:
        add("name_present", "Name is set", "fail", "Add a skill name.")

    if not name:
        add("name_format", "Name is kebab-case", "fail", "Name is empty.")
    elif best_practices.NAME_RE.match(name):
        add("name_format", "Name is kebab-case", "pass")
    else:
        add(
            "name_format",
            "Name is kebab-case",
            "warn",
            "Use lowercase letters, digits and single hyphens (e.g. pdf-extractor).",
        )

    if not name:
        add("name_length", f"Name is within {best_practices.MAX_NAME} characters", "fail", "Name is empty.")
    elif len(name) <= best_practices.MAX_NAME:
        add("name_length", f"Name is within {best_practices.MAX_NAME} characters", "pass")
    else:
        add(
            "name_length",
            f"Name is within {best_practices.MAX_NAME} characters",
            "warn",
            f"Name is {len(name)} characters; keep it to {best_practices.MAX_NAME} or fewer.",
        )

    # --- Metadata: description ---
    if description:
        add("desc_present", "Description is set", "pass")
    else:
        add("desc_present", "Description is set", "fail", "Add a description.")

    if not description:
        add("desc_detail", "Description has enough detail", "fail", "Description is empty.")
    elif len(description) < 30:
        add(
            "desc_detail",
            "Description has enough detail",
            "warn",
            "Say what the skill does AND when to use it, with trigger keywords.",
        )
    else:
        add("desc_detail", "Description has enough detail", "pass")

    if len(description) <= best_practices.MAX_DESC:
        add("desc_max_length", f"Description is within {best_practices.MAX_DESC} characters", "pass")
    else:
        add(
            "desc_max_length",
            f"Description is within {best_practices.MAX_DESC} characters",
            "warn",
            f"Description is {len(description)} characters; keep it to {best_practices.MAX_DESC} or fewer.",
        )

    if description and re.search(r"\bwhen\b", description, re.IGNORECASE):
        add("desc_trigger", "Description states when to use it", "pass")
    elif description:
        add(
            "desc_trigger",
            "Description states when to use it",
            "warn",
            "Add a trigger such as 'Use when ...' so the agent knows when to apply it.",
        )
    else:
        add("desc_trigger", "Description states when to use it", "fail", "Description is empty.")

    if description and _person_hits(description) == 0:
        add("desc_person", "Description is in third person", "pass")
    elif description:
        add(
            "desc_person",
            "Description is in third person",
            "warn",
            "Write in third person ('Extracts ...'), not 'I can help' or 'you'.",
        )
    else:
        add("desc_person", "Description is in third person", "fail", "Description is empty.")

    # --- Front matter: only supported keys (name, description) ---
    fm_keys = _frontmatter_keys(content)
    if fm_keys is None:
        add("frontmatter_fields", "Front matter uses only supported fields", "pass")
    else:
        extra = sorted({k for k in fm_keys if k not in best_practices.ALLOWED_FM_KEYS})
        if extra:
            add(
                "frontmatter_fields",
                "Front matter uses only supported fields",
                "warn",
                "Remove unsupported front-matter fields ("
                + ", ".join(extra)
                + "); only name and description are supported.",
            )
        else:
            add("frontmatter_fields", "Front matter uses only supported fields", "pass")

    # --- Body ---
    body_text = re.sub(r"(?m)^\s{0,3}#{1,6}\s.*$", "", content).strip()
    substantial = len(body_text) >= best_practices.MIN_BODY

    if substantial:
        add("body_present", "Body has enough content", "pass")
    elif body_text:
        add(
            "body_present",
            "Body has enough content",
            "fail",
            "Body is a stub; add real instructions, steps, and examples.",
        )
    elif content.strip():
        add(
            "body_present",
            "Body has enough content",
            "fail",
            "Add instructions under your headings; a heading alone is not enough.",
        )
    else:
        add("body_present", "Body has enough content", "fail", "Add Markdown instructions.")

    if re.search(r"^#{1,6}\s", content, re.MULTILINE):
        add("body_headings", "Body uses headings", "pass")
    elif content.strip():
        add("body_headings", "Body uses headings", "warn", "Structure the body with Markdown headings (##).")
    else:
        add("body_headings", "Body uses headings", "fail", "Body is empty.")

    if not best_practices.TABLE_ROW_RE.search(content) or best_practices.TABLE_SEP_RE.search(content):
        add("body_tables", "Tables are well-formed", "pass")
    else:
        add(
            "body_tables",
            "Tables are well-formed",
            "warn",
            "A Markdown table needs a header separator row (e.g. | --- | --- |).",
        )

    lines = content.count("\n") + 1 if content.strip() else 0
    if not substantial:
        add(
            "body_length",
            "Body is a useful length",
            "fail",
            "Body is too short to be useful; add steps and examples.",
        )
    elif lines > best_practices.MAX_LINES:
        add(
            "body_length",
            "Body is a useful length",
            "warn",
            f"Body is {lines} lines; keep it under {best_practices.MAX_LINES} and move detail to references.",
        )
    else:
        add("body_length", "Body is a useful length", "pass")

    tokens = _estimate_tokens(content)
    if not substantial:
        add(
            "body_tokens",
            "Body is a useful size",
            "fail",
            "Body is too short; add detail.",
        )
    elif tokens > best_practices.MAX_TOKENS:
        add(
            "body_tokens",
            "Body is a useful size",
            "warn",
            f"Body is ~{tokens} tokens; trim it under ~{best_practices.MAX_TOKENS} or move detail to references.",
        )
    else:
        add("body_tokens", "Body is a useful size", "pass")

    bad_refs = _unresolved_references(content)
    if not bad_refs:
        add("references", "References resolve under resource/", "pass")
    else:
        add(
            "references",
            "References resolve under resource/",
            "warn",
            "Point local links at files under resource/ (check: "
            + ", ".join(sorted(set(bad_refs))[:5])
            + ").",
        )

    status_value = {"pass": 1.0, "warn": 0.5, "fail": 0.0}
    total_weight = sum(best_practices.WEIGHTS.get(c["id"], 1) for c in checks)
    earned = sum(status_value[c["status"]] * best_practices.WEIGHTS.get(c["id"], 1) for c in checks)
    score = round(100 * earned / total_weight) if total_weight else 0

    if score >= best_practices.RATING_EXCELLENT:
        rating = "Excellent"
    elif score >= best_practices.RATING_GOOD:
        rating = "Good"
    elif score >= best_practices.RATING_FAIR:
        rating = "Fair"
    else:
        rating = "Poor"

    hue = round(120 * score / 100)  # 0 = red, 120 = green
    color = f"hsl({hue}, 70%, 45%)"

    return {"score": score, "rating": rating, "color": color, "checks": checks}
