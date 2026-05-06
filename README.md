# Real-time ECG Monitor with AG2 Multi-Agent Reasoning

Live demo: [https://ecag2.netlify.app/](https://ecag2.netlify.app/)

An interactive cardiac-monitoring demo that combines deterministic ECG signal processing with a two-agent clinical reasoning layer. The project is designed to show how life-critical AI systems can keep the signal analysis traceable while using an LLM only for explanation and synthesis.

## Why this project matters

Medical AI should not let an LLM hallucinate a diagnosis from raw signals. This demo uses a two-layer architecture:

1. **Algorithms decide on signal quality and feature extraction.**
2. **The LLM explains and synthesizes from clean, structured numbers.**

Every diagnosis points back to specific feature values such as heart rate, HRV, RR variability, ectopic-beat ratio, R-peak count, and R-peak amplitude. The output is designed to be traceable rather than a black box.

## Architecture

```text
PhysioNet ECG record
        |
        v
DSP pipeline
Pan-Tompkins QRS detection
        |
        v
Feature bundle
HR, HRV, RR-CV, ectopic ratio, R-peak amplitude
        |
        v
Rule-based risk + arrhythmia classifier
        |
        v
AG2 multi-agent consultation
SignalAnalyst -> Cardiologist
        |
        v
Structured verdict + clinician/patient explanation
```

## Layer 1: DSP Pipeline

The signal layer implements the classical **Pan-Tompkins QRS detection algorithm**, still a gold standard for finding heartbeats in noisy ECG.

Pipeline:

- Bandpass filter between **5 and 15 Hz**
- Derivative to emphasize QRS slopes
- Squaring to amplify strong QRS energy
- Moving-window integration over **150 ms**
- Adaptive thresholding to locate R-peaks

From detected R-peaks, the app computes:

- Heart rate
- HRV / SDNN
- RR-interval variability
- Ectopic-beat ratio
- R-peak amplitude

This layer is deterministic, fast, and explainable. It also exposes where classical signal processing can fail.

## Layer 1 Failure Mode

One demo scenario uses a real PhysioNet bundle branch block record. In this case, QRS morphology is distorted and Pan-Tompkins detects R-peaks at only about **48% sensitivity**.

That failure is the core motivation for the second layer: a pure DSP system could miss or misclassify difficult rhythms, so the project adds a reasoning layer that can interpret the feature bundle while still citing numbers.

## Layer 2: AG2 Multi-Agent Reasoning

The reasoning layer is built with the **AG2 framework** and configured for **Claude Sonnet 4.5**.

It uses two specialist agents:

- **SignalAnalyst**: a biosignal specialist that reads the feature bundle, flags the strongest statistic, and proposes ranked hypotheses.
- **Cardiologist**: a senior electrophysiologist persona that commits to one diagnosis and must cite at least one specific feature value.

The final diagnosis is constrained to one of:

- Normal Sinus Rhythm
- PVCs / Short VT
- Severe Arrhythmia with Bundle Branch Block
- Ventricular Fibrillation
- Indeterminate

Risk levels are normalized to:

- `normal`
- `watch`
- `concern`
- `critical`

Unknown or unexpected LLM outputs are normalized conservatively. For a medical demo, it is safer to over-warn than under-warn.

## What was hard

**Multi-agent termination.** The first AG2 implementation allowed agents to terminate one another prematurely. The final version uses manual two-turn orchestration for deterministic control.

**LLM rule violations.** Even at low temperature, the LLM could invent unsupported risk labels. A normalization layer constrains output back to the schema.

**Messy ground truth.** Real ECG labels are not perfectly clean. A record labeled normal can still contain isolated ectopic beats that the agents correctly detect. The demo explicitly treats simplified labels as presentation-stage shortcuts, not production clinical truth.

## Demo Scenarios

The interface includes four PhysioNet-backed rhythm scenarios:

- **Normal Sinus Rhythm**: stable rhythm and low risk
- **PVCs / Short VT**: premature beats and watch-level risk
- **Severe Arrhythmia (BBB)**: distorted QRS morphology and elevated risk
- **Ventricular Fibrillation**: chaotic rhythm and critical risk

The frontend provides both **clinician** and **patient** modes so the same signal can be explained at different levels of detail.

## Tech Stack

- Python
- JavaScript
- HTML/CSS
- NumPy
- SciPy
- AG2 / AutoGen-style agents
- Anthropic Claude Sonnet 4.5
- PhysioNet ECG records

## Local Run

Install Python dependencies, then start the local server:

```bash
python3 server.py
```

Open:

```text
http://localhost:5173/index.html
```

For AG2 consultation mode, set:

```bash
export ANTHROPIC_API_KEY="your_api_key"
```

The visual ECG dashboard works as a deterministic demo even when the LLM key is not configured.

## Repository Structure

```text
.
├── agents/
│   └── cardiac_team.py        # AG2 SignalAnalyst + Cardiologist orchestration
├── algorithms/
│   ├── heart_rate.py          # Pan-Tompkins QRS detection
│   ├── classifier.py          # Rule-based arrhythmia classifier
│   └── risk.py                # Risk scoring helpers
├── tools/
│   ├── prepare_physionet.py   # Scenario preparation
│   └── validate_features.py   # Feature validation
├── app.js                     # Frontend interactions and ECG rendering
├── index.html                 # Main app
├── server.py                  # Local API/server
└── styles.css                 # UI styling
```

## Disclaimer

This project is an educational demo and is not a medical device. It is not intended for diagnosis, treatment, or emergency decision-making.
