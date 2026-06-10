
"""
Evidence Hunter v2 — Profile-Aware Search Query Generation
"""

import json
import logging
from typing import Optional, List, Dict

# Assuming search_service is a module with a singleton or class we can use
from services.search_service import search_service as global_search_service
# Also need llm_service if we want to use it, but the user's v2 code only used it for injection in __init__
# and didn't seem to use it in _generate_queries (it uses regex/heuristics there).
# I will stick to the user's provided code for EvidenceHunter.

logger = logging.getLogger(__name__)


class EvidenceHunter:
    """Generates targeted search queries from psychology profile and executes searches."""

    def __init__(self, search_service=None, llm_service=None):
        self.search = search_service if search_service else global_search_service
        self.llm = llm_service

    async def hunt(
        self,
        query: str,
        profile: Dict,
        classification: Dict,
    ) -> Dict:
        """
        Generate search queries from the profile and fetch results.
        Returns structured research data.
        """
        search_queries = self._generate_queries(query, profile, classification)

        if not search_queries:
            print("[HUNTER] ⚠️ Profile too thin, using fallback queries.")
            logger.warning("[HUNTER] No search queries generated — profile too thin")
            search_queries = self._fallback_queries(query, classification)

        print(f"[HUNTER] 🕵️ Generated {len(search_queries)} targeted search queries:")
        logger.info(f"[HUNTER] Executing {len(search_queries)} search queries")

        all_results = []
        for sq in search_queries:
            print(f"   ► Intent: {sq['intent']} -> Query: '{sq['query']}'")
            try:
                results = await self.search.search(
                    sq["query"], 
                    category=classification.get("topic_category")
                )
                tagged = [
                    {**r, "search_intent": sq["intent"], "search_query": sq["query"]}
                    for r in results
                ]
                all_results.extend(tagged)
                logger.info(f"[HUNTER] '{sq['intent']}': {len(results)} results")
                
                if results:
                     print(f"   ✅ Found {len(results)} results")
                else:
                     print(f"   ⚠️ No results found")

            except Exception as e:
                print(f"   ❌ Search failed: {e}")
                logger.error(f"[HUNTER] Search failed for '{sq['intent']}': {e}")

        # Deduplicate by URL
        seen_urls = set()
        unique_results = []
        for r in all_results:
            url = r.get("url", r.get("link", ""))
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_results.append(r)

        logger.info(f"[HUNTER] Total unique results: {len(unique_results)}")

        if not unique_results:
            return {
                "results": [],
                "sources": [],
                "queries_used": [],
                "source_count": 0,
                "sentiment_summary": "Insufficient data",
                "fact_bludgeons": ["No strong external evidence found"]
            }

        return {
            "results": unique_results[:15],  # Cap at 15
            "queries_used": [sq["query"] for sq in search_queries],
            "source_count": len(unique_results),
            # VerdictService expects: common_experiences, typical_outcomes, etc.
            # We arguably should return the raw results and let VerdictService process them,
            # OR we process them here. The user's provided code returns `results` list.
            # The existing VerdictService expects `sentiment_summary`, `sources`, etc.
            # I will add a method to structure them or just return what VerdictService needs if I can.
            # However, looking at the user's `generate_verdict_with_profile` placeholder in `chat.py` plan,
            # it receives `research`.
            # I will ensure `sources` is present as VerdictService relies on it.
            "sources": unique_results[:15],
            "sentiment_summary": self._analyze_sentiment(unique_results),
            "fact_bludgeons": self._extract_fact_bludgeons(unique_results),
        }

    def _extract_fact_bludgeons(self, results: List[Dict]) -> List[str]:
        facts = []
        for result in results[:5]:
            title = (result.get("title") or "").strip()
            snippet = (result.get("snippet") or "").strip()
            if title:
                facts.append(f"Fact: {title}")
            if snippet:
                facts.append(f"Fact: {snippet[:140]}")
        return facts[:5]

    def _analyze_sentiment(self, results: List[Dict]) -> str:
        """
        Heuristic sentiment analysis of search snippets.
        Counts positive vs negative markers in titles and snippets.
        """
        if not results:
            return "No data available"

        positive_markers = {
            "best decision", "worth it", "glad i did", "life changing", 
            "amazing", "success", "happy", "love it", "do it", "positive"
        }
        negative_markers = {
            "regret", "mistake", "wish i hadn't", "worst", "don't do it",
            "avoid", "waste", "trap", "nightmare", "depressed", "fail"
        }

        score = 0
        total_hits = 0

        for r in results:
            text = (r.get("title", "") + " " + r.get("snippet", "")).lower()
            
            # Check matches
            pos_hits = sum(1 for m in positive_markers if m in text)
            neg_hits = sum(1 for m in negative_markers if m in text)
            
            if pos_hits > neg_hits:
                score += 1
                total_hits += 1
            elif neg_hits > pos_hits:
                score -= 1
                total_hits += 1

        # Determine label
        if total_hits == 0:
            return "Neutral / Mixed"
        
        ratio = score / len(results)
        
        if ratio > 0.3:
            return "Mostly Positive (Encouraging)"
        elif ratio < -0.3:
            return "Mostly Negative (Warning Signs)"
        elif ratio > 0:
            return "Leaning Positive"
        elif ratio < 0:
            return "Leaning Negative"
        else:
            return "Controversial / Split"

    def _generate_queries(
        self,
        query: str,
        profile: Dict,
        classification: Dict,
    ) -> List[Dict]:
        """Generate search queries based on actual profile data."""
        queries = []
        # Profile might be nested or direct depending on how it's passed
        profile_data = profile.get("profile", profile)
        topic = classification.get("topic_category", "general")

        # ─── Query 1: Core decision + real experiences ────────────────
        # Always search for the actual decision topic
        clean_query = query.strip("?!. ").lower()
        if len(clean_query) > 10:
            queries.append({
                "intent": "real_experiences",
                "query": f'site:reddit.com "{self._extract_core_topic(clean_query)}" "I wish" OR "regret" OR "best decision"',
            })

        # ─── Query 2: Based on real_motivation ────────────────────────
        real_motivation = profile_data.get("real_motivation")
        if real_motivation and len(real_motivation) > 5:
            keywords = self._extract_keywords(real_motivation, max_words=4)
            queries.append({
                "intent": "motivation_validation",
                "query": f'site:reddit.com {keywords} experience "turned out"',
            })

        # ─── Query 3: Based on core_fear ──────────────────────────────
        core_fear = profile_data.get("core_fear") or profile_data.get("hidden_fear")
        if core_fear and len(core_fear) > 5:
            keywords = self._extract_keywords(core_fear, max_words=4)
            queries.append({
                "intent": "fear_validation",
                "query": f'site:reddit.com {keywords} "scared" OR "afraid" "I wish I"',
            })

        # ─── Query 4: Based on competence_gap ─────────────────────────
        competence_gap = profile_data.get("competence_gap")
        if competence_gap and len(competence_gap) > 5:
            keywords = self._extract_keywords(competence_gap, max_words=4)
            queries.append({
                "intent": "competence_stories",
                "query": f'site:reddit.com {keywords} "no experience" OR "first time" "mistake" OR "learned"',
            })

        # ─── Query 5: Topic-specific ──────────────────────────────────
        topic_queries = {
            "career": f'site:reddit.com {self._extract_core_topic(clean_query)} career advice "honestly"',
            "finance": f'site:reddit.com {self._extract_core_topic(clean_query)} money decision "regret" OR "worth it"',
            "relationship": f'site:reddit.com {self._extract_core_topic(clean_query)} relationship "looking back"',
            "education": f'site:reddit.com {self._extract_core_topic(clean_query)} degree "worth it" OR "waste"',
            "health": f'site:reddit.com {self._extract_core_topic(clean_query)} health decision "glad I did" OR "wish I hadn\'t"',
        }
        if topic == "entertainment":
            # For entertainment, we want metadata from IMDb (handled by SearchService)
            # AND Reddit discussions
            queries.append({
                "intent": "media_metadata",
                "query": self._extract_core_topic(clean_query), # Clean topic for IMDb
            })
            queries.append({
                "intent": "entertainment_specific",
                "query": f'site:reddit.com {self._extract_core_topic(clean_query)} movie review "worth watching"',
            })
        elif topic in topic_queries:
            queries.append({
                "intent": f"{topic}_specific",
                "query": topic_queries[topic],
            })

        return queries[:5]  # Max 5 queries

    def _fallback_queries(self, query: str, classification: Dict) -> List[Dict]:
        """When profile is too thin, generate generic but relevant queries."""
        core_topic = self._extract_core_topic(query.lower())
        topic = classification.get("topic_category", "general")

        return [
            {
                "intent": "general_experiences",
                "query": f'site:reddit.com {core_topic} "advice" "I did this" OR "regret"',
            },
            {
                "intent": "general_outcomes",
                "query": f'{core_topic} pros cons real experience reddit',
            },
        ]

    def _extract_core_topic(self, query: str, max_words: int = 5) -> str:
        """Extract the core topic from a query, removing fluff."""
        # Remove common question starters
        removals = [
            "should i", "should I", "is it worth", "do i need to",
            "would it be", "can i", "how do i", "what if i",
            "i'm thinking about", "i want to", "i need to",
            "thinking about", "considering", "debating",
        ]
        text = query.lower().strip("?!. ")
        for r in removals:
            text = text.replace(r, "")
        text = text.strip()

        words = text.split()[:max_words]
        return " ".join(words) if words else query[:30]

    def _extract_keywords(self, text: str, max_words: int = 4) -> str:
        """Extract meaningful keywords from a phrase."""
        stop_words = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "can", "shall",
            "to", "of", "in", "for", "on", "with", "at", "by", "from",
            "as", "into", "about", "that", "this", "it", "they", "them",
            "their", "i", "me", "my", "not", "but", "or", "and", "so",
            "if", "just", "very", "really", "too", "also", "than",
        }
        words = text.lower().split()
        keywords = [w.strip(",.!?;:'\"") for w in words if w.lower().strip(",.!?;:'\"") not in stop_words]
        return " ".join(keywords[:max_words])

# Global instance
evidence_hunter = EvidenceHunter()
