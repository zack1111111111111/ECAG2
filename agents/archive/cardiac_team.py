"""
cardiac_team.py
===============
AG2 multi-agent team for cardiac signal interpretation.

Architecture: two-agent sequential chat
    SignalAnalystAgent  ---->  CardiologistAgent
       (feature reader)         (clinical reasoner)

The SignalAnalyst receives a feature bundle extracted from a 5-second
ECG window (HR, HRV, RR-CV, ectopic ratio, R-peak count, recent RR
intervals) and produces a structured "signal-level" report — what the
numbers themselves say, without yet making a clinical call.

The Cardiologist receives that report (via initiate_chat), considers
it against clinical knowledge, and produces the final diagnosis +
explanation + risk level. The Cardiologist's last message is the
team's output.

Notes
-----
- This module does NOT use AG2's GroupChat. Sequential two-agent chat
  via initiate_chat is the simplest, most predictable pattern for a
  hackathon demo — speaker selection cannot drift, and conversation
  length is bounded.
- LLM: claude-sonnet-4-5 (per project consistency).
- Trigger: manual, via run_cardiac_team(features) called from the demo
  when the user presses [A].
- Output: full conversation transcript + final diagnosis dict.
"""

import os
from pathlib import Path
from typing import Optional

# Load .env at module import time
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # not fatal; user may set env var another way


# ============================================================
# Model + LLM config
# ============================================================
LLM_MODEL = "claude-sonnet-4-5"

# AG2 LLM config — Anthropic via the autogen anthropic client.
# api_type="anthropic" tells AG2 to use Anthropic's SDK directly.
LLM_CONFIG = {
    "config_list": [
        {
            "model":    LLM_MODEL,
            "api_type": "anthropic",
            "api_key":  os.getenv("ANTHROPIC_API_KEY", ""),
        }
    ],
    "temperature": 0.3,   # low temperature for clinical consistency
    "cache_seed": None,   # disable caching so repeated runs feel fresh
}


# ============================================================
# Agent system messages
# ============================================================

SIGNAL_ANALYST_SYSTEM_MSG = """You are SignalAnalyst, a biosignal-processing
specialist on a cardiac analysis team. Your role is to read raw ECG
features extracted by Pan-Tompkins QRS detection and produce a
*signal-level* interpretation. You do NOT make clinical diagnoses —
that is the Cardiologist's role.

For each feature bundle you receive, produce:
  1. A one-line summary of signal quality (good / degraded / failed).
  2. The most striking numerical observation (e.g., "HRV SDNN of 358 ms
     is far above the typical adult resting range of 20-50 ms").
  3. Two or three candidate hypotheses about what cardiac state could
     produce these numbers, ordered by likelihood. Use phrasing like
     "consistent with..." rather than "this is...".
  4. A note on what additional data would disambiguate the hypotheses.

Tone: precise, hedged, focused on the numbers. Do NOT invent values
that were not given to you. Keep your message under 8 sentences.
End your message with the line:
  HANDOFF TO CARDIOLOGIST.
"""


CARDIOLOGIST_SYSTEM_MSG = """You are Cardiologist, a board-certified
clinical electrophysiologist on a cardiac analysis team. You receive
a signal-level report from SignalAnalyst plus the original feature
bundle. Your job is to integrate them into a final clinical assessment.

For each handoff, produce a structured response with these sections,
each preceded by a clear marker:

  [DIAGNOSIS]: one of {Normal Sinus Rhythm, PVCs / Short VT,
               Severe Arrhythmia (BBB), Ventricular Fibrillation,
               Indeterminate}. Pick the single most likely.

  [RISK LEVEL]: one of {normal, watch, concern, critical}.

  [REASONING]: 2-3 sentences referencing the specific numerical
               features that drove your decision. Cite at least one
               number explicitly.

  [RECOMMENDATION]: one short sentence on next clinical step
                    (e.g., "continue routine monitoring",
                    "12-lead ECG and electrolyte panel",
                    "immediate defibrillation").

Be decisive — the SignalAnalyst's job was to hedge; yours is to commit.
If the data are truly insufficient (e.g., signal failure with no R
peaks), choose Indeterminate and say what's missing.

After the [RECOMMENDATION] line, end your message with exactly:
  END OF CONSULTATION.
"""


# ============================================================
# Build the feature prompt the SignalAnalyst sees
# ============================================================
def build_feature_prompt(features: dict) -> str:
    """
    Format the feature bundle into a clean text block for the
    SignalAnalyst's first message. Includes context (level C from
    our design discussion: features + brief textual context).
    """
    hr  = features.get("hr_bpm")
    hrv = features.get("hrv_sdnn_ms")
    rr_cv         = features.get("rr_cv")
    ectopic_ratio = features.get("ectopic_ratio")
    n_peaks       = features.get("n_r_peaks")
    r_amp         = features.get("r_amp_mV")
    rr_intervals  = features.get("rr_intervals_ms", [])
    fs            = features.get("fs")
    window_s      = features.get("window_s")
    scenario_src  = features.get("scenario_source", "unknown source")

    def fmt(v, nd=1, suffix=""):
        if v is None:
            return "N/A"
        try:
            if isinstance(v, float) and (v != v):  # NaN
                return "N/A (algorithm failed)"
            return f"{v:.{nd}f}{suffix}"
        except Exception:
            return str(v)

    rr_preview = ", ".join(f"{x:.0f}" for x in rr_intervals[:8])
    if len(rr_intervals) > 8:
        rr_preview += f", ... ({len(rr_intervals)} total)"
    if not rr_preview:
        rr_preview = "none detected"

    return f"""Cardiac feature bundle from a {window_s}-second ECG window.

Source            : {scenario_src}
Sampling rate     : {fs} Hz

Extracted features:
  Heart rate (HR)         : {fmt(hr,  1, ' bpm')}
  HRV (SDNN)              : {fmt(hrv, 1, ' ms')}
  RR coefficient of var.  : {fmt(rr_cv, 3)}
  Ectopic beat ratio      : {fmt(ectopic_ratio*100 if ectopic_ratio is not None else None, 1, ' %')}
  R-peak count            : {n_peaks if n_peaks is not None else 'N/A'}
  Mean R-peak amplitude   : {fmt(r_amp, 2, ' mV')}
  Recent RR intervals (ms): {rr_preview}

Reference clinical ranges (adult resting):
  Normal HR        : 60-100 bpm
  Normal HRV SDNN  : ~20-50 ms (short-window estimate)
  Normal RR CV     : 0.02-0.06
  VF indicator     : HRV SDNN > 200 ms or no organized QRS

Please analyze and hand off to the Cardiologist."""


# ============================================================
# Run the team
# ============================================================
def run_cardiac_team(features: dict, verbose: bool = True) -> dict:
    """
    Trigger the two-agent consultation. Returns a dict with:
      - transcript    : list of {speaker, content} for each message
      - final_message : the Cardiologist's last message (raw text)
      - parsed        : extracted [DIAGNOSIS], [RISK LEVEL], etc. from
                        the Cardiologist's message
      - error         : str if the call failed, else None
    """
    if not os.getenv("ANTHROPIC_API_KEY"):
        return {
            "transcript":   [],
            "final_message": "",
            "parsed": {"diagnosis": "API key missing"},
            "error": "ANTHROPIC_API_KEY not set in environment",
        }

    # Lazy import so the demo can still load even if AG2 isn't installed
    try:
        from autogen import ConversableAgent
    except ImportError as e:
        return {
            "transcript":   [],
            "final_message": "",
            "parsed": {"diagnosis": "AG2 not installed"},
            "error": f"autogen import failed: {e}",
        }

    # ---- Define the agents ----
    signal_analyst = ConversableAgent(
        name="SignalAnalyst",
        system_message=SIGNAL_ANALYST_SYSTEM_MSG,
        llm_config=LLM_CONFIG,
        human_input_mode="NEVER",
        # SignalAnalyst stops after producing one analysis (handoff line)
        is_termination_msg=lambda m: "HANDOFF TO CARDIOLOGIST" in m.get("content", ""),
    )

    cardiologist = ConversableAgent(
        name="Cardiologist",
        system_message=CARDIOLOGIST_SYSTEM_MSG,
        llm_config=LLM_CONFIG,
        human_input_mode="NEVER",
        # Cardiologist stops after END OF CONSULTATION
        is_termination_msg=lambda m: "END OF CONSULTATION" in m.get("content", ""),
    )

    # ---- Build the initial message for the SignalAnalyst ----
    feature_prompt = build_feature_prompt(features)

    # ---- Run the conversation ----
    # Pattern: cardiologist initiates a chat WITH SignalAnalyst,
    # passing the feature bundle. SignalAnalyst replies with analysis,
    # cardiologist replies with diagnosis, then we stop.
    #
    # max_turns=2 means: SignalAnalyst speaks once, Cardiologist speaks
    # once. That's exactly the sequential handoff we want.

    if verbose:
        print("\n" + "=" * 72)
        print("  🩺 CARDIAC TEAM CONSULTATION")
        print("=" * 72)

    try:
        chat_result = cardiologist.initiate_chat(
            recipient=signal_analyst,
            message=feature_prompt,
            max_turns=2,
            silent=not verbose,
        )
    except Exception as e:
        if verbose:
            print(f"\n[ERROR] {type(e).__name__}: {e}")
            print("=" * 72 + "\n")
        return {
            "transcript":   [],
            "final_message": "",
            "parsed": {"diagnosis": "API call failed"},
            "error": f"{type(e).__name__}: {e}",
        }

    # ---- Extract the transcript ----
    # chat_history is a list of {role, name, content} dicts
    history = chat_result.chat_history or []
    transcript = []
    for msg in history:
        speaker = msg.get("name", msg.get("role", "unknown"))
        content = msg.get("content", "")
        transcript.append({"speaker": speaker, "content": content})

    # The last *Cardiologist* message is the final diagnosis.
    final_message = ""
    for msg in reversed(transcript):
        if msg["speaker"] == "Cardiologist":
            final_message = msg["content"]
            break

    parsed = parse_cardiologist_output(final_message)

    if verbose:
        print("=" * 72)
        print(f"  Final diagnosis: {parsed.get('diagnosis', '?')}  "
              f"(risk: {parsed.get('risk_level', '?')})")
        print("=" * 72 + "\n")

    return {
        "transcript":   transcript,
        "final_message": final_message,
        "parsed":        parsed,
        "error":         None,
    }


# ============================================================
# Parse the Cardiologist's structured output
# ============================================================
def parse_cardiologist_output(text: str) -> dict:
    """
    Pull out [DIAGNOSIS], [RISK LEVEL], [REASONING], [RECOMMENDATION]
    from the Cardiologist's free-form message.

    Robust to extra whitespace, missing sections, and the markers
    appearing on their own line or inline.
    """
    if not text:
        return {
            "diagnosis":      "Indeterminate",
            "risk_level":     "unknown",
            "reasoning":      "(no output from Cardiologist)",
            "recommendation": "—",
        }

    def extract(section: str) -> str:
        # Find the marker, take everything until the next marker or EOC
        marker = f"[{section}]"
        idx = text.find(marker)
        if idx < 0:
            return ""
        rest = text[idx + len(marker):]
        # Cut at the next [SECTION] or END OF CONSULTATION
        next_marker = float("inf")
        for s in ("[DIAGNOSIS]", "[RISK LEVEL]", "[REASONING]",
                  "[RECOMMENDATION]", "END OF CONSULTATION"):
            i = rest.find(s)
            if 0 <= i < next_marker:
                next_marker = i
        if next_marker == float("inf"):
            chunk = rest
        else:
            chunk = rest[:next_marker]
        # Strip leading colon, whitespace, dashes
        return chunk.lstrip(": \n\r\t-").rstrip(" \n\r\t").strip()

    return {
        "diagnosis":      extract("DIAGNOSIS")      or "Indeterminate",
        "risk_level":     extract("RISK LEVEL")     or "unknown",
        "reasoning":      extract("REASONING")      or "(no reasoning given)",
        "recommendation": extract("RECOMMENDATION") or "—",
    }


# ============================================================
# Self-test (run this file directly to verify the team works
# without booting the GUI)
# ============================================================
if __name__ == "__main__":
    # Synthetic feature bundle — mimics what the demo will send.
    # Numbers chosen to look like the mit208 (PVC) scenario so we can
    # see if the team picks up the irregularity.
    test_features = {
        "hr_bpm":          79.6,
        "hrv_sdnn_ms":     358.8,
        "rr_cv":           0.42,
        "ectopic_ratio":   0.18,
        "n_r_peaks":       40,
        "r_amp_mV":        1.05,
        "rr_intervals_ms": [820, 410, 1230, 815, 825, 800, 1180, 815],
        "fs":              360,
        "window_s":        5,
        "scenario_source": "PhysioNet mitdb #208 (test invocation)",
    }

    result = run_cardiac_team(test_features, verbose=True)

    if result["error"]:
        print(f"[error] {result['error']}")
    else:
        print("\n--- Parsed Cardiologist output ---")
        for k, v in result["parsed"].items():
            print(f"  {k:15s}: {v}")
