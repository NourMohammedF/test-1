"""
Web research module — optional cross-platform trend signals.

Uses SerpAPI (https://serpapi.com) if SERPAPI_KEY is set, to pull:
  • Google News headlines for the niche
  • Reddit top posts (r/all or niche subreddits) — surfaces of-the-moment discussions

Falls back to no-op if no key is configured; the rest of the pipeline
still works on YouTube-only signal.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional

import requests


@dataclass
class WebSignal:
    title: str
    url: str
    source: str        # "google_news" | "reddit" | ...
    snippet: str = ""
    engagement: int = 0


@dataclass
class WebBundle:
    query: str
    news: List[WebSignal] = field(default_factory=list)
    reddit: List[WebSignal] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class WebResearcher:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("SERPAPI_KEY", "")

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _serp(self, params: dict) -> dict:
        base = "https://serpapi.com/search.json"
        params = {**params, "api_key": self.api_key, "num": 10}
        r = requests.get(base, params=params, timeout=20)
        r.raise_for_status()
        return r.json()

    def research(self, query: str, subreddit: Optional[str] = None) -> WebBundle:
        bundle = WebBundle(query=query)

        if not self.is_configured:
            bundle.errors.append("SERPAPI_KEY not set — skipping web research")
            return bundle

        # Google News
        try:
            data = self._serp({
                "engine": "google_news",
                "q": query,
                "gl": "us",
                "hl": "en",
                "when": "7d",   # last 7 days
            })
            for item in (data.get("news_results") or [])[:10]:
                bundle.news.append(WebSignal(
                    title=item.get("title", ""),
                    url=item.get("link", ""),
                    source="google_news",
                    snippet=item.get("snippet", ""),
                ))
        except Exception as e:
            bundle.errors.append(f"google_news: {e}")

        # Reddit
        try:
            site = f"reddit.com/r/{subreddit}" if subreddit else "reddit.com"
            data = self._serp({
                "engine": "google",
                "q": f"site:{site} {query}",
                "tbs": "qdr:w",  # past week
            })
            for item in (data.get("organic_results") or [])[:10]:
                bundle.reddit.append(WebSignal(
                    title=item.get("title", ""),
                    url=item.get("link", ""),
                    source="reddit",
                    snippet=item.get("snippet", ""),
                ))
        except Exception as e:
            bundle.errors.append(f"reddit: {e}")

        return bundle


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    r = WebResearcher()
    if not r.is_configured:
        print("Set SERPAPI_KEY in .env to enable web research.")
    else:
        b = r.research("openai gpt-5", subreddit="artificial")
        print(f"News: {len(b.news)} | Reddit: {len(b.reddit)}")
        for n in b.news[:3]:
            print(f" - NEWS: {n.title}")
        for n in b.reddit[:3]:
            print(f" - REDDIT: {n.title}")
