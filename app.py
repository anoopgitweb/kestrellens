import email.utils
import html
import json
import os
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo


HOST = os.environ.get("KESTRELIQ_HOST") or ("0.0.0.0" if os.environ.get("PORT") else "127.0.0.1")
PORT = int(os.environ.get("PORT") or os.environ.get("KESTRELIQ_PORT", "8787"))
ROOT = Path(__file__).resolve().parent
INDEX_FILE = ROOT / "templates" / "index.html"
ASSET_DIR = ROOT / "assets"
FORTUNE_FILE = ASSET_DIR / "fortune500-2026.json"
LLM_RANKINGS_URL = "https://artificialanalysis.ai/leaderboards/models"
CACHE_SECONDS = 15 * 60
QUOTE_CACHE_SECONDS = 60
IST = ZoneInfo("Asia/Kolkata")

NEWS_CACHE = {}

_ORIGINAL_GETADDRINFO = socket.getaddrinfo


def _prefer_ipv4_getaddrinfo(*args, **kwargs):
    results = _ORIGINAL_GETADDRINFO(*args, **kwargs)
    ipv4 = [item for item in results if item[0] == socket.AF_INET]
    return ipv4 or results


socket.getaddrinfo = _prefer_ipv4_getaddrinfo

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
    handler.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
    handler.send_header("Pragma", "no-cache")
    handler.send_header("Expires", "0")
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
    handler.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
    handler.send_header("Pragma", "no-cache")
    handler.send_header("Expires", "0")
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
    return [
        _rss_url(company, days, contextual=True, mode=mode, keyword_config=keyword_config),
        _rss_url(company, days, contextual=False, mode=mode, keyword_config=keyword_config),
    ]


def _rss_type(index, mode):
    if mode == "interests":
        return "Baseline"
    if mode == "agency":
        return "Agency RSS" if index == 0 else "Agency fallback"
    return "Contextual" if index == 0 else "Baseline fallback"


AGENCY_FEEDS = {
    "forrester": {
        "name": "Forrester",
        "domains": ["forrester.com"],
        "feeds": [
            "https://www.forrester.com/blogs/feed/",
            "https://www.forrester.com/feed/",
        ],
    },
    "gartner": {
        "name": "Gartner",
        "domains": ["gartner.com"],
        "resolve_links": True,
        "feeds": [
            "https://news.google.com/rss/search?q=site%3Agartner.com%2Fen%2Fnewsroom%20when%3A30d&hl=en-US&gl=US&ceid=US%3Aen",
        ],
    },
    "everestgroup": {
        "name": "Everest Group",
        "domains": ["everestgrp.com"],
        "resolve_links": True,
        "feeds": [
            "https://news.google.com/rss/search?q=site%3Aeverestgrp.com%20when%3A30d&hl=en-US&gl=US&ceid=US%3Aen",
        ],
    },
    "nelsonhall": {
        "name": "NelsonHall",
        "domains": ["nelson-hall.com"],
        "resolve_links": True,
        "feeds": [
            "https://news.google.com/rss/search?q=site%3Anelson-hall.com%20when%3A30d&hl=en-US&gl=US&ceid=US%3Aen",
        ],
    },
    "frostsullivan": {
        "name": "Frost & Sullivan",
        "domains": ["frost.com"],
        "resolve_links": True,
        "feeds": [
            "https://news.google.com/rss/search?q=site%3Afrost.com%20when%3A30d&hl=en-US&gl=US&ceid=US%3Aen",
        ],
    },
    "isg": {
        "name": "ISG",
        "domains": ["isg-one.com"],
        "resolve_links": True,
        "feeds": [
            "https://news.google.com/rss/search?q=site%3Aisg-one.com%20when%3A30d&hl=en-US&gl=US&ceid=US%3Aen",
        ],
    },
    "hfsresearch": {
        "name": "HFS Research",
        "domains": ["hfsresearch.com"],
        "resolve_links": True,
        "feeds": [
            "https://news.google.com/rss/search?q=site%3Ahfsresearch.com%20when%3A30d&hl=en-US&gl=US&ceid=US%3Aen",
        ],
    },
}


def _fetch_url(url, accept="application/rss+xml, application/xml, text/xml, text/html", timeout=10):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; KestrelIQ/1.0; +local executive intelligence app)",
            "Accept": accept,
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


class _ArticleTextParser(HTMLParser):
    BLOCK_TAGS = {"title", "h1", "h2", "h3", "p", "li", "blockquote", "figcaption"}
    SKIP_TAGS = {"style", "noscript", "svg", "nav", "footer", "header", "aside", "form", "iframe"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.capture = None
        self.current = []
        self.title = ""
        self.description = ""
        self.blocks = []
        self.json_ld = []
        self._script_type = ""
        self._script_data = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script":
            self._script_type = (attrs.get("type") or "").lower()
            self._script_data = []
            if self._script_type != "application/ld+json":
                self.skip_depth += 1
            return
        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag == "meta":
            key = (attrs.get("name") or attrs.get("property") or "").lower()
            if key in {"description", "og:description", "twitter:description"} and attrs.get("content"):
                self.description = self.description or _clean_article_block(attrs["content"])
        if tag in self.BLOCK_TAGS:
            self.capture = tag
            self.current = []

    def handle_endtag(self, tag):
        if tag == "script":
            if self._script_type == "application/ld+json":
                data = "".join(self._script_data).strip()
                if data:
                    self.json_ld.append(data)
                self._script_type = ""
                self._script_data = []
                return
            if self.skip_depth:
                self.skip_depth = max(0, self.skip_depth - 1)
                return
        if self.skip_depth:
            if tag in self.SKIP_TAGS:
                self.skip_depth = max(0, self.skip_depth - 1)
            return
        if tag == self.capture:
            text = _clean_article_block(" ".join(self.current))
            if text:
                if tag == "title" and not self.title:
                    self.title = text
                elif len(text) > 35:
                    self.blocks.append(text)
            self.capture = None
            self.current = []

    def handle_data(self, data):
        if self._script_type == "application/ld+json":
            self._script_data.append(data)
            return
        if not self.skip_depth and self.capture:
            self.current.append(data)


def _clean_article_block(value):
    text = html.unescape(str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _json_ld_type(value):
    raw = value.get("@type") if isinstance(value, dict) else ""
    if isinstance(raw, list):
        return " ".join(str(item) for item in raw).lower()
    return str(raw or "").lower()


def _json_ld_text_candidates(value):
    candidates = []
    if isinstance(value, dict):
        graph = value.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                candidates.extend(_json_ld_text_candidates(item))
        ld_type = _json_ld_type(value)
        article_like = any(kind in ld_type for kind in ("article", "newsarticle", "blogposting", "report"))
        for key in ("articleBody", "description", "headline"):
            item = value.get(key)
            if isinstance(item, str) and (article_like or key == "articleBody"):
                cleaned = _clean_article_block(item)
                if len(cleaned) > 45:
                    candidates.append(cleaned)
        main = value.get("mainEntity") or value.get("mainEntityOfPage")
        if isinstance(main, (dict, list)):
            candidates.extend(_json_ld_text_candidates(main))
    elif isinstance(value, list):
        for item in value:
            candidates.extend(_json_ld_text_candidates(item))
    return candidates


def _extract_json_ld_blocks(parser):
    blocks = []
    for raw in parser.json_ld:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        blocks.extend(_json_ld_text_candidates(payload))
    return blocks


ARTICLE_NOISE_PATTERNS = (
    "subscribe", "sign up", "newsletter", "advertisement", "cookies", "privacy policy",
    "all rights reserved", "terms of use", "enable javascript", "share this article",
    "read more", "follow us", "download our app", "skip to", "comments", "login",
)


def _is_article_noise(block):
    lower = block.lower()
    if len(block) < 36:
        return True
    if _is_google_boilerplate("", block):
        return True
    if any(pattern in lower for pattern in ARTICLE_NOISE_PATTERNS) and len(block) < 180:
        return True
    return False


def _dedupe_article_blocks(blocks):
    seen = set()
    clean = []
    for block in blocks:
        value = _clean_article_block(block)
        if not value or _is_article_noise(value):
            continue
        normalized = re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
        if normalized in seen:
            continue
        seen.add(normalized)
        clean.append(value)
    return clean


GOOGLE_NEWS_BOILERPLATE = "Comprehensive, up-to-date news coverage, aggregated from sources all over the world by Google News."


def _clean_rss_summary(value="", title=""):
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text or _is_google_boilerplate(title, text):
        return ""
    title_text = re.sub(r"\s+", " ", str(title or "")).strip()
    if title_text and text.lower().startswith(title_text.lower()):
        text = text[len(title_text):].lstrip(" .:-")
    if len(text) < 45:
        return ""
    return text[:520].rsplit(" ", 1)[0].strip()


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
    extraction_method = "publisher-html"
    if parsed.netloc.lower().endswith("news.google.com"):
        try:
            resolved = _resolve_google_news_url(url)
            if resolved:
                url = resolved
                extraction_method = "google-news-resolved"
            else:
                return _fallback_article_preview(fallback_title, fallback_source)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError, IndexError, TypeError):
            return _fallback_article_preview(fallback_title, fallback_source)
    raw = _fetch_url(url, accept="text/html, application/xhtml+xml")
    text = raw.decode("utf-8", errors="replace")
    parser = _ArticleTextParser()
    parser.feed(text)
    json_ld_blocks = _extract_json_ld_blocks(parser)
    blocks = _dedupe_article_blocks(json_ld_blocks + parser.blocks)
    if not blocks and parser.description and not _is_google_boilerplate(parser.title, parser.description):
        blocks.append(parser.description)
        extraction_method = "meta-description"
    if not blocks and fallback_title:
        blocks.append(fallback_title)
        extraction_method = "headline-fallback"
    body = "\n\n".join(blocks[:24]).strip()
    if _is_google_boilerplate(parser.title, body):
        return _fallback_article_preview(fallback_title, fallback_source)
    max_chars = 12000
    truncated = len(body) > max_chars
    if truncated:
        body = body[:max_chars].rsplit(" ", 1)[0].strip() + "..."
    return {
        "title": parser.title or fallback_title or "Article text",
        "source": fallback_source,
        "text": body or "Readable article text was not available from this source.",
        "truncated": truncated,
        "resolvedUrl": url,
        "extractionMethod": extraction_method,
        "extractedChars": len(body),
        "blockCount": len(blocks),
    }

EXECUTIVE_SUMMARY_PROMPT = """You are an Executive Communications Assistant for business users.

Review the provided KestrelIQ briefing text, extract the most important factual insights, and generate a polished, concise, VP-ready executive summary.

Use only factual, verifiable information from the provided text. Do not invent or assume details, metrics, dates, conclusions, or strategic claims. Do not include raw extraction text. If the file content is unclear or cannot be extracted, respond exactly with: Sorry, I cannot find the answer. Can you please ask in a different way?

Use this structure:
Title: Executive Summary: [Document Topic or Company Name]

Section 1: Executive Summary
- 3 to 5 short paragraphs in VP-ready language

Section 2: Key Messages for Leadership
- 3 to 5 bullet points

Section 3: Distinct News
- 5 to 7 news in a clear table format with date (DD/MM/YYYY, HH:MM:SS) and source

Section 4: New Launches/Acquisitions/Partnerships
- 5 to 7 news related to new launches, acquisitions, or partnerships in a clear table format with date (DD/MM/YYYY, HH:MM:SS) and source

Section 5: Recommended VP Takeaway
- 1 short paragraph with the main leadership takeaway

Return clean HTML only, using h1, h2, p, ul, li, and table tags. Keep the tone professional, concise, polished, and leadership-ready.
"""


def _call_openai_summary(api_key, document_text):
    body = json.dumps({
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": EXECUTIVE_SUMMARY_PROMPT},
            {"role": "user", "content": document_text[:60000]},
        ],
        "temperature": 0.2,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
    return payload["choices"][0]["message"]["content"]


def _call_claude_summary(api_key, document_text):
    body = json.dumps({
        "model": "claude-3-5-sonnet-20241022",
        "max_tokens": 3500,
        "temperature": 0.2,
        "system": EXECUTIVE_SUMMARY_PROMPT,
        "messages": [{"role": "user", "content": document_text[:60000]}],
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
    return "\n".join(part.get("text", "") for part in payload.get("content", []) if part.get("type") == "text").strip()


SIGNAL_INTELLIGENCE_PROMPT = """You are a business-signal extraction engine for KestrelIQ.

Extract only factual events from the supplied article for the supplied account and signal taxonomy. Return valid JSON only with this shape:
{"events":[{"signal_id":"...","signal_label":"...","event_name":"...","status":"Confirmed|Planned / reported|Needs review","count":0,"count_type":"people|events|money|unknown","date_or_period":"...","evidence":"short exact supporting sentence","confidence":0.0,"is_account_actor":true}]}

Rules:
- Use only the article text. Do not invent products, partners, dates, counts, companies, or status.
- For launches, partnerships, and M&A, include the event only when the watched account is the actor or a clearly named party, not merely mentioned near another company's event.
- For layoffs and AI workforce impact, separate confirmed layoffs from planned, reported, expected, or claimed cuts. Put people counts in count. If the article says planned or coming, status must be "Planned / reported".
- For non-headcount signals, count should be 1 per distinct event and count_type should be "events" unless a better factual numeric metric is explicitly present.
- If there is no reliable event, return {"events":[]}.
- Evidence must be a concise sentence or clause from the article that proves the extraction.
"""


def _article_signal_text(article):
    parts = [article.get("company", ""), article.get("headline", ""), article.get("source", ""), article.get("articleSummary", ""), article.get("fullArticleText", "")]
    return _clean_article_block(". ".join(str(part or "") for part in parts))[:60000]




def _provider_error_detail(exc):
    if isinstance(exc, urllib.error.HTTPError):
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        if body:
            try:
                payload = json.loads(body)
                err = payload.get("error") if isinstance(payload, dict) else None
                if isinstance(err, dict):
                    message = err.get("message") or err.get("type") or body
                    code = err.get("code") or err.get("type")
                    return f"HTTP {exc.code}: {message}" + (f" ({code})" if code else "")
                if isinstance(err, str):
                    return f"HTTP {exc.code}: {err}"
            except json.JSONDecodeError:
                pass
            return f"HTTP {exc.code}: {body[:500]}"
        return f"HTTP {exc.code}: {exc.reason}"
    return str(exc)

def _json_from_model_text(text):
    raw = str(text or "").strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I | re.S).strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end >= start:
        raw = raw[start:end + 1]
    return json.loads(raw)


def _coerce_float(value, default=0.0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, number))


def _coerce_count(value):
    if isinstance(value, (int, float)):
        return max(0, int(round(value)))
    text = str(value or "").lower().replace(",", "")
    match = re.search(r"(\d+(?:\.\d+)?)\s*(k|m|thousand|million)?", text)
    if not match:
        return 0
    number = float(match.group(1))
    unit = match.group(2) or ""
    if unit in {"k", "thousand"}:
        number *= 1000
    if unit in {"m", "million"}:
        number *= 1000000
    return max(0, int(round(number)))


def _extract_people_count(sentence):
    patterns = [
        r"(\d[\d,]*(?:\.\d+)?\s*(?:k|m|thousand|million)?)(?:\s+more)?[^a-z0-9]{0,20}(?:jobs?|roles?|employees?|workers?|staff|positions?|people|job cuts?)",
        r"(?:lay(?:s|ing)? off|laid off|cut(?:s|ting)?|job cuts?|headcount reduction|workforce reduction)[^.]{0,120}?(\d[\d,]*(?:\.\d+)?\s*(?:k|m|thousand|million)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, sentence, re.I)
        if match:
            return _coerce_count(match.group(1))
    return 0


def _normalize_signal_events(payload, provider, article, signals):
    signal_map = {str(item.get("id") or ""): item for item in signals if isinstance(item, dict)}
    raw_events = payload.get("events", payload if isinstance(payload, list) else []) if isinstance(payload, (dict, list)) else []
    clean = []
    seen = set()
    for event in raw_events[:30]:
        if not isinstance(event, dict):
            continue
        signal_id = str(event.get("signal_id") or event.get("signalId") or event.get("id") or "").strip()
        if signal_id not in signal_map:
            continue
        signal = signal_map[signal_id]
        evidence = _clean_article_block(str(event.get("evidence") or event.get("sentence") or ""))[:500]
        if not evidence:
            continue
        status = str(event.get("status") or "Needs review").strip()
        if status.lower() in {"confirmed", "complete", "announced"}:
            status = "Confirmed"
        elif re.search(r"planned|reported|expected|claim|could|may|might|coming", status, re.I):
            status = "Planned / reported"
        else:
            status = "Needs review"
        count = _coerce_count(event.get("count"))
        if signal.get("metric") == "layoffHeadcount" and not count:
            count = _extract_people_count(evidence)
        if signal.get("metric") != "layoffHeadcount" and not count:
            count = 1
        name = _clean_signal_event_name(str(event.get("event_name") or event.get("eventName") or event.get("label") or ""), article) or _clean_signal_event_name(evidence, article) or str(signal.get("label") or signal_id)[:160]
        key = (signal_id, name.lower(), evidence[:120].lower())
        if key in seen:
            continue
        seen.add(key)
        clean.append({
            "provider": provider,
            "signal_id": signal_id,
            "signal_label": str(event.get("signal_label") or event.get("signalLabel") or signal.get("label") or signal_id),
            "event_name": name,
            "status": status,
            "count": count,
            "count_type": str(event.get("count_type") or event.get("countType") or ("people" if signal.get("metric") == "layoffHeadcount" else "events")),
            "date_or_period": str(event.get("date_or_period") or event.get("dateOrPeriod") or "Unspecified")[:80],
            "evidence": evidence,
            "confidence": _coerce_float(event.get("confidence"), 0.55),
            "is_account_actor": bool(event.get("is_account_actor", event.get("isAccountActor", True))),
            "articleId": article.get("id") or "",
        })
    return clean


def _company_aliases_dynamic(company):
    raw = str(company or "").strip()
    if not raw:
        return []
    spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", raw)
    variants = {raw, spaced, raw.replace(" ", ""), spaced.replace(" ", "")}
    suffix_re = re.compile(r"\b(inc|inc\.|corp|corp\.|corporation|co|co\.|company|ltd|ltd\.|limited|plc|llc|technologies|technology|tech|systems|services|group|holdings)\b", re.I)
    for variant in list(variants):
        trimmed = suffix_re.sub("", variant).strip(" ,.-")
        if trimmed:
            variants.add(trimmed)
            variants.add(trimmed.replace(" ", ""))
        if re.search(r"\btech\b", variant, re.I):
            variants.add(re.sub(r"\btech\b", "Technologies", variant, flags=re.I))
    return sorted({item for item in variants if len(item.strip()) >= 2}, key=len, reverse=True)


def _split_signal_sentences(text):
    compact = re.sub(r"\s+", " ", str(text or "")).strip()
    parts = re.split(r"(?<=[.!?;])\s+|\n+", compact)
    return [part.strip(" -") for part in parts if len(part.strip()) >= 25]


def _actor_trigger(signal_id):
    return {"productLaunches": r"launch(?:es|ed)?|unveil(?:s|ed)?|introduc(?:es|ed)?|rolls? out", "aiProductLaunches": r"launch(?:es|ed)?|unveil(?:s|ed)?|introduc(?:es|ed)?|rolls? out", "partnerships": r"partner(?:s|ed)?|teams up|collaborat(?:es|ed|ion)|alliance|joint venture", "aiPartnerships": r"partner(?:s|ed)?|teams up|collaborat(?:es|ed|ion)|alliance|joint venture", "ma": r"acquir(?:es|ed)?|buy(?:s|ing)?|merger|takeover|deal to buy"}.get(signal_id)


def _mentions_alias(sentence, aliases):
    lower = sentence.lower()
    return any(re.search(r"\b" + re.escape(alias.lower()) + r"\b", lower) for alias in aliases)


def _account_is_actor_local(sentence, aliases, signal_id):
    trigger = _actor_trigger(signal_id)
    if not trigger:
        return _mentions_alias(sentence, aliases)
    for alias in aliases:
        escaped = re.escape(alias)
        if re.search(r"\b" + escaped + r"\b[^.;:]{0,70}\b(?:" + trigger + r")\b", sentence, re.I):
            return True
        if re.search(r"\b(?:partnership|alliance|collaboration|merger)\b[^.;:]{0,90}\b" + escaped + r"\b", sentence, re.I):
            return True
    return False


def _local_status(sentence):
    lower = sentence.lower()
    if re.search(r"\b(report claims|reportedly|sources said|could|may|might|expected|likely|planning|plans to|set to|coming|proposed|considering|aims to|forecast|rumou?r)\b", lower):
        return "Planned / reported"
    if re.search(r"\b(announced|confirmed|said it has|said it will|launched|unveiled|introduced|rolled out|completed|signed|partnered|acquired|reported|cut|laid off|eliminated)\b", lower):
        return "Confirmed"
    return "Needs review"



def _clean_signal_event_name(value, article=None):
    text = _clean_article_block(value)
    company = str((article or {}).get("company") or "").strip()
    if company:
        text = re.sub(r"^" + re.escape(company) + r"\s+", "", text, flags=re.I)
    text = re.sub(r"^\(?[A-Z]{1,6}\)?\s+", "", text)
    text = re.sub(r"\b(today|announces?|launches?|launched|unveils?|unveiled|introduces?|introduced|rolls out|rolled out|partners?|partnered|acquires?|acquired|reports?|reported|says|said)\b", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" ,:;.-")
    text = re.sub(r"\s+(as|to|for|after|before|despite|amid|while|when|with)\s+.{45,}$", "", text, flags=re.I).strip(" ,:;.-")
    weak = (not text or len(text) < 4 or re.search(r"^(new|company|offerings?|platform|solution|service|product|experience|cloud|have|has|had|with|for|to|as|and|the|a|an)\b", text, re.I) or re.search(r"\b(have|has|had|coincided|barely existed|stock|shares|target price|cmp|52-week|despite|amid)\b", text, re.I) or len(text.split()) > 12)
    if weak:
        return ""
    return text[:160]

def _event_name_from_sentence(sentence, signal, article=None):
    signal_id = str(signal.get("id") or "")
    if signal_id in {"productLaunches", "aiProductLaunches"}:
        patterns = [
            r"\b(?:launches|launched|unveils|unveiled|introduces|introduced|rolls out|rolled out)\s+(?:(?:an?|the|its|new)\s+)?([^.;:]{3,140})",
            r"\bnew\s+(?:ai\s+)?(?:product|platform|service|feature|tool|solution|assistant|agent)\s+([^.;:]{3,120})",
        ]
    elif signal_id in {"partnerships", "aiPartnerships"}:
        patterns = [
            r"\b(?:partners|partnered|teams up|collaborates|collaboration|alliance)\s+(?:with|between)?\s*([^.;:]{3,140})",
            r"\bpartnership\s+(?:with|between)?\s*([^.;:]{3,140})",
        ]
    elif signal_id == "ma":
        patterns = [
            r"\b(?:acquires|acquired|buying|to buy|merger with|takeover of)\s+([^.;:]{3,140})",
            r"\bacquisition\s+of\s+([^.;:]{3,140})",
        ]
    else:
        patterns = []
    for pattern in patterns:
        match = re.search(pattern, sentence, re.I)
        if match:
            name = _clean_signal_event_name(match.group(1), article)
            if name:
                return name
    return _clean_signal_event_name(sentence, article) or _clean_article_block(sentence)[:120]
def _local_signal_intelligence(article, signals):
    account = str(article.get("company") or "").strip()
    aliases = _company_aliases_dynamic(account)
    sentences = _split_signal_sentences(_article_signal_text(article))
    raw_events = []
    seen = set()
    for signal in signals:
        signal_id = str(signal.get("id") or "")
        keywords = [str(keyword or "").lower() for keyword in signal.get("keywords") or []]
        for sentence in sentences:
            lower = sentence.lower()
            if not any(keyword in lower for keyword in keywords):
                continue
            if re.search(r"\b(also read|read more|stock to buy|hold|target price|cmp:|52-week low)\b", sentence, re.I):
                continue
            actor_ok = _account_is_actor_local(sentence, aliases, signal_id)
            if _actor_trigger(signal_id) and not actor_ok:
                continue
            if not actor_ok and account and account.lower() not in str(article.get("headline", "")).lower():
                continue
            count = _extract_people_count(sentence) if signal.get("metric") == "layoffHeadcount" else 1
            if signal.get("metric") == "layoffHeadcount" and not count:
                continue
            name = _event_name_from_sentence(sentence, signal, article)
            key = (signal_id, name.lower(), sentence[:100].lower())
            if key in seen:
                continue
            seen.add(key)
            status = _local_status(sentence)
            confidence = 0.78 if actor_ok else 0.58
            if status == "Needs review":
                confidence -= 0.15
            raw_events.append({"signal_id": signal_id, "signal_label": signal.get("label") or signal_id, "event_name": name, "status": status, "count": count, "count_type": "people" if signal.get("metric") == "layoffHeadcount" else "events", "date_or_period": "Unspecified", "evidence": sentence[:500], "confidence": confidence, "is_account_actor": actor_ok})
            break
    return _normalize_signal_events({"events": raw_events}, "local", article, signals)


def _signal_intelligence_payload(article, signals):
    return json.dumps({"account": article.get("company") or "", "headline": article.get("headline") or "", "source": article.get("source") or "", "published": article.get("displayDate") or article.get("date") or "", "url": article.get("url") or "", "article_text": _article_signal_text(article), "signals": signals}, ensure_ascii=False)


def _call_openai_signal_intelligence(api_key, article, signals):
    body = json.dumps({"model": os.environ.get("KESTRELIQ_OPENAI_SIGNAL_MODEL", "gpt-4o-mini"), "messages": [{"role": "system", "content": SIGNAL_INTELLIGENCE_PROMPT}, {"role": "user", "content": _signal_intelligence_payload(article, signals)}], "temperature": 0.0, "response_format": {"type": "json_object"}}).encode("utf-8")
    req = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=body, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=90) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
    return _normalize_signal_events(_json_from_model_text(payload["choices"][0]["message"]["content"]), "openai", article, signals)


def _call_claude_signal_intelligence(api_key, article, signals):
    body = json.dumps({"model": os.environ.get("KESTRELIQ_CLAUDE_SIGNAL_MODEL", "claude-3-5-sonnet-20241022"), "max_tokens": 2500, "temperature": 0.0, "system": SIGNAL_INTELLIGENCE_PROMPT, "messages": [{"role": "user", "content": _signal_intelligence_payload(article, signals)}]}).encode("utf-8")
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=90) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
    text = "\n".join(part.get("text", "") for part in payload.get("content", []) if part.get("type") == "text").strip()
    return _normalize_signal_events(_json_from_model_text(text), "claude", article, signals)
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
    ("Generative AI", ("generative ai", "genai", "llm", "large language model", "gpt", "claude", "gemini", "copilot")),
    ("Agentic AI", ("agentic ai", "ai agent", "autonomous agent", "multi-agent", "workflow agent", "agent platform")),
    ("AI New Launches", ("ai launch", "ai product", "launches ai", "unveils ai", "introduces ai", "new ai", "ai assistant", "ai agent")),
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
    urls = _rss_urls(company, days, mode=mode, keyword_config=keyword_config)
    last_fetch_error = None
    for index, url in enumerate(urls):
        if stats is not None:
            stats["rssUrlsRequested"] += 1
            stats["rssUrls"].append({
                "target": company,
                "type": _rss_type(index, mode),
                "url": url,
                "cacheHit": False,
            })
        target_stats["rssUrls"] += 1
        try:
            xml_bytes = _fetch_url(url, timeout=8)
            root = ET.fromstring(xml_bytes)
        except (urllib.error.URLError, TimeoutError, ET.ParseError, OSError) as exc:
            last_fetch_error = exc
            if index < len(urls) - 1:
                continue
            if not items:
                raise
            break
        for item in root.findall("./channel/item"):
            if stats is not None:
                stats["rawItemsScanned"] += 1
            target_stats["rawItems"] += 1
            title = _clean_title(item.findtext("title"))
            rss_summary = _clean_rss_summary(item.findtext("description"), title)
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
                "articleSummary": rss_summary,
                "url": link,
                "sentiment": _sentiment(title),
                "scanThemes": raw_themes,
            })

    if last_fetch_error and not items:
        raise last_fetch_error

    items.sort(key=lambda item: item.get("date") or "", reverse=True)
    target_stats["keptItems"] = len(items)
    target_stats["latestUpdate"] = items[0].get("publishedIST", "") if items else ""
    target_stats["sources"] = sorted(target_stats["sources"])
    if stats is not None:
        stats["relevantItemsKept"] += len(items)
        stats["perTarget"].append(target_stats)

    NEWS_CACHE[cache_key] = {"time": time.time(), "items": items, "targetStats": target_stats}
    return items


def _agency_meta(name):
    normalized = _normalize_text(name)
    if normalized in {"forrester", "forester"}:
        normalized = "forrester"
    if normalized in {"gartner", "garner"}:
        normalized = "gartner"
    if normalized in {"everest", "everestgroup"}:
        normalized = "everestgroup"
    if normalized in {"nelsonhall"}:
        normalized = "nelsonhall"
    if normalized in {"frostandsullivan", "frostsullivan"}:
        normalized = "frostsullivan"
    if normalized in {"informationservicesgroup", "isg"}:
        normalized = "isg"
    if normalized in {"hfs", "hfsresearch"}:
        normalized = "hfsresearch"
    return AGENCY_FEEDS.get(normalized)


def _is_allowed_agency_url(url, meta):
    parsed = urllib.parse.urlparse(str(url or "").strip())
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme not in {"http", "https"} or not hostname:
        return False
    return any(
        hostname == domain or hostname.endswith(f".{domain}")
        for domain in meta.get("domains", [])
    )


def _agency_article_brief(article):
    fallback = _clean_article_block(article.get("articleSummary", ""))
    try:
        extracted = _article_text_from_url(
            article.get("url", ""),
            article.get("headline", ""),
            article.get("source", ""),
        )
        body = _clean_article_block(extracted.get("text", ""))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return fallback

    headline = _clean_article_block(article.get("headline", ""))
    if headline and body.lower().startswith(headline.lower()):
        body = body[len(headline):].lstrip(" :-")
    sentences = re.split(r"(?<=[.!?])\s+", body)
    selected = []
    seen = set()
    total = 0
    for sentence in sentences:
        sentence = _clean_article_block(sentence)
        normalized = re.sub(r"[^a-z0-9]+", " ", sentence.lower()).strip()
        if len(sentence) < 45 or not normalized or normalized in seen or _is_article_noise(sentence):
            continue
        if total + len(sentence) > 1100 and selected:
            break
        selected.append(sentence)
        seen.add(normalized)
        total += len(sentence) + 1
        if len(selected) >= 7:
            break
    return " ".join(selected) or fallback


def _fetch_agency_news(name, days, stats=None):
    meta = _agency_meta(name)
    if not meta:
        raise ValueError(f"Unknown agency source: {name}")
    agency = meta["name"]
    cache_key = ("agency", agency.lower(), days)
    cached = NEWS_CACHE.get(cache_key)
    if cached and time.time() - cached["time"] < CACHE_SECONDS:
        if stats is not None:
            feeds = meta.get("feeds") or []
            stats["rssUrlsRequested"] += len(feeds)
            stats["rssUrls"].extend([
                {"target": agency, "type": _rss_type(i, "agency"), "url": url, "cacheHit": True}
                for i, url in enumerate(feeds)
            ])
            stats["relevantItemsKept"] += len(cached["items"])
            cached_target = dict(cached.get("targetStats") or {})
            if cached_target:
                cached_target["cacheHit"] = True
                stats["rawItemsScanned"] += int(cached_target.get("rawItems") or 0)
                stats["duplicateCount"] += int(cached_target.get("duplicateItems") or 0)
                stats["perTarget"].append(cached_target)
        return cached["items"]

    items = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days) if days else None
    seen = set()
    target_stats = {
        "name": agency,
        "rssUrls": 0,
        "rawItems": 0,
        "keptItems": 0,
        "duplicateItems": 0,
        "relevanceDiscarded": 0,
        "sources": set(),
        "latestUpdate": "",
        "cacheHit": False,
        "themeCounts": {**_scan_theme_counts_template("interests"), "Market Watch": {"raw": 0, "kept": 0}},
    }
    last_fetch_error = None
    for index, url in enumerate(meta.get("feeds") or []):
        if stats is not None:
            stats["rssUrlsRequested"] += 1
            stats["rssUrls"].append({
                "target": agency,
                "type": _rss_type(index, "agency"),
                "url": url,
                "cacheHit": False,
            })
        target_stats["rssUrls"] += 1
        try:
            xml_bytes = _fetch_url(url, timeout=10)
            root = ET.fromstring(xml_bytes)
        except (urllib.error.URLError, TimeoutError, ET.ParseError, OSError) as exc:
            last_fetch_error = exc
            continue
        for item in root.findall("./channel/item")[:12]:
            if stats is not None:
                stats["rawItemsScanned"] += 1
            target_stats["rawItems"] += 1
            title = _clean_title(item.findtext("title"))
            link = item.findtext("link") or ""
            published = _item_published_date(item)
            rss_summary = _clean_rss_summary(item.findtext("description"), title)
            if meta.get("resolve_links"):
                try:
                    link = _resolve_google_news_url(link)
                except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError, IndexError, TypeError):
                    continue
            raw_themes = _scan_themes_for_title(title, "interests")
            for theme in raw_themes:
                target_stats["themeCounts"].setdefault(theme, {"raw": 0, "kept": 0})["raw"] += 1
            if cutoff and published and published < cutoff:
                continue
            if not title or not link:
                continue
            if not _is_allowed_agency_url(link, meta):
                if stats is not None:
                    stats["relevanceDiscarded"] += 1
                target_stats["relevanceDiscarded"] += 1
                continue
            key = (title.lower(), link.lower())
            if key in seen:
                if stats is not None:
                    stats["duplicateCount"] += 1
                target_stats["duplicateItems"] += 1
                continue
            seen.add(key)
            for theme in raw_themes:
                target_stats["themeCounts"].setdefault(theme, {"raw": 0, "kept": 0})["kept"] += 1
            target_stats["sources"].add(agency)
            items.append({
                "id": _article_id(agency, title, link),
                "company": agency,
                "vertical": "Research",
                "date": published.isoformat() if published else "",
                "displayDate": published.strftime("%d %b %Y") if published else "",
                "displayTimeIST": published.astimezone(IST).strftime("%I:%M %p IST") if published else "",
                "publishedIST": published.astimezone(IST).strftime("%d %b %Y, %I:%M %p IST") if published else "",
                "source": agency,
                "headline": title,
                "articleSummary": rss_summary,
                "url": link,
                "sentiment": _sentiment(title),
                "scanThemes": raw_themes,
            })

    if last_fetch_error and not items:
        raise last_fetch_error

    items.sort(key=lambda item: item.get("date") or "", reverse=True)
    if items:
        with ThreadPoolExecutor(max_workers=min(4, len(items))) as executor:
            briefs = list(executor.map(_agency_article_brief, items))
        for article, brief in zip(items, briefs):
            if brief:
                article["articleSummary"] = brief
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
    if mode == "agency":
        days = max(days or 0, 30)
    stats = _empty_scan_stats(companies, date_range, mode)
    articles = []
    errors = []
    names = [str(company).strip() for company in companies if str(company).strip()]
    if mode == "agency":
        with ThreadPoolExecutor(max_workers=min(7, len(names) or 1)) as executor:
            jobs = [(name, executor.submit(_fetch_agency_news, name, days, None)) for name in names]
            for name, job in jobs:
                try:
                    source_items = job.result()
                    articles.extend(source_items)
                    stats["perTarget"].append({
                        "name": name,
                        "keptItems": len(source_items),
                        "sources": sorted({item.get("source") for item in source_items if item.get("source")}),
                        "themeCounts": {},
                    })
                except (urllib.error.URLError, TimeoutError, ET.ParseError, OSError, ValueError) as exc:
                    errors.append({"company": name, "error": str(exc)})
                    stats["errorsCount"] += 1
    else:
        for name in names:
            try:
                articles.extend(_fetch_company_news(name, days, mode=mode, stats=stats, keyword_config=keyword_config))
            except (urllib.error.URLError, TimeoutError, ET.ParseError, OSError, ValueError) as exc:
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
    if mode == "agency":
        source_order = [str(name).strip().lower() for name in companies if str(name).strip()]
        buckets = {
            source: [item for item in sorted_articles if str(item.get("source") or "").lower() == source]
            for source in source_order
        }
        interleaved = []
        while any(buckets.values()):
            for source in source_order:
                if buckets.get(source):
                    interleaved.append(buckets[source].pop(0))
        known_ids = {item["id"] for item in interleaved}
        sorted_articles = interleaved + [item for item in sorted_articles if item["id"] not in known_ids]
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


def _fortune_news_url(companies, days=2):
    company_clause = " OR ".join(f'"{name}"' for name in companies)
    query = f"({company_clause}) (AI OR technology OR cloud OR digital OR partnership OR launch OR regulation OR cybersecurity OR automation) when:{days}d"
    params = urllib.parse.urlencode({
        "q": query,
        "hl": "en-US",
        "gl": "US",
        "ceid": "US:en",
        "scoring": "n",
    })
    return f"https://news.google.com/rss/search?{params}"


def _match_fortune_company(title, company_rows):
    for row in sorted(company_rows, key=lambda item: len(item["name"]), reverse=True):
        if row["name"] in {"Target", "UPS"}:
            if re.search(r"\b" + re.escape(row["name"]) + r"\b", title):
                return row
            continue
        if any(re.search(r"\b" + re.escape(alias) + r"\b", title, re.I) for alias in _company_aliases_dynamic(row["name"])):
            return row
    return None


def _fetch_fortune_news(company_rows, days=2):
    cache_key = ("fortune50", days)
    cached = NEWS_CACHE.get(cache_key)
    if cached and time.time() - cached["time"] < CACHE_SECONDS:
        return cached["items"]
    batches = [company_rows[index:index + 10] for index in range(0, len(company_rows), 10)]

    def fetch_batch(batch):
        root = ET.fromstring(_fetch_url(_fortune_news_url([row["name"] for row in batch], days), timeout=15))
        found = []
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        for item in root.findall("./channel/item")[:35]:
            title = _clean_title(item.findtext("title"))
            published = _item_published_date(item)
            source = _parse_google_source(item)
            link = item.findtext("link") or ""
            company = _match_fortune_company(title, batch)
            if not title or not link or not company or (published and published < cutoff):
                continue
            text = f"{title} {source}".lower()
            if re.search(r"motley fool|yahoo finance|barchart|simplywall|simply wall|thestreet|investor'?s business daily|benzinga|marketbeat|stocktwits|seeking alpha|quiver quantitative|24/7 wall|tradingview|basenor", text):
                continue
            if re.search(r"\bstock\b|\bshares?\b|buy or sell|price target|dividend|undervalued|overvalued|technical analysis|market cap|wall street|analyst upgrades?", text):
                continue
            if not re.search(r"\b(ai|artificial intelligence|agentic|llm|claude|model|technology|cloud|digital|platform|chip|semiconductor|data cent(?:er|re)|cyber|security|automation|robot|copilot|generative)\b", title, re.I):
                continue
            found.append({
                "id": _article_id(company["name"], title, link),
                "company": company["name"],
                "companyRank": company["rank"],
                "vertical": company.get("sector") or "Fortune 500",
                "date": published.isoformat() if published else "",
                "displayDate": published.strftime("%d %b %Y") if published else "",
                "displayTimeIST": published.astimezone(IST).strftime("%I:%M %p IST") if published else "",
                "publishedIST": published.astimezone(IST).strftime("%d %b %Y, %I:%M %p IST") if published else "",
                "source": source,
                "headline": title,
                "articleSummary": _clean_rss_summary(item.findtext("description"), title),
                "url": link,
                "sentiment": _sentiment(title),
                "scanThemes": _scan_themes_for_title(title, "interests"),
            })
        return found

    articles = []
    with ThreadPoolExecutor(max_workers=len(batches) or 1) as executor:
        jobs = [executor.submit(fetch_batch, batch) for batch in batches]
        for job in jobs:
            try:
                articles.extend(job.result())
            except (urllib.error.URLError, TimeoutError, ET.ParseError, OSError):
                continue
    deduped = {}
    for article in articles:
        deduped.setdefault((article["headline"].lower(), article["source"].lower()), article)
    result = sorted(deduped.values(), key=lambda item: item.get("date") or "", reverse=True)[:16]
    NEWS_CACHE[cache_key] = {"time": time.time(), "items": result}
    return result


def _fetch_llm_rankings():
    cache_key = ("llm-rankings", "artificial-analysis")
    cached = NEWS_CACHE.get(cache_key)
    if cached and time.time() - cached["time"] < CACHE_SECONDS:
        return cached["items"]
    raw = _fetch_url(LLM_RANKINGS_URL, accept="text/html, application/xhtml+xml", timeout=20)
    page = raw.decode("utf-8", errors="replace")
    providers = ("Anthropic", "OpenAI", "Google", "xAI", "Meta", "DeepSeek", "Alibaba", "Mistral", "Moonshot", "Zhipu")
    rows = []
    seen = set()
    for match in re.finditer(r"<tr[^>]*>.*?</tr>", page, re.S):
        text = html.unescape(re.sub(r"<[^>]+>", " ", match.group(0)))
        text = re.sub(r"\s+", " ", text).strip()
        provider_match = re.search(r"\b(" + "|".join(re.escape(item) for item in providers) + r")\b", text)
        context_match = re.search(r"\b\d+(?:\.\d+)?[kKmM]\b", text)
        if not provider_match or not context_match or context_match.start() >= provider_match.start():
            continue
        model = text[:context_match.start()].strip()
        context = text[context_match.start():context_match.end()]
        creator = provider_match.group(1)
        metrics = text[provider_match.end():].strip()
        intelligence_match = re.search(r"\b\d{1,3}\b\s*\*?", metrics)
        if not model or not intelligence_match:
            continue
        intelligence = intelligence_match.group(0).replace("*", "").strip()
        metric_tail = metrics[intelligence_match.end():]
        metric_values = re.findall(r"\$\s*[\d.]+|--|[\d.]+", metric_tail)
        price = metric_values[0].replace(" ", "") if len(metric_values) > 0 else "--"
        speed = metric_values[1] if len(metric_values) > 1 else "--"
        latency = metric_values[2] if len(metric_values) > 2 else "--"
        response_time = metric_values[3] if len(metric_values) > 3 else "--"
        key = (model.lower(), creator.lower())
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "rank": len(rows) + 1,
            "model": model,
            "creator": creator,
            "context": context.upper(),
            "intelligence": intelligence,
            "price": price,
            "speed": speed,
            "latency": latency,
            "responseTime": response_time,
        })
        if len(rows) >= 30:
            break
    NEWS_CACHE[cache_key] = {"time": time.time(), "items": rows}
    return rows


def _fetch_stock_quote(symbol="CNXC"):
    ticker = re.sub(r"[^A-Za-z0-9.^-]", "", str(symbol or "CNXC")).upper() or "CNXC"
    cache_key = ("stock-quote", ticker)
    cached = NEWS_CACHE.get(cache_key)
    if cached and time.time() - cached["time"] < QUOTE_CACHE_SECONDS:
        return cached["item"]
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ticker)}?interval=1d&range=1d"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; KestrelIQ/1.0; +local executive intelligence app)",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
    result = (payload.get("chart", {}).get("result") or [{}])[0]
    meta = result.get("meta") or {}
    price = meta.get("regularMarketPrice")
    previous = meta.get("chartPreviousClose")
    change = (price - previous) if isinstance(price, (int, float)) and isinstance(previous, (int, float)) else None
    change_percent = (change / previous * 100) if change is not None and previous else None
    market_time = meta.get("regularMarketTime")
    updated = ""
    if market_time:
        try:
            updated = datetime.fromtimestamp(int(market_time), timezone.utc).astimezone(IST).strftime("%d %b %Y, %I:%M %p IST")
        except (OSError, ValueError, TypeError):
            updated = ""
    item = {
        "symbol": meta.get("symbol") or ticker,
        "name": meta.get("shortName") or meta.get("longName") or ticker,
        "exchange": meta.get("fullExchangeName") or meta.get("exchangeName") or "",
        "currency": meta.get("currency") or "USD",
        "price": price,
        "previousClose": previous,
        "change": change,
        "changePercent": change_percent,
        "volume": meta.get("regularMarketVolume"),
        "updatedAt": updated,
        "source": "Yahoo Finance",
    }
    NEWS_CACHE[cache_key] = {"time": time.time(), "item": item}
    return item


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
        if self.path.startswith("/assets/"):
            asset = ASSET_DIR / Path(urllib.parse.urlparse(self.path).path).name
            if asset.exists() and asset.is_file() and asset.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
                mime = {".png": "image/png", ".webp": "image/webp"}.get(asset.suffix.lower(), "image/jpeg")
                payload = asset.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                self.wfile.write(payload)
                return
            _json_response(self, 404, {"error": "Asset not found"})
            return
        if self.path == "/api/fortune-intelligence":
            if not FORTUNE_FILE.exists():
                _json_response(self, 503, {"error": "Fortune 500 data is unavailable."})
                return
            ranking = json.loads(FORTUNE_FILE.read_text(encoding="utf-8"))
            companies = ranking.get("companies") or []
            news = _fetch_fortune_news(companies[:50], days=2)
            _json_response(self, 200, {
                "year": ranking.get("year"),
                "source": ranking.get("source"),
                "sourceUrl": ranking.get("sourceUrl"),
                "companies": companies,
                "news": news,
            })
            return
        if self.path == "/api/llm-rankings":
            try:
                rankings = _fetch_llm_rankings()
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                _json_response(self, 503, {"error": f"LLM rankings are temporarily unavailable. {exc}"})
                return
            _json_response(self, 200, {
                "source": "Artificial Analysis",
                "sourceUrl": LLM_RANKINGS_URL,
                "updatedAt": datetime.now(IST).strftime("%d %b %Y, %I:%M %p IST"),
                "rankings": rankings,
            })
            return
        if self.path.startswith("/api/stock-quote"):
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            symbol = (query.get("symbol") or ["CNXC"])[0]
            try:
                quote = _fetch_stock_quote(symbol)
            except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                _json_response(self, 503, {"error": f"Stock quote is temporarily unavailable. {exc}"})
                return
            _json_response(self, 200, quote)
            return
        if self.path == "/api/health":
            _json_response(self, 200, {"ok": True, "service": "KestrelIQ"})
            return
        _json_response(self, 404, {"error": "Not found"})

    def do_POST(self):
        post_path = self.path.split("?", 1)[0].rstrip("/")
        if post_path == "/api/signal-intelligence":
            payload = _read_json(self)
            provider = str(payload.get("provider") or "local").strip().lower()
            api_key = str(payload.get("apiKey") or "").strip()
            article = payload.get("article") or {}
            signals = payload.get("signals") or []
            if provider not in {"local", "openai", "claude"}:
                _json_response(self, 400, {"error": "Provider must be local, openai, or claude."})
                return
            if provider in {"openai", "claude"} and not api_key:
                _json_response(self, 400, {"error": "API key is required for this intelligence engine."})
                return
            if not isinstance(article, dict) or not str(article.get("headline") or "").strip():
                _json_response(self, 400, {"error": "Article is required."})
                return
            if not isinstance(signals, list) or not signals:
                _json_response(self, 400, {"error": "Signal taxonomy is required."})
                return
            try:
                if provider == "local":
                    events = _local_signal_intelligence(article, signals)
                elif provider == "openai":
                    events = _call_openai_signal_intelligence(api_key, article, signals)
                else:
                    events = _call_claude_signal_intelligence(api_key, article, signals)
                _json_response(self, 200, {"provider": provider, "events": events})
            except (urllib.error.URLError, TimeoutError, OSError, KeyError, IndexError, json.JSONDecodeError, ValueError) as exc:
                _json_response(self, 502, {"error": "Could not extract signal intelligence.", "detail": _provider_error_detail(exc)})
            return
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
        if self.path == "/api/executive-summary":
            payload = _read_json(self)
            provider = str(payload.get("provider") or "").strip().lower()
            api_key = str(payload.get("apiKey") or "").strip()
            document_text = str(payload.get("documentText") or "").strip()
            if provider not in {"openai", "claude"}:
                _json_response(self, 400, {"error": "Provider must be openai or claude."})
                return
            if not api_key:
                _json_response(self, 400, {"error": "API key is required."})
                return
            if len(document_text) < 200:
                _json_response(self, 400, {"error": "Briefing text is too short to summarize."})
                return
            try:
                if provider == "openai":
                    summary_html = _call_openai_summary(api_key, document_text)
                else:
                    summary_html = _call_claude_summary(api_key, document_text)
                _json_response(self, 200, {"summaryHtml": summary_html})
            except (urllib.error.URLError, TimeoutError, OSError, KeyError, IndexError, json.JSONDecodeError) as exc:
                _json_response(self, 502, {
                    "error": "Could not generate the executive summary.",
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






