"""
Example: Find Potential Connections (Bridge Finder)
This script identifies "end-of-line" ancestors in your tree and searches 
WikiTree for potential matches that might extend your tree further.
"""

import os
import time
from pathlib import Path
from pywikitree.client import WikiTreeClient

def load_env():
    """Simple .env loader."""
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.strip() and not line.startswith("#"):
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip().strip('"').strip("'")

def get_year(date_str):
    if not date_str or date_str == "0000-00-00":
        return None
    return date_str.split("-")[0]

def main():
    load_env()
    client = WikiTreeClient()
    
    email = os.getenv("WIKITREE_EMAIL")
    password = os.getenv("WIKITREE_PASSWORD")
    
    root_id = None
    if email and password:
        print(f"Authenticating as {email}...")
        auth = client.authenticate(email=email, password=password)
        root_id = auth.user_name if hasattr(auth, 'user_name') else None

    if not root_id:
        # Fallback to an environment variable or prompt
        root_id = os.getenv("WIKITREE_ROOT_ID")
        
    if not root_id:
        print("Error: No root ID found. Please set WIKITREE_ROOT_ID in .env or log in.")
        return

    # 1. Fetch your tree (or a subset)
    print(f"Fetching tree for {root_id} to find end-of-line ancestors...")
    # Use a deeper crawl to find more candidates
    people = client.crawl_tree(root_id, max_people=500, verbose=False)
    
    # 2. Identify "End-of-Line" ancestors
    # These are people who have no parents listed in our dataset
    eol_candidates = []
    existing_ids = {str(p.get("Id")) for p in people}
    
    for p in people:
        f_id = str(p.get("Father", "0"))
        m_id = str(p.get("Mother", "0"))
        
        if f_id == "0" and m_id == "0":
            # Only consider people with enough data to search reliably
            # and respect WikiTree's 1940 privacy limit for searches
            year = get_year(p.get("BirthDate"))
            if p.get("LastNameAtBirth") and year and int(year) < 1940:
                eol_candidates.append(p)

    print(f"Found {len(eol_candidates)} end-of-line ancestors to investigate.\n")

    report_lines = [
        "# Potential WikiTree Connections Report",
        f"Generated on: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Root Profile: [{root_id}](https://www.wikitree.com/wiki/{root_id})",
        "\nThis report lists profiles on WikiTree that match your 'end-of-line' ancestors but are not currently linked to them. These may be 'bridges' to larger trees.\n",
    ]

    # 3. Search for each candidate
    for p in eol_candidates:
        name = f"{p.get('FirstName')} {p.get('LastNameAtBirth')}"
        birth_year = get_year(p.get("BirthDate"))
        
        print(f"Searching for matches for {name} (b. {birth_year})...")
        
        try:
            # Perform search
            search_results = client.search_person(
                FirstName=p.get("FirstName"),
                LastName=p.get("LastNameAtBirth"),
                BirthDate=birth_year,
            )
        except Exception as e:
            print(f"  Error searching for {name}: {e}")
            continue
        
        matches = []
        if search_results and isinstance(search_results, list) and search_results[0].get("matches"):
            for match in search_results[0]["matches"]:
                m_id = str(match.get("Id"))
                if m_id in existing_ids:
                    continue
                
                # Stricter name check: Last name should match
                m_last = match.get("LastNameAtBirth", "").lower()
                p_last = p.get("LastNameAtBirth", "").lower()
                if m_last != p_last:
                    continue

                # Check if this match has parents (which would make it a bridge)
                m_f = str(match.get("Father", "0"))
                m_m = str(match.get("Mother", "0"))
                
                if m_f != "0" or m_m != "0":
                    matches.append(match)

        if matches:
            report_lines.append(f"## Matches for {name} ({p.get('Name')})")
            report_lines.append(f"- **Your Profile**: [View on WikiTree](https://www.wikitree.com/wiki/{p.get('Name')})")
            report_lines.append("- **Potential Bridges found**:")
            for m in matches:
                m_name = m.get("Name")
                m_birth = m.get("BirthDate", "Unknown")
                m_loc = m.get("BirthLocation", "Unknown")
                report_lines.append(f"  - **[{m_name}](https://www.wikitree.com/wiki/{m_name})**")
                report_lines.append(f"    - Birth: {m_birth} in {m_loc}")
                report_lines.append(f"    - Has Parents: {'Yes' if str(m.get('Father','0'))!='0' else 'No'} Father, {'Yes' if str(m.get('Mother','0'))!='0' else 'No'} Mother")
            report_lines.append("\n---\n")
        
        # Be polite to the API
        time.sleep(1)

    # 4. Save Report
    exports_dir = Path(__file__).parent.parent / "exports"
    exports_dir.mkdir(exist_ok=True)
    report_file = exports_dir / "potential_connections.md"
    report_file.write_text("\n".join(report_lines), encoding="utf-8")
    
    print(f"\nReport generated: {report_file.absolute()}")

if __name__ == "__main__":
    main()
