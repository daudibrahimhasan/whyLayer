"""
Search Service v2 — Reliable Multi-Provider Search
"""

import httpx
import json
import logging
import os
import random
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

# ─── Curated SearXNG instances (tested & working as of 2025) ─────────────────
SEARXNG_INSTANCES = [
    "https://search.bus-hit.me",
    "https://searx.prvcy.eu",
    "https://search.inetol.net",
    "https://searx.work",
    "https://search.rhscz.eu",
    "https://searxng.site",
    "https://etsi.me",
    "https://s.mble.dk",
]


class SearchService:
    """Multi-provider search with automatic fallback."""

    def __init__(self):
        self.serper_key = os.getenv("SERPER_API_KEY")  # Free tier: 2500 queries
        self.jina_key = os.getenv("JINA_API_KEY")
        self._searxng_failures: Dict[str, int] = {}  # Track which instances are dead
        self._cache: Dict[str, List] = {}

    async def search(self, query: str, num_results: int = 5, category: Optional[str] = None) -> List[Dict]:
        """
        Search with automatic fallback chain and domain awareness.
        Categories: general, entertainment, academic, etc.
        """
        # Check cache
        cache_key = f"{category}:{query.strip().lower()}"
        if cache_key in self._cache:
            logger.info(f"[SEARCH] Cache hit for: {query[:50]}...")
            return self._cache[cache_key]

        results = []

        # ─── Domain-Specific Routing ──────────────────────────────────
        q_lower = query.lower()
        if category == "entertainment" or "movie" in q_lower or "series" in q_lower or "anime" in q_lower or "manga" in q_lower:
            
            # 1. Jikan: If anime/manga explicitly mentioned OR likely anime context
            if "anime" in q_lower or "manga" in q_lower or "jujutsu" in q_lower or "bleach" in q_lower:
                print(f"[SEARCH] 🗾 Querying Jikan (Anime): '{query}'")
                jikan_results = await self._search_jikan(query, num_results)
                if jikan_results:
                     print(f"[SEARCH] ✅ Jikan found {len(jikan_results)} results")
                     self._cache[cache_key] = jikan_results
                     return jikan_results

            # 2. IMDb: Default for entertainment/movies/series
            print(f"[SEARCH] 🎬 Querying IMDb (UnOfficial): '{query}'")
            imdb_results = await self._search_imdb(query, num_results)
            if imdb_results:
                print(f"[SEARCH] ✅ IMDb found {len(imdb_results)} results")
                self._cache[cache_key] = imdb_results
                return imdb_results

        # ─── Standard Fallback Chain ─────────────────────────────────
        
        # 1. Serper (if key exists — most reliable)
        if self.serper_key:
            print(f"[SEARCH] 🔍 Querying Serper.dev: '{query}'")
            results = await self._search_serper(query, num_results)
            if results:
                print(f"[SEARCH] ✅ Serper found {len(results)} results")
                self._cache[cache_key] = results
                return results

        # 2. SearXNG
        print(f"[SEARCH] 🔄 Querying SearXNG network: '{query}'")
        results = await self._search_searxng(query, num_results)
        if results:
            print(f"[SEARCH] ✅ SearXNG found {len(results)} results")
            self._cache[cache_key] = results
            return results

        # 3. Wikipedia Fallback
        print(f"[SEARCH] 📖 Querying Wikipedia: '{query}'")
        results = await self._search_wikipedia(query, num_results)
        if results:
            print(f"[SEARCH] ✅ Wikipedia found {len(results)} results")
            self._cache[cache_key] = results
            return results

        print(f"[SEARCH] ❌ All providers failed for: '{query}'")
        logger.warning(f"[SEARCH] All providers failed for: {query[:50]}...")
        return []

    async def _search_jikan(self, query: str, num_results: int) -> List[Dict]:
        """Jikan API (v4) — Unofficial MyAnimeList API."""
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                # https://docs.api.jikan.moe/#tag/anime/operation/getAnimeSearch
                response = await client.get(
                    "https://api.jikan.moe/v4/anime",
                    params={"q": query, "limit": num_results, "sfw": True},
                )
                response.raise_for_status()
                data = response.json()
                
                results = []
                for item in data.get("data", []):
                    title = item.get("title", "Unknown")
                    synopsis = item.get("synopsis", "")
                    score = item.get("score", 0)
                    url = item.get("url", "")
                    
                    if title:
                        results.append({
                            "title": f"{title} (Anime)",
                            "url": url,
                            "snippet": f"Score: {score}/10. {synopsis[:200]}...",
                            "source": "jikan_anime"
                        })
                
                return results

        except Exception as e:
            logger.error(f"[SEARCH] Jikan failed: {e}")
            return []

    async def _search_imdb(self, query: str, num_results: int) -> List[Dict]:
        """IMDb (Unofficial API) — For movies/series."""
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                # Based on user's provided URL structure
                response = await client.get(f"https://imdb.iamidiotareyoutoo.com/search?q={query}")
                response.raise_for_status()
                data = response.json()
                
                # The API typically returns a list of objects with title, year, image, distinct
                # Let's inspect known format or adapt dynamically
                # Assuming list of dicts: [{"#TITLE": "Inception", "#YEAR": 2010, "#IMDB_ID": "tt1375666", ...}]
                # Or standard {"description": [...]}
                
                results = []
                # Handle likely list response directly
                items = data.get("description", []) if isinstance(data, dict) else data
                
                for item in items[:num_results]:
                    title = item.get("#TITLE", item.get("title", "Unknown"))
                    year = item.get("#YEAR", item.get("year", ""))
                    imdb_id = item.get("#IMDB_ID", item.get("imdb_id", ""))
                    actors = item.get("#ACTORS", item.get("actors", ""))
                    
                    if title:
                        results.append({
                            "title": f"{title} ({year})",
                            "url": f"https://www.imdb.com/title/{imdb_id}" if imdb_id else "",
                            "snippet": f"Actors: {actors}. IMDb ID: {imdb_id}",
                            "source": "imdb"
                        })
                
                return results

        except Exception as e:
            logger.error(f"[SEARCH] IMDb failed: {e}")
            return []

    async def _search_serper(self, query: str, num_results: int) -> List[Dict]:
        """Serper.dev — Free tier: 2500 queries/month."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    "https://google.serper.dev/search",
                    json={"q": query, "num": num_results},
                    headers={
                        "X-API-KEY": self.serper_key,
                        "Content-Type": "application/json",
                    },
                )
                response.raise_for_status()
                data = response.json()

                results = []
                for item in data.get("organic", [])[:num_results]:
                    results.append({
                        "title": item.get("title", ""),
                        "url": item.get("link", ""),
                        "snippet": item.get("snippet", ""),
                        "source": "serper",
                    })

                if results:
                    logger.info(f"[SEARCH] Serper returned {len(results)} results")
                return results

        except Exception as e:
            logger.error(f"[SEARCH] Serper failed: {e}")
            return []

    async def _search_searxng(self, query: str, num_results: int) -> List[Dict]:
        """Try multiple SearXNG instances with smart rotation."""
        # Filter out recently failed instances
        available = [
            inst for inst in SEARXNG_INSTANCES
            if self._searxng_failures.get(inst, 0) < 3
        ]

        if not available:
            # Reset failures if all instances are marked dead
            self._searxng_failures.clear()
            available = SEARXNG_INSTANCES.copy()

        random.shuffle(available)

        for instance in available[:3]:  # Try max 3 instances
            try:
                async with httpx.AsyncClient(timeout=8) as client:
                    response = await client.get(
                        f"{instance}/search",
                        params={
                            "q": query,
                            "format": "json",
                            "pageno": 1,
                            "categories": "general",
                        },
                        headers={"User-Agent": "whyLayer/2.2"},
                    )
                    response.raise_for_status()
                    data = response.json()

                    results = []
                    for item in data.get("results", [])[:num_results]:
                        results.append({
                            "title": item.get("title", ""),
                            "url": item.get("url", ""),
                            "snippet": item.get("content", ""),
                            "source": f"searxng:{instance.split('//')[1].split('/')[0]}",
                        })

                    if results:
                        logger.info(f"[SEARCH] SearXNG ({instance}) returned {len(results)} results")
                        # Reset failure count on success
                        self._searxng_failures[instance] = 0
                        return results

            except Exception as e:
                self._searxng_failures[instance] = self._searxng_failures.get(instance, 0) + 1
                logger.debug(f"[SEARCH] SearXNG {instance} failed ({self._searxng_failures[instance]}x): {type(e).__name__}")
                continue

        return []

    async def _search_wikipedia(self, query: str, num_results: int) -> List[Dict]:
        """Wikipedia API — Free, high-quality, factual."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                # 1. Search for titles
                search_params = {
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "format": "json",
                    "srlimit": num_results
                }
                search_resp = await client.get("https://en.wikipedia.org/w/api.php", params=search_params)
                search_data = search_resp.json()
                
                search_results = search_data.get("query", {}).get("search", [])
                if not search_results:
                    return []
                
                # 2. Get extracts for top results
                page_ids = "|".join(str(r["pageid"]) for r in search_results)
                extract_params = {
                    "action": "query",
                    "pageids": page_ids,
                    "prop": "extracts|info",
                    "inprop": "url",
                    "exintro": True,
                    "explaintext": True,
                    "format": "json"
                }
                extract_resp = await client.get("https://en.wikipedia.org/w/api.php", params=extract_params)
                extract_data = extract_resp.json()
                pages = extract_data.get("query", {}).get("pages", {})
                
                results = []
                for pid, page in pages.items():
                    if "extract" in page and page["extract"]:
                        results.append({
                            "title": page["title"],
                            "url": page.get("fullurl", f"https://en.wikipedia.org/?curid={pid}"),
                            "snippet": page["extract"][:300] + "...",
                            "source": "wikipedia"
                        })
                
                if results:
                    print(f"[SEARCH] ✅ Wikipedia found {len(results)} results")
                return results

        except Exception as e:
            logger.error(f"[SEARCH] Wikipedia failed: {e}")
            return []

# Global instance
search_service = SearchService()
