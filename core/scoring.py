import re
from core.storage import get_active_profile, get_all_profiles

def calculate_skill_match_score(title, company="", location="", description="", profile=None):
    """
    Calculates a dynamic 0-100 skill & role match score against a profile's keywords.
    If no profile is supplied, uses the active profile.
    """
    if profile is None:
        profile = get_active_profile()

    if not profile:
        return 50

    role_keywords = profile.get("role_keywords", [])
    level_keywords = profile.get("level_keywords", [])
    skills = profile.get("skills", [])
    target_locations = profile.get("target_locations", [])
    exclude_keywords = profile.get("exclude_keywords", [])
    exclude_locations = profile.get("exclude_locations", [])

    text = f"{title} {company} {location} {description}".lower()
    title_lower = title.lower()

    # Check exclusions first
    for ex in exclude_keywords:
        if ex.lower() in title_lower or ex.lower() in text:
            return 0

    for ex_loc in exclude_locations:
        if ex_loc.lower() in location.lower() or ex_loc.lower() in text:
            return 0

    score = 20  # Base score for valid open vacancy

    # 1. Role Keywords Match (up to 40 pts)
    matched_roles = [kw for kw in role_keywords if kw.lower() in title_lower or kw.lower() in text]
    if matched_roles:
        score += min(40, len(matched_roles) * 20)

    # 2. Level Keywords Match (up to 15 pts)
    matched_levels = [lvl for lvl in level_keywords if lvl.lower() in title_lower or lvl.lower() in text]
    if matched_levels:
        score += min(15, len(matched_levels) * 10)
    elif not level_keywords:
        score += 10

    # 3. Skills Match (up to 15 pts)
    matched_skills = [sk for sk in skills if re.search(r'\b' + re.escape(sk.lower()) + r'\b', text)]
    if matched_skills:
        score += min(15, len(matched_skills) * 5)

    # 4. Target Location Match (up to 10 pts)
    matched_locations = [loc for loc in target_locations if loc.lower() in location.lower() or loc.lower() in text]
    if matched_locations:
        score += 10
    elif any(k in location.lower() for k in ["uk", "remote", "london", "hybrid", "united kingdom"]):
        score += 8

    return min(100, max(0, score))

def evaluate_job_for_all_profiles(title, company="", location="", description=""):
    """
    Evaluates a job against all configured profiles and returns a map of {profile_id: score}.
    """
    profiles = get_all_profiles()
    scores = {}
    for p in profiles:
        p_id = p.get("id")
        scores[p_id] = calculate_skill_match_score(title, company, location, description, profile=p)
    return scores

def is_job_relevant_for_profile(title, company="", location="", profile=None):
    """
    Determines if a job meets the relevance criteria for a given profile.
    """
    if profile is None:
        profile = get_active_profile()

    if not profile:
        return True

    text = f"{title} {company} {location}".lower()
    title_lower = title.lower()

    # Check exclusions
    for ex in profile.get("exclude_keywords", []):
        if ex.lower() in title_lower:
            return False

    for ex_loc in profile.get("exclude_locations", []):
        if ex_loc.lower() in location.lower():
            return False

    # Check role keyword presence
    role_kws = profile.get("role_keywords", [])
    if role_kws:
        has_role = any(kw.lower() in text for kw in role_kws)
        if not has_role:
            return False

    return True
