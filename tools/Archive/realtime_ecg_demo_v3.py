"""
realtime_ecg_demo.py
====================
Real-time ECG monitor demo for the AG2 Cardiac project.

Plays back PhysioNet records (MIT-BIH Arrhythmia + Malignant Ventricular
Arrhythmia) at their native sampling rate, with a scrolling 2-second ECG
window, R-peak overlay, classification probability bars, live cardiac
metrics with EMA smoothing, and an AI diagnosis panel.

Pipeline (per scenario switch + per analysis tick):
    raw ecg window  ->  Pan-Tompkins (heart_rate.pan_tompkins)
                    ->  HR / HRV / R-peaks / RR intervals
                    ->  rhythm CV + ectopic ratio
                    ->  hard-rule classifier (classifier.classify)
                    ->  panel updates

Two-tier update frequency:
    0.5 s : full DSP + classification (low latency for VF detection)
    2.0 s : displayed metric numbers (EMA-smoothed, stable for the eye)

Controls:
    [1-4]   Switch scenario (Normal / PVCs / Severe / VF)
    [SPACE] Pause / Resume
    [Q]     Quit
"""

import sys
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

# Allow `from algorithms import ...` when running from project root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from algorithms.heart_rate import pan_tompkins
from algorithms.classifier import classify, KNOWLEDGE_TABLE


# ============================================================
# Paths & Scenario configuration
# ============================================================
SCENARIOS_DIR = ROOT / "data" / "scenarios"

# Order matters: keys 1-4 map to this list.
SCENARIO_FILES = [
    ("mit100_normal.npz",  "Normal Sinus Rhythm"),
    ("mit208_pvc.npz",     "PVCs / Short VT"),
    ("mit207_severe.npz",  "Severe Arrhythmia (BBB)"),
    ("vf418_arrest.npz",   "Ventricular Fibrillation"),
]

# Class display order follows KNOWLEDGE_TABLE (most-critical first)
CLASS_ORDER  = [entry["id"]    for entry in KNOWLEDGE_TABLE]
CLASS_LABELS = [entry["label"] for entry in KNOWLEDGE_TABLE]
CLASS_COLORS = [entry["color"] for entry in KNOWLEDGE_TABLE]
N_CLASSES    = len(CLASS_ORDER)


# ============================================================
# Demo class
# ============================================================
class ECGRealtimeDemo:
    def __init__(self, scenarios_dir: Path):
        # ---- Load all scenarios ----
        print("Loading PhysioNet scenarios...")
        self.scenarios = {}
        for fname, display_name in SCENARIO_FILES:
            path = scenarios_dir / fname
            if not path.exists():
                raise FileNotFoundError(
                    f"Scenario file not found: {path}\n"
                    f"Run `python tools/prepare_physionet.py` first."
                )
            data = np.load(path, allow_pickle=True)
            self.scenarios[display_name] = {
                "ecg":         data["ecg"].astype(np.float64),
                "fs":          int(data["fs"]),
                "duration_s":  int(data["duration_s"]),
                "source":      str(data["source"]),
                "diagnosis":   str(data["diagnosis"]),
                "ann_samples": data["ann_samples"],
                "ann_symbols": data["ann_symbols"],
                "filename":    fname,
            }
            print(f"  ✓ {display_name:30s}  fs={int(data['fs']):>3d}Hz  "
                  f"len={len(data['ecg'])} samples  ({fname})")

        # ---- Display + analysis parameters ----
        self.display_duration_s   = 2.0    # rolling waveform window
        self.feature_duration_s   = 5.0    # window fed to Pan-Tompkins
        self.target_fps           = 20
        self.frame_interval_ms    = int(1000 / self.target_fps)
        self.playback_speed       = 1.0

        # Two-tier update cadence
        self.classify_interval_s  = 0.5
        self.metrics_display_s    = 2.0
        self.frames_per_classify  = max(1, int(self.classify_interval_s
                                               * self.target_fps))
        self.frames_per_metrics   = max(1, int(self.metrics_display_s
                                               * self.target_fps))

        # EMA smoothing factor (0..1). 0.3 = "30% new, 70% history"
        self.ema_alpha = 0.3

        # ---- State ----
        self.current_name    = "Normal Sinus Rhythm"
        self.playback_pos    = 0
        self.paused          = False
        self.signal_buffer   = None
        self.display_samples = 0
        self.feature_samples = 0
        self.frame_count     = 0

        self._reset_state_for_scenario()
        self._switch_scenario(self.current_name, reset=True)

        # ---- Setup plot ----
        self.setup_plot()

        # Banner
        print("\n" + "=" * 64)
        print("  AG2 Cardiac — Real-time ECG Monitor")
        print("=" * 64)
        print("  Controls:")
        print("    [1] Normal sinus rhythm")
        print("    [2] PVCs / short VT")
        print("    [3] Severe arrhythmia (BBB)")
        print("    [4] Ventricular fibrillation")
        print("    [SPACE] pause / resume   [Q] quit")
        print("=" * 64 + "\n")

    # --------------------------------------------------------
    # State helpers
    # --------------------------------------------------------
    def _reset_state_for_scenario(self):
        """Wipe smoothed metrics + classification when switching scenario."""
        self.smoothed_hr     = None
        self.smoothed_hrv    = None
        self.smoothed_r_amp  = None
        self.last_classification = None
        self.last_r_peaks_global = np.array([], dtype=int)
        self.displayed_probs = {cid: 0.0 for cid in CLASS_ORDER}

    def _ema(self, prev, new):
        """Exponential moving average with safe init."""
        if new is None or (isinstance(new, float) and np.isnan(new)):
            return prev
        if prev is None:
            return float(new)
        return self.ema_alpha * float(new) + (1 - self.ema_alpha) * prev

    # --------------------------------------------------------
    # Scenario management
    # --------------------------------------------------------
    def _switch_scenario(self, name: str, reset: bool = True):
        sc = self.scenarios[name]
        self.current_name    = name
        self.fs              = sc["fs"]
        self.display_samples = int(self.display_duration_s * self.fs)
        self.feature_samples = int(self.feature_duration_s * self.fs)
        self.signal_buffer   = np.zeros(self.display_samples, dtype=np.float64)
        if reset:
            self.playback_pos = 0
            self._reset_state_for_scenario()
        print(f"▶ Scenario: {name}  ({sc['source']})")

    # --------------------------------------------------------
    # Plot setup
    # --------------------------------------------------------
    def setup_plot(self):
        self.fig = plt.figure(figsize=(14, 10))
        self.fig.suptitle(
            "AG2 Cardiac — Real-time ECG Monitor",
            fontsize=16, fontweight="bold"
        )

        gs = self.fig.add_gridspec(
            4, 2,
            height_ratios=[2.2, 1.5, 0.7, 0.5],
            width_ratios=[2, 1],
            hspace=0.45, wspace=0.3,
        )

        # ---- Panel 1: Scrolling ECG ----
        self.ax_signal = self.fig.add_subplot(gs[0, :])
        self.line_signal, = self.ax_signal.plot([], [], color="#0aa",
                                                linewidth=1.0)
        # R-peak overlay (red dots)
        self.scatter_rpeaks = self.ax_signal.scatter(
            [], [], s=40, c="#e74c3c", marker="o",
            edgecolors="white", linewidths=0.8, zorder=5,
        )
        self.ax_signal.set_xlim(0, self.display_duration_s)
        self.ax_signal.set_ylim(-2.0, 2.0)
        self.ax_signal.set_xlabel("Time (s)")
        self.ax_signal.set_ylabel("Voltage (mV)")
        self.ax_signal.set_title(
            "Lead ECG — last 2 seconds (PhysioNet replay at native sampling rate)",
            fontweight="bold"
        )
        self.ax_signal.grid(True, alpha=0.3)
        self.ax_signal.axhline(0, color="gray", linewidth=0.5, alpha=0.5)

        # ---- Panel 2 left: Classification probabilities ----
        self.ax_probs = self.fig.add_subplot(gs[1, 0])
        self.bars = self.ax_probs.barh(
            range(N_CLASSES),
            [0.0] * N_CLASSES,
            color=["#cccccc"] * N_CLASSES,
        )
        self.ax_probs.set_yticks(range(N_CLASSES))
        self.ax_probs.set_yticklabels(CLASS_LABELS)
        self.ax_probs.set_xlim(0, 1.0)
        self.ax_probs.set_xlabel("Probability")
        self.ax_probs.set_title("Cardiac Rhythm Classification",
                                fontweight="bold")
        self.ax_probs.grid(True, alpha=0.3, axis="x")
        self.ax_probs.invert_yaxis()  # most-critical class on top

        # ---- Panel 2 right: Live cardiac metrics ----
        self.ax_metrics = self.fig.add_subplot(gs[1, 1])
        self.ax_metrics.axis("off")
        self.ax_metrics.set_title("Live Cardiac Metrics", fontweight="bold")
        self.text_metrics = self.ax_metrics.text(
            0.5, 0.5,
            self._metrics_string(None, None, None),
            fontsize=12,
            family="monospace",
            verticalalignment="center",
            horizontalalignment="center",
            bbox=dict(boxstyle="round", facecolor="#eef", alpha=0.6),
        )

        # ---- Panel 3 left: Controls ----
        self.ax_info = self.fig.add_subplot(gs[2, 0])
        self.ax_info.axis("off")
        info_text = (
            "CONTROLS\n"
            "[1] Normal sinus rhythm    [2] PVCs / short VT\n"
            "[3] Severe arrhythmia      [4] Ventricular fibrillation\n"
            "[SPACE] pause/resume       [Q] quit"
        )
        self.ax_info.text(
            0.02, 0.5, info_text, fontsize=10,
            verticalalignment="center", family="monospace",
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.4),
        )

        # ---- Panel 3 right: Record info ----
        self.ax_record = self.fig.add_subplot(gs[2, 1])
        self.ax_record.axis("off")
        self.text_record = self.ax_record.text(
            0.5, 0.5, "",
            fontsize=10, family="monospace",
            verticalalignment="center", horizontalalignment="center",
            bbox=dict(boxstyle="round", facecolor="lightblue", alpha=0.5),
        )

        # ---- Panel 4: AI diagnosis ----
        self.ax_diag = self.fig.add_subplot(gs[3, :])
        self.ax_diag.axis("off")
        self.text_diag = self.ax_diag.text(
            0.5, 0.5,
            "🩺 AI Diagnosis: awaiting analysis...   |   Ground truth: —",
            fontsize=12, fontweight="bold",
            verticalalignment="center", horizontalalignment="center",
            bbox=dict(boxstyle="round", facecolor="lightgreen", alpha=0.5),
            wrap=True,
        )

    # --------------------------------------------------------
    # Helpers
    # --------------------------------------------------------
    @staticmethod
    def _metrics_string(hr, hrv, r_amp):
        def fmt(v, unit, nd=1):
            if v is None or (isinstance(v, float) and np.isnan(v)):
                return f"{'—':>8s} {unit}"
            return f"{v:>8.{nd}f} {unit}"

        return (
            "Heart Rate     " + fmt(hr,    "bpm",  nd=1) + "\n"
            "HRV (SDNN)     " + fmt(hrv,   "ms",   nd=1) + "\n"
            "R-peak ampl.   " + fmt(r_amp, "mV",   nd=2) + "\n"
            "\n(EMA-smoothed,\n updates every 2 s)"
        )

    def _record_info_string(self):
        sc = self.scenarios[self.current_name]
        pos_s   = self.playback_pos / sc["fs"]
        total_s = sc["duration_s"]
        return (
            f"Source\n"
            f"{sc['source']}\n"
            f"\n"
            f"fs        : {sc['fs']} Hz\n"
            f"window    : {sc['duration_s']} s\n"
            f"position  : {pos_s:5.1f} / {total_s} s\n"
            f"GT label  : {sc['diagnosis']}"
        )

    # --------------------------------------------------------
    # DSP + classification (called every 0.5 s)
    # --------------------------------------------------------
    def _run_dsp_and_classify(self):
        """
        Run Pan-Tompkins on the most recent feature window of the full record,
        compute rhythm CV + ectopic ratio, classify, and update internal state.
        """
        sc = self.scenarios[self.current_name]
        ecg_full = sc["ecg"]
        fs       = sc["fs"]

        end   = self.playback_pos
        start = max(0, end - self.feature_samples)
        feature_window = ecg_full[start:end]

        if len(feature_window) < int(0.5 * fs):
            return  # not enough data yet

        try:
            pt = pan_tompkins(feature_window, fs)
        except Exception as e:
            print(f"[DSP error] {type(e).__name__}: {e}")
            return

        r_peaks_local  = pt["r_peaks"]
        r_peaks_global = r_peaks_local + start
        rr_s = pt["rr_intervals_s"]
        hr   = pt["heart_rate_bpm"]
        hrv  = pt["hrv_sdnn_ms"]

        # Rhythm CV + ectopic ratio (inline, mirrors risk.py logic)
        if len(rr_s) >= 2:
            rr_cv = float(np.std(rr_s) / np.mean(rr_s))
        else:
            rr_cv = 0.0

        if len(rr_s) >= 3:
            median_rr = float(np.median(rr_s))
            deviations = np.abs(rr_s - median_rr) / median_rr
            ectopic_ratio = float(np.sum(deviations > 0.20) / len(rr_s))
        else:
            ectopic_ratio = 0.0

        # R-peak amplitude in raw signal
        if len(r_peaks_local) > 0:
            r_amp = float(np.mean(np.abs(feature_window[r_peaks_local])))
        else:
            r_amp = float("nan")

        classification = classify(hr, hrv, rr_cv, ectopic_ratio)

        self.last_classification = classification
        self.last_r_peaks_global = r_peaks_global

        # EMA on probability vector (per class)
        target_probs = classification["probabilities"]
        for cid in CLASS_ORDER:
            self.displayed_probs[cid] = (
                self.ema_alpha * target_probs[cid]
                + (1 - self.ema_alpha) * self.displayed_probs[cid]
            )

        # EMA on metric numbers
        self.smoothed_hr    = self._ema(self.smoothed_hr,    hr)
        self.smoothed_hrv   = self._ema(self.smoothed_hrv,   hrv)
        self.smoothed_r_amp = self._ema(self.smoothed_r_amp, r_amp)

    # --------------------------------------------------------
    # Animation update
    # --------------------------------------------------------
    def update(self, frame):
        if self.paused:
            return

        sc       = self.scenarios[self.current_name]
        ecg_full = sc["ecg"]
        fs       = sc["fs"]

        step = max(1, int(round(self.frame_interval_ms / 1000.0
                                * fs * self.playback_speed)))

        if self.playback_pos + step >= len(ecg_full):
            self.playback_pos = 0
            self._reset_state_for_scenario()

        new_samples = ecg_full[self.playback_pos:self.playback_pos + step]
        self.playback_pos += step

        # Scrolling buffer
        self.signal_buffer = np.roll(self.signal_buffer, -step)
        self.signal_buffer[-step:] = new_samples

        # Panel 1: ECG waveform
        t_axis = np.linspace(0, self.display_duration_s, self.display_samples)
        self.line_signal.set_data(t_axis, self.signal_buffer)

        # Trace color: red when classifier says VF
        if (self.last_classification is not None
                and self.last_classification["category_id"] == "vf_arrest"):
            self.line_signal.set_color("#c0392b")
        else:
            self.line_signal.set_color("#0aa")

        # R-peak overlay: convert global indices into the visible 2 s window
        if len(self.last_r_peaks_global) > 0:
            seconds_ago = (self.playback_pos - self.last_r_peaks_global) / fs
            mask = (seconds_ago >= 0) & (seconds_ago < self.display_duration_s)
            visible = self.last_r_peaks_global[mask]
            if len(visible) > 0:
                x_pos = self.display_duration_s - (
                    (self.playback_pos - visible) / fs)
                y_pos = ecg_full[visible]
                self.scatter_rpeaks.set_offsets(np.c_[x_pos, y_pos])
            else:
                self.scatter_rpeaks.set_offsets(np.empty((0, 2)))
        else:
            self.scatter_rpeaks.set_offsets(np.empty((0, 2)))

        # DSP + classify every N frames
        if self.frame_count % self.frames_per_classify == 0:
            self._run_dsp_and_classify()

        # Probability bars: every frame (cheap, smooth)
        for i, cid in enumerate(CLASS_ORDER):
            self.bars[i].set_width(self.displayed_probs[cid])
            if self.displayed_probs[cid] > 0.5:
                self.bars[i].set_color(CLASS_COLORS[i])
            else:
                self.bars[i].set_color("#cccccc")

        # Metrics panel: every 2 s
        if self.frame_count % self.frames_per_metrics == 0:
            self.text_metrics.set_text(
                self._metrics_string(self.smoothed_hr,
                                     self.smoothed_hrv,
                                     self.smoothed_r_amp))

        # Record info: every frame (cheap text)
        self.text_record.set_text(self._record_info_string())

        # AI diagnosis: every classify tick
        if (self.frame_count % self.frames_per_classify == 0
                and self.last_classification is not None):
            cl = self.last_classification
            ai_label = cl["category_label"]
            gt_label = sc["diagnosis"]
            # Loose matching: first content word of AI label appears in GT label
            ai_first = ai_label.lower().split()[0]
            match = "✓ MATCH" if ai_first in gt_label.lower() else "≈"
            expl = cl["explanation"]["text"].split(".")[0].strip()
            if len(expl) > 140:
                expl = expl[:140] + "..."
            self.text_diag.set_text(
                f"🩺 AI Diagnosis: {ai_label}   |   "
                f"Ground truth: {gt_label}   [{match}]\n"
                f"{expl}."
            )

        self.frame_count += 1

    # --------------------------------------------------------
    # Keyboard handling
    # --------------------------------------------------------
    def on_key(self, event):
        if event.key == "q":
            print("Bye.")
            plt.close(self.fig)
            return

        if event.key == " ":
            self.paused = not self.paused
            print("⏸ Paused" if self.paused else "▶ Resumed")
            return

        if event.key in "1234":
            idx = int(event.key) - 1
            scenario_names = [name for _, name in SCENARIO_FILES]
            if 0 <= idx < len(scenario_names):
                self._switch_scenario(scenario_names[idx], reset=True)
            return

    # --------------------------------------------------------
    # Run
    # --------------------------------------------------------
    def run(self):
        self.fig.canvas.mpl_connect("key_press_event", self.on_key)
        self.anim = FuncAnimation(
            self.fig,
            self.update,
            interval=self.frame_interval_ms,
            blit=False,
            cache_frame_data=False,
        )
        plt.tight_layout(rect=[0, 0, 1, 0.96])
        plt.show()


# ============================================================
# Main
# ============================================================
def main():
    if not SCENARIOS_DIR.exists():
        print(f"ERROR: scenarios directory not found: {SCENARIOS_DIR}")
        print("Run `python tools/prepare_physionet.py` first.")
        return

    demo = ECGRealtimeDemo(SCENARIOS_DIR)
    demo.run()


if __name__ == "__main__":
    main()
