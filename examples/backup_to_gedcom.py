"""
Example: Backup to GEDCOM
This script demonstrates how to fetch a family tree and export it to a 
standard GEDCOM 5.5.1 file for local backup or use in other genealogy software.
"""

import os
from pathlib import Path
from pywikitree.client import WikiTreeClient
from pywikitree.gedcom import GedcomExporter

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
    
    # Optional: Authenticate if you want to include private/trusted profiles
    email = os.getenv("WIKITREE_EMAIL")
    password = os.getenv("WIKITREE_PASSWORD")
    
    if email and password:
        print(f"Authenticating as {email}...")
        client.authenticate(email=email, password=password)
        print("Authentication successful.\n")
        
        # Option A: Fetch the entire watchlist (Best for "My Entire Tree")
        print("Fetching your entire watchlist...")
        people = client.get_entire_watchlist()
    else:
        print("No credentials found in .env. Proceeding with public crawl.\n")
        
        # Option B: Deep crawl from a root ID
        root_id = "Clemens-1"
        print(f"Performing deep crawl starting from {root_id}...")
        people = client.crawl_tree(root_id, max_people=500)
    
    try:
        if not people:
            print("No people found.")
            return
            
        print(f"Found {len(people)} individuals. Generating GEDCOM...")
        
        # 2. Export to GEDCOM
        exporter = GedcomExporter(people)
        gedcom_content = exporter.export()
        
        # 3. Save to file
        output_file = Path(f"{root_id}_backup.ged")
        output_file.write_text(gedcom_content, encoding="utf-8")
        
        print(f"\nSuccess! Backup saved to: {output_file.absolute()}")
        print(f"You can now import this file into Ancestry, MyHeritage, Gramps, etc.")
        
    except Exception as e:
        print(f"Error during backup: {e}")

if __name__ == "__main__":
    main()
