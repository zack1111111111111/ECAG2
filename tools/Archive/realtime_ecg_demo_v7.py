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
import threading
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

# Allow `from algorithms import ...` and `from agents import ...`
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from algorithms.heart_rate import pan_tompkins
from algorithms.classifier import classify, KNOWLEDGE_TABLE
from agents.cardiac_team import run_cardiac_team


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

        # ---- Agent team state (must exist before _reset_state_for_scenario) ----
        self.agent_thread       = None
        self.agent_running      = False
        self.last_agent_result  = None
        self.agent_status_text  = "Press [A] for AI cardiac team consultation"

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
        print("    [A] AI cardiac team consultation (multi-agent)")
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
        # Also clear any stale agent result so Panel 4 returns to feature
        # summary mode for the new scenario
        self.last_agent_result = None

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
            hspace=0.65, wspace=0.3,
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

        # ---- Panel 2 left: Classification block ----
        # Split into two sub-axes:
        #   top    : banner showing agent diagnosis (or hint to press A)
        #   bottom : probability bars
        gs_left = gs[1, 0].subgridspec(2, 1, height_ratios=[0.30, 1.0],
                                       hspace=0.55)

        # ---- Banner (top) ----
        self.ax_banner = self.fig.add_subplot(gs_left[0])
        self.ax_banner.axis("off")
        self.text_banner = self.ax_banner.text(
            0.5, 0.5,
            "Press [A] for AI team diagnosis",
            fontsize=11, fontweight="bold",
            verticalalignment="center", horizontalalignment="center",
            bbox=dict(boxstyle="round,pad=0.4",
                      facecolor="#dddddd", edgecolor="#888888", alpha=0.8),
            transform=self.ax_banner.transAxes,
        )

        # ---- Probability bars (bottom) ----
        self.ax_probs = self.fig.add_subplot(gs_left[1])
        self.bars = self.ax_probs.barh(
            range(N_CLASSES),
            [0.0] * N_CLASSES,
            color=["#cccccc"] * N_CLASSES,
        )
        self.ax_probs.set_yticks(range(N_CLASSES))
        self.ax_probs.set_yticklabels(CLASS_LABELS)
        self.ax_probs.set_xlim(0, 1.0)
        self.ax_probs.set_xlabel("Probability")
        # Title text will be updated dynamically with ground truth
        self.ax_probs.set_title(
            "Cardiac Rhythm Classification",
            fontweight="bold"
        )
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
            "[A] AI cardiac team consultation (multi-agent)\n"
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

        # ---- Panel 4: Feature summary (preliminary, before agent diagnosis) ----
        self.ax_diag = self.fig.add_subplot(gs[3, :])
        self.ax_diag.axis("off")
        self.text_diag = self.ax_diag.text(
            0.5, 0.5,
            "📊 Feature Summary: awaiting analysis...   |   Ground truth: —",
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
    # Banner above probability bars
    # --------------------------------------------------------
    def _update_banner(self, sc):
        """
        Update the banner above the probability bars based on current
        agent state. Three modes:
          - idle      : grey hint text "Press [A] for AI team diagnosis"
          - running   : amber text "🤖 Cardiac team consulting..."
          - completed : colored banner with agent's final diagnosis
        """
        if self.agent_running:
            self.text_banner.set_text("🤖 Cardiac team consulting...")
            self.text_banner.set_bbox(dict(
                boxstyle="round,pad=0.4",
                facecolor="#fff3cd", edgecolor="#856404", alpha=0.9,
            ))
            self.text_banner.set_color("#856404")
            return

        if self.last_agent_result is not None and not self.last_agent_result.get("error"):
            p = self.last_agent_result["parsed"]
            ai_dx = p.get("diagnosis", "Indeterminate")
            risk  = p.get("risk_level", "?")

            # Find the matching class in CLASS_ORDER to pick its color
            face_color = "#cccccc"
            edge_color = "#666666"
            text_color = "#000000"
            for i, label in enumerate(CLASS_LABELS):
                if label.lower().split()[0] in ai_dx.lower():
                    face_color = CLASS_COLORS[i]
                    text_color = "#ffffff"
                    edge_color = "#222222"
                    break

            self.text_banner.set_text(
                f"🩺 AI Team Diagnosis: {ai_dx.upper()}   (risk: {risk})"
            )
            self.text_banner.set_bbox(dict(
                boxstyle="round,pad=0.4",
                facecolor=face_color, edgecolor=edge_color, alpha=0.9,
            ))
            self.text_banner.set_color(text_color)
            return

        # Idle / error state
        if self.last_agent_result is not None and self.last_agent_result.get("error"):
            self.text_banner.set_text(f"⚠ Agent error — see cmd")
            self.text_banner.set_bbox(dict(
                boxstyle="round,pad=0.4",
                facecolor="#f8d7da", edgecolor="#721c24", alpha=0.9,
            ))
            self.text_banner.set_color("#721c24")
        else:
            self.text_banner.set_text("Press [A] for AI team diagnosis")
            self.text_banner.set_bbox(dict(
                boxstyle="round,pad=0.4",
                facecolor="#dddddd", edgecolor="#888888", alpha=0.8,
            ))
            self.text_banner.set_color("#333333")

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

        # Probability panel title shows ground truth for the current scenario
        self.ax_probs.set_title(
            f"Cardiac Rhythm Classification   |   "
            f"Ground Truth: {sc['diagnosis']}",
            fontweight="bold"
        )

        # Banner above probabilities: reflects current agent state
        self._update_banner(sc)

        # Metrics panel: every 2 s
        if self.frame_count % self.frames_per_metrics == 0:
            self.text_metrics.set_text(
                self._metrics_string(self.smoothed_hr,
                                     self.smoothed_hrv,
                                     self.smoothed_r_amp))

        # Record info: every frame (cheap text)
        self.text_record.set_text(self._record_info_string())

        # Panel 4 update logic:
        #   priority 1: agent result is in -> show final diagnosis
        #   priority 2: agent is currently running -> show waiting message
        #   priority 3: no agent activity -> show feature summary (preliminary)
        if self.frame_count % self.frames_per_classify == 0:
            if self.last_agent_result is not None:
                # Agent finished; show its diagnosis
                r = self.last_agent_result
                if r.get("error"):
                    self.text_diag.set_text(
                        f"⚠ Agent error: {r['error']}\n"
                        f"Falling back to preliminary feature summary."
                    )
                else:
                    p = r["parsed"]
                    gt_label = sc["diagnosis"]
                    ai_dx    = p.get("diagnosis", "Indeterminate")
                    ai_first = ai_dx.lower().split()[0] if ai_dx else ""
                    match = "✓ MATCH" if ai_first and ai_first in gt_label.lower() else "≈"
                    reasoning = p.get("reasoning", "")
                    if len(reasoning) > 200:
                        reasoning = reasoning[:200] + "..."
                    self.text_diag.set_text(
                        f"🩺 Cardiac Team Diagnosis: {ai_dx}   |   "
                        f"Risk: {p.get('risk_level', '?')}   |   "
                        f"Ground truth: {gt_label}   [{match}]\n"
                        f"{reasoning}"
                    )
            elif self.agent_running:
                self.text_diag.set_text(
                    f"🤖 Cardiac team consulting... (see cmd terminal for live transcript)\n"
                    f"Ground truth: {sc['diagnosis']}"
                )
            elif self.last_classification is not None:
                # Preliminary feature summary (no agent output yet)
                cl = self.last_classification
                ai_label = cl["category_label"]
                gt_label = sc["diagnosis"]
                ai_first = ai_label.lower().split()[0]
                match = "✓ MATCH" if ai_first in gt_label.lower() else "≈"
                expl = cl["explanation"]["text"].split(".")[0].strip()
                if len(expl) > 140:
                    expl = expl[:140] + "..."
                self.text_diag.set_text(
                    f"📊 Feature Summary: {ai_label}   |   "
                    f"Ground truth: {gt_label}   [{match}]\n"
                    f"{expl}.   "
                    f"(Press [A] for AI cardiac team consultation)"
                )

        self.frame_count += 1

    # --------------------------------------------------------
    # Agent team consultation (background thread)
    # --------------------------------------------------------
    def _trigger_agent_consultation(self):
        """
        Build a feature bundle from the most recent DSP run and dispatch
        the cardiac team in a background thread. The animation thread
        polls self.last_agent_result on each frame and updates Panel 4
        when the result arrives.
        """
        if self.agent_running:
            print("⏳ Agent team is already running; please wait...")
            return

        if self.last_classification is None:
            print("⚠ No features available yet; let DSP run for a few seconds first.")
            return

        # Build feature bundle from the most recent DSP output
        sc = self.scenarios[self.current_name]
        cl = self.last_classification
        feats = cl["features"]

        # Recompute RR intervals from the most recent feature window for
        # the agent to see. (We don't keep the array around, so re-run
        # the slim part of the pipeline here.)
        ecg_full = sc["ecg"]
        fs = sc["fs"]
        end   = self.playback_pos
        start = max(0, end - self.feature_samples)
        feature_window = ecg_full[start:end]

        try:
            pt = pan_tompkins(feature_window, fs)
            rr_ms = (pt["rr_intervals_s"] * 1000.0).tolist()
        except Exception:
            rr_ms = []

        feature_bundle = {
            "hr_bpm":          feats["hr_bpm"],
            "hrv_sdnn_ms":     feats["hrv_sdnn_ms"],
            "rr_cv":           feats["rr_cv"],
            "ectopic_ratio":   feats["ectopic_ratio"],
            "n_r_peaks":       len(self.last_r_peaks_global),
            "r_amp_mV":        self.smoothed_r_amp,
            "rr_intervals_ms": rr_ms,
            "fs":              fs,
            "window_s":        int(self.feature_duration_s),
            "scenario_source": sc["source"],
        }

        self.agent_running     = True
        self.last_agent_result = None
        self.agent_status_text = "🤖 Cardiac team is consulting... (cmd terminal shows live transcript)"

        def worker():
            try:
                result = run_cardiac_team(feature_bundle, verbose=True)
            except Exception as e:
                result = {
                    "transcript":   [],
                    "final_message": "",
                    "parsed":       {"diagnosis": "Error", "risk_level": "unknown",
                                     "reasoning": str(e), "recommendation": "—"},
                    "error":        f"{type(e).__name__}: {e}",
                }
            self.last_agent_result = result
            self.agent_running     = False

        self.agent_thread = threading.Thread(target=worker, daemon=True)
        self.agent_thread.start()
        print("\n[A] pressed — dispatching cardiac team in background...")

    # --------------------------------------------------------
    # Keyboard handling
    # --------------------------------------------------------
    def on_key(self, event):
        key = event.key or ""

        # Quit
        if key in ("q", "Q"):
            print("Bye.")
            plt.close(self.fig)
            return

        # Pause / resume
        if key == " ":
            self.paused = not self.paused
            print("⏸ Paused" if self.paused else "▶ Resumed")
            return

        # Scenario switch (1-4)
        if key in "1234":
            idx = int(key) - 1
            scenario_names = [name for _, name in SCENARIO_FILES]
            if 0 <= idx < len(scenario_names):
                self._switch_scenario(scenario_names[idx], reset=True)
            return

        # Agent consultation — accept literal a/A AND fall back to '??' /
        # other garbled keys produced by Chinese IME interference.
        if key.lower() in ("a", "alt+a", "ctrl+a"):
            self._trigger_agent_consultation()
            return

        # IME-garbled fallback: treat any unknown short key as A.
        IGNORED = {"shift", "ctrl", "alt", "super", "control",
                   "shift+??", "ctrl+??", "alt+??",
                   "escape", "tab", "enter", "return",
                   "left", "right", "up", "down",
                   "backspace", "delete", "home", "end",
                   "pageup", "pagedown", "f1", "f2", "f3", "f4",
                   "f5", "f6", "f7", "f8", "f9", "f10", "f11", "f12"}
        if key and key.lower() not in IGNORED:
            self._trigger_agent_consultation()
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
