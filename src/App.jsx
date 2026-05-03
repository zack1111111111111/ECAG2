import React, { useEffect, useMemo, useState } from "react";
import {
  Activity,
  BrainCircuit,
  Check,
  Clipboard,
  Database,
  FileText,
  HeartPulse,
  MonitorDot,
  ShieldCheck,
  Stethoscope,
  UserRound,
} from "lucide-react";

const API_BASE = "http://127.0.0.1:8000";

const fallbackScenarios = [
  {
    id: "normal",
    title: "MIT100 normal",
    rhythm: "Normal Sinus Rhythm",
    status: "Stable",
    risk: "08",
    heartRate: "72",
    events: "38",
    eventType: "N x36 / + x1 / A x1",
    rate: "360 Hz",
    diagnosis: "Normal Sinus Rhythm",
    source: "Demo fallback / MIT100",
    duration_s: 30,
    annotations: [
      { sample: 18, time: 0.05, symbol: "+", aux: "(N" },
      { sample: 77, time: 0.214, symbol: "N", aux: "" },
      { sample: 370, time: 1.028, symbol: "N", aux: "" },
      { sample: 662, time: 1.839, symbol: "N", aux: "" },
    ],
    fs: 360,
    ecg: [-0.14, -0.2, 0.1, 0.84, -0.41, -0.33, -0.3, -0.22, -0.35, 0.92, -0.44],
  },
  {
    id: "lbbb",
    title: "MIT207 severe LBBB",
    rhythm: "Severe arrhythmia with LBBB",
    status: "Review",
    risk: "71",
    heartRate: "58",
    events: "34",
    eventType: "V x13 / L x11 / R x9",
    rate: "360 Hz",
    diagnosis: "Severe arrhythmia with LBBB",
    source: "Demo fallback / MIT207",
    duration_s: 30,
    annotations: [
      { sample: 134, time: 0.372, symbol: "L", aux: "" },
      { sample: 485, time: 1.347, symbol: "L", aux: "" },
      { sample: 820, time: 2.278, symbol: "V", aux: "" },
      { sample: 1154, time: 3.206, symbol: "R", aux: "" },
    ],
    fs: 360,
    ecg: [-0.15, -1.0, 0.3, -0.2, -0.1, 0.8, -0.6, -0.2, 0.45, -0.95, -0.1],
  },
  {
    id: "pvc",
    title: "MIT208 PVC / short VT",
    rhythm: "Frequent PVCs with short VT",
    status: "Elevated",
    risk: "84",
    heartRate: "96",
    events: "53",
    eventType: "N x26 / V x20 / F x5",
    rate: "360 Hz",
    diagnosis: "Frequent PVCs with short VT",
    source: "Demo fallback / MIT208",
    duration_s: 30,
    annotations: [
      { sample: 128, time: 0.356, symbol: "V", aux: "" },
      { sample: 348, time: 0.967, symbol: "N", aux: "" },
      { sample: 739, time: 2.053, symbol: "F", aux: "" },
      { sample: 815, time: 2.264, symbol: "+", aux: "(T" },
    ],
    fs: 360,
    ecg: [-0.2, 1.4, -0.8, -0.25, 0.2, -0.1, 1.6, -0.9, -0.3, 0.1, -0.2],
  },
  {
    id: "vf",
    title: "VF418 ventricular fibrillation",
    rhythm: "Ventricular Fibrillation",
    status: "Critical",
    risk: "96",
    heartRate: "--",
    events: "2",
    eventType: "+ x2",
    rate: "250 Hz",
    diagnosis: "Ventricular Fibrillation",
    source: "Demo fallback / VF418",
    duration_s: 30,
    annotations: [
      { sample: 2500, time: 10, symbol: "+", aux: "(VFL" },
      { sample: 4375, time: 17.5, symbol: "+", aux: "(N" },
    ],
    fs: 250,
    ecg: [-0.17, 0.55, -0.4, 1.0, -1.2, 0.7, -0.95, 1.25, -0.62, 0.18, -0.2],
  },
];

const stepItems = [
  { id: 1, label: "Patient Profile", icon: UserRound },
  { id: 2, label: "Monitor", icon: MonitorDot },
  { id: 3, label: "Analysis & Report", icon: BrainCircuit },
];

const riskProfiles = {
  normal: {
    summary: "No critical abnormality detected.",
    rhythm: 88,
    arrhythmia: 12,
    confidence: 92,
    urgency: 10,
    level: "Low",
    pulseBase: 72,
  },
  lbbb: {
    summary: "Possible left bundle branch block pattern detected.",
    rhythm: 56,
    arrhythmia: 64,
    confidence: 81,
    urgency: 58,
    level: "Medium",
    pulseBase: 62,
  },
  pvc: {
    summary: "Premature ventricular contractions detected.",
    rhythm: 45,
    arrhythmia: 78,
    confidence: 84,
    urgency: 72,
    level: "High",
    pulseBase: 98,
  },
  vf: {
    summary: "Ventricular fibrillation risk pattern detected. Emergency attention recommended.",
    rhythm: 18,
    arrhythmia: 96,
    confidence: 88,
    urgency: 98,
    level: "Critical",
    pulseBase: 128,
  },
};

function App() {
  const [step, setStep] = useState(1);
  const [scenarios, setScenarios] = useState(fallbackScenarios);
  const [activeId, setActiveId] = useState("normal");
  const [connected, setConnected] = useState(false);
  const [copied, setCopied] = useState(false);
  const [patient, setPatient] = useState({
    age: "",
    gender: "Male",
    height: "",
    weight: "",
  });

  useEffect(() => {
    let mounted = true;

    async function loadData() {
      try {
        const response = await fetch(`${API_BASE}/api/scenarios`);
        if (!response.ok) throw new Error("Failed to load scenarios");
        const { scenarios: summary } = await response.json();
        const detailed = await Promise.all(
          summary.map(async (item) => {
            const detail = await fetch(`${API_BASE}/api/scenarios/${item.id}`);
            return detail.ok ? detail.json() : item;
          }),
        );
        if (mounted) {
          setScenarios(detailed);
          setConnected(true);
        }
      } catch {
        if (mounted) setConnected(false);
      }
    }

    loadData();
    return () => {
      mounted = false;
    };
  }, []);

  const activeScenario = scenarios.find((scenario) => scenario.id === activeId) || scenarios[0];
  const bmi = calculateBmi(patient.height, patient.weight);
  const bmiStatus = getBmiStatus(bmi);
  const reportText = buildReport({ patient, bmi, bmiStatus, activeScenario, connected });

  async function copyReport() {
    try {
      await navigator.clipboard.writeText(reportText);
    } catch {
      const textArea = document.createElement("textarea");
      textArea.value = reportText;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand("copy");
      document.body.removeChild(textArea);
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  }

  return (
    <main className="min-h-screen bg-[#081013] px-4 py-5 font-sans text-white sm:px-6 lg:px-8">
      <div className="mx-auto max-w-7xl">
        <Header connected={connected} />
        <StepNav currentStep={step} setStep={setStep} />

        {step === 1 && (
          <PatientProfileStep
            patient={patient}
            setPatient={setPatient}
            bmi={bmi}
            bmiStatus={bmiStatus}
            onContinue={() => setStep(2)}
          />
        )}

        {step === 2 && (
          <MonitorStep
            patient={patient}
            bmi={bmi}
            bmiStatus={bmiStatus}
            scenarios={scenarios}
            activeScenario={activeScenario}
            activeId={activeId}
            setActiveId={setActiveId}
            onContinue={() => setStep(3)}
          />
        )}

        {step === 3 && (
          <AnalysisReportStep
            patient={patient}
            bmi={bmi}
            bmiStatus={bmiStatus}
            activeScenario={activeScenario}
            connected={connected}
            copied={copied}
            copyReport={copyReport}
          />
        )}
      </div>
    </main>
  );
}

function Header({ connected }) {
  return (
    <header className="mb-5 flex flex-col justify-between gap-4 rounded-[2rem] border border-white/10 bg-white/[0.06] p-4 shadow-[0_24px_80px_rgba(0,0,0,0.25)] backdrop-blur md:flex-row md:items-center">
      <div className="flex items-center gap-3">
        <span className="grid size-12 place-items-center rounded-full bg-[#24f2bd]/15 text-[#24f2bd]">
          <HeartPulse size={24} strokeWidth={2.4} />
        </span>
        <div>
          <h1 className="text-2xl font-black tracking-[-0.04em]">ECAG2 Health Dashboard</h1>
          <p className="text-sm font-semibold text-slate-400">3-step ECG research demo prototype</p>
        </div>
      </div>
      <div className="flex items-center gap-2 rounded-full border border-white/10 bg-black/20 px-4 py-2 text-sm font-black text-slate-200">
        <span className={`size-2 rounded-full ${connected ? "bg-[#24f2bd]" : "bg-[#facc15]"}`} />
        {connected ? "GitHub data" : "Demo data"}
      </div>
    </header>
  );
}

function StepNav({ currentStep, setStep }) {
  return (
    <nav className="mb-6 grid gap-3 md:grid-cols-3" aria-label="Dashboard steps">
      {stepItems.map((item) => {
        const Icon = item.icon;
        const active = currentStep === item.id;
        return (
          <button
            key={item.id}
            type="button"
            onClick={() => setStep(item.id)}
            className={`flex items-center gap-3 rounded-[1.5rem] border p-4 text-left transition ${
              active
                ? "border-[#24f2bd]/50 bg-[#24f2bd]/15 shadow-[0_16px_42px_rgba(36,242,189,0.10)]"
                : "border-white/10 bg-white/[0.055] hover:border-white/20"
            }`}
          >
            <span
              className={`grid size-11 place-items-center rounded-full ${
                active ? "bg-[#24f2bd] text-[#071113]" : "bg-white/10 text-slate-300"
              }`}
            >
              <Icon size={20} strokeWidth={2.4} />
            </span>
            <div>
              <p className="text-xs font-black uppercase tracking-[0.16em] text-slate-400">Step {item.id}</p>
              <p className="font-black">{item.label}</p>
            </div>
          </button>
        );
      })}
    </nav>
  );
}

function PatientProfileStep({ patient, setPatient, bmi, bmiStatus, onContinue }) {
  return (
    <section className="grid gap-5 lg:grid-cols-[1.1fr_0.9fr]">
      <Panel>
        <SectionKicker icon={UserRound} label="Patient Profile" />
        <h2 className="mt-4 text-4xl font-black tracking-[-0.05em] sm:text-5xl">
          Enter basic patient information.
        </h2>
        <p className="mt-3 max-w-2xl text-base leading-7 text-slate-400">
          This profile is shared across the monitor and report steps. BMI updates in real time as
          height and weight change.
        </p>

        <div className="mt-8 grid gap-4 sm:grid-cols-2">
          <Field label="Age">
            <input
              value={patient.age}
              onChange={(event) => setPatient({ ...patient, age: event.target.value })}
              placeholder="42"
              type="number"
              className="input"
            />
          </Field>
          <Field label="Gender">
            <select
              value={patient.gender}
              onChange={(event) => setPatient({ ...patient, gender: event.target.value })}
              className="input"
            >
              <option>Male</option>
              <option>Female</option>
              <option>Other</option>
            </select>
          </Field>
          <Field label="Height">
            <div className="relative">
              <input
                value={patient.height}
                onChange={(event) => setPatient({ ...patient, height: event.target.value })}
                placeholder="175"
                type="number"
                className="input pr-14"
              />
              <span className="absolute right-4 top-1/2 -translate-y-1/2 text-sm font-black text-slate-500">
                cm
              </span>
            </div>
          </Field>
          <Field label="Weight">
            <div className="relative">
              <input
                value={patient.weight}
                onChange={(event) => setPatient({ ...patient, weight: event.target.value })}
                placeholder="70"
                type="number"
                className="input pr-14"
              />
              <span className="absolute right-4 top-1/2 -translate-y-1/2 text-sm font-black text-slate-500">
                kg
              </span>
            </div>
          </Field>
        </div>

        <button type="button" onClick={onContinue} className="mt-8 rounded-full bg-[#24f2bd] px-7 py-4 font-black text-[#071113]">
          Continue to Monitor
        </button>
      </Panel>

      <PatientSummaryCard patient={patient} bmi={bmi} bmiStatus={bmiStatus} large />
    </section>
  );
}

function MonitorStep({ patient, bmi, bmiStatus, scenarios, activeScenario, activeId, setActiveId, onContinue }) {
  const vitals = useLiveVitals(activeScenario);

  return (
    <section className="grid gap-5 xl:grid-cols-[320px_1fr]">
      <div className="grid gap-5">
        <PatientSummaryCard patient={patient} bmi={bmi} bmiStatus={bmiStatus} />
        <Panel>
          <SectionKicker icon={Activity} label="Live Vitals" />
          <div className="mt-5 grid gap-3">
            <VitalCard label="Heart Rate" value={vitals.heartRate} unit="bpm" tone={activeScenario.id} />
            <VitalCard label="Pulse" value={vitals.pulse} unit="bpm" tone={activeScenario.id} />
            <VitalCard label="Risk Score" value={activeScenario.risk} unit="/100" tone={activeScenario.id} />
            <VitalCard label="Sampling Rate" value={activeScenario.rate} unit="" tone={activeScenario.id} />
          </div>
        </Panel>
      </div>

      <div className="grid gap-5">
        <Panel className="bg-[#050b0d]">
          <div className="mb-5 flex flex-col justify-between gap-4 md:flex-row md:items-start">
            <div>
              <SectionKicker icon={MonitorDot} label="Patient Monitor" />
              <h2 className="mt-3 text-3xl font-black tracking-[-0.04em] sm:text-4xl">
                {activeScenario.rhythm}
              </h2>
              <p className="mt-2 text-sm font-semibold text-slate-400">{activeScenario.diagnosis}</p>
            </div>
            <span
              className={`rounded-full px-4 py-2 text-sm font-black ${
                activeScenario.id === "vf"
                  ? "bg-red-500/20 text-red-200"
                  : activeScenario.id === "normal"
                    ? "bg-[#24f2bd]/15 text-[#24f2bd]"
                    : "bg-yellow-400/15 text-yellow-200"
              }`}
            >
              {activeScenario.id === "vf" ? "Critical" : activeScenario.status}
            </span>
          </div>
          <ECGMonitor scenario={activeScenario} />
        </Panel>

        <div className="grid gap-3 md:grid-cols-4">
          {scenarios.map((scenario) => (
            <ScenarioCard
              key={scenario.id}
              scenario={scenario}
              selected={scenario.id === activeId}
              onClick={() => setActiveId(scenario.id)}
            />
          ))}
        </div>

        <div className="flex justify-end">
          <button type="button" onClick={onContinue} className="rounded-full bg-[#24f2bd] px-7 py-4 font-black text-[#071113]">
            Go to Analysis
          </button>
        </div>
      </div>
    </section>
  );
}

function AnalysisReportStep({ patient, bmi, bmiStatus, activeScenario, connected, copied, copyReport }) {
  const profile = riskProfiles[activeScenario.id] || riskProfiles.normal;
  const annotations = activeScenario.annotations?.length
    ? activeScenario.annotations.slice(0, 8)
    : fallbackScenarios.find((scenario) => scenario.id === activeScenario.id)?.annotations || [];

  return (
    <section className="grid gap-5 xl:grid-cols-[1fr_0.95fr]">
      <Panel>
        <SectionKicker icon={BrainCircuit} label="AI Analysis" />
        <h2 className="mt-4 text-4xl font-black tracking-[-0.05em]">Analysis summary</h2>
        <p className="mt-4 rounded-[1.5rem] border border-[#24f2bd]/20 bg-[#24f2bd]/10 p-5 text-lg font-bold leading-8 text-[#d9fff4]">
          {profile.summary}
        </p>

        <div className="mt-6 grid gap-4">
          <RiskBar label="Rhythm Stability" value={profile.rhythm} inverse />
          <RiskBar label="Arrhythmia Risk" value={profile.arrhythmia} />
          <RiskBar label="Signal Confidence" value={profile.confidence} inverse />
          <RiskBar label="Urgency Level" value={profile.urgency} />
        </div>

        <div className="mt-7">
          <h3 className="text-xl font-black">Detected Events</h3>
          <div className="mt-3 overflow-hidden rounded-[1.5rem] border border-white/10">
            {annotations.map((annotation, index) => (
              <div
                key={`${annotation.sample}-${index}`}
                className="grid grid-cols-[1fr_1fr_1fr] gap-3 border-b border-white/10 bg-white/[0.035] px-4 py-3 text-sm last:border-b-0"
              >
                <span className="font-bold text-slate-400">sample {annotation.sample}</span>
                <span className="font-black">{annotation.symbol}</span>
                <span className="text-slate-300">{annotation.aux || `t=${annotation.time}s`}</span>
              </div>
            ))}
          </div>
        </div>
      </Panel>

      <Panel>
        <SectionKicker icon={FileText} label="Data Report" />
        <h2 className="mt-4 text-4xl font-black tracking-[-0.05em]">Patient & ECG report</h2>

        <div className="mt-6 grid gap-3">
          <ReportRow label="Age" value={patient.age || "--"} />
          <ReportRow label="Gender" value={patient.gender || "--"} />
          <ReportRow label="Height" value={patient.height ? `${patient.height} cm` : "--"} />
          <ReportRow label="Weight" value={patient.weight ? `${patient.weight} kg` : "--"} />
          <ReportRow label="BMI" value={bmi ? `${bmi} (${bmiStatus})` : "--"} />
          <ReportRow label="Scenario ID" value={activeScenario.id} />
          <ReportRow label="Diagnosis" value={activeScenario.diagnosis} />
          <ReportRow label="Source" value={activeScenario.source || "--"} />
          <ReportRow label="Sampling" value={activeScenario.rate || `${activeScenario.fs} Hz`} />
          <ReportRow label="Duration" value={`${activeScenario.duration_s || 30}s`} />
          <ReportRow label="Event count" value={activeScenario.events || activeScenario.annotations?.length || "--"} />
          <ReportRow label="API status" value={connected ? "GitHub data" : "Demo data"} />
        </div>

        <p className="mt-5 rounded-[1.4rem] border border-yellow-300/20 bg-yellow-300/10 p-4 text-sm font-semibold leading-6 text-yellow-100">
          This dashboard is a research and demo visualization only. It is not a certified medical
          device and should not be used as a formal medical diagnosis.
        </p>

        <button
          type="button"
          onClick={copyReport}
          className="mt-5 inline-flex items-center gap-2 rounded-full bg-[#24f2bd] px-6 py-4 font-black text-[#071113]"
        >
          {copied ? <Check size={18} /> : <Clipboard size={18} />}
          {copied ? "Copied!" : "Copy Report"}
        </button>
      </Panel>
    </section>
  );
}

function ECGMonitor({ scenario }) {
  const [cursor, setCursor] = useState(0);

  useEffect(() => {
    setCursor(0);
  }, [scenario.id]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setCursor((value) => {
        const length = scenario.ecg?.length || 1;
        const step = Math.max(4, Math.round((scenario.fs || 360) / 18));
        return (value + step) % length;
      });
    }, 70);

    return () => window.clearInterval(timer);
  }, [scenario.ecg, scenario.fs]);

  const points = useMemo(() => {
    const data = scenario.ecg?.length ? scenario.ecg : fallbackScenarios[0].ecg;
    const windowSize = Math.min(620, data.length);
    const stride = Math.max(1, Math.floor(windowSize / 170));
    const samples = [];

    for (let i = 0; i < windowSize; i += stride) {
      samples.push(data[(cursor + i) % data.length]);
    }

    const min = Math.min(...samples);
    const max = Math.max(...samples);
    const range = max - min || 1;

    return samples
      .map((value, index) => {
        const x = (index / Math.max(samples.length - 1, 1)) * 900;
        const y = 220 - ((value - min) / range) * 170;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");
  }, [cursor, scenario.ecg]);

  return (
    <div className="relative overflow-hidden rounded-[1.7rem] border border-[#24f2bd]/20 bg-[#031a17] p-4 shadow-[inset_0_0_70px_rgba(36,242,189,0.06)]">
      <svg viewBox="0 0 900 280" className="h-[320px] w-full" role="img" aria-label="Realtime ECG waveform">
        <defs>
          <pattern id="monitorGrid" width="36" height="36" patternUnits="userSpaceOnUse">
            <path d="M 36 0 L 0 0 0 36" fill="none" stroke="rgba(36,242,189,0.11)" strokeWidth="1" />
          </pattern>
          <linearGradient id="scanGlow" x1="0" x2="1">
            <stop offset="0%" stopColor="rgba(36,242,189,0)" />
            <stop offset="55%" stopColor="rgba(36,242,189,0.34)" />
            <stop offset="100%" stopColor="rgba(36,242,189,0)" />
          </linearGradient>
        </defs>
        <rect width="900" height="280" rx="22" fill="url(#monitorGrid)" />
        <line x1="0" x2="900" y1="142" y2="142" stroke="rgba(36,242,189,0.18)" strokeWidth="2" />
        <rect x={(cursor % 100) * 9 - 80} y="0" width="130" height="280" fill="url(#scanGlow)" opacity="0.65" />
        <polyline
          fill="none"
          points={points}
          stroke="#24f2bd"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="4"
          filter="drop-shadow(0 0 8px rgba(36,242,189,0.75))"
        />
      </svg>
    </div>
  );
}

function ScenarioCard({ scenario, selected, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-[1.5rem] border p-4 text-left transition ${
        selected
          ? "border-[#24f2bd]/70 bg-[#24f2bd]/15"
          : "border-white/10 bg-white/[0.055] hover:border-white/20"
      }`}
    >
      <p className="text-sm font-black uppercase tracking-[0.15em] text-slate-400">{scenario.id}</p>
      <h3 className="mt-2 text-lg font-black">{scenario.rhythm}</h3>
      <div className="mt-4 flex items-center justify-between">
        <span className="text-sm font-semibold text-slate-400">Risk</span>
        <span className="font-black text-[#24f2bd]">{scenario.risk}</span>
      </div>
    </button>
  );
}

function PatientSummaryCard({ patient, bmi, bmiStatus, large = false }) {
  return (
    <Panel className={large ? "min-h-full" : ""}>
      <SectionKicker icon={UserRound} label="Patient Summary" />
      <div className="mt-5 grid gap-3">
        <SummaryRow label="Age" value={patient.age || "--"} />
        <SummaryRow label="Gender" value={patient.gender || "--"} />
        <SummaryRow label="Height" value={patient.height ? `${patient.height} cm` : "--"} />
        <SummaryRow label="Weight" value={patient.weight ? `${patient.weight} kg` : "--"} />
      </div>
      <div className="mt-5 rounded-[1.5rem] border border-[#24f2bd]/20 bg-[#24f2bd]/10 p-5">
        <p className="text-sm font-black uppercase tracking-[0.15em] text-slate-400">BMI</p>
        <p className="mt-2 text-5xl font-black tracking-[-0.06em]">{bmi || "--"}</p>
        <p className="mt-2 font-black text-[#24f2bd]">{bmi ? bmiStatus : "Waiting for height / weight"}</p>
      </div>
    </Panel>
  );
}

function VitalCard({ label, value, unit, tone }) {
  const critical = tone === "vf";
  return (
    <article className={`rounded-[1.4rem] border p-4 ${critical ? "border-red-400/25 bg-red-500/10" : "border-white/10 bg-white/[0.055]"}`}>
      <p className="text-sm font-black text-slate-400">{label}</p>
      <p className={`mt-2 text-3xl font-black tracking-[-0.05em] ${critical ? "text-red-200" : "text-white"}`}>
        {value}
        {unit && <span className="ml-2 text-sm font-black text-slate-500">{unit}</span>}
      </p>
    </article>
  );
}

function RiskBar({ label, value, inverse = false }) {
  const color = inverse ? "bg-[#24f2bd]" : value > 85 ? "bg-red-400" : value > 60 ? "bg-yellow-300" : "bg-[#24f2bd]";
  return (
    <div>
      <div className="mb-2 flex justify-between text-sm font-black">
        <span className="text-slate-300">{label}</span>
        <span>{value}%</span>
      </div>
      <div className="h-3 overflow-hidden rounded-full bg-white/10">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${value}%` }} />
      </div>
    </div>
  );
}

function Panel({ children, className = "" }) {
  return (
    <section className={`rounded-[2rem] border border-white/10 bg-white/[0.07] p-5 shadow-[0_22px_70px_rgba(0,0,0,0.22)] sm:p-6 ${className}`}>
      {children}
    </section>
  );
}

function SectionKicker({ icon: Icon, label }) {
  return (
    <div className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-2 text-sm font-black text-slate-300">
      <Icon size={16} strokeWidth={2.4} />
      {label}
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="mb-2 block text-sm font-black text-slate-300">{label}</span>
      {children}
    </label>
  );
}

function SummaryRow({ label, value }) {
  return (
    <div className="flex items-center justify-between rounded-[1.2rem] bg-white/[0.055] px-4 py-3">
      <span className="text-sm font-bold text-slate-400">{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ReportRow({ label, value }) {
  return (
    <div className="flex flex-col justify-between gap-1 rounded-[1.2rem] bg-white/[0.055] px-4 py-3 sm:flex-row sm:items-center">
      <span className="text-sm font-bold text-slate-400">{label}</span>
      <strong className="text-right">{value}</strong>
    </div>
  );
}

function useLiveVitals(activeScenario) {
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const timer = window.setInterval(() => setTick((value) => value + 1), 900);
    return () => window.clearInterval(timer);
  }, []);

  return useMemo(() => {
    const profile = riskProfiles[activeScenario.id] || riskProfiles.normal;
    const drift = Math.round(Math.sin(tick / 2) * 3 + Math.cos(tick / 3) * 2);
    const heartRate =
      activeScenario.id === "vf"
        ? "Critical"
        : Math.max(42, Number(activeScenario.heartRate) || profile.pulseBase) + drift;
    const pulse = activeScenario.id === "vf" ? profile.pulseBase + drift * 2 : profile.pulseBase + drift;
    return { heartRate, pulse };
  }, [activeScenario, tick]);
}

function calculateBmi(height, weight) {
  const h = Number(height);
  const w = Number(weight);
  if (!h || !w) return null;
  return (w / (h / 100) ** 2).toFixed(1);
}

function getBmiStatus(bmi) {
  if (!bmi) return "--";
  const value = Number(bmi);
  if (value < 18.5) return "Underweight";
  if (value < 25) return "Normal";
  if (value < 30) return "Overweight";
  return "Obese";
}

function buildReport({ patient, bmi, bmiStatus, activeScenario, connected }) {
  return [
    "ECAG2 ECG Health Dashboard Report",
    "",
    `Age: ${patient.age || "--"}`,
    `Gender: ${patient.gender || "--"}`,
    `Height: ${patient.height ? `${patient.height} cm` : "--"}`,
    `Weight: ${patient.weight ? `${patient.weight} kg` : "--"}`,
    `BMI: ${bmi ? `${bmi} (${bmiStatus})` : "--"}`,
    "",
    `Scenario ID: ${activeScenario.id}`,
    `Diagnosis: ${activeScenario.diagnosis}`,
    `Source: ${activeScenario.source || "--"}`,
    `Sampling: ${activeScenario.rate || `${activeScenario.fs} Hz`}`,
    `Duration: ${activeScenario.duration_s || 30}s`,
    `Event Count: ${activeScenario.events || activeScenario.annotations?.length || "--"}`,
    `API Status: ${connected ? "GitHub data" : "Demo data"}`,
    "",
    "Clinical Note: This dashboard is a research and demo visualization only. It is not a certified medical device and should not be used as a formal medical diagnosis.",
  ].join("\n");
}

export default App;
