from __future__ import annotations

import base64
import json
import os
import threading
import time
import urllib.request
from io import BytesIO
from typing import Any

import pandas as pd

from sentiment_analysis_engine import build_analysis, sentiment_summary


PROGRESS: dict[str, dict[str, Any]] = {}
PROGRESS_LOCK = threading.Lock()


def _openai_sentiment(texts: list[str]) -> list[dict[str, Any]]:
    api_key = os.environ.get("OPENAI_API_KEY") or ""
    if not api_key:
        raise ValueError("OpenAI is not configured. Add OPENAI_API_KEY to the KestrelIQ server environment.")
    body = {
        "model": os.environ.get("KESTRELIQ_OPENAI_SENTIMENT_MODEL", "gpt-4o-mini"),
        "messages": [
            {
                "role": "system",
                "content": (
                    "Classify customer feedback sentiment. Return JSON only with an items array. "
                    "Each item must contain index, sentiment (Positive, Neutral, or Negative), "
                    "confidence from 0 to 1, and a concise rationale. Preserve every input index."
                ),
            },
            {"role": "user", "content": json.dumps({"feedback": [{"index": index, "text": text[:4000]} for index, text in enumerate(texts)]}, ensure_ascii=False)},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
    content = payload["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    items = parsed.get("items") if isinstance(parsed, dict) else None
    if not isinstance(items, list) or len(items) != len(texts):
        raise RuntimeError("OpenAI returned an incomplete sentiment batch.")
    return items


def _decode(payload: dict[str, Any]) -> pd.DataFrame:
    raw = str(payload.get("data") or "")
    if "," in raw:
        raw = raw.split(",", 1)[1]
    content = base64.b64decode(raw)
    name = str(payload.get("name") or "").lower()
    if name.endswith(".csv"):
        return pd.read_csv(BytesIO(content))
    if name.endswith((".tsv", ".txt")):
        return pd.read_csv(BytesIO(content), sep="\t")
    return pd.read_excel(BytesIO(content))


def _guess(columns: list[str]) -> dict[str, str]:
    lowered = {str(column).lower(): str(column) for column in columns}

    def pick(*needles: str) -> str:
        for needle in needles:
            for lower, original in lowered.items():
                if needle in lower:
                    return original
        return ""

    return {
        "feedback": pick("comment", "verbatim", "feedback", "review", "response", "text"),
        "agent": pick("agent", "advisor", "employee", "associate"),
        "manager": pick("manager/tl", "tl name", "team manager", "manager", "supervisor"),
        "date": pick("date", "survey date", "response date", "created"),
    }


def _column_profile(frame: pd.DataFrame) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for column in frame.columns:
        series = frame[column]
        text = series.fillna("").astype(str).str.strip()
        non_blank = text[text != ""]
        unique = int(non_blank.nunique())
        numeric = pd.to_numeric(non_blank, errors="coerce")
        data_type = "Number" if not non_blank.empty and numeric.notna().mean() >= 0.9 else "Text"
        result[str(column)] = {
            "totalEntries": len(frame),
            "totalBlanks": int((text == "").sum()),
            "unique": unique,
            "uniqueLabel": f"{unique:,}",
            "uniqueValues": non_blank.drop_duplicates().head(7).tolist() if unique < 8 else [],
            "dataType": data_type,
            "sampleValue": str(non_blank.iloc[0]) if not non_blank.empty else "",
        }
    return result


def inspect(payload: dict[str, Any]) -> dict[str, Any]:
    frame = _decode(payload)
    columns = [str(column) for column in frame.columns]
    return {
        "ok": True,
        "rows": len(frame),
        "columns": columns,
        "guesses": _guess(columns),
        "columnStats": _column_profile(frame),
    }


def _tokens(value: Any) -> set[str]:
    clean = "".join(char if char.isalnum() else " " for char in str(value or "").lower())
    return {token for token in clean.split() if len(token) > 2}


def _category(text: Any, categories: list[str]) -> tuple[str, float]:
    banks = {
        "wait": {"wait", "waiting", "delay", "slow", "queue", "hold"},
        "agent": {"agent", "advisor", "representative", "rude", "helpful", "polite"},
        "behavior": {"rude", "polite", "helpful", "attitude", "empathy", "professional"},
        "resolution": {"resolved", "resolution", "fix", "solve", "unresolved", "issue"},
        "knowledge": {"knowledge", "understand", "trained", "expert", "information"},
        "billing": {"bill", "billing", "charge", "payment", "refund", "invoice", "fee"},
        "technical": {"technical", "system", "app", "website", "login", "error", "crash"},
        "process": {"process", "policy", "procedure", "steps", "documents", "approval"},
        "communication": {"communication", "explained", "explain", "update", "email", "call"},
        "follow": {"follow", "callback", "respond", "response", "update"},
    }
    feedback = _tokens(text)
    best, best_score = categories[-1], -1
    for category in categories:
        expanded = set(_tokens(category))
        for token in list(expanded):
            expanded |= banks.get(token, set())
        score = len(feedback & expanded)
        if score > best_score:
            best, best_score = category, score
    if best_score <= 0:
        return next((item for item in categories if item.lower() == "other"), categories[-1]), 0.25
    return best, round(min(0.98, 0.45 + best_score * 0.12), 2)


def _set_progress(analysis_id: str, percent: float, message: str, done: int, total: int, complete: bool = False) -> None:
    if not analysis_id:
        return
    with PROGRESS_LOCK:
        PROGRESS[analysis_id] = {
            "ok": True,
            "id": analysis_id,
            "mode": "sentiment",
            "percent": round(max(0.0, min(float(percent), 100.0)), 1),
            "message": message,
            "done": done,
            "total": total,
            "currentRow": done,
            "complete": complete,
            "updatedAt": time.time(),
        }


def progress(analysis_id: str) -> dict[str, Any]:
    with PROGRESS_LOCK:
        value = dict(PROGRESS.get(analysis_id, {}))
    return value or {
        "ok": True,
        "id": analysis_id,
        "percent": 0,
        "message": "Waiting for analysis to start...",
        "done": 0,
        "total": 0,
        "currentRow": 0,
        "complete": False,
    }


def _top_terms(frame: pd.DataFrame, limit: int = 6) -> list[tuple[str, int]]:
    stop = {"the", "and", "for", "with", "that", "this", "was", "were", "are", "but", "not", "you", "your", "customer", "service", "agent", "issue", "call", "support"}
    counts: dict[str, int] = {}
    for text in frame.get("Verbatim Feedback", pd.Series(dtype=str)).fillna("").astype(str):
        for token in _tokens(text):
            if len(token) >= 4 and token not in stop:
                counts[token] = counts.get(token, 0) + 1
    return sorted(counts.items(), key=lambda item: item[1], reverse=True)[:limit]


def _insights(frame: pd.DataFrame) -> list[dict[str, Any]]:
    total = max(len(frame), 1)
    sentiment = frame["Sentiment"].value_counts()
    categories = frame["Custom Category"].value_counts()
    negative = frame[frame["Sentiment"] == "Negative"]["Custom Category"].value_counts()
    rows = [
        {"Title": "Negative feedback concentration", "Insight": f"{round(int(sentiment.get('Negative', 0)) / total * 100, 1)}% of verbatims are negative."},
        {"Title": "Positive feedback signal", "Insight": f"{round(int(sentiment.get('Positive', 0)) / total * 100, 1)}% of verbatims are positive."},
    ]
    if not categories.empty:
        rows.append({"Title": "Largest custom category", "Insight": f"{categories.index[0]} has {int(categories.iloc[0]):,} verbatims."})
    if not negative.empty:
        rows.append({"Title": "Highest negative category", "Insight": f"{negative.index[0]} has the most negative verbatims."})
    return rows


def _intelligence(frame: pd.DataFrame) -> list[dict[str, Any]]:
    total = max(len(frame), 1)
    sentiments = frame["Sentiment"].value_counts()
    categories = frame["Custom Category"].value_counts()
    negative = frame[frame["Sentiment"] == "Negative"]
    negative_categories = negative["Custom Category"].value_counts()
    terms = _top_terms(frame)
    top_category = str(categories.index[0]) if not categories.empty else "Uncategorized"
    top_negative = str(negative_categories.index[0]) if not negative_categories.empty else "No dominant negative driver"
    return [
        {"Title": "Emotion Mix", "Metric": f"{round(int(sentiments.get('Positive', 0)) / total * 100, 1)}% positive", "Insight": "Overall emotion mix inferred from sentiment and recurring language.", "Evidence": []},
        {"Title": "Sentiment Driver", "Metric": top_negative, "Insight": f"The strongest negative driver is {top_negative}.", "Evidence": []},
        {"Title": "Verbatim Intelligence Summary", "Metric": f"{len(frame):,} verbatims", "Insight": f"The dominant discussion area is {top_category}.", "Evidence": []},
        {"Title": "Common Customer Themes", "Metric": ", ".join(map(str, categories.head(3).index)), "Insight": "Most frequently observed feedback categories.", "Evidence": []},
        {"Title": "Emerging Issues", "Metric": ", ".join(term for term, _ in terms[:4]) or "No emerging issue", "Insight": "Recurring language signals across the uploaded verbatims.", "Evidence": []},
        {"Title": "Repeat Pain Points", "Metric": top_negative, "Insight": "Prioritize this area for coaching, process, or knowledge-base actions.", "Evidence": []},
    ]


def analyze(payload: dict[str, Any]) -> dict[str, Any]:
    frame = _decode(payload)
    mapping = payload.get("mapping") if isinstance(payload.get("mapping"), dict) else {}
    feedback = str(mapping.get("feedback") or "").strip()
    agent = str(mapping.get("agent") or "").strip()
    manager = str(mapping.get("manager") or "").strip()
    date = str(mapping.get("date") or "").strip()
    analysis_id = str(payload.get("analysisId") or "").strip()
    engines = payload.get("engines") if isinstance(payload.get("engines"), dict) else {}
    engine = str(engines.get("sentiment") or "local").strip().lower()
    if not feedback or feedback not in frame.columns:
        raise ValueError("Map a valid feedback/comment column before analysis.")
    total = len(frame)
    _set_progress(analysis_id, 2, f"Validating {total:,} rows...", 0, total)

    def callback(done: int, steps: int, message: str | None = None) -> None:
        percent = 5 + min(max(done, 0), max(steps, 1)) / max(steps, 1) * 72
        estimated = min(total, int(percent / 77 * total))
        _set_progress(analysis_id, percent, message or "Running local sentiment rules...", estimated, total)

    analyzed = build_analysis(frame, feedback, None, agent or None, date or None, progress_callback=callback)
    analyzed["Analysis Source"] = "KestrelIQ Local Rules"
    if engine == "openai":
        values = analyzed["Verbatim Feedback"].fillna("").astype(str).tolist()
        for start in range(0, len(values), 30):
            batch = values[start:start + 30]
            results = _openai_sentiment(batch)
            for item in results:
                local_index = int(item.get("index", -1))
                if local_index < 0 or local_index >= len(batch):
                    continue
                row_index = start + local_index
                sentiment = str(item.get("sentiment") or "Neutral").title()
                if sentiment not in {"Positive", "Neutral", "Negative"}:
                    sentiment = "Neutral"
                confidence = max(0.0, min(float(item.get("confidence") or 0.0), 1.0))
                analyzed.at[row_index, "Sentiment"] = sentiment
                analyzed.at[row_index, "Sentiment Score"] = round(confidence if sentiment == "Positive" else -confidence if sentiment == "Negative" else 0.0, 3)
                analyzed.at[row_index, "AI Rationale"] = str(item.get("rationale") or "")[:500]
                analyzed.at[row_index, "Analysis Source"] = "OpenAI API"
            done = min(start + len(batch), len(values))
            _set_progress(analysis_id, 15 + done / max(len(values), 1) * 65, f"OpenAI analyzed {done:,} of {len(values):,} rows.", done, len(values))
    if manager and manager in frame.columns:
        analyzed["Manager/TL"] = frame[manager].reset_index(drop=True).reindex(range(len(analyzed))).fillna("Unknown").astype(str).to_numpy()
    categories = ["Wait Time", "Agent Behavior", "Resolution", "Product Knowledge", "Billing", "Technical Issue", "Communication", "Process", "Follow-up", "Other"]
    selected = [_category(value, categories) for value in analyzed["Verbatim Feedback"].fillna("").astype(str)]
    analyzed["Custom Category"] = [item[0] for item in selected]
    analyzed["Category Confidence"] = [item[1] for item in selected]
    _set_progress(analysis_id, 92, "Building dashboards, word cloud, and export tables...", total, total)
    summary = sentiment_summary(analyzed)
    visible = ["Verbatim Feedback", "Sentiment", "Sentiment Score", "Custom Category", "Category Confidence", "Agent Name", "Manager/TL", "Feedback Date", "Analysis Source", "AI Rationale"]
    available = [column for column in visible if column in analyzed.columns]
    clean = analyzed[available].head(1000).copy()
    clean.insert(0, "__row_id", clean.index.astype(str))
    clean = clean.astype(object).where(pd.notna(clean), "")
    result = {
        "ok": True,
        "mode": "sentiment",
        "columns": [str(column) for column in frame.columns],
        "guesses": _guess([str(column) for column in frame.columns]),
        "summary": {"total": total, "sentiment": summary, "positive": summary.get("Positive", 0), "neutral": summary.get("Neutral", 0), "negative": summary.get("Negative", 0)},
        "dimensions": [],
        "themes": [{"Field": "Custom Category", "Theme": str(label), "Count": int(count)} for label, count in analyzed["Custom Category"].value_counts().head(12).items()],
        "insights": _insights(analyzed),
        "intelligenceCards": _intelligence(analyzed),
        "rows": clean.to_dict(orient="records"),
    }
    _set_progress(analysis_id, 100, "Analysis complete.", total, total, True)
    return result
