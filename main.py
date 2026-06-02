"""
YouTube Viral Optimizer — entry point.

Usage:
    python main.py path/to/script.txt
    python main.py --script "Paste the script text inline..."
    python main.py --script-stdin            # read from stdin
    python main.py --script examples/sample_script.txt --max 25 --json-out output/report.json
    python main.py --script script.txt --region US --category 28 --with-web

Environment:
    YOUTUBE_API_KEY  — required (YouTube Data API v3)
    SERPAPI_KEY      — optional (cross-platform trend signal)
    YT_REGION        — optional, default US

What it does:
  1. Parses the script to extract topic, niche, keyphrases, and tone.
  2. Pulls live YouTube data: trending in the niche + top videos for the topic.
  3. Optionally pulls Google News / Reddit signals.
  4. Mines winning patterns: title formulas, tags, hashtags, description openers & CTAs.
  5. Synthesizes optimized title variants, description, tags, hashtags, and a thumbnail brief.
  6. Prints a Rich-formatted report and saves JSON + markdown artifacts.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.script_parser import parse_script, read_script_file, ScriptAnalysis
from src.youtube_research import YouTubeResearcher
from src.web_research import WebResearcher
from src.analyzer import analyze
from src.generator import generate

console = Console()


# -------- CLI argument parsing --------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="youtube-viral-optimizer",
        description="Analyze a script + current YouTube trends to produce viral metadata.",
    )
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("script_path", nargs="?", help="Path to a script text file")
    src.add_argument("--script", help="Inline script text")
    src.add_argument("--script-stdin", action="store_true", help="Read script from stdin")

    p.add_argument("--region", default=os.getenv("YT_REGION", "US"),
                   help="ISO 3166-1 alpha-2 region code (default: US)")
    p.add_argument("--category", default=None,
                   help="Override YouTube categoryId (e.g. 28=Science&Tech, 20=Gaming, 25=News)")
    p.add_argument("--max", type=int, default=20,
                   help="Max videos per source (default: 20)")
    p.add_argument("--with-web", action="store_true",
                   help="Enable SerpAPI web research (requires SERPAPI_KEY)")
    p.add_argument("--subreddit", default=None,
                   help="Optional subreddit name for Reddit signal (e.g. 'artificial')")
    p.add_argument("--out-dir", default="output",
                   help="Where to write JSON + markdown reports")
    p.add_argument("--json-out", default=None,
                   help="Explicit path for JSON report")
    p.add_argument("--md-out", default=None,
                   help="Explicit path for markdown report")
    p.add_argument("--quiet", action="store_true",
                   help="Suppress per-step progress output")
    return p.parse_args()


# -------- input loading --------

def _load_script(args: argparse.Namespace) -> str:
    if args.script_path:
        return read_script_file(args.script_path)
    if args.script:
        return args.script
    if args.script_stdin:
        return sys.stdin.read()
    console.print("[red]No script provided.[/red]")
    sys.exit(1)


# -------- rendering --------

def _print_header(script: ScriptAnalysis, args: argparse.Namespace):
    console.print(Panel.fit(
        Text.assemble(
            ("YouTube Viral Optimizer", "bold magenta"),
            ("\n"),
            (f"Topic: {script.primary_topic or '?'}  |  Words: {script.word_count}  |  "
             f"Niche: {script.suggested_category_name or '—'} ({script.suggested_category_id or '—'})  |  "
             f"Region: {args.region}", "dim"),
        ),
        border_style="magenta",
    ))


def _print_research_meta(bundle, web_bundle=None, args=None):
    table = Table(title="Research Pool", show_header=True, header_style="bold cyan")
    table.add_column("Source", style="cyan")
    table.add_column("Videos", justify="right")
    table.add_column("Region / Query", style="dim")
    table.add_row("YouTube Trending",   str(len(bundle.trending)),          f"{args.region} / {bundle.category_id or 'all'}")
    table.add_row("YouTube Top (key)",  str(len(bundle.top_by_keyphrase)), bundle.query)
    if web_bundle is not None:
        table.add_row("Google News",     str(len(web_bundle.news)),         web_bundle.query)
        table.add_row("Reddit",          str(len(web_bundle.reddit)),       web_bundle.query)
    console.print(table)


def _print_patterns(report):
    if not report.title_formulas:
        return
    t = Table(title="Top Title Formulas (avg views)", header_style="bold yellow")
    t.add_column("Formula")
    t.add_column("Match Rate", justify="right")
    t.add_column("Avg Views", justify="right")
    t.add_column("Example", style="dim", overflow="fold")
    for f in report.title_formulas[:8]:
        t.add_row(f.label, f"{f.match_rate*100:.0f}%", f"{f.avg_views:,}", f.example)
    console.print(t)

    if report.tags:
        tg = Table(title="Top Tags (frequency × velocity)", header_style="bold green")
        tg.add_column("Tag")
        tg.add_column("Freq", justify="right")
        tg.add_column("Avg Views", justify="right")
        for s in report.tags[:12]:
            tg.add_row(s.tag, str(s.frequency), f"{s.avg_views:,}")
        console.print(tg)

    if report.hashtags:
        h = Table(title="Top Hashtags", header_style="bold blue")
        h.add_column("Hashtag")
        h.add_column("Freq", justify="right")
        h.add_column("Avg Views", justify="right")
        for s in report.hashtags[:10]:
            h.add_row(s.tag, str(s.frequency), f"{s.avg_views:,}")
        console.print(h)


def _print_metadata(meta):
    console.rule("[bold magenta]Generated Metadata")
    console.print(Panel(
        "\n".join(f"  {i+1}. {t}" for i, t in enumerate(meta.title_variants)),
        title="Title Variants", border_style="magenta",
    ))
    console.print(Panel(meta.description, title="Description (copy-paste ready)",
                        border_style="green"))
    console.print(Panel(
        ", ".join(meta.tags), title="Tags (comma-separated, YouTube limit ~500 chars total)",
        border_style="cyan",
    ))
    console.print(Panel(
        " ".join(meta.hashtags), title="Hashtags (for description / first comment)",
        border_style="blue",
    ))
    console.print(Panel(meta.thumbnail_brief, title="Thumbnail Brief",
                        border_style="yellow"))


def _print_reasoning(meta):
    console.rule("[bold dim]Why this metadata")
    for line in meta.reasoning:
        console.print(f"  {line}")
    console.print(f"\n  Confidence: [{ 'green' if meta.confidence=='high' else 'yellow' if meta.confidence=='medium' else 'red'}]{meta.confidence}[/]")


# -------- output files --------

def _write_reports(meta, script, report, bundle, out_dir, json_path=None, md_path=None, web_bundle=None):
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = json_path or str(Path(out_dir) / f"viral_report_{ts}.json")
    md_path   = md_path   or str(Path(out_dir) / f"viral_report_{ts}.md")

    payload = {
        "generated_at": datetime.now().isoformat(),
        "script": {
            "primary_topic": script.primary_topic,
            "keyphrases": script.keyphrases,
            "entities": script.entities,
            "category_id": script.suggested_category_id,
            "category_name": script.suggested_category_name,
            "tone": script.tone,
            "word_count": script.word_count,
        },
        "research": bundle.to_dict(),
        "analysis": {
            "total_videos": report.total_videos,
            "median_views": report.median_views,
            "median_vph": report.median_vph,
            "avg_duration_seconds": report.avg_duration_seconds,
            "title_formulas": [f.__dict__ for f in report.title_formulas],
            "top_tags": [s.__dict__ for s in report.tags[:20]],
            "top_hashtags": [s.__dict__ for s in report.hashtags[:20]],
            "description_ctas": [s.__dict__ for s in report.description_stats],
            "description_openers": [s.__dict__ for s in report.description_opener_stats],
        },
        "output": {
            "title_variants": meta.title_variants,
            "description": meta.description,
            "tags": meta.tags,
            "hashtags": meta.hashtags,
            "thumbnail_brief": meta.thumbnail_brief,
            "reasoning": meta.reasoning,
            "confidence": meta.confidence,
        },
    }
    if web_bundle is not None:
        payload["web"] = {
            "news": [n.__dict__ for n in web_bundle.news],
            "reddit": [n.__dict__ for n in web_bundle.reddit],
            "errors": web_bundle.errors,
        }
    Path(json_path).write_text(json.dumps(payload, indent=2, ensure_ascii=False))

    md = [
        f"# Viral Metadata Report — {script.primary_topic or 'untitled'}",
        f"_Generated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_",
        "",
        "## Title Variants",
        *[f"{i+1}. {t}" for i, t in enumerate(meta.title_variants)],
        "",
        "## Description",
        "```",
        meta.description.rstrip(),
        "```",
        "",
        "## Tags",
        ", ".join(meta.tags),
        "",
        "## Hashtags",
        " ".join(meta.hashtags),
        "",
        "## Thumbnail Brief",
        meta.thumbnail_brief,
        "",
        "## Why this metadata",
        *[f"- {r}" for r in meta.reasoning],
        f"\n**Confidence:** `{meta.confidence}`",
        "",
        "## Top Title Formulas",
        "| Formula | Match Rate | Avg Views | Example |",
        "|---|---|---|---|",
        *[f"| {f.label} | {f.match_rate*100:.0f}% | {f.avg_views:,} | {f.example} |"
          for f in report.title_formulas[:10]],
        "",
        "## Top Tags",
        "| Tag | Freq | Avg Views |",
        "|---|---|---|",
        *[f"| {s.tag} | {s.frequency} | {s.avg_views:,} |" for s in report.tags[:15]],
    ]
    Path(md_path).write_text("\n".join(md), encoding="utf-8")
    return json_path, md_path


# -------- main --------

def main() -> int:
    load_dotenv()
    args = _parse_args()
    raw_script = _load_script(args)

    # 1. parse
    if not args.quiet:
        console.print("[dim]→ Parsing script…[/dim]")
    script = parse_script(raw_script)
    if not args.quiet:
        _print_header(script, args)

    # 2. youtube research
    if not args.quiet:
        console.print("[dim]→ Querying YouTube Data API…[/dim]")
    yt = YouTubeResearcher(region=args.region)
    if not yt.is_configured:
        console.print(Panel(
            "[bold red]YOUTUBE_API_KEY is not set.[/bold red]\n\n"
            "Get one at https://console.cloud.google.com/apis/credentials "
            "(enable 'YouTube Data API v3'), then add it to your .env file:\n"
            "  YOUTUBE_API_KEY=AIza...",
            border_style="red", title="Setup needed",
        ))
        return 2

    cat_id = args.category or script.suggested_category_id
    bundle = yt.research(script.primary_topic or script.keyphrases[0] if script.keyphrases else script.primary_topic,
                         category_id=cat_id, max_per_source=args.max)
    if not bundle.trending and not bundle.top_by_keyphrase:
        console.print("[yellow]No videos returned. Check your API key, region, or query.[/yellow]")
        return 3

    # 3. web (optional)
    web_bundle = None
    if args.with_web:
        if not args.quiet:
            console.print("[dim]→ Querying web signals…[/dim]")
        wr = WebResearcher()
        web_bundle = wr.research(script.primary_topic or "", subreddit=args.subreddit)

    # 4. analyze
    if not args.quiet:
        console.print("[dim]→ Mining patterns…[/dim]")
    report = analyze(bundle, script=script)

    # 5. generate
    if not args.quiet:
        console.print("[dim]→ Generating metadata…[/dim]")
    meta = generate(script, report)

    # 6. render
    if not args.quiet:
        _print_research_meta(bundle, web_bundle, args)
        _print_patterns(report)
        _print_metadata(meta)
        _print_reasoning(meta)

    # 7. write files
    j, m = _write_reports(meta, script, report, bundle, args.out_dir,
                          args.json_out, args.md_out, web_bundle)
    console.print(f"\n[green]✓[/green] JSON report:  {j}")
    console.print(f"[green]✓[/green] Markdown:    {m}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
