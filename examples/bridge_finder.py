"""
Bridge Finder - Find potential connections for end-of-line ancestors
Crawls tree, finds candidates, fetches full data + relatives, scores comprehensively.

Improvements:
- Fuzzy string matching via rapidfuzz (handles "Jon" vs "John", "Smyth" vs "Smith")
- Robust date parsing (handles "Abt 1850", "bef 1900", "1850/51")
- Base score threshold before fetching relatives (avoids N+1 API problem)
- External config file for weights and locations
"""

import os
import sys
import time
import re
import json
from pathlib import Path
from datetime import datetime

sys.path.append(str(Path(__file__).parent.parent / "src"))

from pywikitree.client import WikiTreeClient
from dotenv import load_dotenv
from rapidfuzz import fuzz

# ============================================================================
# LOAD CONFIGURATION
# ============================================================================
CONFIG_FILE = Path(__file__).parent / "bridge_finder_config.json"

def load_config():
    """Load configuration from JSON file, with fallback defaults."""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    # Fallback defaults if config missing
    return {
        "thresholds": {
            "min_match_threshold": 50,
            "base_score_threshold": 20,
            "confirmed_threshold": 70,
            "max_crawl_people": 1000,
            "api_delay": 1.5
        },
        "fuzzy_matching": {
            "exact_threshold": 90,
            "partial_threshold": 70
        },
        "weights": {},
        "locations": {}
    }

CONFIG = load_config()
WEIGHTS = CONFIG.get("weights", {})
THRESHOLDS = CONFIG.get("thresholds", {})
FUZZY = CONFIG.get("fuzzy_matching", {})
LOCATIONS = CONFIG.get("locations", {})

# Extract thresholds
MIN_MATCH_THRESHOLD = THRESHOLDS.get("min_match_threshold", 50)
BASE_SCORE_THRESHOLD = THRESHOLDS.get("base_score_threshold", 20)
CONFIRMED_THRESHOLD = THRESHOLDS.get("confirmed_threshold", 70)
MAX_CRAWL_PEOPLE = THRESHOLDS.get("max_crawl_people", 1000)
API_DELAY = THRESHOLDS.get("api_delay", 1.5)

# Fuzzy thresholds
FUZZY_EXACT = FUZZY.get("exact_threshold", 90)
FUZZY_PARTIAL = FUZZY.get("partial_threshold", 70)

# Location data
US_STATES = set(LOCATIONS.get("us_states", []))
UK_COUNTIES = set(LOCATIONS.get("uk_counties", []))
COUNTRIES = LOCATIONS.get("countries", {})
REGIONS = LOCATIONS.get("regions", {})


def parse_date(date_str):
    """
    Parse date string into (year, month, day) tuple.
    Handles messy genealogy formats:
    - ISO: 2023-01-15
    - Partial: 2023-00-00, 1850-01-00
    - Approximate: "Abt 1850", "About 1850", "~1850", "c. 1850", "circa 1850"
    - Before/After: "Bef 1900", "Before 1900", "Aft 1800", "After 1800"
    - Ranges: "1850/51", "1850-1851", "1850 or 1851"
    - Text dates: "15 Jan 1850", "January 15, 1850"
    """
    if not date_str:
        return None, None, None
    
    date_str = str(date_str).strip()
    
    # Handle "0000-00-00" or empty
    if date_str == "0000-00-00" or date_str == "0":
        return None, None, None
    
    year, month, day = None, None, None
    
    # Try ISO format first (most common in WikiTree)
    iso_match = re.match(r'^(\d{4})-(\d{2})-(\d{2})$', date_str)
    if iso_match:
        y, m, d = iso_match.groups()
        year = int(y) if y != "0000" and int(y) > 0 else None
        month = int(m) if m != "00" and int(m) > 0 else None
        day = int(d) if d != "00" and int(d) > 0 else None
        return year, month, day
    
    # Strip qualifiers (Abt, About, Bef, Before, Aft, After, circa, c., ~)
    date_str = re.sub(r'^(abt\.?|about|bef\.?|before|aft\.?|after|circa|c\.?|~)\s*', '', date_str, flags=re.IGNORECASE)
    
    # Handle year ranges: "1850/51" -> take first year
    range_match = re.match(r'^(\d{4})[/-](\d{2,4})$', date_str)
    if range_match:
        year = int(range_match.group(1))
        return year, None, None
    
    # Handle "1850 or 1851" -> take first year
    or_match = re.match(r'^(\d{4})\s+or\s+\d{4}$', date_str, flags=re.IGNORECASE)
    if or_match:
        year = int(or_match.group(1))
        return year, None, None
    
    # Handle text dates: "15 Jan 1850", "January 15, 1850"
    month_names = {
        'jan': 1, 'january': 1, 'feb': 2, 'february': 2, 'mar': 3, 'march': 3,
        'apr': 4, 'april': 4, 'may': 5, 'jun': 6, 'june': 6,
        'jul': 7, 'july': 7, 'aug': 8, 'august': 8, 'sep': 9, 'sept': 9, 'september': 9,
        'oct': 10, 'october': 10, 'nov': 11, 'november': 11, 'dec': 12, 'december': 12
    }
    
    # "15 Jan 1850" or "Jan 15 1850" or "Jan 15, 1850"
    text_match = re.match(r'^(\d{1,2})\s+([a-zA-Z]+)\s+(\d{4})$', date_str)
    if text_match:
        day = int(text_match.group(1))
        month = month_names.get(text_match.group(2).lower()[:3])
        year = int(text_match.group(3))
        return year, month, day
    
    text_match2 = re.match(r'^([a-zA-Z]+)\s+(\d{1,2}),?\s+(\d{4})$', date_str)
    if text_match2:
        month = month_names.get(text_match2.group(1).lower()[:3])
        day = int(text_match2.group(2))
        year = int(text_match2.group(3))
        return year, month, day
    
    # Just a year: "1850"
    year_match = re.match(r'^(\d{4})$', date_str)
    if year_match:
        year = int(year_match.group(1))
        return year, None, None
    
    # Last resort: extract any 4-digit year
    any_year = re.search(r'\b(\d{4})\b', date_str)
    if any_year:
        year = int(any_year.group(1))
        return year, None, None
    
    return None, None, None


def parse_location(loc_str):
    """Parse location string into: city, county, state, country, region"""
    result = {"city": None, "county": None, "state": None, "country": None, "region": None}
    
    if not loc_str:
        return result
    
    loc_lower = loc_str.lower()
    parts = [p.strip() for p in loc_str.split(",")]
    parts_lower = [p.lower().strip() for p in parts]
    
    # Country
    for country_key, keywords in COUNTRIES.items():
        if any(kw in loc_lower for kw in keywords):
            result["country"] = country_key
            break
    
    # Region from country
    if result["country"]:
        for region_key, countries in REGIONS.items():
            if result["country"] in countries:
                result["region"] = region_key
                break
    
    # State (US)
    for state in US_STATES:
        if state in loc_lower:
            result["state"] = state
            result["country"] = result["country"] or "usa"
            result["region"] = result["region"] or "north_america"
            break
    
    # County (UK)
    for county in UK_COUNTIES:
        if county in loc_lower:
            result["county"] = county
            result["country"] = result["country"] or "uk"
            result["region"] = result["region"] or "british_isles"
            break
    
    # City (first part if not a state/county)
    if len(parts) >= 2 and parts_lower[0] not in US_STATES and parts_lower[0] not in UK_COUNTIES:
        result["city"] = parts_lower[0]
    
    # County in "X County" format
    county_match = re.search(r'(\w+)\s+county', loc_lower)
    if county_match and not result["county"]:
        result["county"] = county_match.group(1)
    
    return result


def parse_name(profile):
    """Extract name components from profile."""
    first = (profile.get("FirstName") or "").strip().lower()
    middle = (profile.get("MiddleName") or "").strip().lower()
    last = (profile.get("LastNameAtBirth") or "").strip().lower()
    suffix = (profile.get("Suffix") or "").strip().lower()
    
    suffix_map = {"jr": "jr", "jr.": "jr", "junior": "jr", 
                  "sr": "sr", "sr.": "sr", "senior": "sr",
                  "ii": "ii", "iii": "iii", "iv": "iv"}
    suffix = suffix_map.get(suffix, suffix)
    
    return {"first": first, "middle": middle, "last": last, "suffix": suffix}


def fetch_relatives(client, profile_id):
    """Fetch relatives using getRelatives API."""
    try:
        result = client.get_relatives(
            profile_id,
            get_parents=True,
            get_children=True,
            get_spouses=True,
            get_siblings=True
        )
        if result and isinstance(result, list) and result[0].get("items"):
            person = result[0]["items"][0].get("person", {})
            return {
                "Parents": person.get("Parents", {}),
                "Children": person.get("Children", {}),
                "Spouses": person.get("Spouses", {}),
                "Siblings": person.get("Siblings", {})
            }
    except Exception as e:
        pass
    return {"Parents": {}, "Children": {}, "Spouses": {}, "Siblings": {}}


def compare_relatives(rels1, rels2):
    """Compare relatives, return (matches, conflicts, stats)."""
    matches = []
    conflicts = []
    stats = {
        "p1_parents": 0, "p2_parents": 0,
        "p1_spouses": 0, "p2_spouses": 0,
        "p1_children": 0, "p2_children": 0,
        "p1_siblings": 0, "p2_siblings": 0,
    }
    
    for category in ["Parents", "Children", "Spouses", "Siblings"]:
        list1 = rels1.get(category, {})
        list2 = rels2.get(category, {})
        
        if isinstance(list1, dict):
            list1 = list(list1.values())
        if isinstance(list2, dict):
            list2 = list(list2.values())
        
        cat_lower = category.lower()
        stats[f"p1_{cat_lower}"] = len(list1)
        stats[f"p2_{cat_lower}"] = len(list2)
        
        matched_indices = set()
        
        for r1 in list1:
            first1 = (r1.get("FirstName") or "").lower().strip()
            last1 = (r1.get("LastNameAtBirth") or "").lower().strip()
            
            found_match = False
            for idx, r2 in enumerate(list2):
                if idx in matched_indices:
                    continue
                    
                first2 = (r2.get("FirstName") or "").lower().strip()
                last2 = (r2.get("LastNameAtBirth") or "").lower().strip()
                
                if first1 and first2 and first1 == first2:
                    if last1 == last2 or not last1 or not last2:
                        matches.append((category, f"{first1.title()} {last1.title()}"))
                        matched_indices.add(idx)
                        found_match = True
                        break
            
            # Check for conflicts in Parents
            if not found_match and category == "Parents" and first1 and list2:
                for r2 in list2:
                    first2 = (r2.get("FirstName") or "").lower().strip()
                    if first2 and first1 != first2:
                        conflicts.append((category, first1.title(), first2.title()))
                        break
    
    return matches, conflicts, stats


def calculate_match_score(p1, p2, rels1=None, rels2=None, base_only=False):
    """
    Comprehensive weighted match score.
    Evaluates EVERY field: match (+), mismatch (-), null (0)
    
    Args:
        p1, p2: Profile dicts
        rels1, rels2: Relatives dicts (optional)
        base_only: If True, only calculate names + dates (for pre-filtering)
    """
    score = 0
    max_possible = 0
    reasons = []
    
    rels1 = rels1 or {}
    rels2 = rels2 or {}
    
    # === PARSE DATA ===
    name1 = parse_name(p1)
    name2 = parse_name(p2)
    
    birth1 = parse_date(p1.get("BirthDate"))
    birth2 = parse_date(p2.get("BirthDate"))
    
    death1 = parse_date(p1.get("DeathDate"))
    death2 = parse_date(p2.get("DeathDate"))
    
    birth_loc1 = parse_location(p1.get("BirthLocation", ""))
    birth_loc2 = parse_location(p2.get("BirthLocation", ""))
    
    death_loc1 = parse_location(p1.get("DeathLocation", ""))
    death_loc2 = parse_location(p2.get("DeathLocation", ""))
    
    # === FIRST NAME (fuzzy matching) ===
    max_possible += WEIGHTS.get("first_name_exact", 15)
    if name1["first"] and name2["first"]:
        ratio = fuzz.ratio(name1["first"], name2["first"])
        if ratio >= FUZZY_EXACT:
            score += WEIGHTS.get("first_name_exact", 15)
            reasons.append(f"✅ First name: {name1['first'].title()} ({ratio}%)")
        elif ratio >= FUZZY_PARTIAL:
            score += WEIGHTS.get("first_name_partial", 8)
            reasons.append(f"⚠️ First name similar: {name1['first'].title()} ~ {name2['first'].title()} ({ratio}%)")
        else:
            score += WEIGHTS.get("first_name_mismatch", -20)
            reasons.append(f"❌ First name mismatch: {name1['first'].title()} vs {name2['first'].title()} ({ratio}%)")
    
    # === MIDDLE NAME (fuzzy matching) ===
    max_possible += WEIGHTS.get("middle_name_exact", 10)
    if name1["middle"] and name2["middle"]:
        ratio = fuzz.ratio(name1["middle"], name2["middle"])
        if ratio >= FUZZY_EXACT:
            score += WEIGHTS.get("middle_name_exact", 10)
            reasons.append(f"✅ Middle name: {name1['middle'].title()}")
        elif name1["middle"][0] == name2["middle"][0]:
            score += WEIGHTS.get("middle_name_partial", 5)
            reasons.append(f"⚠️ Middle initial: {name1['middle'][0].upper()}")
        elif ratio >= FUZZY_PARTIAL:
            score += WEIGHTS.get("middle_name_partial", 5)
            reasons.append(f"⚠️ Middle name similar: {name1['middle'].title()} ~ {name2['middle'].title()} ({ratio}%)")
        else:
            score += WEIGHTS.get("middle_name_mismatch", -8)
            reasons.append(f"❌ Middle name mismatch: {name1['middle'].title()} vs {name2['middle'].title()}")
    
    # === LAST NAME (fuzzy matching) ===
    max_possible += WEIGHTS.get("last_name_exact", 15)
    if name1["last"] and name2["last"]:
        ratio = fuzz.ratio(name1["last"], name2["last"])
        if ratio >= FUZZY_EXACT:
            score += WEIGHTS.get("last_name_exact", 15)
        elif ratio >= FUZZY_PARTIAL:
            score += WEIGHTS.get("last_name_exact", 15) // 2
            reasons.append(f"⚠️ Last name similar: {name1['last'].title()} ~ {name2['last'].title()} ({ratio}%)")
        else:
            score += WEIGHTS.get("last_name_mismatch", -50)
            reasons.append(f"❌ Last name mismatch: {name1['last'].title()} vs {name2['last'].title()}")
    
    # === SUFFIX ===
    max_possible += WEIGHTS.get("suffix_exact", 8)
    if name1["suffix"] and name2["suffix"]:
        if name1["suffix"] == name2["suffix"]:
            score += WEIGHTS.get("suffix_exact", 8)
            reasons.append(f"✅ Suffix: {name1['suffix'].upper()}")
        else:
            score += WEIGHTS.get("suffix_mismatch", -15)
            reasons.append(f"❌ Suffix mismatch: {name1['suffix'].upper()} vs {name2['suffix'].upper()}")
    elif name1["suffix"] or name2["suffix"]:
        score += WEIGHTS.get("suffix_mismatch", -15) // 2
        reasons.append(f"⚠️ Suffix: {name1['suffix'] or 'none'} vs {name2['suffix'] or 'none'}")
    
    # === BIRTH YEAR ===
    max_possible += WEIGHTS.get("birth_year_exact", 15)
    y1, y2 = birth1[0], birth2[0]
    if y1 and y2:
        diff = abs(y1 - y2)
        if diff == 0:
            score += WEIGHTS.get("birth_year_exact", 15)
            reasons.append(f"✅ Birth year: {y1}")
        elif diff <= 2:
            score += WEIGHTS.get("birth_year_close", 10)
            reasons.append(f"✅ Birth year close: {y1} vs {y2}")
        elif diff <= 5:
            score += WEIGHTS.get("birth_year_near", 5)
            reasons.append(f"⚠️ Birth year near: {y1} vs {y2}")
        else:
            penalty = min(30, (diff - 5) * abs(WEIGHTS.get("birth_year_mismatch_per_year", -3)))
            score -= penalty
            reasons.append(f"❌ Birth year gap: {diff} years ({y1} vs {y2})")
    
    # === BIRTH MONTH ===
    max_possible += WEIGHTS.get("birth_month_exact", 10)
    m1, m2 = birth1[1], birth2[1]
    if m1 and m2:
        if m1 == m2:
            score += WEIGHTS.get("birth_month_exact", 10)
            reasons.append(f"✅ Birth month: {m1}")
        elif abs(m1 - m2) <= 1 or abs(m1 - m2) == 11:
            score += WEIGHTS.get("birth_month_close", 5)
        else:
            score += WEIGHTS.get("birth_month_mismatch", -8)
            reasons.append(f"❌ Birth month mismatch: {m1} vs {m2}")
    
    # === BIRTH DAY ===
    max_possible += WEIGHTS.get("birth_day_exact", 10)
    d1, d2 = birth1[2], birth2[2]
    if d1 and d2:
        if d1 == d2:
            score += WEIGHTS.get("birth_day_exact", 10)
            reasons.append(f"✅ Birth day: {d1}")
        elif abs(d1 - d2) <= 3:
            score += WEIGHTS.get("birth_day_close", 5)
        else:
            score += WEIGHTS.get("birth_day_mismatch", -8)
            reasons.append(f"❌ Birth day mismatch: {d1} vs {d2}")
    
    # === DEATH YEAR ===
    max_possible += WEIGHTS.get("death_year_exact", 12)
    y1, y2 = death1[0], death2[0]
    if y1 and y2:
        diff = abs(y1 - y2)
        if diff == 0:
            score += WEIGHTS.get("death_year_exact", 12)
            reasons.append(f"✅ Death year: {y1}")
        elif diff <= 2:
            score += WEIGHTS.get("death_year_close", 8)
            reasons.append(f"✅ Death year close: {y1} vs {y2}")
        elif diff <= 5:
            score += WEIGHTS.get("death_year_near", 4)
        else:
            penalty = min(20, (diff - 5) * abs(WEIGHTS.get("death_year_mismatch_per_year", -2)))
            score -= penalty
            reasons.append(f"❌ Death year gap: {diff} years ({y1} vs {y2})")
    
    # === DEATH MONTH ===
    max_possible += WEIGHTS.get("death_month_exact", 8)
    m1, m2 = death1[1], death2[1]
    if m1 and m2:
        if m1 == m2:
            score += WEIGHTS.get("death_month_exact", 8)
            reasons.append(f"✅ Death month: {m1}")
        elif abs(m1 - m2) <= 1 or abs(m1 - m2) == 11:
            score += WEIGHTS.get("death_month_close", 4)
        else:
            score += WEIGHTS.get("death_month_mismatch", -6)
    
    # === DEATH DAY ===
    max_possible += WEIGHTS.get("death_day_exact", 8)
    d1, d2 = death1[2], death2[2]
    if d1 and d2:
        if d1 == d2:
            score += WEIGHTS.get("death_day_exact", 8)
            reasons.append(f"✅ Death day: {d1}")
        elif abs(d1 - d2) <= 3:
            score += WEIGHTS.get("death_day_close", 4)
        else:
            score += WEIGHTS.get("death_day_mismatch", -6)
    
    # === BASE SCORE EARLY RETURN ===
    # If only calculating base score (names + dates), return here to avoid expensive API calls
    if base_only:
        if max_possible > 0:
            percentage = max(0, min(100, int((score / max_possible) * 100)))
        else:
            percentage = 0
        return score, max_possible, percentage, reasons
    
    # === BIRTH LOCATION (hierarchical) ===
    # Region
    max_possible += WEIGHTS.get("birth_region_exact", 5)
    if birth_loc1["region"] and birth_loc2["region"]:
        if birth_loc1["region"] == birth_loc2["region"]:
            score += WEIGHTS.get("birth_region_exact", 5)
        else:
            score += WEIGHTS.get("birth_region_mismatch", -40)
            reasons.append(f"❌ Birth region mismatch: {birth_loc1['region']} vs {birth_loc2['region']}")
    
    # Country
    max_possible += WEIGHTS.get("birth_country_exact", 8)
    if birth_loc1["country"] and birth_loc2["country"]:
        if birth_loc1["country"] == birth_loc2["country"]:
            score += WEIGHTS.get("birth_country_exact", 8)
        else:
            score += WEIGHTS.get("birth_country_mismatch", -30)
            reasons.append(f"❌ Birth country mismatch: {birth_loc1['country']} vs {birth_loc2['country']}")
    
    # State
    max_possible += WEIGHTS.get("birth_state_exact", 10)
    if birth_loc1["state"] and birth_loc2["state"]:
        if birth_loc1["state"] == birth_loc2["state"]:
            score += WEIGHTS.get("birth_state_exact", 10)
            reasons.append(f"✅ Birth state: {birth_loc1['state'].title()}")
        else:
            score += WEIGHTS.get("birth_state_mismatch", -8)
            reasons.append(f"❌ Birth state mismatch: {birth_loc1['state'].title()} vs {birth_loc2['state'].title()}")
    
    # County
    max_possible += WEIGHTS.get("birth_county_exact", 12)
    if birth_loc1["county"] and birth_loc2["county"]:
        if birth_loc1["county"] == birth_loc2["county"]:
            score += WEIGHTS.get("birth_county_exact", 12)
            reasons.append(f"✅ Birth county: {birth_loc1['county'].title()}")
        else:
            score += WEIGHTS.get("birth_county_mismatch", -10)
            reasons.append(f"❌ Birth county mismatch: {birth_loc1['county'].title()} vs {birth_loc2['county'].title()}")
    
    # City
    max_possible += WEIGHTS.get("birth_city_exact", 15)
    if birth_loc1["city"] and birth_loc2["city"]:
        if birth_loc1["city"] == birth_loc2["city"]:
            score += WEIGHTS.get("birth_city_exact", 15)
            reasons.append(f"✅ Birth city: {birth_loc1['city'].title()}")
        else:
            score += WEIGHTS.get("birth_city_mismatch", -12)
            reasons.append(f"❌ Birth city mismatch: {birth_loc1['city'].title()} vs {birth_loc2['city'].title()}")
    
    # === DEATH LOCATION ===
    # Region
    max_possible += WEIGHTS.get("death_region_exact", 4)
    if death_loc1["region"] and death_loc2["region"]:
        if death_loc1["region"] == death_loc2["region"]:
            score += WEIGHTS.get("death_region_exact", 4)
        else:
            score += WEIGHTS.get("death_region_mismatch", -30)
            reasons.append(f"❌ Death region mismatch")
    
    # Country
    max_possible += WEIGHTS.get("death_country_exact", 6)
    if death_loc1["country"] and death_loc2["country"]:
        if death_loc1["country"] == death_loc2["country"]:
            score += WEIGHTS.get("death_country_exact", 6)
        else:
            score += WEIGHTS.get("death_country_mismatch", -20)
    
    # State
    max_possible += WEIGHTS.get("death_state_exact", 8)
    if death_loc1["state"] and death_loc2["state"]:
        if death_loc1["state"] == death_loc2["state"]:
            score += WEIGHTS.get("death_state_exact", 8)
            reasons.append(f"✅ Death state: {death_loc1['state'].title()}")
        else:
            score += WEIGHTS.get("death_state_mismatch", -6)
            reasons.append(f"❌ Death state mismatch")
    
    # County
    max_possible += WEIGHTS.get("death_county_exact", 10)
    if death_loc1["county"] and death_loc2["county"]:
        if death_loc1["county"] == death_loc2["county"]:
            score += WEIGHTS.get("death_county_exact", 10)
            reasons.append(f"✅ Death county: {death_loc1['county'].title()}")
        else:
            score += WEIGHTS.get("death_county_mismatch", -8)
    
    # City
    max_possible += WEIGHTS.get("death_city_exact", 12)
    if death_loc1["city"] and death_loc2["city"]:
        if death_loc1["city"] == death_loc2["city"]:
            score += WEIGHTS.get("death_city_exact", 12)
            reasons.append(f"✅ Death city: {death_loc1['city'].title()}")
        else:
            score += WEIGHTS.get("death_city_mismatch", -10)
    
    # === HAS PARENTS (Bridge potential) ===
    max_possible += WEIGHTS.get("has_parents", 10)
    has_father = str(p2.get("Father", "0")) != "0"
    has_mother = str(p2.get("Mother", "0")) != "0"
    if has_father or has_mother:
        score += WEIGHTS.get("has_parents", 10)
        reasons.append(f"✅ Has parents (bridge potential)")
    
    # === RELATIVES COMPARISON ===
    if rels1 and rels2:
        matching_rels, conflicts, stats = compare_relatives(rels1, rels2)
        
        p1_has_rels = any(stats[k] > 0 for k in ["p1_parents", "p1_spouses", "p1_children", "p1_siblings"])
        p2_has_rels = any(stats[k] > 0 for k in ["p2_parents", "p2_spouses", "p2_children", "p2_siblings"])
        
        if not p1_has_rels and not p2_has_rels:
            score += WEIGHTS.get("no_relatives_data", -5)
            reasons.append("⚠️ No relatives data to compare")
        elif p1_has_rels and p2_has_rels and not matching_rels and not conflicts:
            score += WEIGHTS.get("no_matching_relatives", -10)
            reasons.append("❌ Both have relatives but none match")
            max_possible += WEIGHTS.get("parent_match", 25) * 2
        
        # Score matching relatives
        for category, name in matching_rels:
            if category == "Parents":
                score += WEIGHTS.get("parent_match", 25)
                max_possible += WEIGHTS.get("parent_match", 25)
                reasons.append(f"✅ Parent match: {name}")
            elif category == "Spouses":
                score += WEIGHTS.get("spouse_match", 20)
                max_possible += WEIGHTS.get("spouse_match", 20)
                reasons.append(f"✅ Spouse match: {name}")
            elif category == "Children":
                score += WEIGHTS.get("child_match", 15)
                max_possible += WEIGHTS.get("child_match", 15)
                reasons.append(f"✅ Child match: {name}")
            elif category == "Siblings":
                score += WEIGHTS.get("sibling_match", 12)
                max_possible += WEIGHTS.get("sibling_match", 12)
                reasons.append(f"✅ Sibling match: {name}")
        
        # Penalize conflicts
        for category, name1, name2 in conflicts:
            if category == "Parents":
                score += WEIGHTS.get("parent_mismatch", -20)
                reasons.append(f"❌ Parent conflict: {name1} vs {name2}")
    
    # Calculate percentage
    if max_possible > 0:
        percentage = max(0, min(100, int((score / max_possible) * 100)))
    else:
        percentage = 0
    
    return score, max_possible, percentage, reasons


def main():
    load_dotenv()
    client = WikiTreeClient()
    
    email = os.getenv("WIKITREE_EMAIL")
    password = os.getenv("WIKITREE_PASSWORD")
    
    root_id = None
    if email and password:
        print(f"Authenticating as {email}...")
        auth = client.authenticate(email=email, password=password)
        root_id = auth.user_name if hasattr(auth, 'user_name') else None

    if not root_id:
        root_id = os.getenv("WIKITREE_ROOT_ID")
        
    if not root_id:
        print("Error: No root ID found. Set WIKITREE_ROOT_ID in .env or log in.")
        return

    # 1. Crawl tree
    print(f"Fetching tree for {root_id}...")
    people = client.crawl_tree(root_id, max_people=MAX_CRAWL_PEOPLE, verbose=True, fields="*")
    print(f"✓ Found {len(people)} profiles.\n")
    
    # 2. Find end-of-line ancestors
    eol_candidates = []
    existing_ids = {str(p.get("Id")) for p in people}
    
    for p in people:
        f_id = str(p.get("Father", "0"))
        m_id = str(p.get("Mother", "0"))
        
        if f_id == "0" or m_id == "0":
            year, _, _ = parse_date(p.get("BirthDate"))
            if p.get("LastNameAtBirth") and (not year or year < 1950):
                eol_candidates.append(p)

    print(f"Found {len(eol_candidates)} end-of-line ancestors.\n")

    report = [
        "# Bridge Finder Report",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Root: [{root_id}](https://www.wikitree.com/wiki/{root_id})",
        f"Threshold: {MIN_MATCH_THRESHOLD}%\n",
    ]

    total_matches = 0
    confirmed_matches = []
    
    # 3. Search and score each candidate
    for idx, p in enumerate(eol_candidates):
        name = f"{p.get('FirstName')} {p.get('LastNameAtBirth')}"
        birth_year, _, _ = parse_date(p.get("BirthDate"))
        
        print(f"[{idx+1}/{len(eol_candidates)}] {name} (b. {birth_year})...")
        
        # Search with retry
        search_results = None
        for attempt in range(3):
            try:
                search_results = client.search_person(
                    FirstName=p.get("FirstName"),
                    LastName=p.get("LastNameAtBirth"),
                    BirthDate=birth_year,
                )
                break
            except Exception as e:
                if "429" in str(e):
                    wait = 5 * (attempt + 1)
                    print(f"  Rate limited, waiting {wait}s...")
                    time.sleep(wait)
                else:
                    break
        
        if not search_results:
            time.sleep(API_DELAY)
            continue
        
        matches = []
        skipped_low_base = 0
        
        if isinstance(search_results, list) and search_results[0].get("matches"):
            for match in search_results[0]["matches"]:
                m_id = str(match.get("Id"))
                if m_id in existing_ids:
                    continue
                
                # Last name filter (fuzzy)
                m_last = (match.get("LastNameAtBirth") or "").lower()
                p_last = (p.get("LastNameAtBirth") or "").lower()
                if m_last and p_last:
                    last_ratio = fuzz.ratio(m_last, p_last)
                    if last_ratio < FUZZY_PARTIAL:
                        continue  # Skip obvious last name mismatches

                # Fetch full profile
                try:
                    full_resp = client.get_profile(match.get("Name"), fields="*")
                    full_match = full_resp[0].get("profile", {}) if full_resp else match
                except:
                    full_match = match

                # === BASE SCORE CHECK (N+1 optimization) ===
                # Calculate base score (names + dates only) before expensive relatives API calls
                base_score, base_max, base_pct, _ = calculate_match_score(p, full_match, base_only=True)
                
                if base_pct < BASE_SCORE_THRESHOLD:
                    skipped_low_base += 1
                    continue  # Skip fetching relatives for obvious non-matches

                # Only fetch relatives if base score is promising
                rels1 = fetch_relatives(client, p.get("Name"))
                rels2 = fetch_relatives(client, full_match.get("Name"))

                # Calculate comprehensive score with relatives
                score, max_possible, pct, reasons = calculate_match_score(p, full_match, rels1, rels2)
                
                if pct >= MIN_MATCH_THRESHOLD:
                    matches.append({
                        "profile": full_match,
                        "score": score,
                        "max": max_possible,
                        "pct": pct,
                        "reasons": reasons,
                    })
        
        if skipped_low_base > 0:
            print(f"    (skipped {skipped_low_base} low base score candidates)")

        if matches:
            matches.sort(key=lambda x: x["pct"], reverse=True)
            total_matches += len(matches)
            
            report.append(f"## {name} ({p.get('Name')})")
            report.append(f"- Your profile: [{p.get('Name')}](https://www.wikitree.com/wiki/{p.get('Name')})")
            report.append(f"- Born: {p.get('BirthDate', '?')} in {p.get('BirthLocation', '?')}")
            report.append(f"- Died: {p.get('DeathDate', '?')} in {p.get('DeathLocation', '?')}")
            report.append("- **Matches:**\n")
            
            for m in matches:
                mp = m["profile"]
                verdict = "✅ CONFIRMED" if m["pct"] >= CONFIRMED_THRESHOLD else "⚠️ POSSIBLE"
                
                if m["pct"] >= CONFIRMED_THRESHOLD:
                    confirmed_matches.append((p.get("Name"), mp.get("Name"), m["pct"]))
                
                report.append(f"### [{mp.get('Name')}](https://www.wikitree.com/wiki/{mp.get('Name')}) — {m['pct']}% {verdict}")
                report.append(f"- Score: {m['score']}/{m['max']}")
                report.append(f"- Born: {mp.get('BirthDate', '?')} in {mp.get('BirthLocation', '?')}")
                report.append(f"- Died: {mp.get('DeathDate', '?')} in {mp.get('DeathLocation', '?')}")
                report.append("- Analysis:")
                for r in m["reasons"]:
                    report.append(f"  - {r}")
                report.append("")
            
            report.append("---\n")
            time.sleep(API_DELAY)  # Only delay if we made API calls

    # Summary
    report.insert(4, f"\n**Found {total_matches} matches, {len(confirmed_matches)} confirmed (≥70%).**\n")
    
    if confirmed_matches:
        report.insert(5, "### Confirmed Matches (≥70%)")
        for your_id, match_id, pct in confirmed_matches:
            report.insert(6, f"- [{your_id}](https://www.wikitree.com/wiki/{your_id}) ↔ [{match_id}](https://www.wikitree.com/wiki/{match_id}) ({pct}%)")
        report.insert(6 + len(confirmed_matches), "\n")

    # Save
    exports_dir = Path(__file__).parent.parent / "exports"
    exports_dir.mkdir(exist_ok=True)
    report_file = exports_dir / "bridge_finder_report.md"
    report_file.write_text("\n".join(report), encoding="utf-8")
    
    print(f"\n✓ Report: {report_file}")
    print(f"✓ Found {total_matches} matches, {len(confirmed_matches)} confirmed.")


if __name__ == "__main__":
    main()
