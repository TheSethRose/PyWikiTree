from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from pywikitree import WikiTreeClient


class TestWikiTreeClient(unittest.TestCase):
    def test_get_profile_serializes_fields_list(self) -> None:
        session = MagicMock()
        response = MagicMock()
        response.status_code = 200
        response.raise_for_status.return_value = None
        response.json.return_value = [{"status": 0, "profile": {"Id": 1}}]
        session.post.return_value = response
        session.headers = {}

        client = WikiTreeClient(session=session)
        client.get_profile("Clemens-1", fields=["Id", "Name"])

        _, kwargs = session.post.call_args
        data = kwargs["data"]
        self.assertEqual(data["action"], "getProfile")
        self.assertEqual(data["key"], "Clemens-1")
        self.assertEqual(data["fields"], "Id,Name")

    def test_get_connections_requires_app_id(self) -> None:
        session = MagicMock()
        response = MagicMock()
        response.status_code = 200
        response.raise_for_status.return_value = None
        response.json.return_value = [{"status": 0}]
        session.post.return_value = response
        session.headers = {}

        client = WikiTreeClient(session=session)
        with self.assertRaises(ValueError):
            client.get_connections(["Adams-35", "Windsor-1"])


if __name__ == "__main__":
    unittest.main()
