"""
Generator — synthesize the final deliverables from analysis + script.

Produces:
  • 3-5 title variants using the highest-performing formulas
  • Optimized description (hook → summary → CTAs → hashtags → links placeholders → timestamps)
  • Optimized tags (broad + long-tail, mixed frequencies)
  • Hashtag set (top performer hashtags + niche hashtags)
  • Thumbnail brief
  • Reasoning & confidence notes
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from .analyzer import AnalysisReport
from .script_parser import ScriptAnalysis


@dataclass
class GeneratedMetadata:
    title_variants: List[str]
    description: str
    tags: List[str]
    hashtags: List[str]
    thumbnail_brief: str
    reasoning: List[str] = field(default_factory=list)
    confidence: str = "low"  # low | medium | high


# -------- helpers --------

def _brand_map_from_script(script: ScriptAnalysis) -> dict:
    """Map lowercase brand tokens to their original casing from the script."""
    m = {}
    for e in script.entities:
        m[e.lower()] = e
    return m


def _title_case_phrase(s: str, brand_map: Optional[dict] = None) -> str:
    """Preserve brand-shaped tokens; title-case the rest. Strips trailing junk.

    `brand_map` lets you force brand casing — e.g. {"chatgpt": "ChatGPT"}.
    """
    if not s:
        return ""
    preserve = {"ai", "gpt", "ios", "macos", "nasa", "mlb", "nba", "nfl", "uefa", "ufo",
                "vr", "ar", "pc", "yt", "4k", "hd", "llm", "ml"}
    brand_map = brand_map or {}
    words = []
    for w in s.split():
        lw = w.lower()
        if lw in brand_map:
            words.append(brand_map[lw])
        elif lw in preserve:
            words.append(w.upper() if lw in {"ai", "gpt", "vr", "ar", "pc", "yt", "hd", "4k"} else w.upper())
        elif any(c.isupper() for c in w[1:]):  # mixed-case brand (ChatGPT, iPhone)
            words.append(w)
        else:
            words.append(w.capitalize())
    return " ".join(words)


def _pick_top_tag_combinations(tags: List, n: int = 12) -> List[str]:
    """Mix of most-frequent + best-velocity, with a soft cap on total."""
    seen, out = set(), []
    for t in tags:
        lt = t.tag.lower()
        if lt not in seen:
            seen.add(lt); out.append(t.tag)
        if len(out) >= n:
            break
    return out


def _best_formula_names(report: AnalysisReport, k: int = 2) -> List[str]:
    """Pick the k highest-velocity title formula names that should be combined."""
    return [f.name for f in report.title_formulas[:k]]


def _format_timestamp_chapter(idx: int, hms: str, label: str) -> str:
    return f"{hms} — {_title_case_phrase(label)}"


# -------- title generation --------

def generate_title_variants(script: ScriptAnalysis, report: AnalysisReport) -> List[str]:
    bmap = _brand_map_from_script(script)
    base = _title_case_phrase(script.primary_topic, bmap) if script.primary_topic else "This Topic"
    formula_names = {f.name for f in report.title_formulas}
    formula_names_set = formula_names
    year = datetime.now().year
    variants: List[str] = []

    # How-to (the most reliable evergreen formula)
    if "how_to" in formula_names_set or not formula_names_set:
        variants.append(f"How to {base} the Right Way ({year})")
    # Numbered / Top-N list
    if "number" in formula_names_set or "top_n" in formula_names_set:
        variants.append(f"7 {base} Tips That Actually Work")
    # The truth / secret reveal
    if "shocking" in formula_names_set or "secret" in formula_names_set or "the_truth" in formula_names_set:
        variants.append(f"The Truth About {base} Nobody Tells You")
    # I-tried
    if "i_tried" in formula_names_set:
        variants.append(f"I Tried {base} for 30 Days — Here's What Happened")
    # Fallback
    if not variants:
        variants.append(f"Everything You Need to Know About {base}")
    # Always have at least one question-hook
    if not any("?" in v for v in variants):
        variants.append(f"Why Is Everyone Talking About {base}?")

    # de-dupe, trim to 5
    seen, final = set(), []
    for v in variants:
        if v.lower() not in seen:
            seen.add(v.lower()); final.append(v)
        if len(final) >= 5:
            break
    return final


# -------- description generation --------

def _readable_topic(s: ScriptAnalysis) -> str:
    """Turn a primary_topic into a readable phrase for the description body.

    If the topic is a single token (e.g. 'chatgpt'), we treat it as a brand/product.
    If it's a verb-phrase (e.g. 'work using chatgpt'), we humanize it.
    """
    pt = (s.primary_topic or "").strip()
    if not pt:
        return "this topic"
    bmap = _brand_map_from_script(s)
    if s.entities and pt.lower() == s.entities[0].lower():
        return s.entities[0]
    if " " in pt:
        return _title_case_phrase(pt, bmap)
    return _title_case_phrase(pt, bmap)


def generate_description(script: ScriptAnalysis, report: AnalysisReport) -> str:
    """Build a multi-section description driven by the top opener + CTA patterns from the data."""
    topic = _readable_topic(script)
    year = datetime.now().year
    bmap = _brand_map_from_script(script)

    opener_pool = [o for o in report.description_opener_stats if o.match_rate >= 0.15]
    opener_label = opener_pool[0].label if opener_pool else "Welcome"

    # pick a strong opener template based on the most common pattern in the niche
    openers = {
        "Welcome":        f"Welcome back! In today's video, we break down {topic} — what it is, why it matters, and exactly how to use it.",
        "Hey":            f"Hey! If you've been wanting to master {topic}, this is the video for you.",
        "In This Video":  f"In this video on {topic}, I'll walk you through everything step by step.",
        "Today":          f"Today we're diving into {topic} — the trends, the data, and what you should actually do.",
        "If You":         f"If you've been searching for the real story on {topic}, you're in the right place.",
        "Question Hook":  f"Want to actually understand {topic}? Let's get into it.",
        "Emoji Line":     f"🔥 {topic} — explained the way it should be.",
        "Product Focus":  f"Today we're covering {topic} — what's working right now, and what's not.",
    }
    opener = openers.get(opener_label, openers["Welcome"])

    # hook + body
    body = (
        f"\n\n{topic} is moving fast in {year}, and most of the advice out there is outdated. "
        f"I spent the past few weeks researching what the top creators in this space are doing differently, "
        f"and in this video I'll share the patterns, the mistakes, and the playbook.\n"
    )

    # CTA block — only include CTAs that ≥30% of top performers use
    cta_block_lines = ["\n📌 What you'll get from this video:"]
    cta_block_lines.append(f"• The current {topic} trend (with real data, not vibes)")
    cta_block_lines.append("• The 3 things top creators are doing that you probably aren't")
    cta_block_lines.append("• A step-by-step plan you can use today")

    cta_lines = ["\n👉 If this helped, smash that like button — it tells the algorithm this is worth pushing."]
    cta_pool = {c.name: c for c in report.description_stats}
    if cta_pool.get("subscribe") and cta_pool["subscribe"].match_rate >= 0.3:
        cta_lines.append("🔔 Subscribe and hit the bell so you don't miss the next one.")
    if cta_pool.get("comment") and cta_pool["comment"].match_rate >= 0.3:
        cta_lines.append("💬 Drop a comment with your biggest question — I read every one.")
    if cta_pool.get("playlist") and cta_pool["playlist"].match_rate >= 0.3:
        cta_lines.append("📂 Check the playlist link below for the full series.")
    cta_lines.append("🔗 Links & resources ↓ in the description")

    # hashtags
    hashtag_str = " ".join(h.tag for h in report.hashtags[:5]) if report.hashtags else f"#{topic.replace(' ', '')}"

    # chapters placeholder (top performers use them when the CTA pattern shows up)
    chapters = ""
    if cta_pool.get("timestamps") and cta_pool["timestamps"].match_rate >= 0.3:
        chapters = (
            "\n\n⏱️ Chapters:\n"
            "0:00 — Intro\n"
            "1:00 — The current trend\n"
            "3:00 — What's actually working\n"
            "6:00 — The step-by-step playbook\n"
            "9:00 — Wrap-up + next steps\n"
        )

    description = opener + body + "\n".join(cta_block_lines) + "\n" + "\n".join(cta_lines) + chapters + f"\n\n{hashtag_str}\n"
    return description.strip() + "\n"


# -------- tags generation --------

def generate_tags(script: ScriptAnalysis, report: AnalysisReport, max_tags: int = 25) -> List[str]:
    """Hybrid: top performer tags + script topic/entities + niche tail terms.

    Filters out script-artifact noise (n-gram phrases, filler words, contractions).
    """
    _TAG_NOISE = re.compile(r"^(\W+|\w{1,2}$|.*[''][smtd]|.*[''][lr]e$|.*['']ll$|.*['']ve$)")

    def _clean(t: str) -> Optional[str]:
        s = re.sub(r"\s+", " ", t.strip().lower())
        if not s or len(s) < 3 or len(s) > 60:
            return None
        if _TAG_NOISE.match(s):
            return None
        return s

    # 1. Top performer tags (the strongest signal — frequency-weighted)
    seed = [t.tag for t in report.tags]

    # 2. The script's own topic + at most 2 best entities
    if script.primary_topic:
        seed.append(script.primary_topic)
    for e in script.entities[:2]:
        if e.lower() != script.primary_topic.lower():
            seed.append(e)

    # 3. Niche-broad tag from category
    if script.suggested_category_name:
        seed.append(script.suggested_category_name.lower())

    # 4. Tail terms (how to, best, 2026, etc.)
    if script.primary_topic:
        pt = script.primary_topic
        seed.append(f"how to {pt}")
        seed.append(f"best {pt}")
        seed.append(f"{pt} {datetime.now().year}")
        seed.append(f"{pt} tutorial")
        seed.append(f"{pt} tips")

    combined: List[str] = []
    seen = set()
    for s in seed:
        c = _clean(s)
        if c and c not in seen:
            seen.add(c); combined.append(c)
        if len(combined) >= max_tags:
            break
    return combined


# -------- hashtags --------

def generate_hashtags(script: ScriptAnalysis, report: AnalysisReport, max_tags: int = 8) -> List[str]:
    """Pick from top performer hashtags + add 1-2 niche-specific ones (cleaned)."""
    bmap = _brand_map_from_script(script)
    # build a lookup: "chatgpt" -> "ChatGPT"
    brand_lookup = {k.lower(): v for k, v in bmap.items()}

    def _clean_hashtag(phrase: str) -> str:
        # remove stopwords so "#work using chatgpt" becomes "#chatgpt" not "#workusingchatgpt"
        words = [w for w in re.findall(r"[A-Za-z0-9]+", phrase.lower())
                 if w not in {"the", "a", "an", "and", "or", "of", "to", "for", "in", "on",
                              "how", "is", "with", "this", "that", "you", "your", "we", "i",
                              "my", "be", "as", "at", "by", "it"} and len(w) > 1]
        if not words:
            words = [w for w in re.findall(r"[A-Za-z0-9]+", phrase.lower()) if w]
        # preserve brand casing
        words = [brand_lookup.get(w, w) for w in words[:3]]
        return "#" + "".join(w.capitalize() if w.islower() else w for w in words)

    base: List[str] = [h.tag for h in report.hashtags[:6]]
    if script.primary_topic:
        base.insert(0, _clean_hashtag(script.primary_topic))
    if script.suggested_category_name:
        base.append(_clean_hashtag(script.suggested_category_name))
    seen, out = set(), []
    for h in base:
        h_norm = h.lower()
        if h_norm not in seen and h_norm != "#":
            seen.add(h_norm); out.append(h)
        if len(out) >= max_tags:
            break
    return out


# -------- thumbnail brief --------

def generate_thumbnail_brief(script: ScriptAnalysis, report: AnalysisReport) -> str:
    bmap = _brand_map_from_script(script)
    topic = _title_case_phrase(script.primary_topic, bmap) if script.primary_topic else "the topic"
    formula_names = {f.name for f in report.title_formulas[:5]}
    use_face = "shocking" in formula_names or "secret" in formula_names
    use_arrow = "vs" in formula_names or "this_is_why" in formula_names
    use_number = "number" in formula_names or "top_n" in formula_names

    bits = []
    bits.append(f"📸 Thumbnail brief ({topic}):")
    bits.append("• Subject: a high-contrast close-up of a face reacting" if use_face
                else "• Subject: bold object/scene tied to the topic")
    bits.append("• Big 3-5 word text overlay — readable on mobile")
    if use_arrow:
        bits.append("• Use a red/yellow arrow or circle pointing at the key detail")
    if use_number:
        bits.append("• Include a large number (3, 5, 7) in a contrasting color")
    bits.append("• Background: blurred or pure-color, NOT the same as other videos in your niche")
    bits.append("• Test: shrink to 1 inch tall — can you still read the text and see the emotion?")
    return "\n".join(bits)


# -------- reasoning / confidence --------

def _confidence_level(script: ScriptAnalysis, report: AnalysisReport) -> str:
    if report.total_videos < 8:
        return "low"
    if report.total_videos < 20 or report.median_vph < 100:
        return "medium"
    return "high"


def generate_reasoning(script: ScriptAnalysis, report: AnalysisReport) -> List[str]:
    notes = []
    notes.append(f"Pool: {report.total_videos} videos "
                 f"(trending={report.total_videos and 'yes'}).")
    if report.median_vph:
        notes.append(f"Median velocity in pool: {report.median_vph:,.0f} views/hour. "
                     f"Anything above that in the first 48h is strong signal.")
    if report.title_formulas:
        top3 = ", ".join(f.label for f in report.title_formulas[:3])
        notes.append(f"Top-performing title formulas in this niche: {top3}. "
                     f"Title variants combine these.")
    if report.tags:
        notes.append(f"Tag pool drawn from top {len(report.tags[:12])} performers — frequency-weighted, not just popular.")
    if report.hashtags:
        notes.append(f"Hashtags pulled from descriptions of top performers, capped at 8 to avoid spam signals.")
    if report.description_stats:
        cta_top = ", ".join(c.label for c in report.description_stats[:3] if c.match_rate >= 0.3)
        if cta_top:
            notes.append(f"Description CTAs included only when ≥30% of pool uses them: {cta_top}.")
    if report.posting:
        notes.append(f"Best posting window in this pool: {report.posting.day_of_week_best} "
                     f"around {report.posting.hour_local_best:02d}:00 local.")
    notes.append("⚠️ No tool can guarantee virality — this is the best-evidenced metadata, not a promise.")
    return notes


# -------- public API --------

def generate(script: ScriptAnalysis, report: AnalysisReport) -> GeneratedMetadata:
    titles = generate_title_variants(script, report)
    description = generate_description(script, report)
    tags = generate_tags(script, report)
    hashtags = generate_hashtags(script, report)
    thumb = generate_thumbnail_brief(script, report)
    reasoning = generate_reasoning(script, report)
    conf = _confidence_level(script, report)
    return GeneratedMetadata(
        title_variants=titles,
        description=description,
        tags=tags,
        hashtags=hashtags,
        thumbnail_brief=thumb,
        reasoning=reasoning,
        confidence=conf,
    )
