"""
Script parser — extract topic, niche, keyphrases, and tone signals from a script.

Pure-Python implementation. No heavy NLP dependencies.
Uses frequency analysis + heuristics to identify the core topic, niche category,
and keyphrases that the YouTube research module will use as search seeds.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import List, Optional


# Lightweight English stopwords (we only need enough to suppress obvious noise).
_STOPWORDS = {
    # articles, prepositions, conjunctions, pronouns, modals, aux verbs
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have",
    "had", "he", "her", "his", "i", "in", "is", "it", "its", "of", "on", "or",
    "that", "the", "this", "to", "was", "were", "will", "with", "you", "your",
    "we", "our", "they", "their", "them", "but", "not", "so", "if", "then",
    "than", "into", "out", "up", "down", "over", "under", "about", "just",
    "do", "does", "did", "doing", "done", "been", "being", "am", "should",
    "would", "could", "can", "may", "might", "must", "shall", "ve", "re", "ll",
    "m", "s", "t", "d", "don", "now", "here", "there", "when", "where", "why",
    "how", "what", "which", "who", "whom", "these", "those", "some", "any",
    "all", "more", "most", "much", "many", "few", "each", "every", "other",
    "such", "no", "yes", "very", "too", "also", "only", "own", "same", "my",
    "me", "him", "us",
    # common conversational fillers & sentence starters
    "okay", "ok", "yeah", "gonna", "wanna", "really", "actually", "literally",
    "basically", "stuff", "things", "thing", "kind", "sort", "bit",
    "back", "going", "go", "get", "got", "gets", "getting", "see", "saw",
    "seen", "know", "knows", "knew", "known", "think", "thinks", "thought",
    "say", "says", "said", "want", "wants", "wanted", "need", "needs", "needed",
    "tell", "tells", "told", "let", "lets", "put", "puts", "give", "gives",
    "gave", "try", "tries", "tried", "trying", "keep", "keeps", "kept",
    "find", "finds", "found", "one", "two", "first", "last", "next", "previous",
    "still", "always", "never", "ever", "often", "sometimes",
    "someone", "anyone", "everyone", "something", "anything", "everything",
    "nothing", "that's", "it's", "we're", "you're", "i'm", "they're", "i've",
    "we've", "you've", "they've", "isn't", "aren't", "wasn't", "weren't",
    "don't", "doesn't", "didn't", "won't", "wouldn't", "shouldn't", "couldn't",
    "can't", "cannot", "hi", "hello", "hey", "welcome", "today", "tomorrow",
    "yesterday", "make", "makes", "made", "making", "take", "takes", "took",
    "taking", "use", "uses", "used", "using",
}

# Common YouTube niche → categoryId mapping (Data API v3).
# Reference: https://developers.google.com/youtube/v3/docs/videoCategories/list
# Structure: list of (keywords, categoryId) groups. Each keyword votes for its categoryId.
NICHE_CATEGORY_MAP: list[tuple[list[str], str]] = [
    # Science & Tech (AI tools, gadgets, software)
    (["chatgpt", "claude", "openai", "anthropic", "gemini", "llm", "gpt",
      "machine learning", "deep learning", "neural", "ai tools", "ai",
      "artificial intelligence", "iphone", "android", "macbook", "windows",
      "linux", "tech", "software", "app review", "nvidia", "gpu", "cpu"], "28"),
    # News / Politics
    (["breaking", "election", "politics", "war", "news", "geopolitics"], "25"),
    # Gaming
    (["game", "gaming", "fortnite", "minecraft", "roblox", "gta", "call of duty",
      "elden ring", "zelda", "pokemon", "esports", "twitch"], "20"),
    # Music
    (["song", "album", "music video", "lyrics", "remix", "concert", "taylor swift",
      "drake", "kanye", "beyonce"], "10"),
    # Howto / Style / Tech (also covers diet/fitness)
    (["tutorial", "how to", "guide", "tips", "review", "iphone", "android", "macbook",
      "coding", "programming", "python", "javascript", "productivity",
      "diet", "fitness", "workout", "carnivore", "keto", "vegan", "paleo",
      "weight loss", "exercise", "gym", "bodybuilding", "meal prep", "nutrition"], "26"),
    # Science / Education
    (["science", "physics", "biology", "space", "nasa", "history", "psychology",
      "explained", "education"], "27"),
    # Sports
    (["nba", "nfl", "soccer", "football", "f1", "tennis", "olympics", "ufc", "boxing"], "17"),
    # Entertainment (movies, celebs)
    (["movie", "film", "marvel", "dc", "netflix", "disney", "celebrity", "drama",
      "trailer"], "24"),
    # Comedy
    (["funny", "comedy", "meme", "prank", "standup"], "23"),
    # Food
    (["recipe", "cooking", "food", "restaurant", "chef", "kitchen"], "26"),
    # Travel
    (["travel", "vlog", "trip", "tokyo", "paris", "tourism"], "19"),
    # Finance / Business
    (["stock", "crypto", "bitcoin", "investing", "money", "wealth", "business"], "28"),
]

# Title-formula detectors — used to suggest a formula for the new video.
TITLE_FORMULAS = {
    "how_to":   [r"\bhow to\b", r"\btutorial\b", r"\bguide\b", r"\bstep[- ]by[- ]step\b"],
    "list":     [r"\btop\s?\d+\b", r"\bbest\s+\d+\b", r"\d+\s+(ways|tips|things|reasons)"],
    "vs":       [r"\bvs\.?\b", r"\bversus\b", r"\bor\b.*\bwhich\b"],
    "challenge":[r"\bchallenge\b", r"\bI tried\b", r"\bfor\s+\d+\s+days\b", r"\b24 hours?\b"],
    "reaction": [r"\breact(ing|ion)?\b", r"\bfirst time\b", r"\bfirst listen\b"],
    "news":     [r"\bbreaking\b", r"\bjust (in|released|happened)\b", r"\bofficial\b"],
    "story":    [r"\bthe truth\b", r"\bstory (behind|of)\b", r"\bwhat happened\b"],
}


@dataclass
class ScriptAnalysis:
    raw_text: str
    word_count: int
    primary_topic: str
    keyphrases: List[str] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)
    tone: dict = field(default_factory=dict)
    niche_keywords: List[str] = field(default_factory=list)
    suggested_category_id: Optional[str] = None
    suggested_category_name: Optional[str] = None
    detected_formulas: List[str] = field(default_factory=list)


_CATEGORY_ID_TO_NAME = {
    "1": "Film & Animation", "2": "Autos & Vehicles", "10": "Music",
    "15": "Pets & Animals", "17": "Sports", "19": "Travel & Events",
    "20": "Gaming", "22": "People & Blogs", "23": "Comedy",
    "24": "Entertainment", "25": "News & Politics", "26": "Howto & Style",
    "27": "Education", "28": "Science & Tech",
}


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-zA-Z][a-zA-Z0-9'-]+", text.lower())


def _extract_ngrams(tokens: List[str], n: int, top_k: int = 20) -> List[str]:
    """Return top multi-word n-grams by frequency, filtering stopword-heavy phrases.

    Strict rules:
      • bigrams: both tokens must be content words (no "the cat", "going to", "chatgpt the")
      • trigrams: at least 2 of 3 tokens must be content
    """
    counts: Counter = Counter()
    for i in range(len(tokens) - n + 1):
        gram = tokens[i:i + n]
        content_tokens = [t for t in gram if t not in _STOPWORDS and len(t) > 2]
        if n == 2 and len(content_tokens) < 2:
            continue
        if n == 3 and len(content_tokens) < 2:
            continue
        if not content_tokens:
            continue
        counts[tuple(gram)] += 1
    return [" ".join(g) for g, _ in counts.most_common(top_k)]


# Known brand patterns — case-insensitive, matched anywhere in the text.
# Used as a fallback when proper-noun regex misses brands with mixed casing
# (iPhone, macOS, eBay, etc.).
_BRANDS = [
    "iphone", "ipad", "imac", "ipados", "macos", "macbook", "airpods", "apple watch",
    "playstation", "xbox", "nintendo", "steam deck", "tesla", "spacex", "nasa",
    "openai", "anthropic", "chatgpt", "claude", "gemini", "copilot", "midjourney",
    "spotify", "netflix", "disney", "hbo", "tiktok", "instagram", "youtube",
    "google", "microsoft", "amazon", "meta", "twitter", "roblox", "minecraft",
    "fortnite", "valorant", "league of legends", "overwatch", "zelda", "pokemon",
    "mario", "sony", "samsung", "oneplus", "pixel", "galaxy", "nvidia", "amd", "intel",
    "uber", "airbnb", "doordash", "linkedin", "github", "figma", "notion", "slack",
    "rivian", "lucid", "byd", "bmw", "mercedes", "audi", "porsche", "ferrari",
    "bitcoin", "ethereum", "solana", "dogecoin", "coinbase", "binance",
    "carnivore", "keto", "vegan", "paleo", "mediterranean diet",
    "tesla model", "cybertruck", "model 3", "model y",
]


def _extract_brands(text: str) -> List[str]:
    """Detect known brand names anywhere in the text (case-insensitive)."""
    lower = text.lower()
    out: Counter = Counter()
    for brand in _BRANDS:
        if brand in lower:
            # preserve original casing of first match
            idx = lower.find(brand)
            original = text[idx:idx + len(brand)]
            out[original] += 1
    return [w for w, _ in out.most_common(8)]


def _extract_proper_nouns(text: str) -> List[str]:
    """Lightweight proper-noun detection: capitalized runs of tokens.

    Strategy:
      1. Find runs of capitalized words. Multi-word runs are kept regardless of position.
         Single-word first-of-sentence matches are skipped.
      2. Add known brand matches (iPhone, ChatGPT, etc.) that may have failed the regex.
    """
    _FALSE_PROPER = {
        "hey", "hello", "hi", "welcome", "today", "yesterday", "tomorrow",
        "drop", "let's", "let", "i", "i'll", "i've", "we", "we'll", "we've",
        "they", "they're", "they've", "you", "you're", "you've", "he", "she",
        "they'll", "i'm", "we're", "it's", "that's", "what's", "there's",
        "here's", "who's", "where's", "when's", "why's", "how's", "ok", "okay",
        "subscribe", "like", "comment", "share", "click", "watch", "check",
        "link", "video", "videos", "channel", "playlist", "description",
        "top", "best", "worst", "first", "last", "next",
    }
    sentences = re.split(r"(?<=[.!?])\s+", text)
    proper: Counter = Counter()
    for sent in sentences:
        runs = re.findall(r"\b[A-Z][a-zA-Z0-9'-]+(?:\s+[A-Z][a-zA-Z0-9'-]+)*\b", sent)
        for idx, run in enumerate(runs):
            words = run.split()
            if idx == 0 and len(words) == 1:
                continue
            lw = run.lower()
            if lw in _STOPWORDS or lw in _FALSE_PROPER or len(run) <= 2:
                continue
            proper[run] += 1
    # merge in brand matches
    for b in _extract_brands(text):
        proper[b] += 2   # weight brand matches higher
    return [w for w, _ in proper.most_common(15)]


def _detect_tone(text: str) -> dict:
    """Return tone signals: questions, exclamations, urgency, listicle cues."""
    lower = text.lower()
    return {
        "questions":    len(re.findall(r"\?", text)),
        "exclamations": len(re.findall(r"!", text)),
        "urgency_words": sum(1 for w in ["now", "today", "breaking", "just released",
                                          "new", "shocking", "insane", "unbelievable",
                                          "secret", "revealed"] if re.search(rf"\b{w}\b", lower)),
        "listicle_cues": sum(1 for w in ["top", "best", "worst", "reasons", "ways",
                                          "tips", "things"] if re.search(rf"\b{w}\b", lower)),
        "caps_ratio":   sum(1 for c in text if c.isupper()) / max(1, len(text)),
    }


def _detect_niche(keyphrases: List[str], entities: List[str]) -> tuple[Optional[str], Optional[str], List[str]]:
    """Match against NICHE_CATEGORY_MAP to suggest a YouTube categoryId + matched keywords."""
    haystack = " ".join(keyphrases + [e.lower() for e in entities])
    matched_keywords: List[str] = []
    category_votes: Counter = Counter()
    for keywords, cat_id in NICHE_CATEGORY_MAP:
        for needle in keywords:
            if needle in haystack:
                matched_keywords.append(needle)
                category_votes[cat_id] += 1
                break  # one vote per group is enough
    if not category_votes:
        return None, None, matched_keywords
    cat_id, _ = category_votes.most_common(1)[0]
    return cat_id, _CATEGORY_ID_TO_NAME.get(cat_id), matched_keywords


def _detect_formulas(text: str) -> List[str]:
    lower = text.lower()
    found = []
    for formula, patterns in TITLE_FORMULAS.items():
        if any(re.search(p, lower) for p in patterns):
            found.append(formula)
    return found


def parse_script(text: str) -> ScriptAnalysis:
    """Top-level entry point. Takes raw script text → ScriptAnalysis."""
    text = text.strip()
    tokens = _tokenize(text)
    unigrams = Counter(t for t in tokens if t not in _STOPWORDS and len(t) > 2)
    bigrams = _extract_ngrams(tokens, 2, top_k=15)
    trigrams = _extract_ngrams(tokens, 3, top_k=10)
    entities = _extract_proper_nouns(text)

    # Primary topic detection. Strategy:
    #   1. If a proper-noun (entity) appears, anchor on it and find the SHORTEST n-gram containing it
    #      (usually the most natural topic phrase — e.g. "chatgpt" not "work using chatgpt").
    #   2. Otherwise, pick the bigram whose first content word has the highest unigram frequency.
    primary = ""
    if entities:
        anchor = entities[0].lower()
        # prefer the shortest containing phrase (most specific, least awkward)
        containing = [p for p in bigrams + [anchor] if anchor in p]
        if containing:
            primary = min(containing, key=len)
        else:
            primary = anchor
    if not primary:
        if bigrams:
            def _score(phrase: str) -> tuple:
                words = phrase.split()
                first_content = next((w for w in words if w not in _STOPWORDS and len(w) > 2), words[0])
                return (unigrams.get(first_content, 0), len(phrase))
            primary = max(bigrams[:15], key=_score) if bigrams else (unigrams.most_common(1)[0][0] if unigrams else "")
        elif unigrams:
            primary = unigrams.most_common(1)[0][0]

    tone = _detect_tone(text)
    cat_id, cat_name, niche_kws = _detect_niche(bigrams + [primary], entities)
    formulas = _detect_formulas(text)

    return ScriptAnalysis(
        raw_text=text,
        word_count=len(tokens),
        primary_topic=primary,
        keyphrases=bigrams[:10] + trigrams[:5],
        entities=entities,
        tone=tone,
        niche_keywords=niche_kws,
        suggested_category_id=cat_id,
        suggested_category_name=cat_name,
        detected_formulas=formulas,
    )


def read_script_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python script_parser.py <script.txt>")
        sys.exit(1)
    result = parse_script(read_script_file(sys.argv[1]))
    print(f"Topic:        {result.primary_topic}")
    print(f"Words:        {result.word_count}")
    print(f"Category:     {result.suggested_category_name} ({result.suggested_category_id})")
    print(f"Formulas:     {result.detected_formulas}")
    print(f"Niche KW:     {result.niche_keywords}")
    print(f"Top phrases:  {result.keyphrases[:8]}")
    print(f"Entities:     {result.entities[:8]}")
    print(f"Tone:         {result.tone}")
