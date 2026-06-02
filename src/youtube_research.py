"""
YouTube research module — fetch trending + top-performing videos for a niche.

Uses YouTube Data API v3:
  • videos.list?chart=mostPopular       → current trending in a category/region
  • search.list?q=...&order=viewCount   → top videos for a keyphrase
  • videos.list?id=...                  → batch-fetch stats/snippets for IDs
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from typing import List, Optional

try:
    from googleapiclient.discovery import build as build_youtube
    from googleapiclient.errors import HttpError as YouTubeHttpError
except ImportError:  # graceful degradation so the rest of the package can still be imported
    build_youtube = None
    YouTubeHttpError = Exception


@dataclass
class VideoRecord:
    video_id: str
    title: str
    channel_title: str
    published_at: str        # ISO-8601
    description: str
    tags: List[str]
    hashtags: List[str]      # #hashtags extracted from title/description
    view_count: int
    like_count: int
    comment_count: int
    duration_iso: str        # PT4M13S etc.
    category_id: Optional[str]
    thumbnail_url: str
    source: str              # "trending" | "search"
    rank: int                # rank in source feed

    def hours_since_publish(self) -> float:
        try:
            t = datetime.fromisoformat(self.published_at.replace("Z", "+00:00"))
            return max(0.1, (datetime.now(timezone.utc) - t).total_seconds() / 3600.0)
        except Exception:
            return 1.0

    def views_per_hour(self) -> float:
        return self.view_count / self.hours_since_publish()


@dataclass
class ResearchBundle:
    query: str
    region: str
    category_id: Optional[str]
    trending: List[VideoRecord] = field(default_factory=list)
    top_by_keyphrase: List[VideoRecord] = field(default_factory=list)
    raw_metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "region": self.region,
            "category_id": self.category_id,
            "trending_count": len(self.trending),
            "top_by_keyphrase_count": len(self.top_by_keyphrase),
            "trending": [asdict(v) for v in self.trending],
            "top_by_keyphrase": [asdict(v) for v in self.top_by_keyphrase],
            "raw_metadata": self.raw_metadata,
        }


_HASHTAG_RE = __import__("re").compile(r"#([A-Za-z0-9_]{2,40})")


def _extract_hashtags(text: str) -> List[str]:
    return list(dict.fromkeys(m.group(1).lower() for m in _HASHTAG_RE.finditer(text or "")))


class YouTubeResearcher:
    """Wraps the YouTube Data API client with quota-aware helpers."""

    def __init__(self, api_key: Optional[str] = None, region: str = "US"):
        self.api_key = api_key or os.getenv("YOUTUBE_API_KEY", "")
        self.region = region or os.getenv("YT_REGION", "US")
        self._client = None
        if self.api_key and build_youtube is not None:
            self._client = build_youtube("youtube", "v3", developerKey=self.api_key, cache_discovery=False)

    @property
    def is_configured(self) -> bool:
        return self._client is not None

    # ---------- low-level fetchers ----------

    def _fetch_trending(self, category_id: Optional[str], max_results: int = 25) -> List[dict]:
        """videos.list chart=mostPopular — current trending in region/category."""
        if not self.is_configured:
            return []
        items: List[dict] = []
        params = {
            "part": "snippet,statistics,contentDetails",
            "chart": "mostPopular",
            "regionCode": self.region,
            "maxResults": min(50, max_results),
        }
        if category_id:
            params["videoCategoryId"] = category_id
        try:
            resp = self._client.videos().list(**params).execute()
        except YouTubeHttpError as e:
            print(f"[warn] trending fetch failed: {e}")
            return items
        items.extend(resp.get("items", []))
        # paginate
        token = resp.get("nextPageToken")
        while token and len(items) < max_results:
            params["pageToken"] = token
            try:
                resp = self._client.videos().list(**params).execute()
            except YouTubeHttpError as e:
                print(f"[warn] trending pagination failed: {e}")
                break
            items.extend(resp.get("items", []))
            token = resp.get("nextPageToken")
        return items[:max_results]

    def _search_ids(self, query: str, max_results: int = 30, days_back: int = 90) -> List[str]:
        """search.list for the keyphrase, ordered by viewCount, restricted to recent uploads."""
        if not self.is_configured:
            return []
        params = {
            "part": "id",
            "q": query,
            "type": "video",
            "order": "viewCount",
            "regionCode": self.region,
            "relevanceLanguage": "en",
            "publishedAfter": (datetime.now(timezone.utc) - timedelta(days=days_back)).isoformat().replace("+00:00", "Z"),
            "maxResults": min(50, max_results),
        }
        ids: List[str] = []
        try:
            resp = self._client.search().list(**params).execute()
        except YouTubeHttpError as e:
            print(f"[warn] search fetch failed: {e}")
            return ids
        ids.extend(item["id"]["videoId"] for item in resp.get("items", []) if item.get("id", {}).get("videoId"))
        token = resp.get("nextPageToken")
        while token and len(ids) < max_results:
            params["pageToken"] = token
            try:
                resp = self._client.search().list(**params).execute()
            except YouTubeHttpError as e:
                print(f"[warn] search pagination failed: {e}")
                break
            ids.extend(item["id"]["videoId"] for item in resp.get("items", []) if item.get("id", {}).get("videoId"))
            token = resp.get("nextPageToken")
        # de-dupe, preserve order
        seen, out = set(), []
        for vid in ids:
            if vid not in seen:
                seen.add(vid); out.append(vid)
        return out[:max_results]

    def _hydrate(self, video_ids: List[str], source: str) -> List[VideoRecord]:
        """videos.list?part=snippet,statistics,contentDetails to enrich IDs."""
        if not self.is_configured or not video_ids:
            return []
        out: List[VideoRecord] = []
        # batch in chunks of 50
        for i in range(0, len(video_ids), 50):
            chunk = video_ids[i:i + 50]
            try:
                resp = self._client.videos().list(
                    part="snippet,statistics,contentDetails",
                    id=",".join(chunk),
                ).execute()
            except YouTubeHttpError as e:
                print(f"[warn] hydrate failed: {e}")
                continue
            for rank, item in enumerate(resp.get("items", []), start=i + 1):
                sn = item.get("snippet", {})
                stats = item.get("statistics", {})
                cd = item.get("contentDetails", {})
                desc = sn.get("description", "")
                tags = sn.get("tags", []) or []
                out.append(VideoRecord(
                    video_id=item["id"],
                    title=sn.get("title", ""),
                    channel_title=sn.get("channelTitle", ""),
                    published_at=sn.get("publishedAt", ""),
                    description=desc,
                    tags=tags,
                    hashtags=_extract_hashtags((sn.get("title", "") or "") + "\n" + desc),
                    view_count=int(stats.get("viewCount", 0) or 0),
                    like_count=int(stats.get("likeCount", 0) or 0),
                    comment_count=int(stats.get("commentCount", 0) or 0),
                    duration_iso=cd.get("duration", ""),
                    category_id=sn.get("categoryId"),
                    thumbnail_url=(sn.get("thumbnails", {}).get("high") or sn.get("thumbnails", {}).get("default") or {}).get("url", ""),
                    source=source,
                    rank=rank,
                ))
        return out

    # ---------- public API ----------

    def research(self, query: str, category_id: Optional[str] = None, max_per_source: int = 25) -> ResearchBundle:
        """Top-level: fetch trending + top videos for a query. Returns a ResearchBundle."""
        bundle = ResearchBundle(query=query, region=self.region, category_id=category_id)

        # 1. Trending in niche (or region-wide if no category hint)
        trending_raw = self._fetch_trending(category_id, max_results=max_per_source)
        trending_ids = [r["id"] for r in trending_raw if r.get("id")]
        bundle.trending = self._hydrate(trending_ids, source="trending")
        # 2. Top videos matching the script's keyphrases (last 90 days)
        ids = self._search_ids(query, max_results=max_per_source)
        bundle.top_by_keyphrase = self._hydrate(ids, source="search")

        bundle.raw_metadata = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "region": self.region,
            "category_id": category_id,
        }
        return bundle


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    r = YouTubeResearcher()
    if not r.is_configured:
        print("Set YOUTUBE_API_KEY in .env first.")
    else:
        bundle = r.research("how to use chatgpt", category_id="28", max_per_source=5)
        print(f"Trending: {len(bundle.trending)} | Top: {len(bundle.top_by_keyphrase)}")
        for v in bundle.trending[:3]:
            print(f" - {v.title} | {v.view_count:,} views | {v.views_per_hour():.0f}/hr")
