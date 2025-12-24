"""
Example: Watchlist Explorer
This script demonstrates how to authenticate and explore your WikiTree Watchlist.
It requires WIKITREE_EMAIL and WIKITREE_PASSWORD to be set in your environment.
"""

import os
from pywikitree.client import WikiTreeClient
from pywikitree.enums import WatchlistOrder

def main():
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
        watchlist = client.get_watchlist(
            limit=10, 
            order=WatchlistOrder.CHANGED,
            fields=["Name", "RealName", "BirthDate", "DeathDate", "Touched"]
        )
        
        if not watchlist:
            print("Your watchlist is empty or could not be retrieved.")
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
