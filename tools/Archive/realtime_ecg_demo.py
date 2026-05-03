"""
realtime_ecg_demo.py
====================
Real-time ECG monitor demo for the AG2 Cardiac project.

Plays back PhysioNet records (MIT-BIH Arrhythmia + Malignant Ventricular
Arrhythmia) at their native sampling rate, with a scrolling 10-second
ECG window, classification probability bars, live cardiac metrics, and
an AI diagnosis panel.

This file ONLY handles real-time playback and visualization. All DSP,
classification, and AG2 agent integration are placeholders here and
will be wired up in subsequent steps.

Style note: structurally modeled after our earlier BSL realtime demo
(matplotlib FuncAnimation + np.roll-based scrolling buffer + per-frame
panel updates).

Controls:
    [1-4]   Switch scenario (Normal / PVCs / Severe / VF)
    [SPACE] Pause / Resume
    [Q]     Quit
"""

from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation


# ============================================================
# Paths & Scenario configuration
# ============================================================
ROOT       = Path(__file__).resolve().parent.parent
SCENARIOS_DIR = ROOT / "data" / "scenarios"

# Order matters: keys 1-4 map to this list, and so do the
# four classification bars. Keep tightly aligned.
SCENARIO_FILES = [
    ("mit100_normal.npz",  "Normal Sinus Rhythm"),
    ("mit208_pvc.npz",     "PVCs / Short VT"),
    ("mit207_severe.npz",  "Severe Arrhythmia (BBB)"),
    ("vf418_arrest.npz",   "Ventricular Fibrillation"),
]

CLASS_NAMES = [name for _, name in SCENARIO_FILES]
N_CLASSES   = len(CLASS_NAMES)


# ============================================================
# Demo class
# ============================================================
class ECGRealtimeDemo:
    def __init__(self, scenarios_dir: Path):
        # ---- Load all scenarios ----
        print("Loading PhysioNet scenarios...")
        self.scenarios = {}  # name -> dict(ecg, fs, source, diagnosis, ...)
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

        # ---- Display parameters ----
        self.display_duration_s = 10.0   # show last 10 seconds
        self.target_fps         = 20     # animation frame rate
        self.frame_interval_ms  = int(1000 / self.target_fps)
        self.playback_speed     = 1.0    # 1.0 = native real-time

        # ---- State ----
        # Start on scenario 1 (Normal) for a calm opening
        self.current_name   = CLASS_NAMES[0]
        self.playback_pos   = 0          # sample index into current scenario
        self.paused         = False
        self.signal_buffer  = None       # allocated when scenario changes
        self.display_samples = 0
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
        print("    [SPACE] pause / resume")
        print("    [Q] quit")
        print("=" * 64 + "\n")

    # --------------------------------------------------------
    # Scenario management
    # --------------------------------------------------------
    def _switch_scenario(self, name: str, reset: bool = True):
        """Switch to a new scenario and (re)allocate the display buffer."""
        sc = self.scenarios[name]
        self.current_name    = name
        self.fs              = sc["fs"]
        self.display_samples = int(self.display_duration_s * self.fs)
        self.signal_buffer   = np.zeros(self.display_samples, dtype=np.float64)
        if reset:
            self.playback_pos = 0
        print(f"▶ Scenario: {name}  ({sc['source']})")

    # --------------------------------------------------------
    # Plot setup
    # --------------------------------------------------------
    def setup_plot(self):
        """Build the 4-row matplotlib layout."""
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

        # ---- Panel 1: Scrolling ECG (top, full width) ----
        self.ax_signal = self.fig.add_subplot(gs[0, :])
        self.line_signal, = self.ax_signal.plot([], [], color="#0aa", linewidth=1.0)
        self.ax_signal.set_xlim(0, 1)  # set properly in update()
        self.ax_signal.set_ylim(-2.0, 2.0)
        self.ax_signal.set_xlabel("Time (s)")
        self.ax_signal.set_ylabel("Voltage (mV)")
        self.ax_signal.set_title(
            "Lead ECG — last 10 seconds (PhysioNet replay at native sampling rate)",
            fontweight="bold"
        )
        self.ax_signal.grid(True, alpha=0.3)
        self.ax_signal.axhline(0, color="gray", linewidth=0.5, alpha=0.5)

        # ---- Panel 2 left: Classification probabilities ----
        self.ax_probs = self.fig.add_subplot(gs[1, 0])
        self.bars = self.ax_probs.barh(
            range(N_CLASSES),
            [0.0] * N_CLASSES,
            color="#cccccc",
        )
        self.ax_probs.set_yticks(range(N_CLASSES))
        self.ax_probs.set_yticklabels(CLASS_NAMES)
        self.ax_probs.set_xlim(0, 1.0)
        self.ax_probs.set_xlabel("Probability")
        self.ax_probs.set_title("Classification (placeholder — DSP not connected yet)",
                                fontweight="bold")
        self.ax_probs.grid(True, alpha=0.3, axis="x")
        self.ax_probs.invert_yaxis()  # first class on top

        # ---- Panel 2 right: Live cardiac metrics ----
        self.ax_metrics = self.fig.add_subplot(gs[1, 1])
        self.ax_metrics.axis("off")
        self.ax_metrics.set_title("Live Cardiac Metrics", fontweight="bold")
        self.text_metrics = self.ax_metrics.text(
            0.5, 0.5,
            self._metrics_string(hr=None, hrv=None, r_amp=None),
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

        # ---- Panel 4: AI diagnosis (bottom, full width) ----
        self.ax_diag = self.fig.add_subplot(gs[3, :])
        self.ax_diag.axis("off")
        self.text_diag = self.ax_diag.text(
            0.5, 0.5,
            "🩺 AI Diagnosis: awaiting analysis...   |   Ground truth: —",
            fontsize=13, fontweight="bold",
            verticalalignment="center", horizontalalignment="center",
            bbox=dict(boxstyle="round", facecolor="lightgreen", alpha=0.5),
        )

    # --------------------------------------------------------
    # Helpers
    # --------------------------------------------------------
    @staticmethod
    def _metrics_string(hr, hrv, r_amp):
        """Format the live metrics box. None values render as '—'."""
        def fmt(v, unit, nd=1):
            if v is None:
                return f"{'—':>8s} {unit}"
            return f"{v:>8.{nd}f} {unit}"

        return (
            "Heart Rate     " + fmt(hr,    "bpm",  nd=1) + "\n"
            "HRV (SDNN)     " + fmt(hrv,   "ms",   nd=1) + "\n"
            "R-peak ampl.   " + fmt(r_amp, "mV",   nd=2) + "\n"
            "\n(metrics will populate\n once DSP is connected)"
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
    # Animation update
    # --------------------------------------------------------
    def update(self, frame):
        if self.paused:
            return

        sc       = self.scenarios[self.current_name]
        ecg_full = sc["ecg"]
        fs       = sc["fs"]

        # Advance playback by one frame's worth of samples
        # frame_interval_ms / 1000 * fs * playback_speed
        step = max(1, int(round(self.frame_interval_ms / 1000.0 * fs * self.playback_speed)))

        # Loop back to start when reaching end
        if self.playback_pos + step >= len(ecg_full):
            self.playback_pos = 0

        new_samples = ecg_full[self.playback_pos : self.playback_pos + step]
        self.playback_pos += step

        # --- Update scrolling buffer ---
        # Roll left by `step`, write new samples at the right edge.
        # Same idiom as the BSL demo, sized to current scenario's fs.
        self.signal_buffer = np.roll(self.signal_buffer, -step)
        self.signal_buffer[-step:] = new_samples

        # --- Update Panel 1: ECG waveform ---
        t_axis = np.linspace(0, self.display_duration_s, self.display_samples)
        self.line_signal.set_data(t_axis, self.signal_buffer)
        self.ax_signal.set_xlim(0, self.display_duration_s)

        # Color the trace red during VF scenario (bonus visual cue,
        # NOT a real classification — just helps the demo narrative)
        if self.current_name == "Ventricular Fibrillation":
            self.line_signal.set_color("#c0392b")
        else:
            self.line_signal.set_color("#0aa")

        # --- Update Panel 2 left: Classification probs (placeholder zeros) ---
        # Will be replaced when DSP/agent are wired up.
        for bar, prob in zip(self.bars, [0.0] * N_CLASSES):
            bar.set_width(prob)
            bar.set_color("#cccccc")

        # --- Update Panel 2 right: Metrics (still placeholder) ---
        self.text_metrics.set_text(self._metrics_string(hr=None, hrv=None, r_amp=None))

        # --- Update Panel 3 right: Record info ---
        self.text_record.set_text(self._record_info_string())

        # --- Update Panel 4: AI diagnosis (placeholder) ---
        self.text_diag.set_text(
            "🩺 AI Diagnosis: awaiting analysis...   "
            f"|   Ground truth: {sc['diagnosis']}"
        )

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
            if 0 <= idx < N_CLASSES:
                self._switch_scenario(CLASS_NAMES[idx], reset=True)
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
