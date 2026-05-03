const API_BASE = "http://127.0.0.1:8000";

const fallbackScenarios = {
  normal: {
    title: "MIT100 normal",
    rhythm: "Normal Sinus Rhythm",
    status: "Stable",
    rate: "360 Hz",
    risk: "08",
    heartRate: "72",
    events: "38",
    eventType: "N beats",
    summary: "30 秒 Lead II 实时预览，R-R 间期稳定，形态清晰。",
    riskCopy: "Normal morphology, consistent R-R intervals.",
    color: "#1d8c5b",
    pattern: "normal",
    log: [
      ["00:01", "Clean R peak detected", "N"],
      ["00:06", "Stable baseline", "N"],
      ["00:12", "Narrow QRS complex", "N"],
      ["00:24", "No ectopic activity", "N"],
    ],
  },
  lbbb: {
    title: "MIT207 severe LBBB",
    rhythm: "Severe arrhythmia with LBBB",
    status: "Review",
    rate: "360 Hz",
    risk: "71",
    heartRate: "58",
    events: "23",
    eventType: "L / V / R markers",
    summary: "宽 QRS 形态明显，多个 LBBB 与室性事件混合出现。",
    riskCopy: "Wide QRS morphology with irregular annotation clusters.",
    color: "#2878c8",
    pattern: "lbbb",
    log: [
      ["00:02", "Left bundle branch beat", "L"],
      ["00:10", "Ventricular event", "V"],
      ["00:14", "Rhythm transition", "R"],
      ["00:25", "High variance segment", "V"],
    ],
  },
  pvc: {
    title: "MIT208 PVC / short VT",
    rhythm: "Frequent PVCs with short VT",
    status: "Elevated",
    rate: "360 Hz",
    risk: "84",
    heartRate: "96",
    events: "61",
    eventType: "PVC and fusion beats",
    summary: "PVC 标注密集，短阵 VT 片段需要快速复核。",
    riskCopy: "Frequent ventricular annotations and short tachycardia run.",
    color: "#d94b4b",
    pattern: "pvc",
    log: [
      ["00:01", "PVC morphology", "V"],
      ["00:04", "Fusion marker", "F"],
      ["00:08", "Short VT cluster", "V"],
      ["00:21", "Repeated ectopic beats", "V"],
    ],
  },
  vf: {
    title: "VF418 ventricular fibrillation",
    rhythm: "Ventricular Fibrillation",
    status: "Critical",
    rate: "250 Hz",
    risk: "96",
    heartRate: "--",
    events: "02",
    eventType: "VF markers",
    summary: "波形呈无序震荡，缺少稳定 R-R 间期，应作为最高优先级查看。",
    riskCopy: "Disorganized waveform with loss of beat-to-beat structure.",
    color: "#7d4fc7",
    pattern: "vf",
    log: [
      ["00:10", "VF onset marker", "+"],
      ["00:16", "Irregular fibrillation", "N"],
      ["00:19", "No stable R-R interval", "+"],
      ["00:28", "Continuous review needed", "+"],
    ],
  },
};

const markerColors = {
  N: "#1d8c5b",
  L: "#2878c8",
  V: "#d94b4b",
  R: "#8a9499",
  F: "#d78a23",
  "+": "#7d4fc7",
};

const markerSets = {
  normal: [[8, "N"], [18, "N"], [29, "N"], [38, "N"], [49, "N"], [60, "N"], [70, "N"], [82, "N"], [93, "N"]],
  lbbb: [[6, "L"], [16, "L"], [27, "L"], [39, "V"], [52, "R"], [64, "V"], [77, "V"], [90, "V"]],
  pvc: [[5, "V"], [12, "F"], [21, "V"], [33, "V"], [46, "V"], [58, "F"], [73, "V"], [88, "V"]],
  vf: [[35, "+"], [61, "N"]],
};

const canvas = document.querySelector("#ecgCanvas");
const context = canvas.getContext("2d");
const playToggle = document.querySelector("#playToggle");
const markerToggle = document.querySelector("#markerToggle");
const speedSelect = document.querySelector("#speedSelect");

let scenarios = { ...fallbackScenarios };
let currentScenario = scenarios.normal;
let animationFrame = 0;
let isPlaying = true;
let showMarkers = true;
let speed = 1;

function drawGrid(width, height) {
  context.clearRect(0, 0, width, height);
  context.fillStyle = "#fcfefe";
  context.fillRect(0, 0, width, height);

  context.strokeStyle = "#edf2f4";
  context.lineWidth = 1;
  for (let x = 0; x <= width; x += 32) {
    context.beginPath();
    context.moveTo(x, 0);
    context.lineTo(x, height);
    context.stroke();
  }
  for (let y = 0; y <= height; y += 32) {
    context.beginPath();
    context.moveTo(0, y);
    context.lineTo(width, y);
    context.stroke();
  }

  context.strokeStyle = "#d8e5da";
  for (let x = 0; x <= width; x += 160) {
    context.beginPath();
    context.moveTo(x, 0);
    context.lineTo(x, height);
    context.stroke();
  }
}

function spikeShape(phase, profile) {
  if (profile === "vf") {
    return Math.sin(phase * Math.PI * 2) * 0.42 + Math.sin(phase * Math.PI * 9) * 0.16;
  }

  const qrs = Math.exp(-Math.pow((phase - 0.18) / 0.018, 2)) * (profile === "pvc" ? 1.45 : 1.15);
  const sWave = Math.exp(-Math.pow((phase - 0.205) / 0.025, 2)) * (profile === "lbbb" ? -0.95 : -0.52);
  const tWave = Math.exp(-Math.pow((phase - 0.55) / 0.095, 2)) * (profile === "lbbb" ? 0.46 : 0.22);
  const pWave = Math.exp(-Math.pow((phase - 0.04) / 0.035, 2)) * 0.15;
  return pWave + qrs + sWave + tWave;
}

function drawWave() {
  const width = canvas.width;
  const height = canvas.height;
  const mid = height * 0.52;
  const profile = currentScenario.pattern;

  drawGrid(width, height);
  context.lineWidth = 3;
  context.strokeStyle = "#223139";
  context.beginPath();

  const realSignal = Array.isArray(currentScenario.ecg) && currentScenario.ecg.length > 0;
  for (let x = 0; x < width; x += 2) {
    const y = realSignal ? realSignalY(x, width, mid) : syntheticSignalY(x, width, mid, profile);
    if (x === 0) context.moveTo(x, y);
    else context.lineTo(x, y);
  }

  context.stroke();
  if (showMarkers) drawMarkers(profile);
  if (isPlaying) {
    const span = realSignal ? currentScenario.ecg.length : width;
    const step = realSignal ? Math.max(1, Math.round((currentScenario.fs || 360) / 30)) : 1.2;
    animationFrame = (animationFrame + step * speed) % span;
  }
  requestAnimationFrame(drawWave);
}

function drawMarkers(profile) {
  const markers = currentScenario.annotations?.length
    ? currentScenario.annotations.map((ann) => [(ann.sample / currentScenario.sample_count) * 100, ann.symbol])
    : markerSets[profile];

  markers.forEach(([percent, label]) => {
    const x = (percent / 100) * canvas.width;
    context.strokeStyle = markerColors[label];
    context.lineWidth = 2;
    context.beginPath();
    context.moveTo(x, 0);
    context.lineTo(x, canvas.height);
    context.stroke();
    context.fillStyle = markerColors[label];
    context.font = "700 16px Inter, sans-serif";
    context.fillText(label, x + 6, 34);
  });
}

function syntheticSignalY(x, width, mid, profile) {
  const t = (x + animationFrame) / width;
  const beatRate = profile === "vf" ? 16 : profile === "pvc" ? 12 : profile === "lbbb" ? 8.5 : 10.5;
  const phase = (t * beatRate) % 1;
  const baseline = Math.sin(t * Math.PI * 20) * 0.04 + Math.sin(t * Math.PI * 47) * 0.025;
  let signal = spikeShape(phase, profile) + baseline;

  if (profile === "pvc" && Math.floor(t * 16) % 5 === 0) signal *= 1.35;
  if (profile === "lbbb" && t > 0.36 && t < 0.48) signal += Math.sin(t * 80) * 0.32;
  if (profile === "vf") signal += Math.sin(t * Math.PI * 31) * 0.24;

  return mid - signal * (profile === "vf" ? 96 : 130);
}

function realSignalY(x, width, mid) {
  const samples = currentScenario.ecg;
  const stats = currentScenario.stats || {};
  const sampleIndex = Math.floor(((x / width) * samples.length + animationFrame) % samples.length);
  const value = samples[sampleIndex] - (stats.mean || 0);
  const range = Math.max(0.8, Math.abs(stats.max || 1), Math.abs(stats.min || -1));
  const scale = (canvas.height * 0.38) / range;
  return mid - value * scale;
}

function renderEvents(log) {
  const list = document.querySelector("#eventList");
  list.innerHTML = log
    .map(([time, label, type]) => `<li><time>${time}</time><span>${label}</span><b style="background:${markerColors[type]}">${type}</b></li>`)
    .join("");
}

function eventLogFromAnnotations(scenario) {
  if (!scenario.annotations?.length) return scenario.log || [];
  return scenario.annotations.slice(0, 4).map((annotation) => [
    formatTime(annotation.time),
    annotation.aux ? `${annotation.symbol} ${annotation.aux}` : annotationLabel(annotation.symbol),
    annotation.symbol,
  ]);
}

function annotationLabel(symbol) {
  const labels = {
    N: "Normal beat",
    L: "Left bundle branch beat",
    V: "PVC morphology",
    R: "Rhythm transition",
    F: "Fusion marker",
    "+": "Rhythm annotation",
  };
  return labels[symbol] || "ECG annotation";
}

function formatTime(seconds) {
  const value = Number(seconds) || 0;
  return `00:${String(Math.floor(value)).padStart(2, "0")}`;
}

function selectScenario(key) {
  currentScenario = scenarios[key];
  animationFrame = 0;
  document.querySelector("#scenarioTitle").textContent = currentScenario.title;
  document.querySelector("#waveTitle").textContent = currentScenario.rhythm;
  document.querySelector("#scenarioStatus").textContent = currentScenario.status;
  document.querySelector("#scenarioSummary").textContent = currentScenario.summary;
  document.querySelector("#riskScore").textContent = currentScenario.risk;
  document.querySelector("#heartRate").textContent = currentScenario.heartRate;
  document.querySelector("#eventCount").textContent = currentScenario.events;
  document.querySelector("#eventType").textContent = currentScenario.eventType;
  document.querySelector("#riskCopy").textContent = currentScenario.riskCopy;
  document.querySelector(".status-pill").style.borderColor = `${currentScenario.color}45`;
  document.querySelector(".status-pill span").style.background = currentScenario.color;
  document.querySelector(".status-pill span").style.boxShadow = `0 0 0 6px ${currentScenario.color}22`;
  renderEvents(eventLogFromAnnotations(currentScenario));

  document.querySelectorAll(".scenario-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.scenario === key);
  });
}

async function hydrateScenario(key) {
  const response = await fetch(`${API_BASE}/api/scenarios/${key}`);
  if (!response.ok) throw new Error(`Scenario request failed: ${response.status}`);
  const payload = await response.json();
  scenarios[key] = {
    ...fallbackScenarios[key],
    ...payload,
    log: fallbackScenarios[key].log,
  };
}

async function connectBackend() {
  try {
    await fetch(`${API_BASE}/api/health`);
    await Promise.all(Object.keys(fallbackScenarios).map(hydrateScenario));
    selectScenario(currentScenario.pattern || "normal");
    document.querySelector(".topbar .eyebrow").textContent = "Connected to ECAG2 backend";
  } catch (error) {
    document.querySelector(".topbar .eyebrow").textContent = "Offline mock mode / ECAG2 backend not running";
  }
}

document.querySelectorAll(".scenario-item").forEach((button) => {
  button.addEventListener("click", () => selectScenario(button.dataset.scenario));
});

playToggle.addEventListener("click", () => {
  isPlaying = !isPlaying;
  playToggle.textContent = isPlaying ? "II" : ">";
  playToggle.setAttribute("aria-label", isPlaying ? "暂停实时波形" : "播放实时波形");
});

markerToggle.addEventListener("click", () => {
  showMarkers = !showMarkers;
  markerToggle.classList.toggle("active", showMarkers);
});

speedSelect.addEventListener("change", (event) => {
  speed = Number(event.target.value);
});

selectScenario("normal");
connectBackend();
drawWave();
