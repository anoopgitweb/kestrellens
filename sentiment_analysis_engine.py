from __future__ import annotations

from collections import Counter
from functools import lru_cache
from io import BytesIO
import json
from pathlib import Path
import re
import sys

import pandas as pd
from pandas.api.types import is_datetime64_any_dtype, is_numeric_dtype


POSITIVE_WORDS = {
    "amazing", "awesome", "best", "clear", "easy", "efficient", "excellent",
    "fantastic", "fast", "friendly", "good", "great", "helpful", "impressed",
    "love", "pleasant", "professional", "prompt", "quick", "quickly", "resolved",
    "responsive", "satisfied", "seamless", "smooth", "solved", "supportive", "wonderful",
    "happy", "polite", "kind", "courteous", "knowledgeable", "attentive", "thorough",
    "patient", "efficiently", "appreciated", "appreciate", "pleased", "superb", "brilliant",
    "outstanding", "perfect", "convenient", "simple", "useful", "informative", "reliable",
}

NEGATIVE_WORDS = {
    "angry", "annoying", "awful", "bad", "broken", "bug", "bugs", "confusing",
    "delay", "delayed", "difficult", "disappointed", "error", "frustrated",
    "frustrating", "hard", "horrible", "poor", "problem",
    "rude", "slow", "terrible", "unhelpful", "wait", "wrong",
    "upset", "useless", "inconvenient", "complicated", "annoyed", "disappointing",
    "unresponsive", "unclear", "failed", "failure", "worse", "worst", "late",
    "lag", "crash", "crashed", "glitch", "confused", "misleading",
}

POSITIVE_STEMS = {
    "amaz", "awesom", "best", "clear", "eas", "efficien", "excel", "fantast",
    "fast", "friend", "good", "great", "help", "impress", "love", "pleasant",
    "profession", "prompt", "quick", "resolv", "respons", "satisf", "seamless",
    "smooth", "solv", "support", "wonder", "happ", "polit", "kind", "courte",
    "knowledge", "attent", "thorough", "patient", "appreci", "pleas", "superb",
    "brilliant", "outstand", "perfect", "conven", "simpl", "use", "inform", "reliab",
}

NEGATIVE_STEMS = {
    "angr", "annoy", "awful", "bad", "broken", "bug", "confus", "delay",
    "diffic", "disappoint", "error", "frustrat", "hard", "horribl", "poor",
    "problem", "rude", "slow", "terribl", "unhelp", "wait", "wrong", "upset",
    "useless", "inconven", "complicat", "unrespons", "unclear", "fail", "wors",
    "worst", "late", "lag", "crash", "glitch", "mislead",
}

STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from",
    "had", "has", "have", "i", "if", "in", "is", "it", "my", "of", "on", "or",
    "our", "so", "that", "the", "their", "them", "there", "they", "this", "to",
    "very", "was", "we", "were", "with", "you", "your",
    "can", "could", "would", "should", "did", "got", "get", "getting", "gotten",
    "one", "two", "also", "still", "really", "just", "only", "much", "many",
}

GENERIC_CLOUD_WORDS = {
    "customer", "customers", "service", "support", "experience", "call", "calls",
    "comment", "comments", "feedback", "agent", "agents", "team", "staff",
    "representative", "advisor", "associate", "issue", "issues",
    "cust", "cx", "usr", "user", "users", "client", "clients",
}

THEME_KEYWORDS = {
    "People": {
        "Agent Performance": ["agent", "representative", "advisor", "associate"],
        "Soft Skills": ["friendly", "polite", "kind", "courteous", "professional", "tone"],
        "Empathy": ["empathetic", "empathy", "cared", "understood", "listened", "compassion"],
        "Communication": ["communication", "explain", "explained", "clarity", "clear", "confusing"],
        "Knowledge": ["knowledge", "informed", "expert", "answer", "answers", "training"],
    },
    "Process": {
        "Wait Time": ["wait", "queue", "hold", "delay", "delayed", "slow"],
        "Policy": ["policy", "process", "procedure", "approval", "rules"],
        "Ease of Use": ["easy", "simple", "complicated", "difficult", "hard", "steps"],
        "Billing": ["billing", "invoice", "payment", "charged", "refund", "fee"],
    },
    "Technology": {
        "Website": ["website", "site", "portal", "browser"],
        "App Bugs": ["app", "bug", "error", "crash", "glitch", "issue", "issues"],
        "Automation": ["automation", "bot", "chatbot", "ivr", "self-service"],
        "Navigation": ["navigation", "menu", "screen", "find", "locate", "search"],
    },
}


def clean_text(value: object) -> str:
    if pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def tokenize(text: str) -> list[str]:
    return re.findall(r"[A-Za-z']+", text.lower())


def normalize_token(token: str) -> str:
    token = token.lower().strip("'")
    for suffix in ("ingly", "edly", "ing", "ed", "ly", "es", "s"):
        if len(token) > len(suffix) + 2 and token.endswith(suffix):
            token = token[: -len(suffix)]
            break
    return token


def score_sentiment(text: str, nps_score: object = None) -> tuple[str, float]:
    tokens = tokenize(text)
    nps_bias = 0.0
    try:
        if nps_score is not None and not pd.isna(nps_score):
            numeric_nps = float(nps_score)
            if numeric_nps >= 9:
                nps_bias = 0.35
            elif numeric_nps <= 6:
                nps_bias = -0.35
            elif numeric_nps >= 7:
                nps_bias = 0.0
    except (TypeError, ValueError):
        nps_bias = 0.0

    if not tokens:
        if nps_bias >= 0.2:
            return "Positive", round(nps_bias, 3)
        if nps_bias <= -0.2:
            return "Negative", round(nps_bias, 3)
        return "Neutral", 0.0
    normalized_tokens = [normalize_token(token) for token in tokens]
    positives = sum(
        token in POSITIVE_WORDS or normalized in POSITIVE_STEMS
        for token, normalized in zip(tokens, normalized_tokens)
    )
    negatives = sum(
        token in NEGATIVE_WORDS or normalized in NEGATIVE_STEMS
        for token, normalized in zip(tokens, normalized_tokens)
    )
    balance = positives - negatives
    lexical_score = balance / max(len(tokens), 1)
    final_score = round(lexical_score + nps_bias, 3)
    if balance >= 1 or final_score >= 0.2:
        return "Positive", final_score
    if balance <= -1 or final_score <= -0.2:
        return "Negative", final_score
    return "Neutral", final_score


def classify_nps(score: object) -> str:
    try:
        value = float(score)
    except (TypeError, ValueError):
        return "Unknown"
    if value >= 9:
        return "Promoter"
    if value >= 7:
        return "Passive"
    if value >= 0:
        return "Detractor"
    return "Unknown"


def compute_silent_detractor_alert(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=bool)
    passive = df["NPS Type"] == "Passive"
    negative = df["Sentiment"] == "Negative"
    neutral_risk = (
        (df["Sentiment"] == "Neutral")
        & (df["Bucket Category"].isin(["Process", "Technology"]))
        & (pd.to_numeric(df["Impact Score"], errors="coerce").fillna(0) >= 2.5)
    )
    return passive & (negative | neutral_risk)


def detect_themes(text: str) -> tuple[str, str]:
    lowered = text.lower()
    matches: list[tuple[str, str, int]] = []
    for bucket, reasons in THEME_KEYWORDS.items():
        for reason, keywords in reasons.items():
            count = sum(lowered.count(keyword) for keyword in keywords)
            if count:
                matches.append((bucket, reason, count))
    if not matches:
        return "Uncategorized", "General"
    bucket, reason, _ = sorted(matches, key=lambda item: item[2], reverse=True)[0]
    return bucket, reason


def importance_score(text: str, sentiment_score: float) -> float:
    return round(abs(sentiment_score) * 10 + min(len(text.split()), 50) / 10, 2)


def build_analysis(
    df: pd.DataFrame,
    feedback_col: str,
    score_col: str | None,
    agent_col: str | None,
    date_col: str | None,
    progress_callback=None,
) -> pd.DataFrame:
    def report(done: int, total: int, message: str | None = None) -> None:
        if progress_callback:
            progress_callback(done, total, message)

    total_steps = 8
    working = df.copy()
    report(1, total_steps, "Cleaning verbatim feedback and standardizing text...")
    working["Verbatim Feedback"] = working[feedback_col].apply(clean_text)
    working["NPS Score"] = pd.to_numeric(working[score_col], errors="coerce") if score_col else pd.NA
    report(2, total_steps, "Reading NPS scores and preparing sentiment inputs...")
    sentiments = working.apply(
        lambda row: score_sentiment(row["Verbatim Feedback"], row["NPS Score"]),
        axis=1,
    )
    working["Sentiment"] = sentiments.apply(lambda item: item[0])
    working["Sentiment Score"] = sentiments.apply(lambda item: item[1])
    report(3, total_steps, "Detecting feedback themes with local rules...")
    themes = working["Verbatim Feedback"].apply(detect_themes)
    working["Bucket Category"] = themes.apply(lambda item: item[0])
    working["Primary Reason"] = themes.apply(lambda item: item[1])
    report(4, total_steps, "Calculating impact scores for each response...")
    working["Impact Score"] = working.apply(
        lambda row: importance_score(row["Verbatim Feedback"], row["Sentiment Score"]),
        axis=1,
    )
    report(5, total_steps, "Classifying NPS response types...")
    working["NPS Type"] = working["NPS Score"].apply(classify_nps) if score_col else "Unknown"
    report(6, total_steps, "Mapping agent names and feedback dates...")
    working["Agent Name"] = working[agent_col].fillna("Unknown").astype(str) if agent_col else "Unknown"
    working["Feedback Date"] = pd.to_datetime(working[date_col], errors="coerce") if date_col else pd.NaT
    report(7, total_steps, "Checking silent detractor alerts...")
    working["Silent Detractor Alert"] = compute_silent_detractor_alert(working)
    working["Analysis Source"] = "Local Rules"
    working["AI Rationale"] = ""
    report(8, total_steps, "Local preparation complete.")
    return working


def _normalize_model_sentiment(label: str) -> str:
    upper_label = str(label).upper()
    if "POS" in upper_label:
        return "Positive"
    if "NEG" in upper_label:
        return "Negative"
    if "NEU" in upper_label:
        return "Neutral"
    return "Neutral"


def _sentiment_score_from_model(sentiment: str, confidence: float) -> float:
    if sentiment == "Positive":
        return round(confidence, 3)
    if sentiment == "Negative":
        return round(-confidence, 3)
    return 0.0


def _blend_model_and_rule_sentiment(
    model_sentiment: str,
    model_confidence: float,
    rule_sentiment: str,
    rule_score: float,
) -> tuple[str, float, str]:
    if model_sentiment == "Neutral" and rule_sentiment != "Neutral" and abs(rule_score) >= 0.2:
        return (
            rule_sentiment,
            rule_score,
            f"Sparrow returned neutral ({model_confidence:.3f}); text/NPS guardrail used {rule_sentiment.lower()} ({rule_score:.3f})",
        )
    if model_sentiment == "Neutral" and rule_sentiment != "Neutral" and model_confidence < 0.8:
        return (
            rule_sentiment,
            rule_score,
            f"Sparrow returned low-confidence neutral ({model_confidence:.3f}); text/NPS guardrail used {rule_sentiment.lower()} ({rule_score:.3f})",
        )
    return (
        model_sentiment,
        _sentiment_score_from_model(model_sentiment, model_confidence),
        f"Roberta_1 predicted {model_sentiment.lower()} with confidence {model_confidence:.3f}",
    )


def resolve_roberta_model_path(model_path: str | None = None) -> Path:
    candidates: list[Path] = []
    if model_path:
        candidates.append(Path(model_path))

    current_dir = Path(__file__).resolve().parent
    cwd = Path.cwd()
    candidates.extend(
        [
            current_dir / "sparrow_cnx_sentimentmodel",
            cwd / "sparrow_cnx_sentimentmodel",
            current_dir / "dist" / "sparrow_cnx_sentimentmodel",
            cwd / "dist" / "sparrow_cnx_sentimentmodel",
        ]
    )

    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.extend(
            [
                exe_dir / "sparrow_cnx_sentimentmodel",
                exe_dir / "dist" / "sparrow_cnx_sentimentmodel",
            ]
        )

    for candidate in candidates:
        if (
            candidate.exists()
            and (candidate / "config.json").exists()
            and (candidate / "model.safetensors").exists()
            and ((candidate / "tokenizer.json").exists() or (candidate / "vocab.json").exists())
        ):
            return candidate

    checked_paths = "\n".join(f"- {path}" for path in candidates)
    raise FileNotFoundError(
        "Unable to find a complete local Sparrow_Sentiment_CNX model folder. "
        "Expected folder name: sparrow_cnx_sentimentmodel. "
        "The folder must include config, weights, and tokenizer files. Checked:\n"
        f"{checked_paths}"
    )


@lru_cache(maxsize=1)
def _sparrow_pipeline(model_path: str | None = None):
    from transformers import AutoModelForSequenceClassification, AutoTokenizer, TextClassificationPipeline

    resolved_model_path = resolve_roberta_model_path(model_path)
    tokenizer = AutoTokenizer.from_pretrained(resolved_model_path)
    model = AutoModelForSequenceClassification.from_pretrained(resolved_model_path)
    return TextClassificationPipeline(
        model=model,
        tokenizer=tokenizer,
        return_all_scores=False,
        function_to_apply="softmax",
    )


VULTURE_OUTPUT_COLUMNS = {
    "Primary_Driver": "Vulture Primary Driver",
    "Secondary_Driver": "Vulture Secondary Driver",
    "Tertiary_Driver": "Vulture Tertiary Driver",
    "People_Sentiment": "Vulture People Sentiment",
    "Process_Sentiment": "Vulture Process Sentiment",
    "Tech_Sentiment": "Vulture Tech Sentiment",
    "Issue_Type": "Vulture Issue Type",
    "Customer_Impact": "Vulture Customer Impact",
    "Resolution_Status": "Vulture Resolution Status",
}


def _complete_vulture_model_folder(candidate: Path) -> Path | None:
    if (
        candidate.exists()
        and (candidate / "config.json").exists()
        and ((candidate / "model.safetensors").exists() or (candidate / "pytorch_model.bin").exists())
        and (candidate / "vulture_model.pt").exists()
        and (candidate / "vulture_model_config.json").exists()
        and ((candidate / "tokenizer.json").exists() or (candidate / "vocab.json").exists())
    ):
        return candidate
    if candidate.exists() and candidate.is_dir():
        for child in candidate.iterdir():
            if child.is_dir():
                complete_child = _complete_vulture_model_folder(child)
                if complete_child is not None:
                    return complete_child
    return None


def resolve_vulture_model_path(model_path: str | None = None) -> Path:
    candidates: list[Path] = []
    if model_path:
        candidates.append(Path(model_path))

    current_dir = Path(__file__).resolve().parent
    cwd = Path.cwd()
    candidates.extend(
        [
            current_dir / "vulture_cnx_multiclassmodel",
            cwd / "vulture_cnx_multiclassmodel",
            current_dir / "dist" / "vulture_cnx_multiclassmodel",
            cwd / "dist" / "vulture_cnx_multiclassmodel",
        ]
    )
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.extend(
            [
                exe_dir / "vulture_cnx_multiclassmodel",
                exe_dir / "dist" / "vulture_cnx_multiclassmodel",
            ]
        )

    for candidate in candidates:
        complete = _complete_vulture_model_folder(candidate)
        if complete is not None:
            return complete

    checked_paths = "\n".join(f"- {path}" for path in candidates)
    raise FileNotFoundError(
        "Unable to find a complete local Vulture CNX multi-classification model folder. "
        "Expected folder name: vulture_cnx_multiclassmodel. Checked:\n"
        f"{checked_paths}"
    )


@lru_cache(maxsize=1)
def _vulture_components(model_path: str | None = None):
    import torch
    from torch import nn
    from transformers import AutoConfig, AutoModel, AutoTokenizer

    resolved_model_path = resolve_vulture_model_path(model_path)
    with open(resolved_model_path / "vulture_model_config.json", "r", encoding="utf-8") as handle:
        vulture_config = json.load(handle)
    target_fields = list(vulture_config["target_fields"])
    id_maps = {
        field: {int(index): label for index, label in mapping.items()}
        for field, mapping in vulture_config["id_maps"].items()
    }

    class VultureMultiOutputModel(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            base_config = AutoConfig.from_pretrained(resolved_model_path)
            self.base_model = AutoModel.from_config(base_config)
            hidden_size = int(vulture_config.get("hidden_size") or base_config.hidden_size)
            self.heads = nn.ModuleDict(
                {
                    field: nn.Linear(hidden_size, len(vulture_config["label_schema"][field]))
                    for field in target_fields
                }
            )

        def forward(self, **inputs):
            outputs = self.base_model(**inputs)
            pooled = getattr(outputs, "pooler_output", None)
            if pooled is None:
                pooled = outputs.last_hidden_state[:, 0]
            return {field: head(pooled) for field, head in self.heads.items()}

    tokenizer = AutoTokenizer.from_pretrained(resolved_model_path)
    model = VultureMultiOutputModel()
    state_dict = torch.load(resolved_model_path / "vulture_model.pt", map_location="cpu")
    model.load_state_dict(state_dict)
    model.eval()
    return resolved_model_path, tokenizer, model, target_fields, id_maps


def add_vulture_classification_outputs(
    df: pd.DataFrame,
    feedback_col: str = "Verbatim Feedback",
    model_path: str | None = None,
    progress_callback=None,
) -> pd.DataFrame:
    working = df.copy()
    for output_column in VULTURE_OUTPUT_COLUMNS.values():
        if output_column not in working.columns:
            working[output_column] = ""
    if working.empty or feedback_col not in working.columns:
        return working

    def report(done: int, total: int, message: str | None = None) -> None:
        if progress_callback:
            progress_callback(done, total, message)

    try:
        import torch
    except ImportError as exc:
        raise RuntimeError("Vulture classification requires torch and transformers.") from exc

    _resolved, tokenizer, model, target_fields, id_maps = _vulture_components(model_path)
    texts = working[feedback_col].fillna("").astype(str).tolist()
    total = len(texts)
    if not total:
        return working

    predictions: dict[str, list[str]] = {field: [] for field in target_fields}
    batch_size = 48
    max_length = 256
    report(0, total)
    with torch.no_grad():
        for start in range(0, total, batch_size):
            batch = texts[start : start + batch_size]
            inputs = tokenizer(batch, padding=True, truncation=True, max_length=max_length, return_tensors="pt")
            logits_by_field = model(**inputs)
            for field in target_fields:
                indices = torch.argmax(logits_by_field[field], dim=-1).tolist()
                predictions[field].extend(id_maps[field].get(int(index), "") for index in indices)
            report(min(start + len(batch), total), total)

    for field, output_column in VULTURE_OUTPUT_COLUMNS.items():
        working[output_column] = predictions.get(field, [""] * total)
    working["Vulture Analysis Source"] = "Vulture_CNX_Multi_Classification"
    return working


def build_analysis_with_local_model(
    df: pd.DataFrame,
    feedback_col: str,
    score_col: str | None,
    agent_col: str | None,
    date_col: str | None,
    model_path: str | None = None,
    progress_callback=None,
) -> pd.DataFrame:
    def report(done: int, total: int, message: str | None = None) -> None:
        if progress_callback:
            progress_callback(done, total, message)

    report(0, 1, "Loading local AI libraries for Sparrow sentiment...")
    try:
        import transformers  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "Roberta_1 mode requires the transformers package. Install it with: pip install transformers torch"
        ) from exc

    report(0, 1, "Sparrow AI libraries are ready. Preparing feedback for sentiment review...")
    working = build_analysis(df, feedback_col, score_col, agent_col, date_col, progress_callback=progress_callback)
    report(0, 1, "Retrieving Sparrow sentiment model from local model folder...")
    resolved_model_path = resolve_roberta_model_path(model_path)
    report(0, 1, "Sparrow model successfully retrieved from local files.")

    texts = working["Verbatim Feedback"].fillna("").astype(str).tolist()
    if not texts:
        working["Analysis Source"] = "Sparrow_Sentiment_CNX"
        return working

    report(0, len(texts), "Loading Sparrow tokenizer from local files...")
    report(0, len(texts), "Loading Sparrow neural network weights...")
    classifier = _sparrow_pipeline(str(resolved_model_path))
    report(0, len(texts), "Sparrow model is active. Processing customer feedback now...")

    sentiments: list[str] = []
    sentiment_scores: list[float] = []
    rationales: list[str] = []
    batch_size = 48

    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        predictions = classifier(batch, truncation=True, batch_size=batch_size)
        for offset, prediction in enumerate(predictions):
            sentiment = _normalize_model_sentiment(prediction.get("label", ""))
            confidence = float(prediction.get("score", 0.0))
            sentiments.append(sentiment)
            sentiment_scores.append(_sentiment_score_from_model(sentiment, confidence))
            rationales.append(f"Sparrow_Sentiment_CNX predicted {sentiment.lower()} with confidence {confidence:.3f}")
            report(start + offset + 1, len(texts))
        report(min(start + len(batch), len(texts)), len(texts))

    working["Sentiment"] = sentiments
    working["Sentiment Score"] = sentiment_scores
    working["Impact Score"] = working.apply(
        lambda row: importance_score(row["Verbatim Feedback"], row["Sentiment Score"]),
        axis=1,
    )
    working["Silent Detractor Alert"] = compute_silent_detractor_alert(working)
    working["Analysis Source"] = "Sparrow_Sentiment_CNX"
    working["AI Rationale"] = rationales
    return working


def nps_summary(df: pd.DataFrame) -> dict[str, float]:
    valid = df[df["NPS Type"].isin(["Promoter", "Passive", "Detractor"])]
    total = len(valid)
    if total == 0:
        return {"total": 0, "nps": 0.0, "promoters": 0.0, "passives": 0.0, "detractors": 0.0}
    counts = valid["NPS Type"].value_counts()
    promoters = counts.get("Promoter", 0) / total * 100
    passives = counts.get("Passive", 0) / total * 100
    detractors = counts.get("Detractor", 0) / total * 100
    return {
        "total": total,
        "nps": float(round(promoters - detractors, 1)),
        "promoters": float(round(promoters, 1)),
        "passives": float(round(passives, 1)),
        "detractors": float(round(detractors, 1)),
    }


def nps_composition_counts(df: pd.DataFrame) -> dict[str, int]:
    counts = df["NPS Type"].value_counts()
    return {
        "Promoter": int(counts.get("Promoter", 0)),
        "Passive": int(counts.get("Passive", 0)),
        "Detractor": int(counts.get("Detractor", 0)),
    }


def sentiment_summary(df: pd.DataFrame) -> dict[str, float]:
    total = len(df)
    if total == 0:
        return {"Positive": 0.0, "Neutral": 0.0, "Negative": 0.0}
    counts = df["Sentiment"].value_counts()
    return {
        "Positive": float(round(counts.get("Positive", 0) / total * 100, 1)),
        "Neutral": float(round(counts.get("Neutral", 0) / total * 100, 1)),
        "Negative": float(round(counts.get("Negative", 0) / total * 100, 1)),
    }


def feedback_alignment_summary(analyzed_df: pd.DataFrame) -> dict[str, pd.DataFrame | str]:
    if analyzed_df.empty:
        empty = pd.DataFrame(columns=["Label", "Count"])
        matrix = pd.DataFrame(columns=["NPS Type", "Positive", "Neutral", "Negative"])
        return {
            "chart": empty,
            "matrix": matrix,
            "summary_text": "Run analysis to view sentiment and NPS alignment insights.",
            "correlation_text": "Run analysis to unlock correlation insights from the verbatim feedback.",
            "correlation_coefficient": None,
        }

    valid = analyzed_df[analyzed_df["NPS Type"].isin(["Promoter", "Passive", "Detractor"])].copy()
    if valid.empty:
        empty = pd.DataFrame(columns=["Label", "Count"])
        matrix = pd.DataFrame(columns=["NPS Type", "Positive", "Neutral", "Negative"])
        return {
            "chart": empty,
            "matrix": matrix,
            "summary_text": "Map a valid NPS score field to unlock this insight.",
            "correlation_text": "Map a valid NPS score field to compare sentiment against NPS.",
            "correlation_coefficient": None,
        }

    mismatches = [
        ("Positive comment, Detractor score", (valid["Sentiment"] == "Positive") & (valid["NPS Type"] == "Detractor")),
        ("Negative comment, Promoter score", (valid["Sentiment"] == "Negative") & (valid["NPS Type"] == "Promoter")),
        ("Positive comment, Passive score", (valid["Sentiment"] == "Positive") & (valid["NPS Type"] == "Passive")),
        ("Negative comment, Passive score", (valid["Sentiment"] == "Negative") & (valid["NPS Type"] == "Passive")),
    ]
    chart = pd.DataFrame(
        [{"Label": label, "Count": int(mask.sum())} for label, mask in mismatches]
    )
    matrix = (
        valid.groupby(["NPS Type", "Sentiment"])
        .size()
        .unstack(fill_value=0)
        .reset_index()
    )
    for column in ["Positive", "Neutral", "Negative"]:
        if column not in matrix.columns:
            matrix[column] = 0
    type_order = {"Promoter": 0, "Passive": 1, "Detractor": 2}
    matrix = matrix.sort_values("NPS Type", key=lambda col: col.map(type_order)).reset_index(drop=True)

    aligned = (
        ((valid["Sentiment"] == "Positive") & (valid["NPS Type"] == "Promoter"))
        | ((valid["Sentiment"] == "Negative") & (valid["NPS Type"] == "Detractor"))
    ).sum()
    mismatch_rows = valid[
        ((valid["Sentiment"] == "Positive") & (valid["NPS Type"].isin(["Passive", "Detractor"])))
        | ((valid["Sentiment"] == "Negative") & (valid["NPS Type"].isin(["Passive", "Promoter"])))
    ].copy()
    mismatch_rate = round(len(mismatch_rows) / max(len(valid), 1) * 100, 1)

    lines = [
        f"Alignment check: {int(aligned):,} of {len(valid):,} scored comments are fully aligned between sentiment and NPS.",
        f"Mismatch rate: {mismatch_rate:.1f}% of scored comments show a gap between tone and numeric score.",
    ]

    if not mismatch_rows.empty:
        top_reason = mismatch_rows["Primary Reason"].value_counts()
        if not top_reason.empty:
            lines.append(
                f"Most common mismatch driver: {top_reason.index[0]} appears in {int(top_reason.iloc[0])} contradictory comments."
            )

        strongest_positive_detractor = mismatch_rows[
            (mismatch_rows["Sentiment"] == "Positive") & (mismatch_rows["NPS Type"] == "Detractor")
        ]
        if not strongest_positive_detractor.empty:
            row = strongest_positive_detractor.sort_values("Impact Score", ascending=False).iloc[0]
            lines.append(
                f"Positive tone but low score example: {row['Primary Reason']} | {row['Verbatim Feedback']}"
            )

        strongest_negative_promoter = mismatch_rows[
            (mismatch_rows["Sentiment"] == "Negative") & (mismatch_rows["NPS Type"] == "Promoter")
        ]
        if not strongest_negative_promoter.empty:
            row = strongest_negative_promoter.sort_values("Impact Score", ascending=False).iloc[0]
            lines.append(
                f"Negative tone but high score example: {row['Primary Reason']} | {row['Verbatim Feedback']}"
            )
    else:
        lines.append("No major sentiment-to-score mismatches were detected in the current file.")

    correlation_lines: list[str] = []
    for _, row in matrix.iterrows():
        total = int(row[["Positive", "Neutral", "Negative"]].sum())
        if total == 0:
            continue
        positive_pct = round(row["Positive"] / total * 100, 1)
        neutral_pct = round(row["Neutral"] / total * 100, 1)
        negative_pct = round(row["Negative"] / total * 100, 1)
        correlation_lines.append(
            f"{row['NPS Type']}: {positive_pct:.1f}% positive, {neutral_pct:.1f}% neutral, {negative_pct:.1f}% negative."
        )

    passive_mismatch = mismatch_rows[mismatch_rows["NPS Type"] == "Passive"]
    if not passive_mismatch.empty:
        top_bucket = passive_mismatch["Bucket Category"].value_counts()
        if not top_bucket.empty:
            correlation_lines.append(
                f"Passive comments are most conflicted around {top_bucket.index[0]}, which is the biggest conversion opportunity."
            )

    promoter_negatives = valid[(valid["NPS Type"] == "Promoter") & (valid["Sentiment"] == "Negative")]
    detractor_positives = valid[(valid["NPS Type"] == "Detractor") & (valid["Sentiment"] == "Positive")]
    correlation_lines.append(
        f"Contradictory edge cases: {len(promoter_negatives):,} promoters used negative language and {len(detractor_positives):,} detractors used positive language."
    )

    sentiment_numeric = valid["Sentiment"].map({"Negative": -1, "Neutral": 0, "Positive": 1}).astype(float)
    if valid["NPS Score"].notna().any():
        nps_numeric = ((pd.to_numeric(valid["NPS Score"], errors="coerce") - 5) / 5).clip(-1, 1)
    else:
        nps_numeric = valid["NPS Type"].map({"Detractor": -1, "Passive": 0, "Promoter": 1}).astype(float)
    corr_frame = pd.DataFrame({"sentiment_numeric": sentiment_numeric, "nps_numeric": nps_numeric}).dropna()
    coefficient = None
    if len(corr_frame) >= 2 and corr_frame["sentiment_numeric"].nunique() > 1 and corr_frame["nps_numeric"].nunique() > 1:
        coefficient = round(float(corr_frame["sentiment_numeric"].corr(corr_frame["nps_numeric"])), 3)
        correlation_lines.insert(0, f"Correlation coefficient: {coefficient:.3f} on a -1 to 1 scale.")
    else:
        correlation_lines.insert(0, "Correlation coefficient: not enough variation in the current file.")

    return {
        "chart": chart,
        "matrix": matrix[["NPS Type", "Positive", "Neutral", "Negative"]],
        "summary_text": "\n\n".join(lines),
        "correlation_text": "\n\n".join(correlation_lines).strip(),
        "correlation_coefficient": coefficient,
    }


def executive_snapshot_insights(analyzed_df: pd.DataFrame, reasons_df: pd.DataFrame) -> str:
    if analyzed_df.empty:
        return "Load and analyze a file to generate executive insights."

    nps = nps_summary(analyzed_df)
    sentiment = sentiment_summary(analyzed_df)
    lines: list[str] = []
    lines.append(
        f"Snapshot: {len(analyzed_df):,} comments analyzed with NPS at {nps['nps']:.1f} and sentiment split "
        f"{sentiment['Positive']:.1f}% positive, {sentiment['Neutral']:.1f}% neutral, {sentiment['Negative']:.1f}% negative."
    )

    top_negative = reasons_df[reasons_df["Count"] > 0].head(3) if not reasons_df.empty else pd.DataFrame()
    if not top_negative.empty:
        drivers = ", ".join(
            f"{row['Primary Reason']} ({int(row['Count'])})" for _, row in top_negative.iterrows()
        )
        lines.append(f"Top drivers: {drivers}.")

    silent_detractors = int(analyzed_df["Silent Detractor Alert"].sum())
    if silent_detractors:
        lines.append(
            f"Risk alert: {silent_detractors} passive responses contain negative sentiment and may be hidden churn risks."
        )

    detractor_reasons = analyzed_df[analyzed_df["NPS Type"] == "Detractor"]["Primary Reason"].value_counts()
    if not detractor_reasons.empty:
        lines.append(
            f"Biggest detractor pain point: {detractor_reasons.index[0]} is driving the largest share of low-score feedback."
        )

    passive_reasons = analyzed_df[analyzed_df["NPS Type"] == "Passive"]["Primary Reason"].value_counts()
    if not passive_reasons.empty:
        lines.append(
            f"Best opportunity: improving {passive_reasons.index[0]} could shift the highest volume of passives toward promoter scores."
        )

    positive_reasons = analyzed_df[analyzed_df["Sentiment"] == "Positive"]["Primary Reason"].value_counts()
    if not positive_reasons.empty:
        lines.append(
            f"Strength to protect: {positive_reasons.index[0]} is the strongest recurring positive experience in the feedback."
        )

    return "\n\n".join(lines)


def resolve_summarizer_model_path(model_path: str | None = None) -> Path:
    candidates: list[Path] = []
    if model_path:
        candidates.append(Path(model_path))
    current_dir = Path(__file__).resolve().parent
    cwd = Path.cwd()
    candidates.extend(
        [
            current_dir / "dist" / "summarizer_model",
            current_dir / "summarizer_model",
            cwd / "dist" / "summarizer_model",
            cwd / "summarizer_model",
        ]
    )
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.extend([exe_dir / "summarizer_model", exe_dir / "dist" / "summarizer_model"])
    for candidate in candidates:
        if candidate.exists() and (candidate / "config.json").exists():
            return candidate
    checked_paths = "\n".join(f"- {path}" for path in candidates)
    raise FileNotFoundError(f"Unable to find the local summarizer_model folder. Checked:\n{checked_paths}")


@lru_cache(maxsize=1)
def _local_summarizer_components(model_path: str | None = None):
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    resolved = resolve_summarizer_model_path(model_path)
    tokenizer = AutoTokenizer.from_pretrained(resolved)
    model = AutoModelForSeq2SeqLM.from_pretrained(resolved)
    if hasattr(model, "generation_config"):
        model.generation_config.forced_bos_token_id = 0
    if hasattr(model, "config"):
        model.config.forced_bos_token_id = 0
    return tokenizer, model


def summarize_feedback_with_local_model(analyzed_df: pd.DataFrame, model_path: str | None = None) -> str:
    if analyzed_df.empty or "Verbatim Feedback" not in analyzed_df.columns:
        return ""
    nps = nps_summary(analyzed_df)
    sentiment = sentiment_summary(analyzed_df)
    top_reasons = analyzed_df["Primary Reason"].value_counts().head(3) if "Primary Reason" in analyzed_df.columns else pd.Series(dtype=int)
    reason_text = ", ".join(f"{reason} ({count})" for reason, count in top_reasons.items()) or "no recurring theme"
    comments = analyzed_df["Verbatim Feedback"].dropna().astype(str).head(30).tolist()
    if not comments:
        return (
            f"NPS {nps['nps']:.1f}; sentiment mix {sentiment['Positive']:.1f}% positive, "
            f"{sentiment['Neutral']:.1f}% neutral, {sentiment['Negative']:.1f}% negative; top reasons: {reason_text}."
        )
    prompt = " ".join(comments)
    try:
        tokenizer, model = _local_summarizer_components(model_path)
        inputs = tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=768,
        )
        output_ids = model.generate(
            **inputs,
            max_new_tokens=80,
            min_new_tokens=20,
            num_beams=2,
            do_sample=False,
        )
        generated = tokenizer.decode(output_ids[0], skip_special_tokens=True).strip()
    except Exception:
        generated = ""
    base = (
        f"NPS {nps['nps']:.1f}; sentiment mix {sentiment['Positive']:.1f}% positive, "
        f"{sentiment['Neutral']:.1f}% neutral, {sentiment['Negative']:.1f}% negative; top reasons: {reason_text}."
    )
    return f"{base} Comment summary: {generated}" if generated else base


def build_correlation_metric_frames(analyzed_df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if analyzed_df.empty:
        return {"Weekly": pd.DataFrame(), "Agent": pd.DataFrame()}

    working = analyzed_df.copy()
    working["NPS Score"] = pd.to_numeric(working.get("NPS Score"), errors="coerce")
    working["Impact Score"] = pd.to_numeric(working.get("Impact Score"), errors="coerce")

    weekly = weekly_trend(working)
    if not weekly.empty:
        weekly["Promoter %"] = (weekly["Promoter"] / weekly["Responses"] * 100).round(1)
        weekly["Passive %"] = (weekly["Passive"] / weekly["Responses"] * 100).round(1)
        weekly["Detractor %"] = (weekly["Detractor"] / weekly["Responses"] * 100).round(1)
        weekly["Positive Sentiment %"] = (weekly["Positive"] / weekly["Responses"] * 100).round(1)
        weekly["Neutral Sentiment %"] = (weekly["Neutral"] / weekly["Responses"] * 100).round(1)
        weekly["Negative Sentiment %"] = (weekly["Negative"] / weekly["Responses"] * 100).round(1)
        weekly["Silent Detractor Count"] = (
            working.groupby(working["Feedback Date"].dt.to_period("W-SAT").apply(lambda value: value.start_time))["Silent Detractor Alert"]
            .sum()
            .reindex(weekly["Week"])
            .fillna(0)
            .astype(int)
            .to_list()
        )
        weekly["Average NPS Score"] = (
            working.groupby(working["Feedback Date"].dt.to_period("W-SAT").apply(lambda value: value.start_time))["NPS Score"]
            .mean()
            .reindex(weekly["Week"])
            .round(2)
            .to_list()
        )
        weekly["Average Impact Score"] = (
            working.groupby(working["Feedback Date"].dt.to_period("W-SAT").apply(lambda value: value.start_time))["Impact Score"]
            .mean()
            .reindex(weekly["Week"])
            .round(2)
            .to_list()
        )

    agent = (
        working.groupby("Agent Name")
        .agg(
            Responses=("Agent Name", "size"),
            Average_Rating=("NPS Score", "mean"),
            Promoters=("NPS Type", lambda values: int((values == "Promoter").sum())),
            Passives=("NPS Type", lambda values: int((values == "Passive").sum())),
            Detractors=("NPS Type", lambda values: int((values == "Detractor").sum())),
            Positive=("Sentiment", lambda values: int((values == "Positive").sum())),
            Neutral=("Sentiment", lambda values: int((values == "Neutral").sum())),
            Negative=("Sentiment", lambda values: int((values == "Negative").sum())),
            Silent_Detractor_Count=("Silent Detractor Alert", "sum"),
            Average_Impact_Score=("Impact Score", "mean"),
        )
        .reset_index()
    )
    if not agent.empty:
        agent["Agent NPS"] = ((agent["Promoters"] / agent["Responses"] * 100) - (agent["Detractors"] / agent["Responses"] * 100)).round(1)
        agent["Promoter %"] = (agent["Promoters"] / agent["Responses"] * 100).round(1)
        agent["Passive %"] = (agent["Passives"] / agent["Responses"] * 100).round(1)
        agent["Detractor %"] = (agent["Detractors"] / agent["Responses"] * 100).round(1)
        agent["Positive Sentiment %"] = (agent["Positive"] / agent["Responses"] * 100).round(1)
        agent["Neutral Sentiment %"] = (agent["Neutral"] / agent["Responses"] * 100).round(1)
        agent["Negative Sentiment %"] = (agent["Negative"] / agent["Responses"] * 100).round(1)
        agent["Average Rating"] = agent["Average_Rating"].round(2)
        agent["Silent Detractor Count"] = agent["Silent_Detractor_Count"].astype(int)
        agent["Average Impact Score"] = agent["Average_Impact_Score"].round(2)

    return {"Weekly": weekly, "Agent": agent}


def correlation_analysis_summary(metric_df: pd.DataFrame, metric_a: str, metric_b: str, level: str) -> dict[str, object]:
    if metric_df.empty or metric_a not in metric_df.columns or metric_b not in metric_df.columns:
        return {
            "analysis_type": "Correlation",
            "metrics": {},
            "table": pd.DataFrame(),
            "interpretation": f"Not enough {level.lower()} data is available for this correlation.",
            "chart_type": "empty",
            "chart_data": pd.DataFrame(),
        }

    working = metric_df[[metric_a, metric_b]].copy().dropna()
    if working.empty:
        return {
            "analysis_type": "Correlation",
            "metrics": {},
            "table": pd.DataFrame(),
            "interpretation": "The selected metrics do not have enough overlapping values.",
            "chart_type": "empty",
            "chart_data": pd.DataFrame(),
        }

    working[metric_a] = pd.to_numeric(working[metric_a], errors="coerce")
    working[metric_b] = pd.to_numeric(working[metric_b], errors="coerce")
    working = working.dropna()
    if len(working) < 2 or working[metric_a].nunique() < 2 or working[metric_b].nunique() < 2:
        return {
            "analysis_type": "Correlation",
            "metrics": {"Sample Size": str(len(working)), "Correlation": "N/A", "Strength": "Not enough variation"},
            "table": pd.DataFrame(
                [["Metric A", metric_a], ["Metric B", metric_b], ["Sample Size", len(working)]],
                columns=["Metric", "Value"],
            ),
            "interpretation": "There is not enough variation in the selected metrics to calculate a meaningful correlation.",
            "chart_type": "empty",
            "chart_data": pd.DataFrame(),
        }

    correlation = float(working[metric_a].corr(working[metric_b]))
    strength = "High" if abs(correlation) >= 0.7 else "Moderate" if abs(correlation) >= 0.4 else "Low"
    direction = "positive" if correlation > 0 else "negative" if correlation < 0 else "flat"
    if direction == "flat":
        strength_label = "No clear correlation"
    else:
        strength_label = f"{strength} {direction} correlation"
    table = pd.DataFrame(
        [
            ["Metric A", metric_a],
            ["Metric B", metric_b],
            ["Sample Size", len(working)],
            ["Metric A mean", round(float(working[metric_a].mean()), 3)],
            ["Metric B mean", round(float(working[metric_b].mean()), 3)],
            ["Correlation", round(correlation, 3)],
        ],
        columns=["Metric", "Value"],
    )
    return {
        "analysis_type": "Correlation",
        "metrics": {
            "Sample Size": str(len(working)),
            "Correlation": f"{correlation:.3f}",
            "Strength": strength_label,
        },
        "table": table,
        "interpretation": (
            f"Detected a {strength.lower()} {direction} relationship between {metric_a} and {metric_b} "
            f"at the {level.lower()} level based on {len(working)} observations."
        ),
        "chart_type": "scatter",
        "chart_data": working,
    }


def metric_correlation_map_summary(metric_df: pd.DataFrame, metric_a: str) -> dict[str, object]:
    if metric_df.empty or metric_a not in metric_df.columns:
        return {
            "table": pd.DataFrame(columns=["Metric", "Correlation", "Strength", "Direction"]),
            "insight": "Select a primary metric to see how it relates to the other business measures.",
        }

    numeric = metric_df.select_dtypes(include="number").copy()
    if metric_a not in numeric.columns or numeric.shape[1] < 2:
        return {
            "table": pd.DataFrame(columns=["Metric", "Correlation", "Strength", "Direction"]),
            "insight": "Not enough numeric metrics are available to build a correlation map.",
        }

    rows: list[dict[str, object]] = []
    for metric_b in numeric.columns:
        if metric_b == metric_a:
            continue
        working = numeric[[metric_a, metric_b]].dropna()
        if len(working) < 2 or working[metric_a].nunique() < 2 or working[metric_b].nunique() < 2:
            continue
        correlation = float(working[metric_a].corr(working[metric_b]))
        abs_corr = abs(correlation)
        strength = "High" if abs_corr >= 0.7 else "Moderate" if abs_corr >= 0.4 else "Low"
        direction = "Positive" if correlation > 0 else "Negative" if correlation < 0 else "Flat"
        rows.append(
            {
                "Metric": metric_b,
                "Correlation": round(correlation, 3),
                "Strength": strength,
                "Direction": direction,
                "Abs Correlation": abs_corr,
            }
        )

    if not rows:
        return {
            "table": pd.DataFrame(columns=["Metric", "Correlation", "Strength", "Direction"]),
            "insight": "There is not enough overlapping variation to compare the selected metric with the others.",
        }

    ranked = pd.DataFrame(rows).sort_values(["Abs Correlation", "Correlation"], ascending=[False, False]).reset_index(drop=True)
    top = ranked.iloc[0]
    insight = (
        f"The selected primary metric, {metric_a}, is most closely related to {top['Metric']} "
        f"with a {str(top['Direction']).lower()} correlation of {top['Correlation']:.3f}."
    )
    return {
        "table": ranked[["Metric", "Correlation", "Strength", "Direction"]],
        "insight": insight,
    }


def strongest_correlation_summary(metric_df: pd.DataFrame, level: str, limit: int = 8) -> dict[str, object]:
    if metric_df.empty:
        return {
            "table": pd.DataFrame(columns=["Metric A", "Metric B", "Correlation", "Strength"]),
            "chart_data": pd.DataFrame(columns=["Label", "Correlation"]),
            "insight": f"No {level.lower()} metric data is available for correlation ranking.",
        }

    numeric = metric_df.select_dtypes(include="number").dropna(axis=1, how="all")
    if numeric.shape[1] < 2:
        return {
            "table": pd.DataFrame(columns=["Metric A", "Metric B", "Correlation", "Strength"]),
            "chart_data": pd.DataFrame(columns=["Label", "Correlation"]),
            "insight": "Not enough numeric metrics are available to rank correlations.",
        }

    rows: list[dict[str, object]] = []
    columns = list(numeric.columns)
    for i, metric_a in enumerate(columns):
        for metric_b in columns[i + 1 :]:
            working = numeric[[metric_a, metric_b]].dropna()
            if len(working) < 2 or working[metric_a].nunique() < 2 or working[metric_b].nunique() < 2:
                continue
            correlation = float(working[metric_a].corr(working[metric_b]))
            strength = "High" if abs(correlation) >= 0.7 else "Moderate" if abs(correlation) >= 0.4 else "Low"
            rows.append(
                {
                    "Metric A": metric_a,
                    "Metric B": metric_b,
                    "Correlation": round(correlation, 3),
                    "Abs Correlation": abs(correlation),
                    "Strength": f"{strength} {'positive' if correlation > 0 else 'negative' if correlation < 0 else 'flat'}",
                }
            )

    if not rows:
        return {
            "table": pd.DataFrame(columns=["Metric A", "Metric B", "Correlation", "Strength"]),
            "chart_data": pd.DataFrame(columns=["Label", "Correlation"]),
            "insight": "Not enough variation is available to rank correlations.",
        }

    ranked = pd.DataFrame(rows).sort_values(["Abs Correlation", "Correlation"], ascending=[False, False]).head(limit).reset_index(drop=True)
    chart_data = pd.DataFrame(
        {
            "Label": ranked.apply(lambda row: f"{row['Metric A']} vs {row['Metric B']}", axis=1),
            "Correlation": ranked["Abs Correlation"],
        }
    )
    top = ranked.iloc[0]
    insight = (
        f"Strongest {level.lower()} relationship: {top['Metric A']} vs {top['Metric B']} "
        f"at {top['Correlation']:.3f}, which indicates a {str(top['Strength']).lower()}."
    )
    return {
        "table": ranked[["Metric A", "Metric B", "Correlation", "Strength"]],
        "chart_data": chart_data,
        "insight": insight,
    }


def outlier_detection_summary(metric_df: pd.DataFrame, metric_a: str, metric_b: str, level: str) -> dict[str, object]:
    id_col = "Week" if level == "Weekly" and "Week" in metric_df.columns else "Agent Name" if "Agent Name" in metric_df.columns else None
    if metric_df.empty or id_col is None or metric_a not in metric_df.columns or metric_b not in metric_df.columns:
        return {
            "table": pd.DataFrame(columns=["Observation", "Metric A", "Metric B", "Expected", "Residual"]),
            "chart_data": pd.DataFrame(columns=["Observation", "Residual"]),
            "insight": "Outlier detection is unavailable for the current selection.",
        }

    working = metric_df[[id_col, metric_a, metric_b]].copy().dropna()
    working[metric_a] = pd.to_numeric(working[metric_a], errors="coerce")
    working[metric_b] = pd.to_numeric(working[metric_b], errors="coerce")
    working = working.dropna()
    if len(working) < 3 or working[metric_a].nunique() < 2:
        return {
            "table": pd.DataFrame(columns=["Observation", "Metric A", "Metric B", "Expected", "Residual"]),
            "chart_data": pd.DataFrame(columns=["Observation", "Residual"]),
            "insight": "Not enough variation is available to detect outliers for the selected metrics.",
        }

    x = working[metric_a]
    y = working[metric_b]
    covariance = float(((x - x.mean()) * (y - y.mean())).mean())
    variance = float(((x - x.mean()) ** 2).mean())
    slope = covariance / variance if variance else 0.0
    intercept = float(y.mean() - slope * x.mean())
    working["Expected"] = x * slope + intercept
    working["Residual"] = y - working["Expected"]
    working["Abs Residual"] = working["Residual"].abs()
    outliers = working.sort_values("Abs Residual", ascending=False).head(5).copy()
    outliers["Observation"] = outliers[id_col].astype(str)
    table = outliers[["Observation", metric_a, metric_b, "Expected", "Residual"]].round(3)
    chart_data = outliers[["Observation", "Residual"]].round(3)
    if table.empty:
        insight = "No material outliers were detected."
    else:
        top = outliers.iloc[0]
        insight = (
            f"Largest {level.lower()} outlier: {top['Observation']} sits furthest from the expected relationship "
            f"between {metric_a} and {metric_b} with a residual of {top['Residual']:.3f}."
        )
    return {"table": table, "chart_data": chart_data, "insight": insight}


def lag_analysis_summary(metric_df: pd.DataFrame, metric_a: str, metric_b: str, max_lag: int = 3) -> dict[str, object]:
    if metric_df.empty or "Week" not in metric_df.columns or metric_a not in metric_df.columns or metric_b not in metric_df.columns:
        return {
            "table": pd.DataFrame(columns=["Lag", "Correlation"]),
            "chart_data": pd.DataFrame(columns=["Lag", "Correlation"]),
            "insight": "Lag analysis is only available for weekly metrics.",
        }

    working = metric_df[["Week", metric_a, metric_b]].copy().dropna().sort_values("Week")
    working[metric_a] = pd.to_numeric(working[metric_a], errors="coerce")
    working[metric_b] = pd.to_numeric(working[metric_b], errors="coerce")
    working = working.dropna()
    if len(working) < 4:
        return {
            "table": pd.DataFrame(columns=["Lag", "Correlation"]),
            "chart_data": pd.DataFrame(columns=["Lag", "Correlation"]),
            "insight": "At least four weekly observations are recommended for lag analysis.",
        }

    rows = []
    for lag in range(1, max_lag + 1):
        shifted = working[[metric_a, metric_b]].copy()
        shifted["Lagged A"] = shifted[metric_a].shift(lag)
        lagged = shifted[["Lagged A", metric_b]].dropna()
        if len(lagged) < 2 or lagged["Lagged A"].nunique() < 2 or lagged[metric_b].nunique() < 2:
            continue
        correlation = float(lagged["Lagged A"].corr(lagged[metric_b]))
        rows.append({"Lag": f"{lag} week", "Correlation": round(correlation, 3), "Abs": abs(correlation)})

    if not rows:
        return {
            "table": pd.DataFrame(columns=["Lag", "Correlation"]),
            "chart_data": pd.DataFrame(columns=["Lag", "Correlation"]),
            "insight": "Not enough weekly variation is available for lag analysis.",
        }

    table = pd.DataFrame(rows).sort_values("Lag").reset_index(drop=True)
    strongest = table.sort_values("Abs", ascending=False).iloc[0]
    insight = (
        f"Strongest lag signal: {metric_a} leads {metric_b} by {strongest['Lag']} "
        f"with a correlation of {strongest['Correlation']:.3f}."
    )
    return {
        "table": table[["Lag", "Correlation"]],
        "chart_data": table[["Lag", "Correlation"]],
        "insight": insight,
    }


def regression_against_nps_summary(metric_df: pd.DataFrame, level: str, limit: int = 8) -> dict[str, object]:
    target_col = "NPS" if level == "Weekly" else "Agent NPS"
    if metric_df.empty or target_col not in metric_df.columns:
        return {
            "table": pd.DataFrame(columns=["Metric", "Correlation", "R-squared", "Slope"]),
            "chart_data": pd.DataFrame(columns=["Metric", "R-squared"]),
            "insight": f"NPS regression is unavailable for the current {level.lower()} data.",
        }

    numeric = metric_df.select_dtypes(include="number").copy()
    if target_col not in numeric.columns:
        return {
            "table": pd.DataFrame(columns=["Metric", "Correlation", "R-squared", "Slope"]),
            "chart_data": pd.DataFrame(columns=["Metric", "R-squared"]),
            "insight": f"NPS regression is unavailable because {target_col} is missing.",
        }

    rows: list[dict[str, object]] = []
    for metric in numeric.columns:
        if metric == target_col:
            continue
        working = numeric[[metric, target_col]].dropna()
        if len(working) < 2 or working[metric].nunique() < 2 or working[target_col].nunique() < 2:
            continue
        correlation = float(working[metric].corr(working[target_col]))
        covariance = float(((working[metric] - working[metric].mean()) * (working[target_col] - working[target_col].mean())).mean())
        variance = float(((working[metric] - working[metric].mean()) ** 2).mean())
        slope = covariance / variance if variance else 0.0
        rows.append(
            {
                "Metric": metric,
                "Correlation": round(correlation, 3),
                "R-squared": round(correlation ** 2, 3),
                "Slope": round(slope, 3),
                "Abs Correlation": abs(correlation),
            }
        )

    if not rows:
        return {
            "table": pd.DataFrame(columns=["Metric", "Correlation", "R-squared", "Slope"]),
            "chart_data": pd.DataFrame(columns=["Metric", "R-squared"]),
            "insight": "Not enough numeric variation is available to model NPS against the current metrics.",
        }

    ranked = pd.DataFrame(rows).sort_values(["R-squared", "Abs Correlation"], ascending=[False, False]).head(limit).reset_index(drop=True)
    top = ranked.iloc[0]
    direction = "raises" if top["Slope"] > 0 else "reduces" if top["Slope"] < 0 else "does not materially change"
    insight = (
        f"Top {level.lower()} NPS predictor: {top['Metric']} has the highest R-squared at {top['R-squared']:.3f} "
        f"and {direction} NPS as it increases."
    )
    return {
        "table": ranked[["Metric", "Correlation", "R-squared", "Slope"]],
        "chart_data": ranked[["Metric", "R-squared"]],
        "insight": insight,
    }


def statistical_narrative_summary(
    level: str,
    metric_a: str,
    metric_b: str,
    correlation_result: dict[str, object],
    ranking_result: dict[str, object],
    outlier_result: dict[str, object],
    lag_result: dict[str, object],
    regression_result: dict[str, object],
) -> str:
    lines: list[str] = []
    metrics = correlation_result.get("metrics", {})
    if metrics:
        lines.append(
            f"Selected pair: {metric_a} vs {metric_b} at the {level.lower()} level shows "
            f"{metrics.get('Strength', 'an observed relationship')} with a correlation of {metrics.get('Correlation', 'N/A')}."
        )
    ranking_insight = ranking_result.get("insight")
    if ranking_insight:
        lines.append(str(ranking_insight))
    outlier_insight = outlier_result.get("insight")
    if outlier_insight:
        lines.append(str(outlier_insight))
    if level == "Weekly":
        lag_insight = lag_result.get("insight")
        if lag_insight:
            lines.append(str(lag_insight))
    regression_insight = regression_result.get("insight")
    if regression_insight:
        lines.append(str(regression_insight))
    return "\n\n".join(lines) if lines else "No statistical narrative is available yet."


def statistical_quick_insights(
    level: str,
    metric_a: str,
    metric_b: str,
    correlation_result: dict[str, object],
    correlation_map_result: dict[str, object],
    outlier_result: dict[str, object],
    lag_result: dict[str, object],
    regression_result: dict[str, object],
) -> list[str]:
    insights: list[str] = []

    metrics = correlation_result.get("metrics", {})
    strength = str(metrics.get("Strength", "relationship")).lower()
    corr_value = metrics.get("Correlation", "N/A")
    insights.append(
        f"{metric_a} vs {metric_b}: current selection shows {strength} with correlation {corr_value} at the {level.lower()} level."
    )

    correlation_map = correlation_map_result.get("table", pd.DataFrame())
    if not correlation_map.empty:
        top = correlation_map.iloc[0]
        insights.append(
            f"Closest relationship for {metric_a}: {top['Metric']} with a {str(top['Direction']).lower()} correlation of {top['Correlation']}."
        )
        negative_map = correlation_map[correlation_map["Direction"] == "Negative"]
        if not negative_map.empty:
            inverse = negative_map.iloc[0]
            insights.append(
                f"Biggest inverse signal for {metric_a}: {inverse['Metric']} moves opposite to it with correlation {inverse['Correlation']}."
            )
        else:
            insights.append(
                f"No strong inverse relationship was detected for {metric_a} in the current {level.lower()} view."
            )
    else:
        insights.append(f"No broader correlation map is available yet for {metric_a}.")
        insights.append(f"No inverse relationship is available yet for {metric_a}.")

    outlier_table = outlier_result.get("table", pd.DataFrame())
    if not outlier_table.empty:
        top_outlier = outlier_table.iloc[0]
        insights.append(
            f"Primary outlier to review: {top_outlier['Observation']} is behaving differently from the normal {metric_a} and {metric_b} pattern."
        )
    else:
        insights.append("No major outlier stands out yet for the selected metric pair.")

    regression_table = regression_result.get("table", pd.DataFrame())
    if not regression_table.empty:
        top_driver = regression_table.iloc[0]
        insights.append(
            f"Top NPS-linked metric: {top_driver['Metric']} has the strongest fit with NPS in this {level.lower()} analysis."
        )
    else:
        insights.append("No reliable NPS-linked metric stands out yet in the current analysis.")

    if level == "Weekly":
        lag_table = lag_result.get("table", pd.DataFrame())
        if not lag_table.empty:
            top_lag = lag_table.iloc[0]
            insights.append(
                f"Timing pattern: the clearest delayed effect appears at {top_lag['Lag']} with a correlation of {top_lag['Correlation']}."
            )
        else:
            insights.append("There is not enough weekly history yet to identify a meaningful timing pattern.")
    else:
        insights.append("Lag analysis is focused on weekly patterns, so it is not used in the agent-level view.")

    return insights[:5]


def weekly_trend(df: pd.DataFrame) -> pd.DataFrame:
    dated = df.dropna(subset=["Feedback Date"]).copy()
    if dated.empty:
        return pd.DataFrame()
    dated["Week"] = dated["Feedback Date"].dt.to_period("W-SAT").apply(lambda value: value.start_time)
    grouped = dated.groupby("Week")["NPS Type"].value_counts().unstack(fill_value=0)
    for label in ["Promoter", "Passive", "Detractor"]:
        if label not in grouped.columns:
            grouped[label] = 0
    sentiment_grouped = dated.groupby("Week")["Sentiment"].value_counts().unstack(fill_value=0)
    for label in ["Positive", "Neutral", "Negative"]:
        if label not in sentiment_grouped.columns:
            sentiment_grouped[label] = 0
    grouped = grouped.join(sentiment_grouped[["Positive", "Neutral", "Negative"]], how="left").fillna(0)
    grouped = grouped.reset_index()
    grouped["Responses"] = grouped[["Promoter", "Passive", "Detractor"]].sum(axis=1)
    grouped["NPS"] = (
        (grouped["Promoter"] / grouped["Responses"] * 100)
        - (grouped["Detractor"] / grouped["Responses"] * 100)
    ).round(1)
    return grouped.sort_values("Week")


def build_summaries(analyzed_df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if analyzed_df.empty:
        empty = pd.DataFrame()
        return {
            "weekly": empty,
            "agent": empty,
            "complaints": empty,
            "reasons": empty,
            "passive": empty,
        }

    analyzed_df = analyzed_df.copy()
    analyzed_df["Impact Score"] = pd.to_numeric(analyzed_df.get("Impact Score"), errors="coerce")
    analyzed_df["NPS Score"] = pd.to_numeric(analyzed_df.get("NPS Score"), errors="coerce")
    analyzed_df["Silent Detractor Alert"] = compute_silent_detractor_alert(analyzed_df)

    weekly_df = weekly_trend(analyzed_df)
    agent_df = (
        analyzed_df.groupby("Agent Name")
        .agg(
            Responses=("Agent Name", "size"),
            Average_Rating=("NPS Score", "mean"),
            Promoters=("NPS Type", lambda values: (values == "Promoter").sum()),
            Detractors=("NPS Type", lambda values: (values == "Detractor").sum()),
        )
        .reset_index()
    )
    agent_df["Average_Rating"] = agent_df["Average_Rating"].round(2)
    agent_df["Agent NPS"] = (
        (agent_df["Promoters"] / agent_df["Responses"] * 100)
        - (agent_df["Detractors"] / agent_df["Responses"] * 100)
    ).round(1)

    negative = analyzed_df[analyzed_df["Sentiment"] == "Negative"]
    complaints_df = pd.DataFrame()
    if not negative.empty:
        complaints_df = (
            negative.groupby(["Agent Name", "Primary Reason"])
            .size()
            .reset_index(name="Count")
            .sort_values(["Agent Name", "Count"], ascending=[True, False])
            .groupby("Agent Name")
            .head(1)
        )

    reason_base = (
        analyzed_df.groupby(["Bucket Category", "Primary Reason"])
        .agg(
            Count=("Primary Reason", "size"),
            Negative_Count=("Sentiment", lambda values: int((values == "Negative").sum())),
            Detractor_Count=("NPS Type", lambda values: int((values == "Detractor").sum())),
        )
        .reset_index()
    )
    reasons_df = reason_base.sort_values(
        ["Detractor_Count", "Negative_Count", "Count"],
        ascending=[False, False, False],
    )
    if not reasons_df.empty:
        reasons_df["Estimated NPS Uplift"] = reasons_df["Primary Reason"].apply(
            lambda reason: round(
                100
                * len(
                    analyzed_df[
                        (analyzed_df["NPS Type"] == "Detractor")
                        & (analyzed_df["Primary Reason"] == reason)
                    ]
                )
                / max(len(analyzed_df), 1),
                1,
            )
        )

    passive_df = (
        analyzed_df[analyzed_df["NPS Type"] == "Passive"]
        .groupby("Primary Reason")
        .size()
        .reset_index(name="Passive Count")
        .sort_values("Passive Count", ascending=False)
    )

    return {
        "weekly": weekly_df,
        "agent": agent_df,
        "complaints": complaints_df,
        "reasons": reasons_df,
        "passive": passive_df,
    }


def export_workbook(
    analyzed_df: pd.DataFrame,
    weekly_df: pd.DataFrame,
    agent_df: pd.DataFrame,
    complaints_df: pd.DataFrame,
    reasons_df: pd.DataFrame,
    passive_df: pd.DataFrame,
) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        analyzed_df.to_excel(writer, index=False, sheet_name="Analyzed Feedback")
        weekly_df.to_excel(writer, index=False, sheet_name="Weekly Trend")
        agent_df.to_excel(writer, index=False, sheet_name="Agent Scorecard")
        complaints_df.to_excel(writer, index=False, sheet_name="Agent Complaints")
        reasons_df.to_excel(writer, index=False, sheet_name="Root Causes")
        passive_df.to_excel(writer, index=False, sheet_name="Passive Insights")
    output.seek(0)
    return output.getvalue()


def export_detailed_workbook(analyzed_df: pd.DataFrame, detailed_text: str) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        analyzed_df.to_excel(writer, index=False, sheet_name="Analyzed Feedback")
        pd.DataFrame({"Detailed Insight (AI)": detailed_text.splitlines() or [""]}).to_excel(
            writer,
            index=False,
            sheet_name="Detailed Insight",
        )
    output.seek(0)
    return output.getvalue()


def export_feedback_intelligence_workbook(raw_df: pd.DataFrame, analyzed_df: pd.DataFrame) -> tuple[bytes, bytes]:
    raw_output = BytesIO()
    with pd.ExcelWriter(raw_output, engine="openpyxl") as writer:
        raw_df.to_excel(writer, index=False, sheet_name="Raw Data")
    raw_output.seek(0)

    analyzed_output = BytesIO()
    with pd.ExcelWriter(analyzed_output, engine="openpyxl") as writer:
        analyzed_df.to_excel(writer, index=False, sheet_name="Analyzed Feedback")
    analyzed_output.seek(0)
    return raw_output.getvalue(), analyzed_output.getvalue()


def churn_risk_summary(analyzed_df: pd.DataFrame) -> dict[str, pd.DataFrame | str]:
    working = analyzed_df.copy()
    working["Churn Risk Score"] = 0
    working.loc[working["Sentiment"] == "Negative", "Churn Risk Score"] += 2
    working.loc[working["NPS Type"] == "Detractor", "Churn Risk Score"] += 3
    working.loc[working["NPS Type"] == "Passive", "Churn Risk Score"] += 1
    working.loc[working["Silent Detractor Alert"], "Churn Risk Score"] += 2
    working.loc[working["Bucket Category"].isin(["Process", "Technology"]), "Churn Risk Score"] += 1
    working.loc[pd.to_numeric(working["Impact Score"], errors="coerce").fillna(0) >= 4, "Churn Risk Score"] += 1

    def classify(score: int) -> str:
        if score >= 5:
            return "High"
        if score >= 3:
            return "Medium"
        return "Low"

    working["Churn Risk Level"] = working["Churn Risk Score"].apply(classify)
    risk_dist = working["Churn Risk Level"].value_counts().rename_axis("Risk").reset_index(name="Count")
    risk_by_sentiment = working.groupby("Sentiment").size().reset_index(name="Count")
    high_risk = working[working["Churn Risk Level"] == "High"]
    theme_breakdown = (
        high_risk.groupby("Primary Reason").size().reset_index(name="Count").sort_values("Count", ascending=False)
        if not high_risk.empty
        else pd.DataFrame(columns=["Primary Reason", "Count"])
    )
    summary_text = (
        f"High risk comments: {int((working['Churn Risk Level'] == 'High').sum())}\n"
        f"Medium risk comments: {int((working['Churn Risk Level'] == 'Medium').sum())}\n"
        f"Silent detractor alerts: {int(working['Silent Detractor Alert'].sum())}\n"
        f"Top high-risk theme: {theme_breakdown.iloc[0]['Primary Reason'] if not theme_breakdown.empty else 'None'}"
    )
    return {
        "working": working,
        "risk_distribution": risk_dist,
        "risk_by_sentiment": risk_by_sentiment,
        "risk_themes": theme_breakdown,
        "summary_text": summary_text,
    }


def build_simple_pdf(title: str, body: str) -> bytes:
    lines = [title, ""] + body.splitlines()
    lines_per_page = 40
    pages = [lines[index : index + lines_per_page] for index in range(0, len(lines), lines_per_page)] or [[""]]
    objects: list[bytes] = []
    kids: list[int] = []

    def esc(value: str) -> str:
        return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids_placeholder = 0
    objects.append(b"")
    font_obj_num = 3
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    next_obj = 4
    for page_lines in pages:
        content_lines = ["BT", "/F1 11 Tf", "50 780 Td", "14 TL"]
        for idx, line in enumerate(page_lines):
            if idx == 0:
                content_lines.append(f"({esc(line)}) Tj")
            else:
                content_lines.append("T*")
                content_lines.append(f"({esc(line)}) Tj")
        content_lines.append("ET")
        content = "\n".join(content_lines).encode("latin-1", errors="replace")
        content_obj = next_obj + 1
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 {font_obj_num} 0 R >> >> /Contents {content_obj} 0 R >>".encode(
                "ascii"
            )
        )
        objects.append(f"<< /Length {len(content)} >>\nstream\n".encode("ascii") + content + b"\nendstream")
        kids.append(next_obj)
        next_obj += 2

    kids_ref = " ".join(f"{kid} 0 R" for kid in kids)
    objects[1] = f"<< /Type /Pages /Count {len(kids)} /Kids [{kids_ref}] >>".encode("ascii")

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")
    xref_start = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF".encode(
            "ascii"
        )
    )
    return bytes(pdf)


def detractor_word_counts(analyzed_df: pd.DataFrame, segment: str = "Detractor") -> Counter:
    if analyzed_df.empty:
        return Counter()
    text_rows = {
        "Passive": analyzed_df.loc[analyzed_df["NPS Type"] == "Passive", "Verbatim Feedback"],
        "Promoter": analyzed_df.loc[analyzed_df["NPS Type"] == "Promoter", "Verbatim Feedback"],
        "Detractor": analyzed_df.loc[analyzed_df["NPS Type"] == "Detractor", "Verbatim Feedback"],
    }
    rows = text_rows.get(segment, text_rows["Detractor"])
    if rows.dropna().empty:
        fallback_map = {
            "Promoter": analyzed_df.loc[analyzed_df["Sentiment"] == "Positive", "Verbatim Feedback"],
            "Passive": analyzed_df.loc[analyzed_df["Sentiment"].isin(["Neutral", "Positive"]), "Verbatim Feedback"],
            "Detractor": analyzed_df.loc[analyzed_df["Sentiment"] == "Negative", "Verbatim Feedback"],
        }
        rows = fallback_map.get(segment, fallback_map["Detractor"])
    if rows.dropna().empty and segment == "Detractor":
        rows = analyzed_df.loc[analyzed_df["Silent Detractor Alert"], "Verbatim Feedback"]

    unigram_counts: Counter = Counter()
    bigram_counts: Counter = Counter()
    for text in rows.dropna().astype(str).tolist():
        text_tokens = [
            token
            for token in tokenize(text)
            if token not in STOP_WORDS
            and token not in GENERIC_CLOUD_WORDS
            and len(token) > 3
            and not token.isdigit()
        ]
        unigram_counts.update(text_tokens)
        bigram_counts.update(
            f"{text_tokens[index]} {text_tokens[index + 1]}"
            for index in range(len(text_tokens) - 1)
            if text_tokens[index] != text_tokens[index + 1]
        )

    filtered = Counter()
    for phrase, count in bigram_counts.items():
        if count >= 2:
            filtered[phrase] = count + 1
    for token, count in unigram_counts.items():
        if count >= 2:
            filtered[token] = max(filtered.get(token, 0), count)

    if not filtered:
        filtered = Counter(dict(unigram_counts.most_common(20)))
    reason_rows = {
        "Passive": analyzed_df.loc[analyzed_df["NPS Type"] == "Passive", ["Primary Reason", "Bucket Category"]],
        "Promoter": analyzed_df.loc[analyzed_df["NPS Type"] == "Promoter", ["Primary Reason", "Bucket Category"]],
        "Detractor": analyzed_df.loc[analyzed_df["NPS Type"] == "Detractor", ["Primary Reason", "Bucket Category"]],
    }
    reason_frame = reason_rows.get(segment, reason_rows["Detractor"]).copy()
    if reason_frame.empty and segment == "Detractor":
        reason_frame = analyzed_df.loc[analyzed_df["Sentiment"] == "Negative", ["Primary Reason", "Bucket Category"]].copy()

    reason_counter = Counter()
    if not reason_frame.empty:
        primary_reasons = [value for value in reason_frame["Primary Reason"].dropna().astype(str).tolist() if value and value != "General"]
        buckets = [value for value in reason_frame["Bucket Category"].dropna().astype(str).tolist() if value and value != "Uncategorized"]
        reason_counter.update(primary_reasons)
        reason_counter.update(buckets)

    # If the text cloud is too sparse or dominated by a single token, enrich it with structured themes.
    top_share = 0.0
    if filtered:
        total = sum(filtered.values())
        top_share = filtered.most_common(1)[0][1] / max(total, 1)
    if len(filtered) < 6 or top_share >= 0.6:
        for label, count in reason_counter.most_common(10):
            filtered[label] = max(filtered.get(label, 0), count + 1)

    if not filtered:
        filtered = reason_counter
    return filtered
