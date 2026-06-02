"""
Pattern analyzer — extract signals from the ResearchBundle.

Outputs an AnalysisReport with:
  • title formulas (with hit rate among top performers)
  • top tags (frequency + avg views)
  • top hashtags
  • description structure (length stats, common openers, CTA patterns, link presence)
  • velocity leaders (top videos by views/hour)
  • posting patterns (best hour-of-day, day-of-week)
"""
from __future__ import annotations

import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import List, Optional

from .youtube_research import ResearchBundle, VideoRecord
from .script_parser import ScriptAnalysis


# Title patterns we want to surface. Each is a regex + human label.
_TITLE_PATTERNS = [
    ("how_to",       r"\bhow to\b",                                                  "How-to"),
    ("number",       r"(\b\d{1,2}\s+(ways|tips|things|reasons|tricks|ideas|hacks|secrets|mistakes))", "Numbered list"),
    ("top_n",        r"\btop\s+\d+\b",                                               "Top N"),
    ("vs",           r"\bvs\.?\b|\bversus\b",                                        "Versus / compare"),
    ("question",     r"\?$",                                                         "Ends with question"),
    ("caps_hook",    r"\b[A-Z]{3,}\b",                                               "All-caps hook"),
    ("em_dash",      r"\s[–—]\s",                                                    "Em-dash separator"),
    ("paren",        r"\(.+\)",                                                      "Parentheses"),
    ("colon",        r":",                                                           "Has colon"),
    ("year",         r"\b(2024|2025|2026)\b",                                        "Year tag"),
    ("you",          r"\byou(r)?\b",                                                 "Direct address (you)"),
    ("i_tried",      r"\bi tried\b",                                                 "I tried …"),
    ("reaction",     r"\breact(ing|ion)?\b",                                         "Reaction"),
    ("the_truth",    r"\bthe truth\b|\btruth about\b",                               "Truth reveal"),
    ("dont_make",    r"\b(don'?t|never|stop)\b",                                     "Negative command"),
    ("this_is_why",  r"\bthis is (why|how)\b|\bhere'?s why\b",                       "This is why …"),
    ("secret",       r"\bsecret\b|\bhidden\b|\bno one\b",                            "Secret / hidden"),
    ("shocking",     r"\bshock(ing|ed)?\b|\binsane\b|\bunbelievable\b",              "Shock word"),
    ("we_need",      r"\bwe need to\b|\byou need to\b",                              "You/we need to"),
    ("under_xxx",    r"\bunder\s+\d+\b|\bin\s+\d+\s+(min|minutes|seconds|hours)\b",   "Time / quantity constraint"),
]

_CTA_PATTERNS = [
    ("subscribe",     r"\bsubscribe\b"),
    ("like",          r"\b(like|thumbs up)\b"),
    ("comment",       r"\bcomment\b|\bdrop a\b"),
    ("bell",          r"\b(notification)?\s?bell\b|\bhit the bell\b"),
    ("share",         r"\bshare\b"),
    ("follow",        r"\bfollow\b"),
    ("playlist",      r"\bplaylist\b"),
    ("link_in_desc",  r"\blink(s)? (in|in the) (description|desc|bio)\b"),
    ("next_video",    r"\bnext video\b|\bwatch next\b|\bpart \d+\b"),
    ("timestamps",    r"\b0:00\b|\btimestamps?\b"),
]

_DESCRIPTION_OPENER_PATTERNS = [
    ("emoji_line",     r"^[\U0001F300-\U0001FAFF\U00002600-\U000027BF]"),
    ("welcome",        r"^welcome\b"),
    ("hey",            r"^hey\b|^what'?s up\b"),
    ("in_this_video",  r"^in this video\b"),
    ("today",          r"^today\b"),
    ("if_you",         r"^if you\b"),
    ("question_hook",  r"^\w+ ?\?"),
    ("affiliate_disclaimer", r"^disclaimer|affiliate"),
    ("product_focus",  r"^in this\b|^today'?s video\b|^check out\b"),
    ("no_opener",      r"^.{1,80}$"),
]


@dataclass
class TitleFormula:
    name: str
    label: str
    matches: int
    match_rate: float
    avg_views: int
    example: str


@dataclass
class DescriptionStat:
    name: str
    label: str
    matches: int
    match_rate: float


@dataclass
class HashtagStat:
    tag: str
    frequency: int
    avg_views: int


@dataclass
class TagStat:
    tag: str
    frequency: int
    avg_views: int


@dataclass
class PostingStat:
    hour_local_best: int            # 0-23
    day_of_week_best: str           # Mon, Tue, ...
    hours_histogram: List[int]      # 24 entries
    dow_histogram: dict             # {"Mon": n, ...}


@dataclass
class AnalysisReport:
    total_videos: int
    velocity_leaders: List[VideoRecord] = field(default_factory=list)
    title_formulas: List[TitleFormula] = field(default_factory=list)
    tags: List[TagStat] = field(default_factory=list)
    hashtags: List[HashtagStat] = field(default_factory=list)
    description_stats: List[DescriptionStat] = field(default_factory=list)
    description_opener_stats: List[DescriptionStat] = field(default_factory=list)
    posting: Optional[PostingStat] = None
    median_views: int = 0
    median_vph: float = 0.0
    avg_duration_seconds: float = 0.0
    notes: List[str] = field(default_factory=list)


def _video_pool(bundle: ResearchBundle) -> List[VideoRecord]:
    """Combine trending + top-by-keyphrase, dedupe by video_id."""
    seen, out = set(), []
    for v in bundle.trending + bundle.top_by_keyphrase:
        if v.video_id not in seen:
            seen.add(v.video_id); out.append(v)
    return out


def _analyze_titles(videos: List[VideoRecord]) -> List[TitleFormula]:
    if not videos:
        return []
    out: List[TitleFormula] = []
    total_views = sum(v.view_count for v in videos) or 1
    for name, regex, label in _TITLE_PATTERNS:
        matched = [v for v in videos if re.search(regex, v.title, re.IGNORECASE)]
        if not matched:
            continue
        avg_views = sum(v.view_count for v in matched) // len(matched)
        out.append(TitleFormula(
            name=name, label=label,
            matches=len(matched),
            match_rate=len(matched) / len(videos),
            avg_views=avg_views,
            example=max(matched, key=lambda v: v.view_count).title,
        ))
    out.sort(key=lambda f: f.avg_views, reverse=True)
    return out


def _analyze_tags(videos: List[VideoRecord]) -> List[TagStat]:
    freq: Counter = Counter()
    views_by_tag: defaultdict[str, list] = defaultdict(list)
    for v in videos:
        for t in v.tags:
            tt = t.strip().lower()
            if not tt:
                continue
            freq[tt] += 1
            views_by_tag[tt].append(v.view_count)
    out = [
        TagStat(tag=tag, frequency=f, avg_views=int(sum(views_by_tag[tag]) / len(views_by_tag[tag])))
        for tag, f in freq.most_common(60)
    ]
    # sort by combined score: frequency * log(avg_views)
    out.sort(key=lambda s: s.frequency * (1 + __import__("math").log10(1 + s.avg_views)), reverse=True)
    return out


def _analyze_hashtags(videos: List[VideoRecord]) -> List[HashtagStat]:
    freq: Counter = Counter()
    views_by_tag: defaultdict[str, list] = defaultdict(list)
    for v in videos:
        for h in v.hashtags:
            freq[h] += 1
            views_by_tag[h].append(v.view_count)
    out = [
        HashtagStat(tag="#" + tag, frequency=f,
                    avg_views=int(sum(views_by_tag[tag]) / len(views_by_tag[tag])))
        for tag, f in freq.most_common(30)
    ]
    out.sort(key=lambda s: s.frequency * (1 + __import__("math").log10(1 + s.avg_views)), reverse=True)
    return out


def _analyze_descriptions(videos: List[VideoRecord]) -> List[DescriptionStat]:
    if not videos:
        return []
    out: List[DescriptionStat] = []
    for name, regex in _CTA_PATTERNS:
        matched = [v for v in videos if re.search(regex, v.description or "", re.IGNORECASE)]
        if not matched:
            continue
        out.append(DescriptionStat(
            name=name,
            label=name.replace("_", " ").title(),
            matches=len(matched),
            match_rate=len(matched) / len(videos),
        ))
    out.sort(key=lambda s: s.match_rate, reverse=True)
    return out


def _analyze_description_openers(videos: List[VideoRecord]) -> List[DescriptionStat]:
    if not videos:
        return []
    out: List[DescriptionStat] = []
    for name, regex in _DESCRIPTION_OPENER_PATTERNS:
        matched = [v for v in videos if re.search(regex, (v.description or "").strip(), re.IGNORECASE)]
        if not matched:
            continue
        out.append(DescriptionStat(
            name=name,
            label=name.replace("_", " ").title(),
            matches=len(matched),
            match_rate=len(matched) / len(videos),
        ))
    out.sort(key=lambda s: s.match_rate, reverse=True)
    return out


def _analyze_posting(videos: List[VideoRecord]) -> Optional[PostingStat]:
    if not videos:
        return None
    try:
        from datetime import datetime
        hours: Counter = Counter()
        dows: Counter = Counter()
        for v in videos:
            try:
                t = datetime.fromisoformat(v.published_at.replace("Z", "+00:00"))
                hours[t.hour] += 1
                dows[t.strftime("%a")] += 1
            except Exception:
                continue
        if not hours:
            return None
        return PostingStat(
            hour_local_best=hours.most_common(1)[0][0],
            day_of_week_best=dows.most_common(1)[0][0] if dows else "—",
            hours_histogram=[hours.get(h, 0) for h in range(24)],
            dow_histogram=dict(dows),
        )
    except Exception:
        return None


def _parse_duration_iso(iso: str) -> int:
    """PT1H2M3S → seconds."""
    if not iso:
        return 0
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso)
    if not m:
        return 0
    h, mn, s = m.groups()
    return (int(h or 0) * 3600) + (int(mn or 0) * 60) + int(s or 0)


def analyze(bundle: ResearchBundle, script: Optional[ScriptAnalysis] = None) -> AnalysisReport:
    pool = _video_pool(bundle)
    if not pool:
        return AnalysisReport(total_videos=0, notes=["No videos to analyze — check API key and query."])

    pool_sorted_vph = sorted(pool, key=lambda v: v.views_per_hour(), reverse=True)
    title_formulas = _analyze_titles(pool)
    tags = _analyze_tags(pool)
    hashtags = _analyze_hashtags(pool)
    desc_ctas = _analyze_descriptions(pool)
    desc_openers = _analyze_description_openers(pool)
    posting = _analyze_posting(pool)

    median_views = int(statistics.median([v.view_count for v in pool])) if pool else 0
    median_vph = float(statistics.median([v.views_per_hour() for v in pool])) if pool else 0.0
    avg_dur = statistics.mean(_parse_duration_iso(v.duration_iso) for v in pool) if pool else 0.0

    notes: List[str] = []
    if script and script.suggested_category_name:
        notes.append(f"Detected niche: {script.suggested_category_name} (categoryId {script.suggested_category_id}).")
    if median_vph:
        notes.append(f"Median views/hour across the pool: {median_vph:,.0f}. Top 5% set the bar.")

    return AnalysisReport(
        total_videos=len(pool),
        velocity_leaders=pool_sorted_vph[:10],
        title_formulas=title_formulas,
        tags=tags,
        hashtags=hashtags,
        description_stats=desc_ctas,
        description_opener_stats=desc_openers,
        posting=posting,
        median_views=median_views,
        median_vph=median_vph,
        avg_duration_seconds=avg_dur,
        notes=notes,
    )
