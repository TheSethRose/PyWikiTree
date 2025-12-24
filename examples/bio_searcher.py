"""
Example: Biography Keyword Searcher
This script demonstrates how to search for people by name and then 
inspect their biographies for specific keywords.
"""

import os
from pywikitree.client import WikiTreeClient

def main():
    # Initialize the client
    client = WikiTreeClient()
    
    # Search criteria
    last_name = "Clemens"
    keyword = "Mississippi"
    
    print(f"Searching for people with last name '{last_name}' and checking bios for '{keyword}'...")
    
    try:
        # 1. Search for people
        search_results = client.search_person(last_name=last_name, limit=10)
        
        if not search_results or "matches" not in search_results:
            print("No matches found.")
            return
            
        matches = search_results["matches"]
        print(f"Found {len(matches)} matches. Checking biographies...\n")
        
        for match in matches:
            name = match.get("Name")
            real_name = match.get("RealName")
            
            # 2. Get the full biography for each match
            # We use bioFormat='raw' to get the WikiText
            bio_data = client.get_bio(name, bio_format="raw")
            
            if bio_data and "bio" in bio_data:
                bio_text = bio_data["bio"]
                
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
