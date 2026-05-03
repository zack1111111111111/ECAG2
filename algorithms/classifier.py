"""
ECG -> Cardiac arrhythmia classifier (4-class).

Architecture (chosen for hackathon reliability):
  1. Hard rule classifier maps extracted features to one of 4 categories
     using deterministic if-else over a medical knowledge table.
     100% reproducible classification.
  2. LLM explainer (Claude) takes the classified label + the raw features,
     and produces a natural-language explanation of WHY this classification
     fits, in clinician-friendly prose.
  3. Offline mode: when no API key is set or USE_CLAUDE_FOR_EXPLANATION is
     False, the explanation falls back to the static text in the knowledge
     table. The demo never breaks.

This is "retrieval-augmented reasoning over structured medical knowledge"
— the rules are the retrieval layer, the LLM is the reasoning layer.

Categories (top-priority first):
  vf_arrest > severe_arrhythmia > pvc_vt > normal
"""

import os
import numpy as np
from typing import Optional


# ============================================================================
# CONFIG
# ============================================================================
USE_CLAUDE_FOR_EXPLANATION = False    # offline-only for this hack
CLAUDE_MODEL = "claude-sonnet-4-5"
CLAUDE_TIMEOUT_S = 8.0
CLAUDE_MAX_TOKENS = 400


# ============================================================================
# Medical knowledge table — 4 arrhythmia classes aligned with PhysioNet
# scenarios (mit100 / mit208 / mit207 / vfdb418).
# ============================================================================
KNOWLEDGE_TABLE = [
    {
        "id":       "vf_arrest",
        "label":    "Ventricular Fibrillation",
        "color":    "#FF0000",
        "color_secondary": "#000000",
        "flashing": True,
        "is_critical": True,
        "hr_rule":      "< 40 OR > 150 OR no organized QRS",
        "rhythm_rule":  "chaotic, no identifiable rhythm",
        "ectopic_rule": "irrelevant (QRS detection fails)",
        "physiological_why": (
            "V-fib produces wildly varying or absent RR intervals, causing "
            "HRV SDNN to explode beyond 200 ms. The heart is no longer "
            "pumping effectively — this is a medical emergency requiring "
            "immediate defibrillation."
        ),
        "scenario_source": "PhysioNet vfdb #418",
    },
    {
        "id":       "severe_arrhythmia",
        "label":    "Severe Arrhythmia (BBB)",
        "color":    "#FF8C00",
        "color_secondary": None,
        "flashing": False,
        "is_critical": False,
        "hr_rule":      "any",
        "rhythm_rule":  "marked irregularity (CV > 0.15)",
        "ectopic_rule": "frequent (> 10% of beats)",
        "physiological_why": (
            "Persistent abnormal beats throughout the recording, often with "
            "left or right bundle branch block (LBBB/RBBB) producing wide, "
            "abnormal QRS complexes. Coupled rhythm irregularity suggests "
            "underlying conduction disease."
        ),
        "scenario_source": "PhysioNet mitdb #207",
    },
    {
        "id":       "pvc_vt",
        "label":    "PVCs / Short VT",
        "color":    "#FFD700",
        "color_secondary": None,
        "flashing": False,
        "is_critical": False,
        "hr_rule":      "any (premature beats interleaved)",
        "rhythm_rule":  "occasional irregularity",
        "ectopic_rule": "elevated (5-10% of beats)",
        "physiological_why": (
            "Premature ventricular contractions (PVCs) appear earlier than "
            "expected with a wide QRS, often followed by a compensatory "
            "pause. Occasional short runs of ventricular tachycardia (VT) "
            "may also appear. Generally benign in isolation but warrants "
            "monitoring."
        ),
        "scenario_source": "PhysioNet mitdb #208",
    },
    {
        "id":       "normal",
        "label":    "Normal Sinus Rhythm",
        "color":    "#32CD32",
        "color_secondary": None,
        "flashing": False,
        "is_critical": False,
        "hr_rule":      "60-100 bpm",
        "rhythm_rule":  "regular (CV < 0.06)",
        "ectopic_rule": "rare (< 5%)",
        "physiological_why": (
            "Regular sinus rhythm at a healthy resting rate, with consistent "
            "RR intervals and no significant ectopic beats. The cardiac "
            "conduction system is functioning normally."
        ),
        "scenario_source": "PhysioNet mitdb #100",
    },
]


# ============================================================================
# Feature band helpers
# ============================================================================
def _hr_band(hr: float) -> str:
    if hr < 60:
        return "low"
    if hr <= 100:
        return "normal"
    return "high"


def _hrv_band(hrv: float) -> str:
    if hrv < 30:
        return "low"
    if hrv <= 60:
        return "normal"
    if hrv <= 200:
        return "high"
    return "extreme"


def _rr_cv_band(cv: float) -> str:
    if cv < 0.06:
        return "regular"
    if cv < 0.15:
        return "mild_irregular"
    return "marked_irregular"


# ============================================================================
# Hard rule classifier
# ============================================================================
def hard_rule_classify(hr_bpm: float,
                       hrv_sdnn_ms: float,
                       rr_cv: float,
                       ectopic_ratio: float) -> str:
    """
    Returns one of the 4 category IDs.
    Priority order: vf_arrest > severe_arrhythmia > pvc_vt > normal.

    Thresholds derived from the 4 PhysioNet scenarios (see README).
    """
    # --- Override: VF / cardiac arrest ---
    # Bradycardia (<40), severe tachycardia (>150), or HRV explosion (>200 ms)
    # all indicate the heart is no longer in organized sinus rhythm.
    # NaN-safe: NaN > 200 returns False, so explicitly check.
    hrv_extreme = (not np.isnan(hrv_sdnn_ms)) and hrv_sdnn_ms > 200
    hr_extreme  = (not np.isnan(hr_bpm)) and (hr_bpm < 40 or hr_bpm > 150)
    if hr_extreme or hrv_extreme:
        return "vf_arrest"

    # --- Severe arrhythmia: marked rhythm irregularity + frequent ectopy ---
    if rr_cv > 0.15 and ectopic_ratio > 0.10:
        return "severe_arrhythmia"

    # --- PVCs / short VT: elevated ectopic ratio ---
    if ectopic_ratio > 0.05:
        return "pvc_vt"

    # --- Default: normal sinus rhythm ---
    return "normal"


def get_knowledge_entry(category_id: str) -> dict:
    """Look up the table row for a given category."""
    for entry in KNOWLEDGE_TABLE:
        if entry["id"] == category_id:
            return entry
    raise ValueError(f"Unknown category: {category_id}")


# ============================================================================
# Probability vector — for displaying classification bar chart in the demo.
# Hard rules give a single label, so we synthesize a soft probability that
# strongly favors the matched class while keeping a small share of mass
# distributed across nearby classes (for visual realism).
# ============================================================================
def soft_probabilities(category_id: str) -> dict:
    """Return {category_id: probability} dict over all 4 classes."""
    # Default: 0.85 on the matched class, 0.05 on each of the other 3
    probs = {entry["id"]: 0.05 for entry in KNOWLEDGE_TABLE}
    probs[category_id] = 0.85
    return probs


# ============================================================================
# LLM explanation layer (with offline fallback)
# ============================================================================
def _build_explanation_prompt(knowledge: dict,
                              hr_bpm: float, hrv_sdnn_ms: float,
                              rr_cv: float, ectopic_ratio: float,
                              hr_band: str, hrv_band: str,
                              rr_cv_band: str) -> str:
    return f"""A patient's ECG was analyzed by Pan-Tompkins QRS detection.
The extracted features and the matched arrhythmia category are below.

EXTRACTED FEATURES:
  Heart rate (HR)        : {hr_bpm:.1f} bpm   (band: {hr_band})
  HRV (SDNN)             : {hrv_sdnn_ms:.1f} ms   (band: {hrv_band})
  RR coefficient of var. : {rr_cv:.3f}        (band: {rr_cv_band})
  Ectopic beat ratio     : {ectopic_ratio*100:.1f} %

CATEGORY MATCHED:
  {knowledge["label"]}
  HR rule        : {knowledge["hr_rule"]}
  Rhythm rule    : {knowledge["rhythm_rule"]}
  Ectopic rule   : {knowledge["ectopic_rule"]}
  Physiological "why": {knowledge["physiological_why"]}

Write 2-3 short sentences for a clinician dashboard explaining WHY this
ECG matches this category. Reference at least one specific extracted
number. Do not hedge with "may" or "could" — the rules already matched.
Tone: precise, clinical, concise. No greetings, no preamble.

Output only the explanation text, no JSON, no markdown."""


def llm_explain(category_id: str,
                hr_bpm: float, hrv_sdnn_ms: float,
                rr_cv: float, ectopic_ratio: float) -> dict:
    """
    Generate natural-language explanation. Falls back to the table's
    physiological_why on any error or in offline mode.
    """
    knowledge = get_knowledge_entry(category_id)
    fallback_text = knowledge["physiological_why"]

    if not USE_CLAUDE_FOR_EXPLANATION:
        return {"text": fallback_text, "source": "knowledge_table"}

    try:
        from anthropic import Anthropic
    except ImportError:
        return {"text": fallback_text,
                "source": "knowledge_table (anthropic not installed)"}

    if not os.getenv("ANTHROPIC_API_KEY"):
        return {"text": fallback_text,
                "source": "knowledge_table (no API key)"}

    try:
        hr_band = _hr_band(hr_bpm)
        hrv_band = _hrv_band(hrv_sdnn_ms)
        rr_cv_band = _rr_cv_band(rr_cv)
        prompt = _build_explanation_prompt(
            knowledge, hr_bpm, hrv_sdnn_ms, rr_cv, ectopic_ratio,
            hr_band, hrv_band, rr_cv_band)

        client = Anthropic(timeout=CLAUDE_TIMEOUT_S)
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=CLAUDE_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as e:
        return {"text": fallback_text,
                "source": f"knowledge_table (Claude error: "
                          f"{type(e).__name__})"}

    text = response.content[0].text.strip()
    return {"text": text, "source": "claude_api"}


# ============================================================================
# Top-level
# ============================================================================
def classify(hr_bpm: float, hrv_sdnn_ms: float,
             rr_cv: float, ectopic_ratio: float) -> dict:
    """
    Full classification: hard rules + soft probabilities + explanation.
    """
    category_id = hard_rule_classify(hr_bpm, hrv_sdnn_ms, rr_cv, ectopic_ratio)
    knowledge = get_knowledge_entry(category_id)
    explanation = llm_explain(category_id, hr_bpm, hrv_sdnn_ms,
                              rr_cv, ectopic_ratio)
    probabilities = soft_probabilities(category_id)

    return {
        "category_id":    category_id,
        "category_label": knowledge["label"],
        "color":          knowledge["color"],
        "is_critical":    knowledge["is_critical"],
        "flashing":       knowledge["flashing"],
        "probabilities":  probabilities,
        "features": {
            "hr_bpm":         round(hr_bpm, 1) if not np.isnan(hr_bpm) else None,
            "hr_band":        _hr_band(hr_bpm) if not np.isnan(hr_bpm) else "unknown",
            "hrv_sdnn_ms":    round(hrv_sdnn_ms, 1) if not np.isnan(hrv_sdnn_ms) else None,
            "hrv_band":       _hrv_band(hrv_sdnn_ms) if not np.isnan(hrv_sdnn_ms) else "unknown",
            "rr_cv":          round(rr_cv, 3),
            "rr_cv_band":     _rr_cv_band(rr_cv),
            "ectopic_ratio":  round(ectopic_ratio, 3),
        },
        "rules_matched": {
            "hr":      knowledge["hr_rule"],
            "rhythm":  knowledge["rhythm_rule"],
            "ectopic": knowledge["ectopic_rule"],
        },
        "knowledge_table_why": knowledge["physiological_why"],
        "explanation": explanation,
    }
