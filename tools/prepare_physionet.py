"""
prepare_physionet.py
====================
Download labeled ECG records from PhysioNet and convert them into
.npz scenario files for the AG2 Cardiac multi-agent pipeline.

Outputs four scenarios in data/scenarios/:
    - mit100_normal.npz   (healthy sinus rhythm,           360 Hz)
    - mit208_pvc.npz      (frequent PVCs + short VT runs,  360 Hz)
    - mit207_severe.npz   (severe arrhythmia + LBBB,       360 Hz)
    - vf418_arrest.npz    (ventricular fibrillation onset, 250 Hz)

Each .npz contains:
    ecg               : 1D float64 array, units = mV (raw PhysioNet physical signal)
    fs                : sampling rate in Hz (int)
    duration_s        : window length in seconds (int)
    source            : human-readable provenance string
    ann_samples       : 1D int array, beat annotation positions (sample indices into ecg)
    ann_symbols       : 1D str array, beat annotation symbols (e.g. 'N', 'V', 'A')
    ann_aux           : 1D str array, rhythm annotations (e.g. '(VFIB', '(N')
    diagnosis         : ground-truth label (str), used for AI-vs-truth comparison in demo
"""

import os
import sys
from pathlib import Path

import numpy as np
import wfdb


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT       = Path(__file__).resolve().parent.parent
RAW_DIR    = ROOT / "data" / "raw"
OUT_DIR    = ROOT / "data" / "scenarios"
RAW_DIR.mkdir(parents=True, exist_ok=True)
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Scenario definitions
# ---------------------------------------------------------------------------
# (record_id, physionet_db, start_seconds, duration_seconds, output_filename, diagnosis)
SCENARIOS = [
    # MIT-BIH Arrhythmia: 360 Hz, 30-min recordings
    ("100", "mitdb",   0, 30, "mit100_normal.npz",  "Normal Sinus Rhythm"),
    ("208", "mitdb",  60, 30, "mit208_pvc.npz",     "Frequent PVCs with short VT"),
    ("207", "mitdb", 120, 30, "mit207_severe.npz",  "Severe arrhythmia with LBBB"),
    # vfdb: 250 Hz; VF onset varies per record. We auto-detect onset for #418.
    ("418", "vfdb",  None, 30, "vf418_arrest.npz",   "Ventricular Fibrillation"),
]


def download_record(record_id: str, db: str) -> Path:
    """Download a PhysioNet record into data/raw/<db>/ if not already present."""
    target_dir = RAW_DIR / db
    target_dir.mkdir(parents=True, exist_ok=True)

    # wfdb downloads .hea + .dat + .atr (and sometimes others)
    expected = target_dir / f"{record_id}.hea"
    if expected.exists():
        print(f"  [cache] {db}/{record_id} already downloaded.")
        return target_dir

    print(f"  [download] {db}/{record_id} from PhysioNet...")
    wfdb.dl_database(db, dl_dir=str(target_dir), records=[record_id], annotators="all")
    return target_dir


def find_vf_onset(record_id: str, db: str, raw_dir: Path) -> int:
    """
    Scan rhythm annotations for the first VF episode.
    Returns sample index into the original-fs signal.
    Falls back to sample 0 if no VF found (shouldn't happen for vfdb 418).
    """
    record_path = str(raw_dir / record_id)
    ann = wfdb.rdann(record_path, "atr")
    for i, aux in enumerate(ann.aux_note):
        if aux and "VF" in aux.upper():
            return int(ann.sample[i])
    print(f"  [warn] No VF rhythm annotation found in {record_id}, defaulting to sample 0")
    return 0


def build_scenario(record_id, db, start_s, duration_s, out_name, diagnosis):
    print(f"\n--- Processing {db}/{record_id} -> {out_name} ---")
    raw_dir = download_record(record_id, db)
    record_path = str(raw_dir / record_id)

    # Read header to get sampling rate first
    header = wfdb.rdheader(record_path)
    fs = int(header.fs)
    print(f"  fs = {fs} Hz, total samples = {header.sig_len} ({header.sig_len/fs:.1f} s)")

    # Decide window start
    if start_s is None:  # auto-detect (vfdb VF onset)
        vf_sample = find_vf_onset(record_id, db, raw_dir)
        # Start 10 seconds BEFORE VF onset to capture deterioration arc
        start_sample = max(0, vf_sample - 10 * fs)
        print(f"  VF onset at sample {vf_sample} ({vf_sample/fs:.1f}s); "
              f"window starts {10}s earlier at sample {start_sample}")
    else:
        start_sample = int(start_s * fs)

    end_sample = start_sample + duration_s * fs
    if end_sample > header.sig_len:
        end_sample = header.sig_len
        start_sample = end_sample - duration_s * fs
        print(f"  [adjust] window pushed back to fit record length")

    # Read the windowed signal
    record = wfdb.rdrecord(record_path, sampfrom=start_sample, sampto=end_sample)
    ecg = record.p_signal[:, 0].astype(np.float64)  # MLII or first lead, in mV
    lead_name = record.sig_name[0]
    print(f"  lead = {lead_name}, samples = {len(ecg)}, "
          f"range = [{ecg.min():.2f}, {ecg.max():.2f}] mV")

    # Read annotations (full record), then filter to our window
    ann = wfdb.rdann(record_path, "atr")
    mask = (ann.sample >= start_sample) & (ann.sample < end_sample)
    ann_samples_local = (ann.sample[mask] - start_sample).astype(np.int64)
    ann_symbols = np.array(ann.symbol)[mask]
    ann_aux = np.array([s if s else "" for s in ann.aux_note])[mask]
    print(f"  beat annotations in window: {len(ann_samples_local)}")
    if len(ann_symbols) > 0:
        unique, counts = np.unique(ann_symbols, return_counts=True)
        print(f"  symbols: {dict(zip(unique.tolist(), counts.tolist()))}")

    # Save
    out_path = OUT_DIR / out_name
    np.savez(
        out_path,
        ecg=ecg,
        fs=fs,
        duration_s=duration_s,
        source=f"PhysioNet {db}/{record_id} (lead {lead_name}, samples {start_sample}-{end_sample})",
        ann_samples=ann_samples_local,
        ann_symbols=ann_symbols,
        ann_aux=ann_aux,
        diagnosis=diagnosis,
    )
    print(f"  [saved] {out_path}  ({out_path.stat().st_size / 1024:.1f} KB)")


def main():
    print("=" * 70)
    print("AG2 Cardiac: PhysioNet preprocessing")
    print("=" * 70)
    for sc in SCENARIOS:
        try:
            build_scenario(*sc)
        except Exception as e:
            print(f"  [ERROR] Failed to process {sc[0]}/{sc[1]}: {e}")
            print(f"  Continuing with remaining scenarios...")
            continue

    print("\n" + "=" * 70)
    print("Done. Generated files:")
    print("=" * 70)
    for f in sorted(OUT_DIR.glob("*.npz")):
        data = np.load(f, allow_pickle=True)
        print(f"  {f.name:30s}  fs={int(data['fs']):>3d}Hz  "
              f"dur={int(data['duration_s']):>2d}s  "
              f"diagnosis={str(data['diagnosis'])}")


if __name__ == "__main__":
    main()
