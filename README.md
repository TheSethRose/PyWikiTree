# PyWikiTree

A Python client for the [WikiTree API](https://github.com/wikitree/wikitree-api).

## Features

- Complete coverage of all documented WikiTree API endpoints
- Built-in authentication support (`clientLogin` flow)
- Automatic retry/backoff for rate limiting (HTTP 429)
- Session-based cookie management
- Type hints and enum support for parameters
- Minimal opinionated parsing - returns raw API JSON
- Environment variable configuration support

## Installation

```bash
pip install -e .
```

## Quick Start

```pypywikitree
from wikitree_api_client import WikiTreeClient

# Create client with your app ID (recommended for all requests)
client = WikiTreeClient(app_id="YourAppName")

# Get a public profile
profile = client.get_profile("Clemens-1", fields=["Id", "Name", "BirthDate"])
print(profile[0]["profile"])

# Search for people
results = client.search_person(FirstName="Samuel", LastName="Clemens")
print(f"Found {results[0]['total']} matches")

# Get multiple profiles with relationships
people = client.get_people(
    ["Clemens-1", "Windsor-1"], 
    fields=["Id", "Name", "BirthDate"],
    ancestors=2  # Include 2 generations of ancestors
)

# Authenticate for private/trusted profiles (optional)
auth = client.authenticate(email="you@example.com", password="your_password")
watchlist = client.get_watchlist(limit=10)
```

## Available Endpoints

All documented API actions are supported:
- `get_profile()` / `get_person()` - Single profile retrieval
- `get_people()` - Multiple profiles with relationship expansion
- `get_ancestors()` / `get_descendants()` - Multi-generation family trees
- `get_relatives()` - Parents, children, siblings, spouses
- `get_watchlist()` - User's watchlist (requires auth)
- `search_person()` - Search for profiles
- `get_bio()` / `get_photos()` / `get_categories()` - Profile data
- `get_connections()` - Relationship paths between profiles
- `get_dna_*()` - DNA test information
- `authenticate()` / `check_login()` / `logout()` - Session management

## Configuration
### Direct Configuration

```python
from pywikitree import WikiTreeClient

client = WikiTreeClient(
    app_id="YourApp",           # Recommended for all requests
    max_retries=3,              # Retry on 429/5xx errors
    retry_backoff_s=2.0,        # Initial backoff time
    timeout_s=30.0,             # Request timeout
    raise_on_api_status=True    # Raise exception on API errors
)
```

### Environment Variables

Configure via environment variables (see `.env.example`):

```bash
export WIKITREE_APP_ID="YourAppName"
export WIKITREE_MAX_RETRIES=3
export WIKITREE_RETRY_BACKOFF_S=2.0
export WIKITREE_TIMEOUT_S=30.0
```

Then create the client without parameters:

```python
from pywikitree import WikiTreeClient

# Will automatically use environment variables
client = WikiTreeClient(    raise_on_api_status=True    # Raise exception on API errors
)
```

The API uses an authentication flow that ultimately relies on cookies for the `api.wikitree.com` domain.

For browserless scripts, this client supports the two-step flow described in `wikitree-api/authentication.md`:

1. `clientLogin` + `doLogin=1` with `wpEmail` and `wpPassword` (captures `authcode` from the redirect `Location` header)
2. `clientLogin` with that `authcode`

You can persist cookies via `save_cookies()` / `load_cookies()`.
