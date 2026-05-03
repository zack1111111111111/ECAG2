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
specialist on a cardiac analysis team. You speak briefly, like a colleague
flagging an observation to a doctor in a hallway — not like a textbook.

When you receive a feature bundle, respond in this exact format:

  Signal: <one short phrase: clean / noisy / failed>
  Flag:   <one sentence naming the most striking number and what it suggests>
  Bets:   <2-3 short bullets, each one line, ordered by likelihood,
           phrased like "Looks like X" or "Could be Y, but...">

Total length: under 60 words. No headers, no markdown bold, no preambles
like "Based on the data...". Speak as if you're saying it out loud.
Always end with a literal line:
  → Cardiologist?
"""


CARDIOLOGIST_SYSTEM_MSG = """You are Cardiologist, a senior clinical
electrophysiologist. Your colleague SignalAnalyst just flagged ECG
features to you. You commit to a call quickly — like an attending on
rounds, not a paper writer.

Respond in this exact format, each line as short as possible:

  [DIAGNOSIS]: <one of: Normal Sinus Rhythm | PVCs / Short VT |
               Severe Arrhythmia (BBB) | Ventricular Fibrillation |
               Indeterminate>
  [RISK LEVEL]: <normal | watch | concern | critical>
  [REASONING]: <ONE sentence, must cite at least one specific number>
  [RECOMMENDATION]: <ONE short clinical step>

Total length: under 50 words. No preamble, no markdown bold, no
extra commentary. Speak plainly. Be decisive — even when uncertain,
pick the most likely category; only choose Indeterminate if there
is literally no organized signal.

End your message with exactly:
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
    # Pattern: a silent UserProxy orchestrates two sequential specialist
    # turns. This avoids the trap where one specialist's termination
    # condition prematurely ends the other's turn.

    signal_analyst = ConversableAgent(
        name="SignalAnalyst",
        system_message=SIGNAL_ANALYST_SYSTEM_MSG,
        llm_config=LLM_CONFIG,
        human_input_mode="NEVER",
    )

    cardiologist = ConversableAgent(
        name="Cardiologist",
        system_message=CARDIOLOGIST_SYSTEM_MSG,
        llm_config=LLM_CONFIG,
        human_input_mode="NEVER",
    )

    # ---- Build the initial message ----
    feature_prompt = build_feature_prompt(features)

    if verbose:
        print("\n" + "=" * 72)
        print("  🩺 CARDIAC TEAM CONSULTATION")
        print("=" * 72)

    # ---- Turn 1: SignalAnalyst reads the features ----
    transcript = []
    try:
        if verbose:
            print("\n--- Turn 1: SignalAnalyst ---\n")
            print(feature_prompt)
            print()

        analyst_reply = signal_analyst.generate_reply(
            messages=[{"role": "user", "content": feature_prompt}]
        )
        if isinstance(analyst_reply, dict):
            analyst_text = analyst_reply.get("content", "")
        else:
            analyst_text = str(analyst_reply)

        if verbose:
            print(f"SignalAnalyst:\n{analyst_text}\n")

        transcript.append({"speaker": "User",          "content": feature_prompt})
        transcript.append({"speaker": "SignalAnalyst", "content": analyst_text})

    except Exception as e:
        if verbose:
            print(f"\n[ERROR in SignalAnalyst turn] {type(e).__name__}: {e}")
            print("=" * 72 + "\n")
        return {
            "transcript":   transcript,
            "final_message": "",
            "parsed":       {"diagnosis": "API call failed"},
            "error":        f"SignalAnalyst: {type(e).__name__}: {e}",
        }

    # ---- Turn 2: Cardiologist receives the analyst's report ----
    cardiologist_input = (
        f"You have just received this analysis from your colleague "
        f"SignalAnalyst, who reviewed a patient's ECG features:\n\n"
        f"---\n{analyst_text}\n---\n\n"
        f"Original feature bundle for your reference:\n\n"
        f"{feature_prompt}\n\n"
        f"Now produce your final clinical assessment using the "
        f"required [DIAGNOSIS] / [RISK LEVEL] / [REASONING] / "
        f"[RECOMMENDATION] format."
    )

    try:
        if verbose:
            print("--- Turn 2: Cardiologist ---\n")

        cardio_reply = cardiologist.generate_reply(
            messages=[{"role": "user", "content": cardiologist_input}]
        )
        if isinstance(cardio_reply, dict):
            final_message = cardio_reply.get("content", "")
        else:
            final_message = str(cardio_reply)

        if verbose:
            print(f"Cardiologist:\n{final_message}\n")

        transcript.append({"speaker": "Cardiologist", "content": final_message})

    except Exception as e:
        if verbose:
            print(f"\n[ERROR in Cardiologist turn] {type(e).__name__}: {e}")
            print("=" * 72 + "\n")
        return {
            "transcript":   transcript,
            "final_message": "",
            "parsed":       {"diagnosis": "API call failed"},
            "error":        f"Cardiologist: {type(e).__name__}: {e}",
        }

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
