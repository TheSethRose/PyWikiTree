"""
Example: Biography Keyword Searcher
This script demonstrates how to search for people by name and then 
inspect their biographies for specific keywords.
"""

import os
from pathlib import Path
from pywikitree.client import WikiTreeClient

def load_env():
    """Simple .env loader to avoid extra dependencies."""
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.strip() and not line.startswith("#"):
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip().strip('"').strip("'")

def main():
    load_env()
    # Initialize the client
    client = WikiTreeClient()
    
    # Search criteria
    last_name = "Clemens"
    keyword = "Mississippi"
    
    print(f"Searching for people with last name '{last_name}' and checking bios for '{keyword}'...")
    
    try:
        # 1. Search for people
        # Note: WikiTree API uses camelCase for parameters like LastName
        response = client.search_person(LastName=last_name, limit=10)
        
        if not response:
            print("No response from search.")
            return
            
        # API usually returns a list with one item containing 'matches'
        if isinstance(response, list) and len(response) > 0:
            matches = response[0].get("matches", [])
        elif isinstance(response, dict):
            matches = response.get("matches", [])
        else:
            matches = []
            
        if not matches:
            print("No matches found.")
            return
            
        print(f"Found {len(matches)} matches. Checking biographies...\n")
        
        for match in matches:
            name = match.get("Name")
            real_name = match.get("RealName")
            
            # 2. Get the full biography for each match
            # We use bioFormat='raw' to get the WikiText
            bio_response = client.get_bio(name, bio_format="raw")
            
            if bio_response:
                # Handle list or dict response
                if isinstance(bio_response, list) and len(bio_response) > 0:
                    bio_data = bio_response[0]
                else:
                    bio_data = bio_response
                    
                bio_text = bio_data.get("bio", "")
                
                if keyword.lower() in bio_text.lower():
                    print(f"[MATCH] {real_name} ({name})")
                    # Print a small snippet
                    idx = bio_text.lower().find(keyword.lower())
                    start = max(0, idx - 40)
                    end = min(len(bio_text), idx + 40)
                    snippet = bio_text[start:end].replace("\n", " ")
                    print(f"    Snippet: ...{snippet}...")
                else:
                    print(f"[SKIP]  {real_name} ({name}) - Keyword not found.")
            else:
                print(f"[WARN]  Could not fetch bio for {name}")
                
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
