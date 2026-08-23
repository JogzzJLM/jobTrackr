import re
import os
from core.storage import CLOSED_KB_FILE, atomic_write_json, load_json_safe

DEFAULT_CLOSED_PHRASES = [
    "no longer accepting applications",
    "applications are now closed",
    "this job is no longer available",
    "position has been filled",
    "this posting has expired",
    "this position is closed",
    "role is now closed",
    "vacancy is closed",
    "job is not currently open",
    "we are no longer accepting",
    "application deadline has passed",
    "this requisition has been closed",
    "sorry this position has been filled",
    "the page you are looking for does not exist",
    "job expired",
    "this job posting is no longer active",
    "this opening is closed",
    "is no longer taking applications"
]

def load_closed_keywords_kb():
    loaded = load_json_safe(CLOSED_KB_FILE, None)
    if loaded and isinstance(loaded, list) and len(loaded) > 0:
        return loaded
    atomic_write_json(CLOSED_KB_FILE, DEFAULT_CLOSED_PHRASES)
    return list(DEFAULT_CLOSED_PHRASES)

def save_closed_keywords_kb(phrases_list):
    clean_list = []
    seen = set()
    for p in phrases_list:
        if p and isinstance(p, str):
            clean = p.strip().lower()
            if clean and clean not in seen:
                seen.add(clean)
                clean_list.append(clean)
    atomic_write_json(CLOSED_KB_FILE, clean_list)

def extract_generic_closure_phrases(text):
    """Extracts short candidate closure phrases from text."""
    if not text:
        return []
    text_clean = text.lower()
    matches = []
    patterns = [
        r'([a-z\s]{0,20}no longer accepting[a-z\s]{0,20})',
        r'([a-z\s]{0,20}applications? (?:are|is) closed[a-z\s]{0,20})',
        r'([a-z\s]{0,20}position has been filled[a-z\s]{0,20})',
        r'([a-z\s]{0,20}posting has expired[a-z\s]{0,20})'
    ]
    for pat in patterns:
        for m in re.finditer(pat, text_clean):
            phrase = m.group(1).strip()
            if len(phrase.split()) >= 3 and len(phrase) <= 60:
                matches.append(phrase)
    return matches
