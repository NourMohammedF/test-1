"""End-to-end test using mock YouTube data — no API key required.

This verifies that script_parser → youtube_research → analyzer → generator all
work together and produce sensible metadata. Run with:
    python test_e2e.py
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

from src.script_parser import parse_script, read_script_file
from src.youtube_research import VideoRecord, ResearchBundle
from src.analyzer import analyze
from src.generator import generate


def _mk(idx, hours_ago, title, desc, tags, hashtags, views, category_id="28"):
    pub = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat().replace("+00:00", "Z")
    return VideoRecord(
        video_id=f"mock{idx:03d}",
        title=title,
        channel_title=f"Channel {idx}",
        published_at=pub,
        description=desc,
        tags=tags,
        hashtags=hashtags,
        view_count=views,
        like_count=views // 50,
        comment_count=views // 200,
        duration_iso="PT8M15S",
        category_id=category_id,
        thumbnail_url="",
        source="trending" if idx % 2 == 0 else "search",
        rank=idx,
    )


def main():
    script = parse_script(read_script_file("examples/sample_script.txt"))
    print(f"=== Script Analysis ===")
    print(f"  Topic:     {script.primary_topic}")
    print(f"  Category:  {script.suggested_category_name} ({script.suggested_category_id})")
    print(f"  Entities:  {script.entities[:5]}")
    print(f"  Formulas:  {script.detected_formulas}")
    print()

    # Build a mock ResearchBundle that mimics what YouTube would return for a tech/AI niche
    pool = [
        _mk(1, 6,   "How to Use ChatGPT the Right Way (Most People Get This Wrong)",
            "Welcome back! In today's video, I'll show you the 7 prompts that changed how I work with ChatGPT. Subscribe for more AI tips!\n\n#chatgpt #ai #productivity",
            ["chatgpt", "ai", "prompts", "tutorial", "productivity", "openai", "how to"],
            ["chatgpt", "ai", "productivity"], 482000, "28"),
        _mk(2, 12,  "7 ChatGPT Hacks That Save Me 10 Hours a Week",
            "Hey! If you've been using ChatGPT like a search engine, you're missing out. Drop a comment with your favorite prompt!\n\n🔔 Subscribe and hit the bell.\n\n0:00 Intro\n1:00 Hack 1\n\n#chatgpt #aitools",
            ["chatgpt", "ai tools", "hacks", "prompts", "productivity", "tutorial"],
            ["chatgpt", "aitools"], 312000, "28"),
        _mk(3, 24,  "I Tried ChatGPT for 30 Days — Here's What Actually Works",
            "In this video, I spent 30 days using ChatGPT for everything. Here are the prompts that actually moved the needle.\n\n#chatgpt #ai #experiment",
            ["chatgpt", "ai", "experiment", "30 days", "prompts"],
            ["chatgpt", "ai", "experiment"], 198000, "28"),
        _mk(4, 18,  "The Truth About ChatGPT: What Nobody Tells You",
            "Today we're talking about the dark side of ChatGPT. Most people don't know this. Comment below what you think!\n\n#chatgpt #ai #truth",
            ["chatgpt", "ai", "truth", "hidden", "secret"],
            ["chatgpt", "ai", "truth"], 245000, "28"),
        _mk(5, 36,  "ChatGPT vs Claude: Which AI Is Actually Better in 2026?",
            "Hey everyone! Today I compared ChatGPT and Claude head-to-head. Watch the full comparison and let me know which one you prefer.\n\nTimestamps:\n0:00 Intro\n1:00 Speed test\n4:00 Quality test\n\n#chatgpt #claude #ai #comparison",
            ["chatgpt", "claude", "ai", "comparison", "versus", "review"],
            ["chatgpt", "claude", "ai", "comparison"], 521000, "28"),
        _mk(6, 8,   "Top 10 ChatGPT Prompts You NEED to Know",
            "Welcome back! Here are the 10 ChatGPT prompts that have transformed my workflow. Like and subscribe for weekly AI content!\n\n#chatgpt #prompts #ai",
            ["chatgpt", "prompts", "top 10", "ai", "tutorial", "productivity"],
            ["chatgpt", "prompts", "ai"], 156000, "28"),
        _mk(7, 72,  "The ChatGPT Prompt Framework That 10x'd My Output",
            "In this video I share the role-prompting framework that the top 1% of ChatGPT users rely on. Link in description for the full template.\n\n#chatgpt #ai #framework",
            ["chatgpt", "ai", "framework", "prompts", "tutorial"],
            ["chatgpt", "ai", "framework"], 87000, "28"),
        _mk(8, 48,  "Don't Make These 5 ChatGPT Mistakes",
            "Hey! In today's video, I'm covering the 5 biggest ChatGPT mistakes I see every day. Avoid these and you'll be ahead of 90% of users.\n\n#chatgpt #mistakes #ai",
            ["chatgpt", "mistakes", "ai", "tips", "tutorial"],
            ["chatgpt", "mistakes", "ai"], 134000, "28"),
        _mk(9, 96,  "I Built an App with ChatGPT in 1 Hour — Here's How",
            "Today I built a full app using ChatGPT in under an hour. Watch the full build, drop your questions in the comments, and subscribe for the next one.\n\n#chatgpt #coding #ai",
            ["chatgpt", "coding", "ai", "app", "tutorial", "no code"],
            ["chatgpt", "coding", "ai"], 203000, "28"),
        _mk(10, 4,  "GPT-5 Just Changed Everything — Here's What's New",
            "Breaking down everything announced for GPT-5 and what it means for you. Smash that like button if you want more AI news.\n\n#gpt5 #openai #ai #chatgpt",
            ["gpt-5", "openai", "ai", "chatgpt", "news", "breaking"],
            ["gpt5", "openai", "ai", "chatgpt"], 612000, "28"),
        _mk(11, 60, "How to Actually Use AI in 2026 (Beginner's Guide)",
            "Welcome! In this beginner's guide to AI in 2026, I'll walk you through the tools, the prompts, and the workflow that actually works.\n\n#ai #chatgpt #beginner",
            ["ai", "chatgpt", "beginner", "guide", "tutorial", "2026"],
            ["ai", "chatgpt", "beginner"], 178000, "28"),
        _mk(12, 24, "5 ChatGPT Secrets They Don't Want You to Know",
            "Hidden features in ChatGPT that 99% of users miss. Drop a comment with which one surprised you most!\n\n#chatgpt #secrets #ai",
            ["chatgpt", "secrets", "hidden", "ai", "tutorial", "tips"],
            ["chatgpt", "secrets", "ai"], 287000, "28"),
    ]

    bundle = ResearchBundle(
        query=script.primary_topic,
        region="US",
        category_id=script.suggested_category_id,
        trending=[v for v in pool if v.source == "trending"],
        top_by_keyphrase=[v for v in pool if v.source == "search"],
        raw_metadata={"mock": True},
    )

    print(f"=== Research Bundle ===")
    print(f"  Trending: {len(bundle.trending)} | Top-by-keyphrase: {len(bundle.top_by_keyphrase)}")
    print()

    report = analyze(bundle, script=script)
    print(f"=== Analysis ===")
    print(f"  Total pool:        {report.total_videos}")
    print(f"  Median views/hr:   {report.median_vph:,.0f}")
    print(f"  Top formulas:      {[(f.label, f.match_rate) for f in report.title_formulas[:5]]}")
    print(f"  Top tags:          {[t.tag for t in report.tags[:8]]}")
    print(f"  Top hashtags:      {[h.tag for h in report.hashtags[:5]]}")
    print(f"  Top CTAs:          {[(c.label, c.match_rate) for c in report.description_stats[:5]]}")
    print(f"  Top openers:       {[(c.label, c.match_rate) for c in report.description_opener_stats[:5]]}")
    print(f"  Velocity leader:   {report.velocity_leaders[0].title[:60]}")
    print()

    meta = generate(script, report)
    print(f"=== Generated Metadata (confidence={meta.confidence}) ===\n")
    print("TITLE VARIANTS:")
    for i, t in enumerate(meta.title_variants, 1):
        print(f"  {i}. {t}")
    print()
    print("DESCRIPTION:")
    print(meta.description)
    print("TAGS:")
    print("  " + ", ".join(meta.tags))
    print()
    print("HASHTAGS:")
    print("  " + " ".join(meta.hashtags))
    print()
    print("THUMBNAIL BRIEF:")
    print(meta.thumbnail_brief)
    print()
    print("REASONING:")
    for r in meta.reasoning:
        print(f"  • {r}")


if __name__ == "__main__":
    main()
