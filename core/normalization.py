import re

COMPANY_ALIASES = {
    "mwinternshipprogram": "marshallwace",
    "marshallwace": "marshallwace",
    "mw": "marshallwace",
    "squarepointcapital": "squarepoint",
    "squarepoint": "squarepoint",
    "hudsonrivertrading": "hrt",
    "hrt": "hrt",
    "twosigma": "twosigma",
    "twosigmaca": "twosigma",
    "jumptrading": "jumptrading",
    "janestreet": "janestreet",
    "optiver": "optiver",
    "canonical": "canonical",
    "canonicaljobs": "canonical",
    "starlingbank": "starling",
    "starling": "starling",
    "beamng": "beamng",
    "wayve": "wayve",
    "palantir": "palantir",
    "samsara": "samsara",
    "cohere": "cohere",
    "notion": "notion",
    "ramp": "ramp",
    "scaleai": "scaleai",
    "elevenlabs": "elevenlabs",
    "perplexity": "perplexity",
    "replicate": "replicate",
    "linear": "linear",
    "cursor": "cursor",
    "resend": "resend",
    "retool": "retool",
    "postman": "postman",
    "huggingface": "huggingface",
    "deliveroo": "deliveroo",
    "cloudflare": "cloudflare",
    "snyk": "snyk",
    "monzo": "monzo",
    "spotify": "spotify",
    "revolut": "revolut",
    "checkout": "checkout",
    "visa": "visa",
    "ubisoft": "ubisoft",
    "zalando": "zalando",
    "bosch": "bosch"
}

COMPANY_DISPLAY_NAMES = {
    "marshallwace": "Marshall Wace",
    "squarepoint": "Squarepoint Capital",
    "squarepointcapital": "Squarepoint Capital",
    "hrt": "Hudson River Trading",
    "hudsonrivertrading": "Hudson River Trading",
    "jumptrading": "Jump Trading",
    "janestreet": "Jane Street",
    "optiver": "Optiver",
    "twosigma": "Two Sigma",
    "canonical": "Canonical",
    "starling": "Starling Bank",
    "starlingbank": "Starling Bank",
    "palantir": "Palantir",
    "cohere": "Cohere",
    "samsara": "Samsara",
    "ramp": "Ramp",
    "notion": "Notion",
    "beamng": "BeamNG",
    "wayve": "Wayve",
    "verkada": "Verkada",
    "scaleai": "Scale AI",
    "elevenlabs": "ElevenLabs",
    "perplexity": "Perplexity AI",
    "replicate": "Replicate",
    "linear": "Linear",
    "cursor": "Cursor",
    "resend": "Resend",
    "retool": "Retool",
    "postman": "Postman",
    "huggingface": "Hugging Face",
    "deliveroo": "Deliveroo",
    "cloudflare": "Cloudflare",
    "snyk": "Snyk",
    "monzo": "Monzo",
    "spotify": "Spotify",
    "revolut": "Revolut",
    "checkout": "Checkout.com",
    "visa": "Visa",
    "ubisoft": "Ubisoft",
    "zalando": "Zalando",
    "bosch": "Bosch",
    "ikea": "IKEA",
    "vodafone": "Vodafone",
    "lvmh": "LVMH",
    "skyscanner": "Skyscanner"
}

def clean_company_display_name(name):
    if not name:
        return "Unknown"
    cleaned = str(name).strip()

    norm = re.sub(r'[^a-z0-9]', '', cleaned.lower())

    if norm in COMPANY_DISPLAY_NAMES:
        return COMPANY_DISPLAY_NAMES[norm]

    for key, display_val in COMPANY_DISPLAY_NAMES.items():
        if key == norm or key in norm:
            return display_val

    for suffix in ["internshipprogram", "careers", "jobs", "program", "limited", "ltd", "inc", "plc", "llc", "group"]:
        if cleaned.lower().endswith(suffix) and len(cleaned) > len(suffix) + 2:
            cleaned = cleaned[:-len(suffix)].strip()

    cleaned = re.sub(r'([a-z])([A-Z])', r'\1 \2', cleaned)
    cleaned = cleaned.replace('-', ' ').replace('_', ' ')
    cleaned = ' '.join(word.capitalize() for word in cleaned.split())
    return cleaned if cleaned else name

def normalize_company(name):
    if not name:
        return ""
    cleaned = str(name).lower().strip()
    cleaned = re.sub(r'[^a-z0-9]', '', cleaned)
    for suffix in ["ltd", "inc", "plc", "llc", "capital", "technologies", "technology", "group", "uk", "europe", "limited", "careers", "jobs", "program", "internshipprogram"]:
        if cleaned.endswith(suffix) and len(cleaned) > len(suffix) + 2:
            cleaned = cleaned[:-len(suffix)]

    if cleaned in COMPANY_ALIASES:
        return COMPANY_ALIASES[cleaned]

    for alias, canonical in COMPANY_ALIASES.items():
        if alias in cleaned or cleaned in alias:
            return canonical

    return cleaned

ROLE_SYNONYMS = {
    "developer": "engineer",
    "dev": "engineer",
    "programmer": "engineer",
    "mgr": "manager",
    "mgmt": "management",
    "prog": "program",
    "spec": "specialist"
}

def normalize_role(title):
    if not title:
        return ""
    cleaned = str(title).lower().strip()
    cleaned = re.sub(r'-\s*(london|uk|remote|hybrid|emea|uk&i|global)', '', cleaned)
    cleaned = re.sub(r'[^a-z0-9\s]', ' ', cleaned)
    stop_words = {"london", "uk", "remote", "hybrid", "year", "in", "industry", "emea", "the", "and", "or", "of", "for", "to", "at"}
    words = []
    for w in cleaned.split():
        if w not in stop_words:
            syn = ROLE_SYNONYMS.get(w, w)
            words.append(syn)
    return " ".join(words)

def stem_word(w):
    w = str(w).lower()
    w = ROLE_SYNONYMS.get(w, w)
    for suffix in ["ing", "ships", "ship", "ies", "s", "ed"]:
        if w.endswith(suffix) and len(w) > len(suffix) + 3:
            return w[:-len(suffix)]
    return w

def fuzzy_roles_match(title1, title2, threshold=0.50):
    """
    Computes a token-set Jaccard similarity ratio between two role titles after word stemming & synonym resolution.
    Returns True if titles represent the same underlying role.
    """
    if not title1 or not title2:
        return False
    norm1 = normalize_role(title1)
    norm2 = normalize_role(title2)
    if norm1 == norm2:
        return True
    words1 = set(stem_word(w) for w in norm1.split())
    words2 = set(stem_word(w) for w in norm2.split())
    if not words1 or not words2:
        return False
    intersection = words1 & words2
    union = words1 | words2
    jaccard = len(intersection) / len(union) if union else 0.0
    return jaccard >= threshold

def normalize_url(url):
    """Strips query strings, tracking parameters, hashes, and trailing slashes for exact URL matching."""
    if not url or not isinstance(url, str):
        return ""
    cleaned = re.sub(r'^https?://(www\.)?', '', url.strip().lower())
    cleaned = cleaned.split('?')[0].split('#')[0].rstrip('/')
    return cleaned

def extract_ats_post_id(url):
    """Extracts unique ATS job post IDs (Greenhouse, Lever, Ashby, SmartRecruiters, Workday)."""
    if not url or not isinstance(url, str):
        return None
    gh_match = re.search(r'greenhouse\.io/[^/]+/jobs/(\d+)', url, re.IGNORECASE)
    if gh_match:
        return f"gh_{gh_match.group(1)}"
    lev_match = re.search(r'lever\.co/[^/]+/([a-f0-9\-]{20,})', url, re.IGNORECASE)
    if lev_match:
        return f"lev_{lev_match.group(1)}"
    ash_match = re.search(r'ashbyhq\.com/[^/]+/([a-f0-9\-]{20,})', url, re.IGNORECASE)
    if ash_match:
        return f"ash_{ash_match.group(1)}"
    sr_match = re.search(r'smartrecruiters\.com/[^/]+/(\d+)', url, re.IGNORECASE) or re.search(r'smartrecruiters\.com/[^/]+/([a-f0-9\-]{10,})', url, re.IGNORECASE)
    if sr_match:
        return f"sr_{sr_match.group(1)}"
    wd_match = re.search(r'myworkdayjobs\.com/[^/]+/[^/]+/job/[^/]+/([a-zA-Z0-9_\-]+)', url, re.IGNORECASE)
    if wd_match:
        return f"wd_{wd_match.group(1)}"
    return None

def deduplicate_job_list(job_list):
    """
    Multi-Layered Smart Job Deduplication:
    1. ATS Post ID Match (e.g. gh_5162206007 == gh_5162206007)
    2. Normalized URL Match (e.g. job-boards.greenhouse.io/deliveroo/jobs/5162206007)
    3. Company Name + Fuzzy Role Title Match (e.g. Deliveroo + Senior Backend Engineer)
    Collapses duplicates into single master cards with merged sources list.
    """
    if not job_list:
        return []

    deduped = []
    for item in job_list:
        if not item or not isinstance(item, dict):
            continue

        comp = item.get("company", "")
        title = item.get("title", "")
        link = item.get("link", "")

        norm_c = normalize_company(comp)
        norm_t = normalize_role(title)
        norm_u = normalize_url(link)
        ats_id = extract_ats_post_id(link)

        matched = False
        for existing in deduped:
            e_link = existing.get("link", "")
            e_comp = existing.get("company", "")
            e_title = existing.get("title", "")

            e_norm_c = normalize_company(e_comp)
            e_norm_t = normalize_role(e_title)
            e_norm_u = normalize_url(e_link)
            e_ats_id = extract_ats_post_id(e_link)

            is_match = False
            if ats_id and e_ats_id and ats_id == e_ats_id:
                is_match = True
            elif norm_u and e_norm_u and norm_u == e_norm_u:
                is_match = True
            elif norm_c and e_norm_c == norm_c and (norm_t == e_norm_t or fuzzy_roles_match(title, e_title)):
                is_match = True

            if is_match:
                matched = True
                if "sources" not in existing:
                    existing["sources"] = [existing.get("source", "Discovered API")]
                src = item.get("source", "Discovered API")
                if isinstance(item.get("sources"), list):
                    for s in item.get("sources"):
                        if s not in existing["sources"]:
                            existing["sources"].append(s)
                elif src not in existing["sources"]:
                    existing["sources"].append(src)

                # Prefer official direct ATS link over secondary aggregators
                if any(ats in link.lower() for ats in ["greenhouse", "lever", "ashby", "smartrecruiters", "workday"]):
                    existing["link"] = link
                    existing["source_url"] = item.get("source_url") or link
                    if comp and len(comp) > 2:
                        existing["company"] = clean_company_display_name(comp)
                    if title and len(title) > len(existing.get("title", "")):
                        existing["title"] = title
                break

        if not matched:
            item_copy = dict(item)
            item_copy["company"] = clean_company_display_name(comp)
            if "sources" not in item_copy:
                item_copy["sources"] = [item_copy.get("source", "Discovered API")]
            deduped.append(item_copy)

    return deduped
