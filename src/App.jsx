import React, { useEffect, useMemo, useState } from "react";
import {
  Activity,
  ArrowRight,
  Bell,
  Database,
  HeartPulse,
  LineChart,
  Play,
  ShieldCheck,
  Sparkles,
  Stethoscope,
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
    summary: "Stable R-R intervals with clean morphology across the replay window.",
    symbol_counts: { N: 36, "+": 1, A: 1 },
    stats: { min: -0.68, max: 1.05, mean: -0.33 },
    fs: 360,
    sample_count: 10800,
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
    summary: "Wide QRS morphology with irregular annotation clusters.",
    symbol_counts: { L: 11, V: 13, R: 9 },
    stats: { min: -1.2, max: 1.05, mean: -0.12 },
    fs: 360,
    sample_count: 10800,
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
    summary: "Frequent ventricular markers and fusion beats signal elevated review priority.",
    symbol_counts: { V: 20, N: 26, F: 5 },
    stats: { min: -1.18, max: 1.92, mean: -0.15 },
    fs: 360,
    sample_count: 10800,
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
    summary: "Disorganized waveform with loss of beat-to-beat structure.",
    symbol_counts: { "+": 2 },
    stats: { min: -1.75, max: 1.46, mean: 0.02 },
    fs: 250,
    sample_count: 7500,
    ecg: [-0.17, 0.55, -0.4, 1.0, -1.2, 0.7, -0.95, 1.25, -0.62, 0.18, -0.2],
  },
];

const scenarioColors = {
  normal: "bg-[#D9F2C7]",
  lbbb: "bg-[#BFEFF4]",
  pvc: "bg-[#FFE680]",
  vf: "bg-[#F2D6FF]",
};

function App() {
  const [scenarios, setScenarios] = useState(fallbackScenarios);
  const [activeId, setActiveId] = useState("normal");
  const [connected, setConnected] = useState(false);

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

  return (
    <main className="min-h-screen bg-[#F7F7F7] font-sans text-[#0B0B0B]">
      <Header connected={connected} />

      <section className="mx-auto grid max-w-7xl grid-cols-1 gap-10 px-5 pb-14 pt-8 sm:px-8 lg:grid-cols-[0.9fr_1.1fr] lg:px-10 lg:pb-20 lg:pt-14">
        <div className="flex flex-col justify-center">
          <div className="mb-6 flex flex-wrap gap-3">
            <Pill icon={Sparkles} text="AI ECG insight" />
            <Pill icon={Database} text="GitHub scenario data" />
            <Pill icon={ShieldCheck} text="Local API" />
          </div>

          <h1 className="max-w-4xl text-6xl font-black leading-[0.92] tracking-[-0.055em] sm:text-7xl lg:text-[5.8rem]">
            Realtime ECG data, made easier to read.
          </h1>
          <p className="mt-7 max-w-2xl text-lg font-medium leading-8 text-[#5F6368]">
            A clean web dashboard powered by ECAG2 repository data. Review rhythm, risk,
            annotations, and live signal movement without opening the original Python demo.
          </p>

          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <a
              href="#live-monitor"
              className="inline-flex items-center justify-center gap-2 rounded-full bg-[#0B0B0B] px-7 py-4 text-base font-black text-white shadow-[0_18px_40px_rgba(11,11,11,0.16)]"
            >
              View live monitor
              <ArrowRight size={18} strokeWidth={2.5} />
            </a>
            <a
              href="#scenarios"
              className="inline-flex items-center justify-center rounded-full bg-white px-7 py-4 text-base font-black text-[#0B0B0B] shadow-[0_18px_40px_rgba(11,11,11,0.06)]"
            >
              Browse scenarios
            </a>
          </div>
        </div>

        <LiveMonitor activeScenario={activeScenario} scenarios={scenarios} setActiveId={setActiveId} />
      </section>

      <ScenarioSection scenarios={scenarios} activeId={activeId} setActiveId={setActiveId} />
      <InsightSection activeScenario={activeScenario} connected={connected} />
    </main>
  );
}

function Header({ connected }) {
  return (
    <header className="mx-auto flex max-w-7xl items-center justify-between px-5 py-6 sm:px-8 lg:px-10">
      <div className="flex items-center gap-3">
        <span className="grid size-12 place-items-center rounded-full bg-[#D9F2C7]">
          <HeartPulse size={23} strokeWidth={2.4} />
        </span>
        <span className="text-xl font-black tracking-[-0.04em]">ECAG2</span>
      </div>
      <nav className="hidden items-center gap-8 text-sm font-black text-[#5F6368] md:flex">
        <a href="#live-monitor" className="hover:text-[#0B0B0B]">
          Monitor
        </a>
        <a href="#scenarios" className="hover:text-[#0B0B0B]">
          Scenarios
        </a>
        <a href="#insights" className="hover:text-[#0B0B0B]">
          Insights
        </a>
      </nav>
      <div className="flex items-center gap-2 rounded-full bg-white px-4 py-2 text-sm font-black text-[#5F6368] shadow-[0_10px_26px_rgba(11,11,11,0.05)]">
        <span className={`size-2 rounded-full ${connected ? "bg-[#72B36A]" : "bg-[#FFE680]"}`} />
        {connected ? "GitHub data" : "Demo data"}
      </div>
    </header>
  );
}

function LiveMonitor({ activeScenario, scenarios, setActiveId }) {
  return (
    <section
      id="live-monitor"
      className="rounded-[2.25rem] bg-white p-4 shadow-[0_30px_90px_rgba(20,24,22,0.10)] sm:p-6"
    >
      <div className="rounded-[1.75rem] bg-[#F7F7F7] p-5 sm:p-7">
        <div className="flex flex-col justify-between gap-5 sm:flex-row sm:items-start">
          <div>
            <p className="text-sm font-black uppercase tracking-[0.18em] text-[#5F6368]">
              Live ECG monitor
            </p>
            <h2 className="mt-2 text-4xl font-black leading-none tracking-[-0.05em]">
              {activeScenario.rhythm}
            </h2>
          </div>
          <div className="flex gap-2">
            <IconCircle icon={Bell} />
            <IconCircle icon={Play} />
          </div>
        </div>

        <div className="mt-6 grid gap-4 lg:grid-cols-[1fr_220px]">
          <div className={`rounded-[2rem] ${scenarioColors[activeScenario.id] || "bg-[#D9F2C7]"} p-5`}>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <IconCircle icon={Activity} className="bg-white/75" />
              <span className="rounded-full bg-white/75 px-4 py-2 text-sm font-black">
                Risk {activeScenario.risk}/100
              </span>
            </div>
            <RealtimeWave scenario={activeScenario} />
          </div>

          <div className="grid grid-cols-2 gap-4 lg:grid-cols-1">
            <Metric label="Heart rate" value={activeScenario.heartRate} unit="bpm" />
            <Metric label="Events" value={activeScenario.events} unit="beats" />
            <Metric label="Sampling" value={activeScenario.rate} unit="" />
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          {scenarios.map((scenario) => (
            <button
              key={scenario.id}
              type="button"
              onClick={() => setActiveId(scenario.id)}
              className={`rounded-full px-4 py-2 text-sm font-black transition ${
                scenario.id === activeScenario.id
                  ? "bg-[#0B0B0B] text-white"
                  : "bg-white text-[#5F6368] hover:text-[#0B0B0B]"
              }`}
            >
              {scenario.id.toUpperCase()}
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}

function RealtimeWave({ scenario }) {
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
    }, 80);

    return () => window.clearInterval(timer);
  }, [scenario.ecg, scenario.fs]);

  const points = useMemo(() => {
    const data = scenario.ecg?.length ? scenario.ecg : fallbackScenarios[0].ecg;
    const windowSize = Math.min(520, data.length);
    const stride = Math.max(1, Math.floor(windowSize / 160));
    const samples = [];

    for (let i = 0; i < windowSize; i += stride) {
      samples.push(data[(cursor + i) % data.length]);
    }

    const min = Math.min(...samples);
    const max = Math.max(...samples);
    const range = max - min || 1;

    return samples
      .map((value, index) => {
        const x = (index / Math.max(samples.length - 1, 1)) * 760;
        const y = 180 - ((value - min) / range) * 135;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");
  }, [cursor, scenario.ecg]);

  return (
    <div className="mt-6 rounded-[1.6rem] bg-white/70 p-4">
      <svg viewBox="0 0 760 220" className="h-[260px] w-full" role="img" aria-label="Realtime ECG waveform">
        <defs>
          <pattern id="grid" width="38" height="38" patternUnits="userSpaceOnUse">
            <path d="M 38 0 L 0 0 0 38" fill="none" stroke="rgba(11,11,11,0.07)" strokeWidth="1" />
          </pattern>
        </defs>
        <rect width="760" height="220" rx="22" fill="url(#grid)" />
        <line x1="0" x2="760" y1="112" y2="112" stroke="rgba(11,11,11,0.14)" strokeWidth="2" />
        <polyline
          fill="none"
          points={points}
          stroke="#0B0B0B"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="4"
        />
      </svg>
    </div>
  );
}

function ScenarioSection({ scenarios, activeId, setActiveId }) {
  return (
    <section id="scenarios" className="mx-auto max-w-7xl px-5 py-12 sm:px-8 lg:px-10 lg:py-16">
      <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
        <div>
          <p className="text-sm font-black uppercase tracking-[0.18em] text-[#5F6368]">Repository data</p>
          <h2 className="mt-3 max-w-3xl text-5xl font-black leading-none tracking-[-0.05em]">
            Four ECG scenarios from GitHub.
          </h2>
        </div>
        <p className="max-w-md text-base font-medium leading-7 text-[#5F6368]">
          These cards are generated from `data/scenarios/*.npz` through the local API.
        </p>
      </div>

      <div className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {scenarios.map((scenario) => (
          <button
            key={scenario.id}
            type="button"
            onClick={() => setActiveId(scenario.id)}
            className={`rounded-[2rem] p-5 text-left shadow-[0_20px_52px_rgba(11,11,11,0.06)] transition hover:-translate-y-1 ${
              scenarioColors[scenario.id] || "bg-white"
            } ${activeId === scenario.id ? "ring-2 ring-[#0B0B0B]" : ""}`}
          >
            <IconCircle icon={Stethoscope} className="bg-white/75" />
            <h3 className="mt-8 text-2xl font-black tracking-[-0.04em]">{scenario.title}</h3>
            <p className="mt-2 text-sm font-bold text-[#5F6368]">{scenario.diagnosis}</p>
            <div className="mt-6 flex items-end justify-between">
              <div>
                <p className="text-xs font-black uppercase tracking-[0.14em] text-[#5F6368]">Risk</p>
                <p className="text-4xl font-black tracking-[-0.05em]">{scenario.risk}</p>
              </div>
              <span className="rounded-full bg-white/75 px-3 py-1 text-sm font-black">
                {scenario.status}
              </span>
            </div>
          </button>
        ))}
      </div>
    </section>
  );
}

function InsightSection({ activeScenario, connected }) {
  return (
    <section id="insights" className="mx-auto max-w-7xl px-5 pb-20 pt-8 sm:px-8 lg:px-10">
      <div className="grid gap-5 rounded-[2.5rem] bg-white p-5 shadow-[0_30px_90px_rgba(20,24,22,0.09)] lg:grid-cols-[0.9fr_1.1fr] lg:p-8">
        <div className="rounded-[2rem] bg-[#F7F7F7] p-6">
          <IconCircle icon={LineChart} className="bg-[#BFEFF4]" />
          <h2 className="mt-8 text-5xl font-black leading-none tracking-[-0.05em]">
            A web-first view for clinical demos.
          </h2>
          <p className="mt-5 text-base font-medium leading-7 text-[#5F6368]">
            We can keep improving this into a full product page, but the core is now back:
            a live ECG monitor driven by repository data.
          </p>
        </div>

        <div className="grid gap-4">
          <DataRow label="Data mode" value={connected ? "GitHub data connected" : "Demo fallback"} />
          <DataRow label="Active diagnosis" value={activeScenario.diagnosis} />
          <DataRow label="Event summary" value={activeScenario.eventType} />
          <DataRow label="Source rate" value={activeScenario.rate} />
        </div>
      </div>
    </section>
  );
}

function Metric({ label, value, unit }) {
  return (
    <article className="rounded-[1.6rem] bg-white p-5">
      <p className="text-sm font-black text-[#5F6368]">{label}</p>
      <p className="mt-3 text-3xl font-black tracking-[-0.05em]">
        {value}
        {unit && <span className="ml-2 text-sm font-black text-[#5F6368]">{unit}</span>}
      </p>
    </article>
  );
}

function DataRow({ label, value }) {
  return (
    <div className="flex flex-col justify-between gap-2 rounded-[1.5rem] bg-[#F7F7F7] p-5 sm:flex-row sm:items-center">
      <span className="text-sm font-black text-[#5F6368]">{label}</span>
      <strong className="text-lg font-black tracking-[-0.03em]">{value}</strong>
    </div>
  );
}

function Pill({ icon: Icon, text }) {
  return (
    <span className="inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 text-sm font-black text-[#5F6368] shadow-[0_12px_30px_rgba(11,11,11,0.05)]">
      <Icon size={16} strokeWidth={2.5} />
      {text}
    </span>
  );
}

function IconCircle({ icon: Icon, className = "bg-white" }) {
  return (
    <span className={`grid size-12 place-items-center rounded-full ${className}`}>
      <Icon size={21} strokeWidth={2.35} />
    </span>
  );
}

export default App;
