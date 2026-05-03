import React, { useEffect, useMemo, useState } from "react";
import {
  Activity,
  ArrowRight,
  Bell,
  Check,
  HeartPulse,
  LineChart,
  Lock,
  MessageCircle,
  ShieldCheck,
  Sparkles,
  Stethoscope,
  Waves,
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
    ecg: [-0.14, -0.2, 0.1, 0.84, -0.41, -0.33, -0.3, -0.22, -0.35, 0.92, -0.44],
  },
  {
    id: "pvc",
    title: "MIT208 PVC / short VT",
    rhythm: "Frequent PVCs with short VT",
    status: "Elevated",
    risk: "84",
    heartRate: "96",
    events: "53",
    eventType: "V / N / F markers",
    rate: "360 Hz",
    diagnosis: "Frequent PVCs with short VT",
    summary: "Frequent ventricular markers and fusion beats signal elevated review priority.",
    symbol_counts: { V: 22, N: 24, F: 5 },
    stats: { min: -1.18, max: 1.92, mean: -0.15 },
    ecg: [-0.2, 1.4, -0.8, -0.25, 0.2, -0.1, 1.6, -0.9, -0.3, 0.1, -0.2],
  },
  {
    id: "lbbb",
    title: "MIT207 severe LBBB",
    rhythm: "Severe arrhythmia with LBBB",
    status: "Review",
    risk: "71",
    heartRate: "58",
    events: "34",
    eventType: "L / V / R markers",
    rate: "360 Hz",
    diagnosis: "Severe arrhythmia with LBBB",
    summary: "Wide QRS morphology with irregular annotation clusters.",
    symbol_counts: { L: 15, V: 10, R: 4 },
    stats: { min: -1.2, max: 1.05, mean: -0.12 },
    ecg: [-0.15, -1.0, 0.3, -0.2, -0.1, 0.8, -0.6, -0.2, 0.45, -0.95, -0.1],
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
    ecg: [-0.17, 0.55, -0.4, 1.0, -1.2, 0.7, -0.95, 1.25, -0.62, 0.18, -0.2],
  },
];

const features = [
  {
    icon: HeartPulse,
    title: "Gentle ECG tracking",
    description: "Turn raw scenario signals into calm, readable cards for quick daily review.",
    color: "bg-mint",
  },
  {
    icon: Sparkles,
    title: "AI-ready insight layer",
    description: "Surface rhythm, risk, and annotation summaries without burying people in charts.",
    color: "bg-aqua",
  },
  {
    icon: ShieldCheck,
    title: "Private by design",
    description: "Keep interpretation transparent while local data powers the visual experience.",
    color: "bg-butter",
  },
  {
    icon: LineChart,
    title: "Trend-first overview",
    description: "Use clean status bands and simple curves to show what changed at a glance.",
    color: "bg-white",
  },
];

const tags = ["AI insights", "Daily tracking", "Private by design"];

function App() {
  const [scenarios, setScenarios] = useState(fallbackScenarios);
  const [activeId, setActiveId] = useState("normal");
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    let mounted = true;

    async function loadScenarios() {
      try {
        const response = await fetch(`${API_BASE}/api/scenarios`);
        if (!response.ok) throw new Error("Scenario request failed");
        const { scenarios: summaryScenarios } = await response.json();
        const detailed = await Promise.all(
          summaryScenarios.map(async (scenario) => {
            const detailResponse = await fetch(`${API_BASE}/api/scenarios/${scenario.id}`);
            return detailResponse.ok ? detailResponse.json() : scenario;
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

    loadScenarios();
    return () => {
      mounted = false;
    };
  }, []);

  const activeScenario = useMemo(
    () => scenarios.find((scenario) => scenario.id === activeId) || scenarios[0],
    [activeId, scenarios],
  );

  const averageRisk = useMemo(() => {
    const values = scenarios.map((scenario) => Number(scenario.risk)).filter(Number.isFinite);
    return Math.round(values.reduce((sum, value) => sum + value, 0) / values.length);
  }, [scenarios]);

  return (
    <main className="min-h-screen overflow-hidden font-sans text-ink">
      <SiteHeader connected={connected} />

      <section className="mx-auto grid w-full max-w-7xl grid-cols-1 gap-12 px-5 pb-16 pt-10 sm:px-8 lg:grid-cols-[0.95fr_1.05fr] lg:gap-16 lg:px-10 lg:pb-24 lg:pt-16">
        <div className="flex flex-col justify-center">
          <div className="mb-7 flex flex-wrap gap-3">
            {tags.map((tag) => (
              <span
                key={tag}
                className="rounded-full border border-black/5 bg-white px-4 py-2 text-sm font-semibold text-muted shadow-[0_8px_24px_rgba(20,20,20,0.04)]"
              >
                {tag}
              </span>
            ))}
          </div>

          <h1 className="max-w-4xl text-[3.65rem] font-black leading-[0.95] tracking-[-0.04em] text-ink sm:text-7xl lg:text-[5.7rem]">
            Softer heart data for clearer everyday decisions.
          </h1>
          <p className="mt-7 max-w-2xl text-lg leading-8 text-muted sm:text-xl">
            ECAG2 turns real ECG scenario data into a warm wellness dashboard with rhythm context,
            gentle risk cues, and clean summaries built for quick review.
          </p>

          <div className="mt-9 flex flex-col gap-3 sm:flex-row">
            <a
              href="#dashboard"
              className="inline-flex items-center justify-center gap-2 rounded-full bg-ink px-7 py-4 text-base font-bold text-white shadow-lift transition hover:-translate-y-0.5"
            >
              Explore dashboard
              <ArrowRight size={18} strokeWidth={2.4} />
            </a>
            <a
              href="#data-preview"
              className="inline-flex items-center justify-center gap-2 rounded-full border border-black/10 bg-white px-7 py-4 text-base font-bold text-ink transition hover:-translate-y-0.5"
            >
              View data signals
            </a>
          </div>
        </div>

        <DashboardPreview
          activeScenario={activeScenario}
          averageRisk={averageRisk}
          scenarios={scenarios}
          setActiveId={setActiveId}
        />
      </section>

      <FeatureSection />
      <DataPreview scenarios={scenarios} activeScenario={activeScenario} setActiveId={setActiveId} />
    </main>
  );
}

function SiteHeader({ connected }) {
  return (
    <header className="mx-auto flex w-full max-w-7xl items-center justify-between px-5 py-6 sm:px-8 lg:px-10">
      <a href="#" className="flex items-center gap-3" aria-label="ECAG2 home">
        <span className="grid size-12 place-items-center rounded-full bg-mint shadow-[inset_0_0_0_7px_rgba(255,255,255,0.75)]">
          <Activity size={22} strokeWidth={2.4} />
        </span>
        <span className="text-xl font-black tracking-[-0.03em]">ECAG2</span>
      </a>
      <div className="hidden items-center gap-7 text-sm font-bold text-muted md:flex">
        <a href="#dashboard" className="transition hover:text-ink">
          Dashboard
        </a>
        <a href="#features" className="transition hover:text-ink">
          Features
        </a>
        <a href="#data-preview" className="transition hover:text-ink">
          Data
        </a>
      </div>
      <div className="flex items-center gap-2 rounded-full bg-white px-3 py-2 text-sm font-bold text-muted shadow-[0_8px_24px_rgba(20,20,20,0.04)]">
        <span className={`size-2 rounded-full ${connected ? "bg-[#69B578]" : "bg-butter"}`} />
        {connected ? "GitHub data" : "Demo data"}
      </div>
    </header>
  );
}

function DashboardPreview({ activeScenario, averageRisk, scenarios, setActiveId }) {
  return (
    <section
      id="dashboard"
      className="rounded-5xl border border-black/5 bg-white p-4 shadow-soft sm:p-5 lg:p-6"
      aria-label="Dashboard preview"
    >
      <div className="rounded-[2rem] bg-cream p-4 sm:p-6">
        <div className="flex flex-col justify-between gap-5 sm:flex-row sm:items-center">
          <div>
            <p className="text-sm font-bold uppercase tracking-[0.16em] text-muted">Today status</p>
            <h2 className="mt-2 text-3xl font-black tracking-[-0.04em] sm:text-4xl">
              Heart wellness
            </h2>
          </div>
          <div className="flex gap-2">
            <IconBubble icon={Bell} />
            <IconBubble icon={MessageCircle} />
          </div>
        </div>

        <div className="mt-6 grid gap-4 lg:grid-cols-[1.15fr_0.85fr]">
          <div className="rounded-[2rem] bg-mint p-5 shadow-[inset_0_0_0_1px_rgba(11,11,11,0.04)]">
            <div className="flex items-start justify-between gap-4">
              <IconBubble icon={HeartPulse} className="bg-white/80" />
              <span className="rounded-full bg-white/70 px-3 py-1 text-sm font-black">
                Risk {activeScenario.risk}
              </span>
            </div>
            <h3 className="mt-8 text-2xl font-black tracking-[-0.03em]">
              {activeScenario.rhythm}
            </h3>
            <p className="mt-2 max-w-sm text-sm font-medium leading-6 text-muted">
              {activeScenario.summary}
            </p>
            <MiniEcg data={activeScenario.ecg} />
          </div>

          <div className="grid gap-4">
            <MetricTile
              label="Mood index"
              value={statusLabel(activeScenario.status)}
              helper={activeScenario.diagnosis}
              icon={Stethoscope}
              color="bg-aqua"
            />
            <MetricTile
              label="Daily reminder"
              value={`${activeScenario.events} events`}
              helper={activeScenario.eventType}
              icon={Bell}
              color="bg-butter"
            />
          </div>
        </div>

        <div className="mt-4 grid gap-4 md:grid-cols-3">
          <div className="rounded-[1.75rem] bg-white p-5">
            <p className="text-sm font-bold text-muted">Heart rate</p>
            <p className="mt-3 text-4xl font-black tracking-[-0.04em]">
              {activeScenario.heartRate}
              <span className="ml-2 text-base font-bold text-muted">bpm</span>
            </p>
          </div>
          <div className="rounded-[1.75rem] bg-white p-5">
            <p className="text-sm font-bold text-muted">Sampling</p>
            <p className="mt-3 text-4xl font-black tracking-[-0.04em]">{activeScenario.rate}</p>
          </div>
          <div className="rounded-[1.75rem] bg-white p-5">
            <p className="text-sm font-bold text-muted">Avg risk</p>
            <p className="mt-3 text-4xl font-black tracking-[-0.04em]">{averageRisk}</p>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          {scenarios.map((scenario) => (
            <button
              key={scenario.id}
              onClick={() => setActiveId(scenario.id)}
              className={`rounded-full px-4 py-2 text-sm font-black transition ${
                scenario.id === activeScenario.id
                  ? "bg-ink text-white"
                  : "bg-white text-muted hover:text-ink"
              }`}
              type="button"
            >
              {scenario.id.toUpperCase()}
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}

function IconBubble({ icon: Icon, className = "bg-white" }) {
  return (
    <span className={`grid size-12 place-items-center rounded-full ${className}`}>
      <Icon size={21} strokeWidth={2.25} />
    </span>
  );
}

function MetricTile({ label, value, helper, icon, color }) {
  return (
    <article className={`rounded-[2rem] ${color} p-5`}>
      <IconBubble icon={icon} className="bg-white/75" />
      <p className="mt-5 text-sm font-bold text-muted">{label}</p>
      <h3 className="mt-1 text-2xl font-black tracking-[-0.04em]">{value}</h3>
      <p className="mt-2 text-sm font-medium leading-6 text-muted">{helper}</p>
    </article>
  );
}

function MiniEcg({ data = [] }) {
  const points = useMemo(() => {
    const samples = data.length > 24 ? data.filter((_, index) => index % 48 === 0).slice(0, 70) : data;
    const values = samples.length ? samples : fallbackScenarios[0].ecg;
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = max - min || 1;
    return values
      .map((value, index) => {
        const x = (index / Math.max(values.length - 1, 1)) * 520;
        const y = 92 - ((value - min) / range) * 72;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");
  }, [data]);

  return (
    <div className="mt-6 rounded-[1.5rem] bg-white/65 p-3">
      <svg viewBox="0 0 520 112" className="h-28 w-full" role="img" aria-label="ECG signal preview">
        <line x1="0" y1="56" x2="520" y2="56" stroke="rgba(11,11,11,0.12)" strokeWidth="2" />
        <polyline
          className="ecg-line"
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

function FeatureSection() {
  return (
    <section id="features" className="mx-auto w-full max-w-7xl px-5 py-10 sm:px-8 lg:px-10 lg:py-16">
      <div className="flex flex-col justify-between gap-5 md:flex-row md:items-end">
        <div>
          <p className="text-sm font-black uppercase tracking-[0.18em] text-muted">Product system</p>
          <h2 className="mt-3 max-w-2xl text-4xl font-black leading-none tracking-[-0.04em] sm:text-6xl">
            Calm controls for complicated signals.
          </h2>
        </div>
        <p className="max-w-md text-base font-medium leading-7 text-muted">
          Built from ECG scenario data, designed with a wellness-tech language that feels soft,
          spacious, and trustworthy.
        </p>
      </div>

      <div className="mt-10 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {features.map((feature) => (
          <article
            key={feature.title}
            className="rounded-[2rem] border border-black/5 bg-white p-5 shadow-[0_18px_45px_rgba(20,20,20,0.05)] transition hover:-translate-y-1"
          >
            <IconBubble icon={feature.icon} className={feature.color} />
            <h3 className="mt-8 text-2xl font-black tracking-[-0.04em]">{feature.title}</h3>
            <p className="mt-3 text-sm font-medium leading-6 text-muted">{feature.description}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

function DataPreview({ scenarios, activeScenario, setActiveId }) {
  return (
    <section id="data-preview" className="mx-auto w-full max-w-7xl px-5 py-10 sm:px-8 lg:px-10 lg:py-20">
      <div className="rounded-5xl bg-white p-5 shadow-soft sm:p-8 lg:p-10">
        <div className="grid gap-10 lg:grid-cols-[0.9fr_1.1fr] lg:items-center">
          <div>
            <IconBubble icon={Waves} className="bg-aqua" />
            <h2 className="mt-7 text-4xl font-black leading-none tracking-[-0.04em] sm:text-6xl">
              Data from the ECAG2 GitHub repository.
            </h2>
            <p className="mt-5 max-w-xl text-base font-medium leading-7 text-muted">
              The page reads scenario summaries from the local API, which loads the repository
              files in `data/scenarios`. Each card reflects real sampling rates, annotations, and
              diagnosis labels.
            </p>
            <div className="mt-7 flex flex-wrap gap-3">
              <StatusPill icon={Lock} text="Local API" />
              <StatusPill icon={Check} text="Real ECG scenarios" />
            </div>
          </div>

          <div className="grid gap-3">
            {scenarios.map((scenario) => (
              <button
                key={scenario.id}
                onClick={() => setActiveId(scenario.id)}
                className={`grid gap-4 rounded-[1.75rem] border p-4 text-left transition sm:grid-cols-[1fr_140px] sm:items-center ${
                  scenario.id === activeScenario.id
                    ? "border-black/10 bg-mint"
                    : "border-black/5 bg-cream hover:bg-aqua/50"
                }`}
                type="button"
              >
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-black text-ink">{scenario.title}</span>
                    <span className="rounded-full bg-white px-3 py-1 text-xs font-black text-muted">
                      {scenario.status}
                    </span>
                  </div>
                  <p className="mt-2 text-sm font-medium leading-6 text-muted">{scenario.eventType}</p>
                </div>
                <div>
                  <div className="flex items-center justify-between text-xs font-black text-muted">
                    <span>Risk</span>
                    <span>{scenario.risk}/100</span>
                  </div>
                  <div className="mt-2 h-3 overflow-hidden rounded-full bg-white">
                    <div
                      className="h-full rounded-full bg-ink"
                      style={{ width: `${Math.min(Number(scenario.risk) || 0, 100)}%` }}
                    />
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function StatusPill({ icon: Icon, text }) {
  return (
    <span className="inline-flex items-center gap-2 rounded-full bg-cream px-4 py-2 text-sm font-black text-ink">
      <Icon size={16} strokeWidth={2.3} />
      {text}
    </span>
  );
}

function statusLabel(status) {
  const labels = {
    Stable: "Calm",
    Review: "Needs review",
    Elevated: "Elevated",
    Critical: "Critical",
  };
  return labels[status] || status;
}

export default App;
