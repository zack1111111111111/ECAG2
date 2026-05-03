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

const state = {
  scenarioKey: "normal",
  mode: "clinician",
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
  ctx.fillStyle = "#061113";
  ctx.fillRect(0, 0, width, height);

  ctx.strokeStyle = "rgba(40, 226, 178, 0.08)";
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

  ctx.strokeStyle = "rgba(255, 255, 255, 0.18)";
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
  ctx.strokeStyle = current.level === "critical" ? "#ff5c63" : "#28e2b2";
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
  updateProbabilities();
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

window.addEventListener("resize", () => {
  resizeCanvas();
  drawWave();
});

initProbRows();
resizeCanvas();
resetSamples();
updateScenarioUI();
tick();
