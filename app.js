const scenarios = {
  normal: {
    title: "Normal Sinus Rhythm",
    risk: "Low risk",
    level: "normal",
    source: "PhysioNet mitdb/100",
    record: "mitdb/100 MLII",
    truth: "Normal Sinus Rhythm",
    hr: 72,
    hrv: 42,
    rPeak: 1.18,
    trends: { hr: 1, hrv: 3, rPeak: 0.03 },
    confidence: 86,
    diagnosis: "Normal rhythm detected",
    why: "Stable morphology, clear R-peak cadence, and low irregularity across the replay window.",
    actions: ["Continue routine monitoring", "Maintain normal activity", "Review only if symptoms appear"],
    probs: [0.86, 0.09, 0.03, 0.02],
  },
  pvc: {
    title: "PVCs / Short VT",
    risk: "Watch",
    level: "warning",
    source: "PhysioNet mitdb/208",
    record: "mitdb/208 MLII",
    truth: "PVCs / Short VT",
    hr: 96,
    hrv: 68,
    rPeak: 1.34,
    trends: { hr: 8, hrv: -6, rPeak: 0.11 },
    confidence: 79,
    diagnosis: "PVC burden detected",
    why: "Intermittent wide premature complexes and irregular beat timing suggest PVC activity.",
    actions: ["Monitor continuously", "Avoid heavy exertion", "Contact clinician if symptoms persist"],
    probs: [0.12, 0.79, 0.06, 0.03],
  },
  severe: {
    title: "Severe Arrhythmia (BBB)",
    risk: "Elevated risk",
    level: "warning",
    source: "PhysioNet mitdb/207",
    record: "mitdb/207 MLII",
    truth: "Severe Arrhythmia (BBB)",
    hr: 118,
    hrv: 91,
    rPeak: 1.48,
    trends: { hr: 12, hrv: -14, rPeak: 0.18 },
    confidence: 73,
    diagnosis: "Severe conduction abnormality",
    why: "Irregular morphology plus widened QRS complexes indicate a severe arrhythmia pattern.",
    actions: ["Contact clinician", "Reduce activity", "Seek medical attention if symptoms persist"],
    probs: [0.08, 0.13, 0.73, 0.06],
  },
  vf: {
    title: "Ventricular Fibrillation",
    risk: "Critical",
    level: "critical",
    source: "PhysioNet vfdb/418",
    record: "vfdb/418 ECG",
    truth: "Ventricular Fibrillation",
    hr: 0,
    hrv: 0,
    rPeak: 0.24,
    trends: { hr: -118, hrv: -91, rPeak: -1.02 },
    confidence: 91,
    diagnosis: "Ventricular fibrillation likely",
    why: "Chaotic waveform with no organized R-peaks suggests a critical ventricular fibrillation event.",
    actions: ["Call emergency response", "Begin emergency protocol", "Monitor continuously"],
    probs: [0.02, 0.03, 0.04, 0.91],
  },
};

const classNames = [
  "Normal Sinus Rhythm",
  "PVCs / Short VT",
  "Severe Arrhythmia (BBB)",
  "Ventricular Fibrillation",
];

const canvas = document.querySelector("#ecgCanvas");
const ctx = canvas.getContext("2d");
const probList = document.querySelector("#probList");
const buttons = [...document.querySelectorAll(".scenario-button")];
const playButton = document.querySelector("#playButton");
const resetButton = document.querySelector("#resetButton");
const diagnosisPanel = document.querySelector(".diagnosis-panel");
const modeButtons = [...document.querySelectorAll(".mode-button")];
const openEcgModal = document.querySelector("#openEcgModal");
const closeEcgModal = document.querySelector("#closeEcgModal");
const ecgModal = document.querySelector("#ecgModal");
const pageTabs = [...document.querySelectorAll(".page-tab")];
const pageTargets = [...document.querySelectorAll("[data-page-target]")];
const ageSlider = document.querySelector("#ageSlider");
const segmentButtons = [...document.querySelectorAll(".segment-button")];
const stepperButtons = [...document.querySelectorAll(".stepper-button")];

const state = {
  scenarioKey: "normal",
  mode: "clinician",
  page: "setup",
  profile: {
    age: 42,
    gender: "Female",
    height: 168,
    weight: 64,
  },
  paused: false,
  sampleRate: 360,
  duration: 30,
  visibleSeconds: 3,
  position: 0,
  phase: 0,
  samples: [],
};

function byId(id) {
  return document.getElementById(id);
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function setPage(page) {
  state.page = page;
  document.querySelectorAll(".page-section").forEach((section) => {
    section.classList.toggle("active", section.id === `page-${page}`);
  });
  pageTabs.forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.page === page);
  });
  if (page === "live") {
    resizeCanvas();
    drawWave();
  }
}

function initProbRows() {
  probList.innerHTML = classNames
    .map(
      (name, index) => `
        <div class="prob-row">
          <div class="prob-name">${name}</div>
          <div class="prob-track">
            <div class="prob-fill" data-prob-fill="${index}"></div>
          </div>
          <div class="prob-value" data-prob-value="${index}">0%</div>
        </div>
      `
    )
    .join("");
}

function ecgPulse(t, center, width, amplitude) {
  const x = (t - center) / width;
  return amplitude * Math.exp(-x * x);
}

function syntheticSample(key, t) {
  const beatPeriod = key === "normal" ? 0.82 : key === "pvc" ? 0.64 : key === "severe" ? 0.54 : 0.22;
  const beat = t % beatPeriod;
  const drift = 0.05 * Math.sin(t * 2.3) + 0.025 * Math.sin(t * 9.2);

  if (key === "vf") {
    return (
      0.32 * Math.sin(t * 38) +
      0.24 * Math.sin(t * 71 + 1.4) +
      0.11 * Math.sin(t * 143) +
      0.08 * Math.sin(t * 19)
    );
  }

  let value = drift;
  value += ecgPulse(beat, 0.1, 0.028, 0.12);
  value += ecgPulse(beat, 0.2, 0.012, -0.18);
  value += ecgPulse(beat, 0.225, 0.009, key === "severe" ? 1.15 : 1.45);
  value += ecgPulse(beat, 0.25, 0.014, -0.34);
  value += ecgPulse(beat, 0.43, 0.052, 0.22);

  if (key === "pvc" && Math.floor(t / beatPeriod) % 4 === 2) {
    value += ecgPulse(beat, 0.31, 0.035, -0.72);
    value += ecgPulse(beat, 0.36, 0.04, 0.9);
  }

  if (key === "severe") {
    value += 0.16 * Math.sin(t * 16) + ecgPulse(beat, 0.29, 0.032, 0.36);
  }

  return value;
}

function resizeCanvas() {
  const rect = canvas.getBoundingClientRect();
  const scale = window.devicePixelRatio || 1;
  canvas.width = Math.round(rect.width * scale);
  canvas.height = Math.round(rect.height * scale);
  ctx.setTransform(scale, 0, 0, scale, 0, 0);
}

function drawGrid(width, height) {
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#f7fbfb";
  ctx.fillRect(0, 0, width, height);

  ctx.strokeStyle = "rgba(18, 18, 18, 0.06)";
  ctx.lineWidth = 1;
  for (let x = 0; x <= width; x += 32) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, height);
    ctx.stroke();
  }
  for (let y = 0; y <= height; y += 32) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(width, y);
    ctx.stroke();
  }

  ctx.strokeStyle = "rgba(18, 18, 18, 0.16)";
  ctx.beginPath();
  ctx.moveTo(0, height / 2);
  ctx.lineTo(width, height / 2);
  ctx.stroke();
}

function drawWave() {
  const rect = canvas.getBoundingClientRect();
  const width = rect.width;
  const height = rect.height;
  const data = state.samples;
  const current = scenarios[state.scenarioKey];

  drawGrid(width, height);
  if (!data.length) return;

  ctx.beginPath();
  data.forEach((sample, index) => {
    const x = (index / (data.length - 1)) * width;
    const y = height / 2 - sample * (height * 0.24);
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.strokeStyle = current.level === "critical" ? "#ff8a6b" : current.level === "warning" ? "#d0b545" : "#111111";
  ctx.lineWidth = 2;
  ctx.shadowColor = ctx.strokeStyle;
  ctx.shadowBlur = 9;
  ctx.stroke();
  ctx.shadowBlur = 0;
}

function updateProbabilities() {
  const current = scenarios[state.scenarioKey];
  current.probs.forEach((prob, index) => {
    const fill = document.querySelector(`[data-prob-fill="${index}"]`);
    const value = document.querySelector(`[data-prob-value="${index}"]`);
    fill.className = `prob-fill ${current.level === "critical" && index === 3 ? "critical" : current.level === "warning" && prob > 0.5 ? "warning" : ""}`;
    fill.style.width = `${Math.round(prob * 100)}%`;
    value.textContent = `${Math.round(prob * 100)}%`;
  });
}

function trendText(value, unit = "") {
  if (value === 0) return "0";
  const arrow = value > 0 ? "up" : "down";
  const sign = value > 0 ? "+" : "";
  const formatted = Number.isInteger(value) ? value : value.toFixed(2);
  return `${arrow} ${sign}${formatted}${unit}`;
}

function trendClass(value, key) {
  if (value === 0) return "trend stable";
  if (state.scenarioKey === "vf" || (key === "hr" && value > 10)) return "trend critical";
  return `trend ${value > 0 ? "up" : "down"}`;
}

function confidenceClass(confidence) {
  if (confidence >= 80) return "";
  if (confidence >= 50) return "medium";
  return "low";
}

function comparisonModel(current) {
  return [
    {
      key: "hr",
      label: "Heart Rate",
      value: current.hr,
      unit: "bpm",
      min: 60,
      max: state.profile.age > 60 ? 95 : 100,
      caption: current.hr > 100 ? "Above normal range" : current.hr < 60 ? "Below normal range" : "Within normal range",
    },
    {
      key: "hrv",
      label: "HRV",
      value: current.hrv,
      unit: "ms",
      min: state.profile.age > 60 ? 25 : 35,
      max: state.profile.age > 60 ? 70 : 80,
      caption: current.hrv < 35 ? "Below similar group" : current.hrv > 80 ? "Above similar group" : "Within normal range",
    },
    {
      key: "rPeak",
      label: "R-peak",
      value: current.rPeak,
      unit: "mV",
      min: 0.8,
      max: 1.6,
      caption: current.rPeak < 0.8 ? "Low signal amplitude" : current.rPeak > 1.6 ? "Above typical amplitude" : "Within expected amplitude",
    },
  ];
}

function renderComparison(current) {
  const rows = comparisonModel(current);
  byId("compareMetrics").innerHTML = rows
    .map((metric) => {
      const expandedMin = metric.min - (metric.max - metric.min) * 0.35;
      const expandedMax = metric.max + (metric.max - metric.min) * 0.35;
      const marker = clamp(((metric.value - expandedMin) / (expandedMax - expandedMin)) * 100, 0, 100);
      const displayValue = metric.key === "rPeak" ? metric.value.toFixed(2) : metric.value;
      return `
        <article class="range-card">
          <header>
            <h3>${metric.label}</h3>
            <strong>${displayValue} ${metric.unit}</strong>
          </header>
          <div class="range-track">
            <span class="range-marker" style="left: ${marker}%"></span>
          </div>
          <div class="range-labels">
            <span>${metric.min} ${metric.unit}</span>
            <span>You</span>
            <span>${metric.max} ${metric.unit}</span>
          </div>
          <div class="range-caption">${metric.caption}</div>
        </article>
      `;
    })
    .join("");
}

function updateHeartAnimation(current) {
  const heart = byId("heartVisual");
  const speed = current.hr > 0 ? clamp(60 / current.hr, 0.38, 1.2) : 0.5;
  heart.style.setProperty("--heart-speed", `${speed}s`);
  heart.className = `heart-visual ${current.level === "normal" ? "" : current.level}`;
  byId("heartStatus").textContent =
    current.level === "critical" ? "Severe rhythm instability" : current.level === "warning" ? "Elevated cardiac strain" : "Normal cardiac rhythm";
  byId("heartCopy").textContent =
    current.level === "critical"
      ? "The animation accelerates and turns red when the system detects severe rhythm risk."
      : current.level === "warning"
        ? "The animation shifts yellow to show elevated risk while monitoring continues."
        : "The animation stays green when rhythm and rate remain within expected bounds.";
}

function updateLiveInsight(current) {
  byId("liveRiskLabel").textContent = current.risk;
  byId("liveRiskSummary").textContent =
    current.level === "critical" ? "Immediate attention may be required" : current.level === "warning" ? "ECG pattern requires closer monitoring" : "ECG pattern is stable";
  byId("riskBanner").className = `risk-banner ${current.level === "normal" ? "" : current.level}`;
  byId("liveInsightTitle").textContent =
    current.level === "normal" ? "Stable ECG pattern detected." : current.level === "warning" ? "Irregular pattern requires attention." : "Critical rhythm pattern detected.";
  byId("liveInsightCopy").textContent =
    current.level === "normal"
      ? "Your heart rate is within the expected range for your age group."
      : current.level === "warning"
        ? "Irregular rhythm detected. Your heart rate is above the normal range for your age group."
        : "The ECG waveform shows severe instability and loss of organized rhythm.";
  byId("liveActionList").innerHTML = current.actions.map((action) => `<li>${action}</li>`).join("");
}

function updateReport(current) {
  byId("reportStatus").textContent =
    current.level === "normal" ? "Status: Stable" : current.level === "warning" ? "Status: Needs Attention" : "Status: Critical";
  byId("reportRisk").textContent = `Risk Level: ${current.risk}`;
  byId("reportRisk").className = `report-risk ${current.level === "normal" ? "" : current.level}`;
  byId("reportHrTrend").textContent = current.trends.hr > 0 ? `Rising ${trendText(current.trends.hr)}` : current.trends.hr < 0 ? `Falling ${trendText(current.trends.hr)}` : "Stable";
  byId("reportHrvTrend").textContent = current.trends.hrv > 0 ? `Rising ${trendText(current.trends.hrv)}` : current.trends.hrv < 0 ? `Falling ${trendText(current.trends.hrv)}` : "Stable";

  const comparisons = comparisonModel(current);
  byId("reportCompareList").innerHTML = comparisons
    .slice(0, 2)
    .map((metric) => `<li>${metric.label}: ${metric.caption}</li>`)
    .join("");

  byId("reportAnalysis").textContent =
    current.level === "normal"
      ? "Your ECG shows stable sinus rhythm. No significant abnormalities detected. Minor variability observed, within normal limits."
      : current.level === "warning"
        ? "Your ECG shows rhythm irregularity and elevated cardiac strain. Continued monitoring and clinical follow-up are recommended if this pattern persists."
        : "Your ECG shows a critical abnormal rhythm pattern. Immediate clinical assessment is recommended.";

  const findings =
    current.level === "normal"
      ? ["Normal sinus rhythm", "No arrhythmia detected"]
      : current.level === "warning"
        ? ["Irregular rhythm detected", "Heart rate above age-group range", "Clinical follow-up recommended if persistent"]
        : ["Severe rhythm instability", "No organized R-peak pattern", "Emergency response recommended"];
  byId("reportFindings").innerHTML = findings.map((finding) => `<li>${finding}</li>`).join("");
}

function updateScenarioUI() {
  const current = scenarios[state.scenarioKey];
  byId("scenarioTitle").textContent = current.title;
  byId("riskPill").textContent = current.risk;
  byId("riskPill").className = `risk-pill ${current.level === "normal" ? "" : current.level}`;
  byId("sourceText").textContent = current.source;
  byId("recordName").textContent = current.record;
  byId("truthText").textContent = current.truth;
  byId("heartRate").textContent = current.hr;
  byId("hrv").textContent = current.hrv;
  byId("rPeak").textContent = current.rPeak.toFixed(2);
  byId("heartRateTrend").textContent = trendText(current.trends.hr);
  byId("hrvTrend").textContent = trendText(current.trends.hrv);
  byId("rPeakTrend").textContent = trendText(current.trends.rPeak);
  byId("heartRateTrend").className = trendClass(current.trends.hr, "hr");
  byId("hrvTrend").className = trendClass(current.trends.hrv, "hrv");
  byId("rPeakTrend").className = trendClass(current.trends.rPeak, "rPeak");
  byId("sampleRate").textContent = state.sampleRate;
  byId("diagnosisTitle").textContent = current.diagnosis;
  byId("diagnosisStatus").textContent = current.risk;
  byId("diagnosisStatus").className = `diagnosis-status ${current.level === "normal" ? "" : current.level}`;
  byId("diagnosisWhy").textContent = current.why;
  byId("actionList").innerHTML = current.actions.map((action) => `<li>${action}</li>`).join("");
  byId("confidenceText").textContent = `${current.confidence}%`;
  byId("confidenceFill").style.width = `${current.confidence}%`;
  byId("confidenceFill").className = `confidence-fill ${confidenceClass(current.confidence)}`;
  diagnosisPanel.className = `diagnosis-panel ${current.level === "normal" ? "" : current.level}`;

  buttons.forEach((button) => {
    button.classList.toggle("active", button.dataset.scenario === state.scenarioKey);
  });
  modeButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.mode === state.mode);
  });
  renderComparison(current);
  updateHeartAnimation(current);
  updateLiveInsight(current);
  updateReport(current);
  updateProbabilities();
}

function updateProfileUI() {
  byId("ageValue").textContent = state.profile.age;
  byId("heightValue").textContent = state.profile.height;
  byId("weightValue").textContent = state.profile.weight;
  segmentButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.gender === state.profile.gender);
  });
  updateScenarioUI();
}

function resetSamples() {
  const count = state.sampleRate * state.visibleSeconds;
  state.samples = Array.from({ length: count }, (_, index) => {
    const t = Math.max(0, state.position - state.visibleSeconds + index / state.sampleRate);
    return syntheticSample(state.scenarioKey, t);
  });
}

function tick() {
  if (!state.paused) {
    const step = 6;
    for (let i = 0; i < step; i += 1) {
      state.position += 1 / state.sampleRate;
      if (state.position >= state.duration) state.position = 0;
      state.samples.push(syntheticSample(state.scenarioKey, state.position));
      if (state.samples.length > state.sampleRate * state.visibleSeconds) {
        state.samples.shift();
      }
    }
    byId("positionText").textContent = state.position.toFixed(1);
  }
  drawWave();
  requestAnimationFrame(tick);
}

buttons.forEach((button) => {
  button.addEventListener("click", () => {
    state.scenarioKey = button.dataset.scenario;
    state.position = 0;
    resetSamples();
    updateScenarioUI();
  });
});

playButton.addEventListener("click", () => {
  state.paused = !state.paused;
  playButton.textContent = state.paused ? "Resume" : "Pause";
  playButton.setAttribute("aria-label", state.paused ? "Resume realtime replay" : "Pause realtime replay");
});

resetButton.addEventListener("click", () => {
  state.position = 0;
  resetSamples();
});

modeButtons.forEach((button) => {
  button.addEventListener("click", () => {
    state.mode = button.dataset.mode;
    updateScenarioUI();
  });
});

pageTabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    setPage(tab.dataset.page);
  });
});

pageTargets.forEach((button) => {
  button.addEventListener("click", () => {
    setPage(button.dataset.pageTarget);
  });
});

ageSlider.addEventListener("input", () => {
  state.profile.age = Number(ageSlider.value);
  updateProfileUI();
});

segmentButtons.forEach((button) => {
  button.addEventListener("click", () => {
    state.profile.gender = button.dataset.gender;
    updateProfileUI();
  });
});

stepperButtons.forEach((button) => {
  button.addEventListener("click", () => {
    const key = button.dataset.step;
    const delta = Number(button.dataset.delta);
    const min = key === "height" ? 120 : 35;
    const max = key === "height" ? 220 : 180;
    state.profile[key] = clamp(state.profile[key] + delta, min, max);
    updateProfileUI();
  });
});

openEcgModal.addEventListener("click", () => {
  ecgModal.showModal();
});

closeEcgModal.addEventListener("click", () => {
  ecgModal.close();
});

ecgModal.addEventListener("click", (event) => {
  if (event.target === ecgModal) {
    ecgModal.close();
  }
});

window.addEventListener("resize", () => {
  resizeCanvas();
  drawWave();
});

initProbRows();
resizeCanvas();
resetSamples();
updateProfileUI();
setPage("setup");
tick();
