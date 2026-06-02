# 🎬 YouTube Viral Optimizer

A Python tool that takes a video **script**, mines **live YouTube trends** in the same niche, and synthesizes the best-evidenced **titles, descriptions, tags, and hashtags** you can use for the video. Built around YouTube Data API v3 + pattern analysis — no LLM required, fully reproducible.

> **Honest disclaimer:** nothing *guarantees* virality. The YouTube algorithm is opaque and audience taste is moody. What this tool *does* is give your video the best shot: metadata driven by what the top performers in your niche are *actually* doing right now, not vibes.

---

## What it does

1. **Parses your script** → extracts topic, niche (with YouTube categoryId), keyphrases, entities, tone signals, and detected title-formula hints.
2. **Pulls live YouTube data**:
   - Trending feed in your niche (chart=mostPopular, region+category)
   - Top videos for your topic in the last 90 days (search.list ordered by viewCount)
3. *(Optional)* **Cross-platform signals** — Google News + Reddit via SerpAPI.
4. **Mines patterns** from the pool:
   - Title formulas ranked by average views (How-to, Top N, Versus, I Tried, …)
   - Top tags (frequency × velocity-weighted)
   - Top hashtags
   - Description openers & CTA patterns (subscribe / like / timestamps / …)
   - Best posting window (hour-of-day, day-of-week)
5. **Generates**:
   - 5 title variants combining the best formulas
   - A multi-section description built from the dominant opener + CTA patterns
   - 25 tags (frequency-weighted + niche tail terms)
   - 8 hashtags (cleaned & brand-cased)
   - A thumbnail brief tuned to your niche's formula mix
   - A reasoning report showing *why* each piece was chosen
6. **Writes** both a JSON dump (everything) and a Markdown report to `output/`.

## Quick start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Add your YouTube Data API key
cp .env.example .env
# then edit .env and set YOUTUBE_API_KEY=AIza...

# 3. Run it on the sample script
python main.py examples/sample_script.txt

# Or pass inline text
python main.py --script "How to use ChatGPT the right way..."

# Or via stdin
cat examples/sample_script.txt | python main.py --script-stdin
```

### Common flags

| Flag | Description |
|---|---|
| `--region GB` | ISO 3166-1 alpha-2 country code (default: US) |
| `--category 28` | Force a YouTube categoryId (overrides auto-detect) |
| `--max 30` | Videos to pull per source (default: 20) |
| `--with-web` | Enable SerpAPI web research (requires `SERPAPI_KEY`) |
| `--subreddit artificial` | Specific subreddit for Reddit signal |
| `--out-dir reports` | Where to write JSON+MD reports (default: `output/`) |
| `--quiet` | Suppress progress output |

### Get a YouTube API key (free)

1. Go to https://console.cloud.google.com/apis/credentials
2. Create a project → Enable **YouTube Data API v3**
3. **Create credentials → API key**
4. Paste it into `.env` as `YOUTUBE_API_KEY=...`

Free quota: **10,000 units/day** — this tool uses ~150–400 units per run, so you can do 25–60 analyses/day for free.

### Get a SerpAPI key (optional, for web research)

1. Sign up at https://serpapi.com/ (free tier: 100 searches/month)
2. Add to `.env`: `SERPAPI_KEY=...`

---

## Example output

```
=== Generated Metadata (confidence=medium) ===

TITLE VARIANTS:
  1. How to ChatGPT the Right Way (2026)
  2. 7 ChatGPT Tips That Actually Work
  3. The Truth About ChatGPT Nobody Tells You
  4. I Tried ChatGPT for 30 Days — Here's What Happened
  5. Why Is Everyone Talking About ChatGPT?

DESCRIPTION:
Welcome back! In today's video, we break down ChatGPT — what it is, why it matters, and exactly how to use it.
...

TAGS:
  chatgpt, tutorial, prompts, productivity, openai, ai, tips, gpt-5, ...

HASHTAGS:
  #ChatGPT #ai #gpt5 #openai #claude #comparison

REASONING:
  • Pool: 12 videos (trending=yes).
  • Median velocity in pool: 12,785 views/hour.
  • Top-performing title formulas in this niche: Versus / compare, Ends with question, Has colon.
  • Tag pool drawn from top 12 performers — frequency-weighted.
  ...
  • ⚠️ No tool can guarantee virality — this is the best-evidenced metadata, not a promise.
```

A full report is also written to `output/viral_report_<timestamp>.md` and `.json`.

---

## Project structure

```
youtube-viral-optimizer/
├── main.py                     # CLI entry point
├── src/
│   ├── script_parser.py        # Topic / niche / entity / formula extraction
│   ├── youtube_research.py     # YouTube Data API v3 client (trending + search)
│   ├── web_research.py         # Optional SerpAPI web/Reddit signals
│   ├── analyzer.py             # Pattern mining on the research pool
│   └── generator.py            # Synthesizes final titles / desc / tags
├── examples/
│   └── sample_script.txt
├── test_e2e.py                 # End-to-end test with mock YouTube data (no API key needed)
├── requirements.txt
├── .env.example
└── README.md
```

## Test without an API key

```bash
python test_e2e.py
```

This runs the full pipeline (parser → analyzer → generator) against a mock pool of 12 realistic videos. Useful for sanity-checking the generator output or developing new patterns.

## How the analysis works

- **Velocity = views per hour since publish.** Recent high-velocity videos are a stronger trend signal than raw view counts.
- **Title formulas** are regex-matched against titles and ranked by the average view count of videos using each formula. The top 2–3 drive the title variant generation.
- **Tags** are frequency-counted across the pool, then re-scored by `frequency × log10(avg_views)` so a tag that's both common *and* appears on high-view videos wins.
- **CTAs in descriptions** are only included if ≥30% of the pool uses them — this avoids forcing patterns the niche doesn't actually follow.
- **Openers** use the same match-rate threshold to pick the dominant hook style for the description.

## Limitations & honesty

- ❌ Can't see thumbnails, retention curves, or actual click-through rates — those are creator-side.
- ❌ The "trending" feed only shows what YouTube *exposes* as trending in your region. It doesn't include Shorts (separate feed), browse features, or personalized recommendations.
- ❌ A `confidence: low` reading means the pool was thin (niche is too specific, region too narrow) — get more data, broaden the region, or drop `--with-web` for cross-platform signal.
- ✅ The data you get is real, current, and reproducible. The patterns it surfaces are what the audience in your niche is *actually* responding to.

## Extending

- **Add a new title formula** → `src/analyzer.py` `_TITLE_PATTERNS`
- **Add a new niche** → `src/script_parser.py` `NICHE_CATEGORY_MAP`
- **Add a new brand** → `src/script_parser.py` `_BRANDS`
- **Tweak description templates** → `src/generator.py` `generate_description`

## License

MIT — use it, fork it, ship videos with it.
