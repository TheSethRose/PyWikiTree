"""
Example: Watchlist Explorer
This script demonstrates how to authenticate and explore your WikiTree Watchlist.
It requires WIKITREE_EMAIL and WIKITREE_PASSWORD to be set in your environment.
"""

import os
from pathlib import Path
from pywikitree.client import WikiTreeClient
from pywikitree.enums import WatchlistOrder

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
    
    if not email or not password:
        print("Error: WIKITREE_EMAIL and WIKITREE_PASSWORD environment variables must be set.")
        print("Please update your .env file.")
        return

    client = WikiTreeClient()
    
    try:
        # 1. Authenticate
        print(f"Authenticating as {email}...")
        auth = client.authenticate(email=email, password=password)
        print(f"Successfully logged in as {auth.user_name} (ID: {auth.user_id})\n")
        
        # 2. Fetch Watchlist
        # We'll fetch the 10 most recently modified profiles
        print("Fetching your 10 most recently modified watchlist profiles...")
        response = client.get_watchlist(
            limit=10, 
            order=WatchlistOrder.PAGE_TOUCHED,
            fields=["Name", "RealName", "BirthDate", "DeathDate", "Touched"]
        )
        
        if not response:
            print("Your watchlist is empty or could not be retrieved.")
            return

        # Debug: print response type and keys
        # print(f"DEBUG: Response type: {type(response)}")
        # if isinstance(response, list):
        #     print(f"DEBUG: List length: {len(response)}")
        #     if len(response) > 0:
        #         print(f"DEBUG: First item keys: {response[0].keys()}")
        
        # The API usually returns a list with one item containing the data
        if isinstance(response, list) and len(response) > 0:
            data = response[0]
            watchlist = data.get("watchlist", [])
        else:
            watchlist = []
            
        if not watchlist:
            print("No profiles found in watchlist.")
            return
            
        print(f"{'Name':<25} | {'Touched':<20} | {'Dates'}")
        print("-" * 70)
        
        for item in watchlist:
            # The watchlist items are person objects
            name = item.get("RealName", "Unknown")
            wt_id = item.get("Name", "Unknown")
            touched = item.get("Touched", "Unknown")
            birth = item.get("BirthDate", "????")
            death = item.get("DeathDate", "????")
            
            display_name = f"{name} ({wt_id})"
            dates = f"{birth} - {death}"
            
            print(f"{display_name[:25]:<25} | {touched:<20} | {dates}")
            
        # 3. Logout (optional but good practice)
        client.logout()
        print("\nLogged out successfully.")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
