"""
Parallel AI Intelligence Client (api.parallel.ai).
Leverages Parallel's Web Intelligence, Search, and Extract APIs
to ground the Cognitive Safety Agent with live Andhra Pradesh road,
weather, blackspot, and trauma hospital intelligence.
"""

import os
import json
import urllib.request
import urllib.error
from typing import Dict, List, Optional, Any

PARALLEL_API_KEY = os.getenv("PARALLEL_API_KEY", "bhuFWb9Z_gKmuCnqguG1wEODVVc0SXBg73hT19QN")
PARALLEL_BASE_URL = "https://api.parallel.ai/v1"


class ParallelClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or PARALLEL_API_KEY

    def search_highway_intel(self, query: str, objective: str = "Live highway safety and traffic intelligence") -> List[Dict[str, Any]]:
        """
        Executes a targeted search using Parallel's /v1/search API.
        Returns ranked sources and summaries.
        """
        if not self.api_key:
            return []

        url = f"{PARALLEL_BASE_URL}/search"
        payload = {
            "objective": objective,
            "search_queries": [query],
        }

        req = urllib.request.Request(
            url,
            headers={
                "x-api-key": self.api_key,
                "Content-Type": "application/json",
                "User-Agent": "HighwaySafetyAgent/1.0",
            },
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                results = data.get("results", [])
                formatted = []
                for r in results[:3]:
                    formatted.append({
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "snippet": r.get("snippet", "") or r.get("description", ""),
                    })
                return formatted
        except Exception as e:
            print(f"[ParallelClient] Search warning: {e}")
            return []

    def get_corridor_intel(self, corridor_name: str, km_marker: str, incident_type: str) -> Optional[str]:
        """
        Generates contextual safety intelligence using Parallel AI search.
        """
        query = f"Andhra Pradesh {corridor_name} {km_marker} traffic accident blackspot guidelines"
        objective = f"Retrieve safety protocols and trauma facility info for {incident_type} on {corridor_name}"
        results = self.search_highway_intel(query, objective)
        if not results:
            return None

        top = results[0]
        title = top.get("title") or "Andhra Pradesh Highway Corridor Intelligence"
        return f"Parallel AI Intelligence [{title}]: Live highway safety protocols active for {corridor_name}."


parallel_client = ParallelClient()
