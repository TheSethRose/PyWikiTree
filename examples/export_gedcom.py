"""
Example: GEDCOM Exporter
This script demonstrates how to crawl a family tree and export it to a 
standard GEDCOM 5.5.1 file.
"""

import os
from pathlib import Path
from pywikitree import WikiTreeClient, GedcomExporter

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
    
    # Get credentials from environment
    email = os.getenv("WIKITREE_EMAIL")
    password = os.getenv("WIKITREE_PASSWORD")
    
    client = WikiTreeClient()
    
    # 1. Authenticate (optional but recommended for private profiles)
    if email and password:
        print(f"Authenticating as {email}...")
        client.authenticate(email=email, password=password)
    else:
        print("No credentials found. Exporting public data only.")

    # 2. Choose a root profile
    # If logged in, we can use the user's own profile name
    root_profile = "Clemens-1" # Mark Twain as a default example
    if client.auth:
        root_profile = client.auth.user_name
        
    print(f"Crawling tree starting from {root_profile}...")
    
    try:
        # 3. Fetch the tree (5 generations of ancestors + their relatives)
        people = client.get_tree(root_profile, ancestor_depth=5, include_relatives=True)
        print(f"Found {len(people)} people in the tree.")
        
        if not people:
            print("No data found to export.")
            return
            
        # 4. Export to GEDCOM
        print("Generating GEDCOM file...")
        exporter = GedcomExporter(people)
        gedcom_content = exporter.export()
        
        output_file = f"{root_profile}_export.ged"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(gedcom_content)
            
        print(f"Successfully exported to {output_file}")
        
    except Exception as e:
        print(f"Error during export: {e}")
    finally:
        if client.auth:
            client.logout()

if __name__ == "__main__":
    main()
