from __future__ import annotations

import json
import math
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import numpy as np

from algorithms.classifier import get_knowledge_entry, soft_probabilities
from algorithms.heart_rate import pan_tompkins
from algorithms.risk import compute_risk


ROOT = Path(__file__).resolve().parent
SCENARIO_DIR = ROOT / "data" / "scenarios"

SCENARIOS = {
    "normal": {
        "file": "mit100_normal.npz",
        "title": "Normal Sinus Rhythm",
        "category_id": "normal",
        "risk": "Low risk",
        "level": "normal",
        "fallback": {"hr": 72, "hrv": 42, "rPeak": 1.18},
    },
    "pvc": {
        "file": "mit208_pvc.npz",
        "title": "PVCs / Short VT",
        "category_id": "pvc_vt",
        "risk": "Watch",
        "level": "warning",
        "fallback": {"hr": 96, "hrv": 68, "rPeak": 1.34},
    },
    "severe": {
        "file": "mit207_severe.npz",
        "title": "Severe Arrhythmia (BBB)",
        "category_id": "severe_arrhythmia",
        "risk": "Elevated risk",
        "level": "warning",
        "fallback": {"hr": 118, "hrv": 91, "rPeak": 1.48},
    },
    "vf": {
        "file": "vf418_arrest.npz",
        "title": "Ventricular Fibrillation",
        "category_id": "vf_arrest",
        "risk": "Critical",
        "level": "critical",
        "fallback": {"hr": 0, "hrv": 0, "rPeak": 0.24},
    },
}

SCENARIO_CACHE: dict[str, dict] = {}

PROBABILITY_ORDER = {
    "normal": "normal",
    "pvc": "pvc_vt",
    "severe": "severe_arrhythmia",
    "vf": "vf_arrest",
}


def finite_number(value: float | None, fallback: float) -> float:
    if value is None:
        return fallback
    try:
        if math.isnan(float(value)) or math.isinf(float(value)):
            return fallback
    except TypeError:
        return fallback
    return float(value)


def ectopic_ratio(rr_intervals_s: np.ndarray) -> float:
    if len(rr_intervals_s) < 3:
        return 0.0
    median_rr = float(np.median(rr_intervals_s))
    if median_rr == 0:
        return 0.0
    deviations = np.abs(rr_intervals_s - median_rr) / median_rr
    return float(np.sum(deviations > 0.20) / len(rr_intervals_s))


def rr_cv(rr_intervals_s: np.ndarray) -> float:
    if len(rr_intervals_s) < 2 or float(np.mean(rr_intervals_s)) == 0:
        return 0.0
    return float(np.std(rr_intervals_s) / np.mean(rr_intervals_s))


def action_list(level: str, category_id: str) -> list[str]:
    if category_id == "vf_arrest" or level == "critical":
        return ["Call emergency response", "Begin emergency protocol", "Monitor continuously"]
    if level in {"watch", "concern"} or category_id in {"pvc_vt", "severe_arrhythmia"}:
        return ["Reduce physical activity", "Continue monitoring", "Seek medical advice if persists"]
    return ["Continue routine monitoring", "Maintain normal activity", "Review only if symptoms appear"]


def scenario_payload(key: str) -> dict:
    config = SCENARIOS[key]
    path = SCENARIO_DIR / config["file"]
    data = np.load(path, allow_pickle=True)
    ecg = data["ecg"].astype(float)
    fs = int(data["fs"])
    duration = int(data["duration_s"])

    features = pan_tompkins(ecg, fs)
    rr_intervals = features["rr_intervals_s"]
    hr = finite_number(features["heart_rate_bpm"], config["fallback"]["hr"])
    hrv = finite_number(features["hrv_sdnn_ms"], config["fallback"]["hrv"])
    cv = rr_cv(rr_intervals)
    ectopic = ectopic_ratio(rr_intervals)
    risk = compute_risk(hr, hrv, rr_intervals)
    category_id = config["category_id"]
    knowledge = get_knowledge_entry(category_id)

    r_peaks = features["r_peaks"]
    if len(r_peaks):
        r_peak_amp = float(np.max(np.abs(ecg[r_peaks])))
    else:
        r_peak_amp = config["fallback"]["rPeak"]

    probabilities = soft_probabilities(category_id)
    ordered_probs = [
        probabilities.get(PROBABILITY_ORDER["normal"], 0),
        probabilities.get(PROBABILITY_ORDER["pvc"], 0),
        probabilities.get(PROBABILITY_ORDER["severe"], 0),
        probabilities.get(PROBABILITY_ORDER["vf"], 0),
    ]

    return {
        "key": key,
        "title": config["title"],
        "risk": config["risk"],
        "level": config["level"],
        "source": str(data["source"]),
        "record": str(data["source"]).replace("PhysioNet ", ""),
        "truth": str(data["diagnosis"]),
        "hr": round(hr),
        "hrv": round(hrv),
        "rPeak": round(r_peak_amp, 2),
        "trends": {
            "hr": round(hr - config["fallback"]["hr"]),
            "hrv": round(hrv - config["fallback"]["hrv"]),
            "rPeak": round(r_peak_amp - config["fallback"]["rPeak"], 2),
        },
        "confidence": round(max(ordered_probs) * 100),
        "diagnosis": knowledge["label"],
        "why": knowledge["physiological_why"],
        "actions": action_list(config["level"], category_id),
        "probs": ordered_probs,
        "fs": fs,
        "duration": duration,
        "ecg": [round(float(x), 4) for x in ecg],
        "riskDetails": risk,
        "features": {
            "hr_bpm": round(hr, 1),
            "hrv_sdnn_ms": round(hrv, 1),
            "rr_cv": round(cv, 3),
            "ectopic_ratio": round(ectopic, 3),
        },
    }


class ECGHandler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/scenarios":
            self.send_json({"scenarios": SCENARIO_CACHE})
            return
        super().do_GET()

    def send_json(self, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    print("Preparing ECG scenario API payloads...", flush=True)
    for key in SCENARIOS:
        SCENARIO_CACHE[key] = scenario_payload(key)
        print(f"  loaded {key}: {SCENARIO_CACHE[key]['diagnosis']}", flush=True)

    server = ThreadingHTTPServer(("localhost", 5173), ECGHandler)
    print("AG2 ECG app running at http://localhost:5173/index.html", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
