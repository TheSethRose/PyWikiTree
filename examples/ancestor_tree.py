"""
Example: Ancestor Tree Traversal
This script demonstrates how to fetch ancestors for a specific profile and 
display them in a simple text-based tree structure.
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

def print_tree(person, ancestors, depth=0):
    """Recursively print the ancestor tree."""
    indent = "  " * depth
    name = person.get("Name", "Unknown")
    real_name = person.get("RealName", "Unknown")
    birth_date = person.get("BirthDate", "????")
    
    print(f"{indent}└─ {real_name} ({name}) b. {birth_date}")
    
    # Find parents in the ancestors list
    father_id = person.get("Father")
    mother_id = person.get("Mother")
    
    if father_id and str(father_id) != "0":
        father = next((p for p in ancestors if str(p.get("Id")) == str(father_id)), None)
        if father:
            print_tree(father, ancestors, depth + 1)
            
    if mother_id and str(mother_id) != "0":
        mother = next((p for p in ancestors if str(p.get("Id")) == str(mother_id)), None)
        if mother:
            print_tree(mother, ancestors, depth + 1)

def main():
    load_env()
    # Initialize the client. 
    # It will automatically use WIKITREE_APP_ID from your .env file if present.
    client = WikiTreeClient()
    
    # We'll use a well-known public profile: Clemens-1 (Samuel Langhorne Clemens / Mark Twain)
    target_profile = "Clemens-1"
    print(f"Fetching ancestors for {target_profile}...")
    
    try:
        # Fetch 3 generations of ancestors
        response = client.get_ancestors(target_profile, depth=3)
        
        if not response or not isinstance(response, list):
            print(f"No ancestors found or invalid response: {response}")
            return

        # The API returns a list with one item containing the 'ancestors' list
        data = response[0]
        ancestors = data.get("ancestors", [])
        
        if not ancestors:
            print("No ancestors found in response.")
            return

        # The first person in the ancestors list is the target
        root_person = ancestors[0]
        
        print("\nAncestor Tree:")
        print_tree(root_person, ancestors)
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
