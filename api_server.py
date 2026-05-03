from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
import json
import re

import numpy as np


ROOT = Path(__file__).resolve().parent
SCENARIOS_DIR = ROOT / "data" / "scenarios"

SCENARIOS = {
    "normal": {
        "file": "mit100_normal.npz",
        "title": "MIT100 normal",
        "rhythm": "Normal Sinus Rhythm",
        "status": "Stable",
        "risk": "08",
        "summary": "30 秒 Lead II 实时预览，R-R 间期稳定，形态清晰。",
        "riskCopy": "Normal morphology, consistent R-R intervals.",
        "color": "#1d8c5b",
        "pattern": "normal",
    },
    "lbbb": {
        "file": "mit207_severe.npz",
        "title": "MIT207 severe LBBB",
        "rhythm": "Severe arrhythmia with LBBB",
        "status": "Review",
        "risk": "71",
        "summary": "宽 QRS 形态明显，多个 LBBB 与室性事件混合出现。",
        "riskCopy": "Wide QRS morphology with irregular annotation clusters.",
        "color": "#2878c8",
        "pattern": "lbbb",
    },
    "pvc": {
        "file": "mit208_pvc.npz",
        "title": "MIT208 PVC / short VT",
        "rhythm": "Frequent PVCs with short VT",
        "status": "Elevated",
        "risk": "84",
        "summary": "PVC 标注密集，短阵 VT 片段需要快速复核。",
        "riskCopy": "Frequent ventricular annotations and short tachycardia run.",
        "color": "#d94b4b",
        "pattern": "pvc",
    },
    "vf": {
        "file": "vf418_arrest.npz",
        "title": "VF418 ventricular fibrillation",
        "rhythm": "Ventricular Fibrillation",
        "status": "Critical",
        "risk": "96",
        "summary": "波形呈无序震荡，缺少稳定 R-R 间期，应作为最高优先级查看。",
        "riskCopy": "Disorganized waveform with loss of beat-to-beat structure.",
        "color": "#7d4fc7",
        "pattern": "vf",
    },
}


def scenario_payload(scenario_id, include_ecg=False):
    meta = SCENARIOS[scenario_id]
    path = SCENARIOS_DIR / meta["file"]
    data = np.load(path, allow_pickle=True)
    ecg = data["ecg"].astype(float)
    fs = int(data["fs"])
    ann_samples = data["ann_samples"].astype(int)
    ann_symbols = data["ann_symbols"].astype(str)
    ann_aux = data["ann_aux"].astype(str) if "ann_aux" in data.files else np.array([""] * len(ann_samples))

    annotations = [
        {
            "sample": int(sample),
            "time": round(int(sample) / fs, 3),
            "symbol": str(symbol),
            "aux": str(aux),
        }
        for sample, symbol, aux in zip(ann_samples, ann_symbols, ann_aux)
    ]
    symbols, counts = np.unique(ann_symbols, return_counts=True) if len(ann_symbols) else ([], [])
    symbol_counts = {str(symbol): int(count) for symbol, count in zip(symbols, counts)}

    payload = {
        "id": scenario_id,
        "title": meta["title"],
        "rhythm": meta["rhythm"],
        "status": meta["status"],
        "risk": meta["risk"],
        "summary": meta["summary"],
        "riskCopy": meta["riskCopy"],
        "color": meta["color"],
        "pattern": meta["pattern"],
        "fs": fs,
        "rate": f"{fs} Hz",
        "duration_s": int(data["duration_s"]),
        "source": str(data["source"]),
        "diagnosis": str(data["diagnosis"]),
        "sample_count": int(len(ecg)),
        "heartRate": estimate_heart_rate(annotations, fs),
        "events": str(len(annotations)),
        "eventType": describe_event_type(symbol_counts),
        "annotations": annotations,
        "symbol_counts": symbol_counts,
        "stats": {
            "min": float(np.min(ecg)),
            "max": float(np.max(ecg)),
            "mean": float(np.mean(ecg)),
        },
    }
    if include_ecg:
        payload["ecg"] = np.round(ecg, 5).tolist()
    return payload


def estimate_heart_rate(annotations, fs):
    beat_times = [
        ann["sample"] / fs
        for ann in annotations
        if ann["symbol"] not in {"+", "~", "|"}
    ]
    if len(beat_times) < 2:
        return "--"
    duration = beat_times[-1] - beat_times[0]
    if duration <= 0:
        return "--"
    return str(round((len(beat_times) - 1) * 60 / duration))


def describe_event_type(symbol_counts):
    if not symbol_counts:
        return "No annotations"
    top = sorted(symbol_counts.items(), key=lambda item: item[1], reverse=True)[:3]
    return " / ".join(f"{symbol} x{count}" for symbol, count in top)


class ECGHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_cors_headers()
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/health":
            return self.send_json({"ok": True, "service": "ECAG2 API"})
        if path == "/api/scenarios":
            return self.send_json({
                "scenarios": [scenario_payload(scenario_id) for scenario_id in SCENARIOS]
            })
        match = re.fullmatch(r"/api/scenarios/([a-z0-9_-]+)", path)
        if match and match.group(1) in SCENARIOS:
            return self.send_json(scenario_payload(match.group(1), include_ecg=True))
        self.send_json({"error": "Not found"}, status=404)

    def send_json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 8000), ECGHandler)
    print("ECAG2 API running at http://127.0.0.1:8000")
    print("Available endpoints: /api/health, /api/scenarios, /api/scenarios/{id}")
    server.serve_forever()


if __name__ == "__main__":
    main()
