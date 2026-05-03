"""
validate_features.py
====================
Sanity-check our Pan-Tompkins R-peak detection against PhysioNet's
cardiologist-annotated ground truth.

Each .npz scenario contains:
    ann_samples : ground-truth R-peak positions (annotated by clinicians)
    ann_symbols : per-beat label ('N', 'V', 'L', 'R', '+', etc.)

We:
  1. Run Pan-Tompkins on the ECG.
  2. Match each detected peak to the nearest GT peak within ±50 ms.
  3. Report sensitivity, PPV, and mean absolute error.

Notes:
  - vfdb #418 has very few beat annotations because VF is, by definition,
    not a series of identifiable beats. Low scores there are EXPECTED and
    are themselves a useful detection signal (VF -> Pan-Tompkins fails ->
    classifier sees that as a positive VF indicator).
  - '+' annotations are rhythm-change markers, not beats. We filter them.
  - Severe arrhythmia records (mit207) include LBBB/RBBB beats with very
    different morphology; lower scores there are clinically expected.
"""

import sys
from pathlib import Path
import numpy as np

# Make algorithms/ importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from algorithms.heart_rate import pan_tompkins


SCENARIOS_DIR = ROOT / "data" / "scenarios"

SCENARIOS = [
    "mit100_normal.npz",
    "mit208_pvc.npz",
    "mit207_severe.npz",
    "vf418_arrest.npz",
]

# Match tolerance: a detected peak counts as a true positive if it lands
# within ±50 ms of any ground-truth annotation. This is the AAMI standard.
MATCH_TOLERANCE_MS = 50


def filter_beat_annotations(ann_samples, ann_symbols):
    """Keep only true beat annotations; drop '+' (rhythm marker) and similar."""
    # Standard MIT-BIH beat symbols (any uppercase letter is a beat)
    beat_mask = np.array([
        s.isalpha() and s.isupper() and s != "Q"  # Q = unclassifiable
        for s in ann_symbols
    ])
    return ann_samples[beat_mask], ann_symbols[beat_mask]


def match_peaks(detected, ground_truth, fs, tolerance_ms=50):
    """
    For each detected peak, find the closest GT peak within tolerance.
    Returns (n_matched, mean_abs_error_ms).

    Greedy matching: each GT peak can only be claimed once.
    """
    if len(detected) == 0 or len(ground_truth) == 0:
        return 0, float("nan")

    tol_samples = int(tolerance_ms / 1000.0 * fs)
    gt_used = np.zeros(len(ground_truth), dtype=bool)
    errors_samples = []

    for d in detected:
        # Find closest unused GT peak
        candidates = np.where(~gt_used)[0]
        if len(candidates) == 0:
            break
        gt_unused = ground_truth[candidates]
        diffs = np.abs(gt_unused - d)
        best_idx_in_candidates = int(np.argmin(diffs))
        best_diff = int(diffs[best_idx_in_candidates])
        if best_diff <= tol_samples:
            errors_samples.append(best_diff)
            gt_used[candidates[best_idx_in_candidates]] = True

    if not errors_samples:
        return 0, float("nan")

    n_matched = len(errors_samples)
    mean_err_ms = float(np.mean(errors_samples)) / fs * 1000.0
    return n_matched, mean_err_ms


def validate_one(npz_path: Path):
    data = np.load(npz_path, allow_pickle=True)
    ecg = data["ecg"].astype(np.float64)
    fs = int(data["fs"])
    diagnosis = str(data["diagnosis"])

    # Filter to true beat annotations
    gt_samples_all = data["ann_samples"]
    gt_symbols_all = data["ann_symbols"]
    gt_samples, gt_symbols = filter_beat_annotations(gt_samples_all,
                                                     gt_symbols_all)

    # Run Pan-Tompkins
    pt = pan_tompkins(ecg, fs)
    detected = pt["r_peaks"]

    # Match
    n_matched, mean_err_ms = match_peaks(detected, gt_samples, fs,
                                         MATCH_TOLERANCE_MS)
    n_gt = len(gt_samples)
    n_pt = len(detected)

    sensitivity = n_matched / n_gt * 100.0 if n_gt > 0 else float("nan")
    ppv         = n_matched / n_pt * 100.0 if n_pt > 0 else float("nan")

    # Verdict
    if n_gt == 0:
        verdict = "—  (no GT beats; expected for VF)"
    elif sensitivity >= 90 and ppv >= 90:
        verdict = "✓  excellent"
    elif sensitivity >= 75 and ppv >= 75:
        verdict = "~  acceptable"
    else:
        verdict = "✗  poor — investigate"

    return {
        "name":        npz_path.name,
        "diagnosis":   diagnosis,
        "fs":          fs,
        "n_gt":        n_gt,
        "n_pt":        n_pt,
        "n_matched":   n_matched,
        "sensitivity": sensitivity,
        "ppv":         ppv,
        "mean_err_ms": mean_err_ms,
        "hr_bpm":      pt["heart_rate_bpm"],
        "hrv_ms":      pt["hrv_sdnn_ms"],
        "verdict":     verdict,
        "gt_symbols_summary": dict(zip(*np.unique(gt_symbols,
                                                  return_counts=True))) if n_gt else {},
    }


def main():
    print("=" * 80)
    print("  Pan-Tompkins R-peak detection vs PhysioNet ground truth")
    print(f"  Match tolerance: ±{MATCH_TOLERANCE_MS} ms")
    print("=" * 80)
    print()

    for fname in SCENARIOS:
        path = SCENARIOS_DIR / fname
        if not path.exists():
            print(f"  [SKIP] {fname} not found")
            continue

        r = validate_one(path)

        sens_str = f"{r['sensitivity']:5.1f}%" if not np.isnan(r['sensitivity']) else "  N/A"
        ppv_str  = f"{r['ppv']:5.1f}%"         if not np.isnan(r['ppv'])         else "  N/A"
        err_str  = f"{r['mean_err_ms']:5.1f}ms" if not np.isnan(r['mean_err_ms']) else "  N/A"
        hr_str   = f"{r['hr_bpm']:5.1f}"        if not np.isnan(r['hr_bpm'])     else "  N/A"
        hrv_str  = f"{r['hrv_ms']:5.1f}"        if not np.isnan(r['hrv_ms'])     else "  N/A"

        print(f"  {r['name']:24s}  fs={r['fs']:>3d}Hz  GT label: {r['diagnosis']}")
        print(f"    Beats — GT: {r['n_gt']:>3d}   Pan-Tompkins: {r['n_pt']:>3d}   matched: {r['n_matched']:>3d}")
        print(f"    Sensitivity: {sens_str}   PPV: {ppv_str}   Mean error: {err_str}")
        print(f"    Computed HR: {hr_str} bpm   HRV: {hrv_str} ms")
        if r['gt_symbols_summary']:
            sym_str = ", ".join(f"{k}={v}" for k, v in r['gt_symbols_summary'].items())
            print(f"    GT beat types: {sym_str}")
        print(f"    Verdict: {r['verdict']}")
        print()


if __name__ == "__main__":
    main()
