import email.utils
import html
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo


HOST = os.environ.get("KESTRELIQ_HOST") or ("0.0.0.0" if os.environ.get("PORT") else "127.0.0.1")
PORT = int(os.environ.get("PORT") or os.environ.get("KESTRELIQ_PORT", "8787"))
ROOT = Path(__file__).resolve().parent
INDEX_FILE = ROOT / "templates" / "index.html"
CACHE_SECONDS = 15 * 60
IST = ZoneInfo("Asia/Kolkata")

NEWS_CACHE = {}

DEFAULT_COMPANY_KEYWORDS = [
    "company", "business", "CEO", "earnings", "revenue", "partnership",
    "acquisition", "AI", "customer", "launch", "investment", "lawsuit",
    "regulatory", "expansion", "layoffs", "stock", "shares", "outage",
]

POSITIVE_WORDS = {
    "acquires", "acquisition", "award", "beats", "breakthrough", "expands",
    "growth", "launches", "partnership", "profit", "raises", "record",
    "secures", "wins",
}
NEGATIVE_WORDS = {
    "breach", "cuts", "decline", "delay", "fined", "fraud", "investigation",
    "lawsuit", "loss", "recall", "risk", "sues", "warning", "withdraws",
}


def _json_response(handler, status, payload):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.end_headers()
    handler.wfile.write(body)


def _html_response(handler, status, text):
    body = text.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_json(handler):
    length = int(handler.headers.get("Content-Length", "0") or "0")
    if length <= 0:
        return {}
    raw = handler.rfile.read(length).decode("utf-8", errors="replace")
    return json.loads(raw)


def _date_range_to_days(value):
    ranges = {
        "all": None,
        "24h": 1,
        "3d": 3,
        "7d": 7,
        "30d": 30,
    }
    return ranges.get(value, 7)


def _preferred_interest_query(interest):
    normalized = _normalize_text(interest)
    preferred = {
        "claude": "Anthropic Claude AI",
        "chatgpt": "OpenAI ChatGPT",
        "gemini": "Google Gemini AI",
        "grok": "xAI Grok",
        "agenticai": "agentic AI",
        "genai": "generative AI",
    }
    return preferred.get(normalized, str(interest).strip())


def _search_keywords(config, mode="companies"):
    if mode == "interests":
        return []
    if isinstance(config, dict) and not config.get("useDefault", True):
        raw_terms = config.get("terms") or []
        terms = [str(term).strip() for term in raw_terms if str(term).strip()]
    else:
        terms = DEFAULT_COMPANY_KEYWORDS
    clean = []
    seen = set()
    for term in terms:
        normalized = _normalize_text(term)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        clean.append(term[:40])
    return clean[:30] or DEFAULT_COMPANY_KEYWORDS


def _rss_keyword_clause(config, mode="companies"):
    parts = []
    for term in _search_keywords(config, mode=mode):
        safe = str(term).replace('"', "").strip()
        if not safe:
            continue
        parts.append(f'"{safe}"' if re.search(r"\s", safe) else safe)
    return " OR ".join(parts)


def _rss_url(company, days, contextual=False, mode="companies", keyword_config=None):
    company_query = _preferred_company_query(company) if mode != "interests" else _preferred_interest_query(company)
    date_clause = f" when:{days}d" if days else ""
    query = f'"{company_query}"{date_clause}'
    if contextual:
        if mode == "interests":
            business_context = (
                "news OR latest OR analysis OR research OR launch OR AI OR "
                "technology OR customer OR business OR regulation OR market OR trend"
            )
        else:
            business_context = _rss_keyword_clause(keyword_config, mode=mode)
        query = f'"{company_query}" ({business_context}){date_clause}'
    params = urllib.parse.urlencode({
        "q": query,
        "hl": "en-IN",
        "gl": "IN",
        "ceid": "IN:en",
        "scoring": "n",
    })
    return f"https://news.google.com/rss/search?{params}"


def _rss_urls(company, days, mode="companies", keyword_config=None):
    if mode == "interests":
        return [_rss_url(company, days, mode=mode)]
    return [_rss_url(company, days, contextual=True, mode=mode, keyword_config=keyword_config)]


def _rss_type(index, mode):
    return "Baseline" if mode == "interests" else "Contextual"


def _fetch_url(url, accept="application/rss+xml, application/xml, text/xml, text/html"):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; KestrelIQ/1.0; +local executive intelligence app)",
            "Accept": accept,
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read()


class _ArticleTextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.capture = None
        self.current = []
        self.title = ""
        self.description = ""
        self.blocks = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"script", "style", "noscript", "svg", "nav", "footer", "header", "aside", "form"}:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag == "meta":
            key = (attrs.get("name") or attrs.get("property") or "").lower()
            if key in {"description", "og:description", "twitter:description"} and attrs.get("content"):
                self.description = self.description or attrs["content"].strip()
        if tag in {"title", "h1", "h2", "p", "li"}:
            self.capture = tag
            self.current = []

    def handle_endtag(self, tag):
        if self.skip_depth:
            if tag in {"script", "style", "noscript", "svg", "nav", "footer", "header", "aside", "form"}:
                self.skip_depth = max(0, self.skip_depth - 1)
            return
        if tag == self.capture:
            text = re.sub(r"\s+", " ", " ".join(self.current)).strip()
            if text:
                if tag == "title" and not self.title:
                    self.title = text
                elif len(text) > 45:
                    self.blocks.append(text)
            self.capture = None
            self.current = []

    def handle_data(self, data):
        if not self.skip_depth and self.capture:
            self.current.append(data)


GOOGLE_NEWS_BOILERPLATE = "Comprehensive, up-to-date news coverage, aggregated from sources all over the world by Google News."


def _fallback_article_preview(fallback_title="", fallback_source=""):
    headline = (fallback_title or "Article headline unavailable").strip()
    source = (fallback_source or "Google News feed").strip()
    return {
        "title": headline,
        "source": source,
        "text": (
            f"{headline}\n\n"
            f"Source: {source}\n\n"
            "Google News RSS provides this item as a news headline and source reference. "
            "The full publisher body text is not exposed through the RSS wrapper, so KestrelIQ is showing the article preview instead of Google's generic page description."
        ),
        "truncated": False,
        "previewOnly": True,
    }


def _is_google_boilerplate(title, body):
    combined = f"{title or ''} {body or ''}".strip()
    return (
        GOOGLE_NEWS_BOILERPLATE.lower() in combined.lower()
        or combined.lower() == "google news"
    )


def _resolve_google_news_url(url):
    parsed = urllib.parse.urlparse(url)
    if not parsed.netloc.lower().endswith("news.google.com"):
        return url
    html_text = _fetch_url(url, accept="text/html, application/xhtml+xml").decode("utf-8", errors="replace")
    match = re.search(
        r'data-n-a-id="([^"]+)"\s+data-n-a-ts="([^"]+)"\s+data-n-a-sg="([^"]+)"',
        html_text,
    )
    if not match:
        return ""
    article_id, timestamp, signature = match.groups()
    request_args = [
        "garturlreq",
        [
            [
                "en-IN", "IN", ["FINANCE_TOP_INDICES", "WEB_TEST_1_0_0"],
                None, None, 1, 1, "IN:en", None, 180,
                None, None, None, None, None, 0, None, None,
                [1608992183, 723341000],
            ],
            "en-IN", "IN", 1, [2, 3, 4, 8], 1, 0,
            "655000234", 0, 0, None, 0,
        ],
        article_id,
        int(timestamp),
        signature,
    ]
    rpc_payload = [[[
        "Fbv4je",
        json.dumps(request_args, separators=(",", ":")),
        None,
        "generic",
    ]]]
    data = urllib.parse.urlencode({
        "f.req": json.dumps(rpc_payload, separators=(",", ":")),
    }).encode("utf-8")
    request = urllib.request.Request(
        "https://news.google.com/_/DotsSplashUi/data/batchexecute?rpcids=Fbv4je",
        data=data,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; KestrelIQ/1.0)",
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            "Accept": "application/json, text/plain, */*",
        },
    )
    response_text = urllib.request.urlopen(request, timeout=20).read().decode("utf-8", errors="replace")
    json_line = next((line for line in response_text.splitlines() if line.startswith("[[")), "")
    if not json_line:
        return ""
    outer = json.loads(json_line)
    inner = json.loads(outer[0][2])
    resolved = inner[1] if len(inner) > 1 else ""
    return resolved if str(resolved).startswith(("http://", "https://")) else ""


def _article_text_from_url(url, fallback_title="", fallback_source=""):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http and https article links can be viewed.")
    if parsed.netloc.lower().endswith("news.google.com"):
        try:
            resolved = _resolve_google_news_url(url)
            if resolved:
                url = resolved
            else:
                return _fallback_article_preview(fallback_title, fallback_source)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError, IndexError, TypeError):
            return _fallback_article_preview(fallback_title, fallback_source)
    raw = _fetch_url(url, accept="text/html, application/xhtml+xml")
    text = raw.decode("utf-8", errors="replace")
    parser = _ArticleTextParser()
    parser.feed(text)
    seen = set()
    blocks = []
    for block in parser.blocks:
        normalized = block.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        blocks.append(block)
    if not blocks and parser.description and not _is_google_boilerplate(parser.title, parser.description):
        blocks.append(parser.description)
    if not blocks and fallback_title:
        blocks.append(fallback_title)
    body = "\n\n".join(blocks[:12]).strip()
    if _is_google_boilerplate(parser.title, body):
        return _fallback_article_preview(fallback_title, fallback_source)
    max_chars = 4500
    truncated = len(body) > max_chars
    if truncated:
        body = body[:max_chars].rsplit(" ", 1)[0].strip() + "..."
    return {
        "title": parser.title or fallback_title or "Article text",
        "source": fallback_source,
        "text": body or "Readable article text was not available from this source.",
        "truncated": truncated,
        "resolvedUrl": url,
    }


def _parse_google_source(item):
    source = item.find("source")
    if source is not None and source.text:
        return source.text.strip()
    return "Google News"


def _parse_date(value):
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _item_published_date(item):
    candidates = [
        item.findtext("pubDate"),
        item.findtext("published"),
        item.findtext("updated"),
        item.findtext("{http://purl.org/dc/elements/1.1/}date"),
        item.findtext("{http://www.w3.org/2005/Atom}published"),
        item.findtext("{http://www.w3.org/2005/Atom}updated"),
    ]
    for value in candidates:
        parsed = _parse_date(value)
        if parsed:
            return parsed
    return datetime.now(timezone.utc)


def _sentiment(title):
    words = set(re.findall(r"[a-z][a-z0-9]+", title.lower()))
    positive = len(words & POSITIVE_WORDS)
    negative = len(words & NEGATIVE_WORDS)
    if positive > negative:
        return "positive"
    if negative > positive:
        return "negative"
    return "neutral"


def _vertical(company, title):
    normalized = _normalize_text(company)
    company_verticals = {
        "revolut": "BFSI",
        "scotiabank": "BFSI",
        "westpac": "BFSI",
        "dhanalaxmibank": "BFSI",
        "lloyds": "BFSI",
        "db": "Data & Risk",
        "dnb": "Data & Risk",
        "dunbradstreet": "Data & Risk",
        "cisco": "Technology",
        "netapp": "Technology",
        "openai": "AI & Technology",
        "anthropic": "AI & Technology",
        "oracle": "Technology",
        "adobe": "Technology",
        "accenture": "IT Services",
        "concentrix": "CX / BPO",
        "airbnb": "Travel & Hospitality",
        "airbnbinc": "Travel & Hospitality",
    }
    if normalized in company_verticals:
        return company_verticals[normalized]

    text = f"{company} {title}".lower()
    rules = [
        ("BFSI", ["bank", "banking", "fintech", "insurance", "payments", "lending", "credit", "wealth"]),
        ("Retail & Ecommerce", ["retail", "ecommerce", "commerce", "store", "shopping"]),
        ("Travel & Hospitality", ["travel", "hotel", "airline", "hospitality", "booking", "host"]),
        ("Healthcare", ["health", "hospital", "patient", "pharma", "medical"]),
        ("Technology", ["software", "cloud", "cyber", "security", "data", "network", "platform"]),
        ("AI & Technology", [" ai ", "agentic", "genai", "model", "automation", "chatbot"]),
        ("CX / BPO", ["customer experience", "contact center", "bpo", "outsourcing", "support"]),
    ]
    padded = f" {text} "
    for vertical, words in rules:
        if any(word in padded for word in words):
            return vertical
    return "Market"


def _clean_title(value):
    value = html.unescape(value or "").strip()
    value = re.sub(r"\s+-\s+[^-]{2,80}$", "", value)
    return value


def _normalize_text(value):
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def _company_terms(company):
    raw = (company or "").strip()
    lower = raw.lower()
    terms = {lower}
    normalized = _normalize_text(raw)
    if normalized:
        terms.add(normalized)

    aliases = {
        "airbnb": ["airbnb", "air bnb", "airbnb inc"],
        "airbnbinc": ["airbnb", "air bnb", "airbnb inc"],
        "openai": ["openai", "open ai"],
        "scotiabank": ["scotiabank", "scotia bank", "bank of nova scotia"],
        "db": ["d&b", "dnb", "dun & bradstreet", "dun and bradstreet", "dun bradstreet"],
        "dnb": ["d&b", "dnb", "dun & bradstreet", "dun and bradstreet", "dun bradstreet"],
        "lloyds": ["lloyds", "lloyds banking group", "lloyds bank"],
        "netapp": ["netapp", "net app"],
    }
    for alias in aliases.get(normalized, []):
        terms.add(alias)
        terms.add(_normalize_text(alias))
    return {term for term in terms if term}


def _preferred_company_query(company):
    normalized = _normalize_text(company)
    preferred = {
        "airbnb": "Airbnb",
        "airbnbinc": "Airbnb",
        "db": "Dun & Bradstreet",
        "dnb": "Dun & Bradstreet",
        "openai": "OpenAI",
        "scotiabank": "Scotiabank",
    }
    return preferred.get(normalized, company)


def _has_company_term(company, text):
    lower = (text or "").lower()
    normalized = _normalize_text(text)
    for term in _company_terms(company):
        if len(term) <= 2:
            continue
        if term in lower or term in normalized:
            return True
    return False


def _is_company_relevant(company, title, source):
    text = f"{title} {source}"
    if not _has_company_term(company, text):
        return False

    lower = text.lower()
    business_words = {
        "acquires", "acquisition", "ai", "agentic", "analyst", "appoints",
        "banking", "business", "ceo", "cloud", "company", "contract",
        "customer", "earnings", "executive", "expands", "funding", "growth",
        "investment", "launches", "lawsuit", "market", "merger", "outage",
        "partner", "partnership", "platform", "profit", "regulator",
        "revenue", "shares", "stock", "strategy", "valuation",
    }
    if any(re.search(rf"\b{re.escape(word)}\b", lower) for word in business_words):
        return True

    consumer_patterns = (
        r"\bshould i\b",
        r"\bhow to\b",
        r"\bbest\b",
        r"\bguide\b",
        r"\bclass\b",
        r"\bbecome a host\b",
        r"\blisting\b",
        r"\bhomeowner\b",
    )
    return not any(re.search(pattern, lower) for pattern in consumer_patterns)


def _interest_terms(interest):
    raw = (interest or "").strip().lower()
    terms = {raw, _normalize_text(raw)}
    aliases = {
        "chatgpt": ["chatgpt", "chat gpt", "openai chatgpt"],
        "claude": ["claude", "anthropic claude"],
        "gemini": ["gemini", "google gemini"],
        "agenticai": ["agentic ai", "ai agents", "agentic"],
        "genai": ["genai", "generative ai"],
    }
    for alias in aliases.get(_normalize_text(raw), []):
        terms.add(alias)
        terms.add(_normalize_text(alias))
    return {term for term in terms if len(term) > 2}


def _is_interest_relevant(interest, title, source):
    text = f"{title} {source}"
    lower = text.lower()
    normalized = _normalize_text(text)
    if not any(term in lower or term in normalized for term in _interest_terms(interest)):
        return False

    ai_topics = {"claude", "chatgpt", "gemini", "grok", "openai", "anthropic"}
    ai_context = (
        "ai", "anthropic", "openai", "google", "xai", "chatbot", "model",
        "llm", "opus", "sonnet", "haiku", "gpt", "coding", "code",
        "artificial intelligence", "machine learning", "agents", "agentic",
        "api", "developer", "cybersecurity",
    )
    if _normalize_text(interest) in ai_topics and not any(term in lower for term in ai_context):
        return False

    noise_patterns = (
        r"\bquiz\b",
        r"\bmovie\b",
        r"\bsong\b",
        r"\bcelebrity\b",
        r"\bhoroscope\b",
        r"\bobituary\b",
        r"\bfuneral\b",
        r"\bstanley cup\b",
        r"\bnhl\b",
        r"\bdeath certificate\b",
        r"\bfound dead\b",
    )
    return not any(re.search(pattern, lower) for pattern in noise_patterns)


def _article_id(company, title, link):
    base = f"{company}|{title}|{link}"
    return str(abs(hash(base)))


SCAN_THEMES = [
    ("CEO / Leadership", ("ceo", "chief executive", "executive", "leader", "leadership", "cto", "cfo", "chairman")),
    ("Earnings / Revenue", ("earnings", "revenue", "profit", "loss", "quarter", "q1", "q2", "q3", "q4", "results")),
    ("Partnership", ("partnership", "partner", "alliance", "collaboration", "teams up")),
    ("Acquisition / M&A", ("acquisition", "acquires", "acquire", "merger", "m&a", "deal", "takeover")),
    ("AI / Technology", (" ai ", "artificial intelligence", "agentic", "automation", "technology", "cloud", "data")),
    ("Customer / CX", ("customer", "client", "experience", "service", "support", "outage", "complaint")),
    ("Launch / Product", ("launch", "launches", "unveils", "introduces", "rolls out", "product", "platform")),
    ("Investment / Funding", ("investment", "invests", "funding", "raises", "valuation", "stake", "shares", "stock")),
    ("Risk / Regulatory", ("lawsuit", "regulatory", "regulator", "probe", "fine", "breach", "risk", "warning")),
    ("Expansion / Growth", ("expansion", "expands", "growth", "market", "opens", "new business", "international")),
    ("Layoffs / Restructuring", ("layoff", "layoffs", "restructuring", "job cuts", "cuts", "cost cutting")),
]

def _scan_terms(mode="companies", keyword_config=None):
    if mode == "interests":
        return SCAN_THEMES
    return [(term, (term.lower(),)) for term in _search_keywords(keyword_config, mode=mode)]


def _scan_theme_counts_template(mode="companies", keyword_config=None):
    return {label: {"raw": 0, "kept": 0} for label, _ in _scan_terms(mode, keyword_config)}


def _scan_themes_for_title(title, mode="companies", keyword_config=None):
    text = f" {str(title or '').lower()} "
    matches = []
    for label, keywords in _scan_terms(mode, keyword_config):
        if any(keyword in text for keyword in keywords):
            matches.append(label)
    return matches or ["Market Watch"]


def _empty_scan_stats(companies, date_range, mode):
    return {
        "mode": mode,
        "dateRange": date_range,
        "trackedCount": len([c for c in companies if str(c).strip()]),
        "rssUrlsRequested": 0,
        "rawItemsScanned": 0,
        "relevantItemsKept": 0,
        "duplicateCount": 0,
        "uniqueSourcesCount": 0,
        "errorsCount": 0,
        "scanTimestamp": datetime.now(IST).strftime("%d %b %Y, %I:%M %p IST"),
        "perTarget": [],
        "rssUrls": [],
        "uniqueSources": [],
        "topSources": [],
        "keywordBreakdown": [],
        "keywordTotals": [],
    }


def _fetch_company_news(company, days, mode="companies", stats=None, keyword_config=None):
    keyword_key = tuple(_search_keywords(keyword_config, mode=mode))
    cache_key = (mode, company.lower(), days, keyword_key)
    cached = NEWS_CACHE.get(cache_key)
    if cached and time.time() - cached["time"] < CACHE_SECONDS:
        if stats is not None:
            urls = _rss_urls(company, days, mode=mode, keyword_config=keyword_config)
            stats["rssUrlsRequested"] += len(urls)
            stats["rssUrls"].extend([
                {"target": company, "type": _rss_type(i, mode), "url": url, "cacheHit": True}
                for i, url in enumerate(urls)
            ])
            stats["relevantItemsKept"] += len(cached["items"])
            cached_target = dict(cached.get("targetStats") or {})
            if cached_target:
                cached_target["cacheHit"] = True
                stats["rawItemsScanned"] += int(cached_target.get("rawItems") or 0)
                stats["duplicateCount"] += int(cached_target.get("duplicateItems") or 0)
                stats["perTarget"].append(cached_target)
            else:
                theme_counts = _scan_theme_counts_template(mode, keyword_config)
                theme_counts["Market Watch"] = {"raw": 0, "kept": 0}
                for item in cached["items"]:
                    for theme in _scan_themes_for_title(item.get("headline", ""), mode, keyword_config):
                        theme_counts.setdefault(theme, {"raw": 0, "kept": 0})["kept"] += 1
                stats["perTarget"].append({
                    "name": company,
                    "rssUrls": len(_rss_urls(company, days, mode=mode, keyword_config=keyword_config)),
                    "rawItems": 0,
                    "keptItems": len(cached["items"]),
                    "sources": sorted({item.get("source", "") for item in cached["items"] if item.get("source")}),
                    "latestUpdate": cached["items"][0].get("publishedIST", "") if cached["items"] else "",
                    "cacheHit": True,
                    "themeCounts": theme_counts,
                })
        return cached["items"]

    items = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days) if days else None
    seen = set()
    target_stats = {
        "name": company,
        "rssUrls": 0,
        "rawItems": 0,
        "keptItems": 0,
        "duplicateItems": 0,
        "sources": set(),
        "latestUpdate": "",
        "cacheHit": False,
        "themeCounts": {**_scan_theme_counts_template(mode, keyword_config), "Market Watch": {"raw": 0, "kept": 0}},
    }
    for index, url in enumerate(_rss_urls(company, days, mode=mode, keyword_config=keyword_config)):
        if stats is not None:
            stats["rssUrlsRequested"] += 1
            stats["rssUrls"].append({
                "target": company,
                "type": _rss_type(index, mode),
                "url": url,
                "cacheHit": False,
            })
        target_stats["rssUrls"] += 1
        xml_bytes = _fetch_url(url)
        root = ET.fromstring(xml_bytes)
        for item in root.findall("./channel/item"):
            if stats is not None:
                stats["rawItemsScanned"] += 1
            target_stats["rawItems"] += 1
            title = _clean_title(item.findtext("title"))
            raw_themes = _scan_themes_for_title(title, mode, keyword_config)
            for theme in raw_themes:
                target_stats["themeCounts"].setdefault(theme, {"raw": 0, "kept": 0})["raw"] += 1
            link = item.findtext("link") or ""
            source = _parse_google_source(item)
            published = _item_published_date(item)
            if cutoff and published and published < cutoff:
                continue
            if not title or not link:
                continue
            relevant = _is_interest_relevant(company, title, source) if mode == "interests" else _is_company_relevant(company, title, source)
            if not relevant:
                continue
            key = (title.lower(), source.lower())
            if key in seen:
                if stats is not None:
                    stats["duplicateCount"] += 1
                target_stats["duplicateItems"] += 1
                continue
            seen.add(key)
            for theme in raw_themes:
                target_stats["themeCounts"].setdefault(theme, {"raw": 0, "kept": 0})["kept"] += 1
            target_stats["sources"].add(source)
            items.append({
                "id": _article_id(company, title, link),
                "company": company,
                "vertical": _vertical(company, title),
                "date": published.isoformat() if published else "",
                "displayDate": published.strftime("%d %b %Y") if published else "",
                "displayTimeIST": published.astimezone(IST).strftime("%I:%M %p IST") if published else "",
                "publishedIST": published.astimezone(IST).strftime("%d %b %Y, %I:%M %p IST") if published else "",
                "source": source,
                "headline": title,
                "url": link,
                "sentiment": _sentiment(title),
                "scanThemes": raw_themes,
            })

    items.sort(key=lambda item: item.get("date") or "", reverse=True)
    target_stats["keptItems"] = len(items)
    target_stats["latestUpdate"] = items[0].get("publishedIST", "") if items else ""
    target_stats["sources"] = sorted(target_stats["sources"])
    if stats is not None:
        stats["relevantItemsKept"] += len(items)
        stats["perTarget"].append(target_stats)

    NEWS_CACHE[cache_key] = {"time": time.time(), "items": items, "targetStats": target_stats}
    return items


def _fetch_news(companies, date_range, mode="companies", keyword_config=None):
    days = _date_range_to_days(date_range)
    stats = _empty_scan_stats(companies, date_range, mode)
    articles = []
    errors = []
    for company in companies:
        name = str(company).strip()
        if not name:
            continue
        try:
            articles.extend(_fetch_company_news(name, days, mode=mode, stats=stats, keyword_config=keyword_config))
        except (urllib.error.URLError, TimeoutError, ET.ParseError, OSError) as exc:
            errors.append({"company": name, "error": str(exc)})
            stats["errorsCount"] += 1

    deduped = {}
    for article in articles:
        key = (article["headline"].lower(), article["source"].lower())
        if key in deduped:
            stats["duplicateCount"] += 1
        deduped.setdefault(key, article)

    sorted_articles = sorted(
        deduped.values(),
        key=lambda item: item.get("date") or "",
        reverse=True,
    )
    source_counts = {}
    for article in sorted_articles:
        source_counts[article.get("source") or "Unknown"] = source_counts.get(article.get("source") or "Unknown", 0) + 1
    stats["uniqueSourcesCount"] = len(source_counts)
    stats["uniqueSources"] = [{"source": source, "count": count} for source, count in sorted(source_counts.items(), key=lambda x: x[0].lower())]
    stats["topSources"] = [{"source": source, "count": count} for source, count in sorted(source_counts.items(), key=lambda x: x[1], reverse=True)[:8]]
    stats["relevantItemsKept"] = len(sorted_articles)
    breakdown = []
    totals = {}
    for target in stats["perTarget"]:
        for theme, counts in (target.get("themeCounts") or {}).items():
            raw = int(counts.get("raw") or 0)
            kept = int(counts.get("kept") or 0)
            if not raw and not kept:
                continue
            breakdown.append({
                "target": target.get("name", ""),
                "theme": theme,
                "raw": raw,
                "kept": kept,
            })
            totals.setdefault(theme, {"raw": 0, "kept": 0})
            totals[theme]["raw"] += raw
            totals[theme]["kept"] += kept
    stats["keywordBreakdown"] = sorted(
        breakdown,
        key=lambda row: (str(row["target"]).lower(), -row["kept"], -row["raw"], str(row["theme"]).lower()),
    )
    stats["keywordTotals"] = [
        {"theme": theme, "raw": counts["raw"], "kept": counts["kept"]}
        for theme, counts in sorted(totals.items(), key=lambda x: (-x[1]["kept"], -x[1]["raw"], x[0].lower()))
    ]
    return sorted_articles, errors, stats


def _briefing(articles):
    by_company = {}
    for article in articles:
        by_company.setdefault(article["company"], []).append(article)

    highlights = []
    risks = []
    for company, items in by_company.items():
        positives = [x for x in items if x["sentiment"] == "positive"]
        negatives = [x for x in items if x["sentiment"] == "negative"]
        lead = items[0] if items else None
        highlights.append({
            "company": company,
            "count": len(items),
            "positive": len(positives),
            "negative": len(negatives),
            "lead": lead,
        })
        risks.extend(negatives[:2])

    return {
        "generatedAt": datetime.now().strftime("%d %b %Y, %H:%M"),
        "companies": sorted(highlights, key=lambda item: item["count"], reverse=True),
        "risks": risks[:8],
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[KestrelIQ] {self.address_string()} - {fmt % args}")

    def do_OPTIONS(self):
        _json_response(self, 200, {"ok": True})

    def do_GET(self):
        if self.path in {"/", "/index.html"}:
            if not INDEX_FILE.exists():
                _html_response(self, 500, "templates/index.html is missing.")
                return
            _html_response(self, 200, INDEX_FILE.read_text(encoding="utf-8"))
            return
        if self.path == "/api/health":
            _json_response(self, 200, {"ok": True, "service": "KestrelIQ"})
            return
        _json_response(self, 404, {"error": "Not found"})

    def do_POST(self):
        if self.path == "/api/news":
            payload = _read_json(self)
            companies = payload.get("companies") or []
            date_range = payload.get("dateRange") or "7d"
            mode = payload.get("mode") or "companies"
            keyword_config = payload.get("keywordConfig") or {}
            articles, errors, scan = _fetch_news(companies, date_range, mode=mode, keyword_config=keyword_config)
            _json_response(self, 200, {
                "articles": articles,
                "briefing": _briefing(articles),
                "errors": errors,
                "scan": scan,
            })
            return
        if self.path == "/api/scan-test":
            payload = _read_json(self)
            keyword = str(payload.get("keyword") or "").strip()
            if not keyword:
                _json_response(self, 400, {"error": "Keyword is required."})
                return
            date_range = payload.get("dateRange") or "7d"
            mode = payload.get("mode") or "interests"
            keyword_config = payload.get("keywordConfig") or {}
            articles, errors, scan = _fetch_news([keyword], date_range, mode=mode, keyword_config=keyword_config)
            _json_response(self, 200, {
                "keyword": keyword,
                "articles": articles[:20],
                "errors": errors,
                "scan": scan,
            })
            return
        if self.path == "/api/article-text":
            payload = _read_json(self)
            url = str(payload.get("url") or "").strip()
            if not url:
                _json_response(self, 400, {"error": "Article URL is required."})
                return
            try:
                article = _article_text_from_url(
                    url,
                    fallback_title=str(payload.get("headline") or ""),
                    fallback_source=str(payload.get("source") or ""),
                )
                _json_response(self, 200, article)
            except (urllib.error.URLError, TimeoutError, OSError, UnicodeError, ValueError) as exc:
                _json_response(self, 502, {
                    "error": "Could not fetch readable article text.",
                    "detail": str(exc),
                })
            return
        _json_response(self, 404, {"error": "Not found"})


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"KestrelIQ running at http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
