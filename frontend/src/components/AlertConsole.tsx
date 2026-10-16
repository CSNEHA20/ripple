import React from 'react';
import {
  Activity,
  Play,
  RefreshCw,
  FolderOpen,
  ChevronDown,
  Radio,
  Check,
  Flame,
  Timer,
  ShieldAlert,
  Search,
  Wrench,
  BadgeCheck,
  Database,
  Quote,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { ScenarioItem } from '../api';

interface AlertConsoleProps {
  currentIncidentId: string;
  scenarios: ScenarioItem[];
  selectedScenarioId: string;
  onOpenScenarioDrawer: () => void;
  customAlertText: string;
  onChangeCustomAlertText: (text: string) => void;
  customService: string;
  onChangeCustomService: (svc: string) => void;
  tenant: string;
  onChangeTenant: (tenant: string) => void;
  mode: 'replay' | 'live';
  onToggleMode: (m: 'replay' | 'live') => void;
  isRunning: boolean;
  onRunCrew: () => void;
  healthOk: boolean;
  activePhase: string;
  elapsedSeconds: number;
  hasHypotheses: boolean;
}

const PHASES = [
  { id: 'triage', label: 'Triage', icon: ShieldAlert, desc: 'Classify & scope' },
  { id: 'investigator', label: 'Investigate', icon: Search, desc: 'Rank hypotheses' },
  { id: 'responder', label: 'Respond', icon: Wrench, desc: 'Propose safe fix' },
  { id: 'verifier', label: 'Verify', icon: BadgeCheck, desc: 'Confirm recovery' },
];

export const AlertConsole: React.FC<AlertConsoleProps> = ({
  currentIncidentId,
  scenarios,
  selectedScenarioId,
  onOpenScenarioDrawer,
  customAlertText,
  customService,
  tenant,
  onChangeTenant,
  mode,
  onToggleMode,
  isRunning,
  onRunCrew,
  healthOk,
  activePhase,
  elapsedSeconds,
  hasHypotheses,
}) => {
  const selectedScenario = scenarios.find((s) => s.id === selectedScenarioId);

  const formatTimer = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
  };

  const phaseIdx = Math.max(0, PHASES.findIndex((p) => p.id === activePhase));
  const reached = isRunning ? phaseIdx : hasHypotheses ? Math.max(phaseIdx, 1) : -1;

  const stateLabel = isRunning ? 'Crew in progress' : hasHypotheses ? 'Root cause identified' : 'Idle · ready for crew';
  const stateTone = isRunning ? 'chip-orange' : hasHypotheses ? 'chip-green' : '';

  return (
    <section className="surface overflow-hidden anim-fade-up" style={{ ['--i' as string]: 0 }}>
      {/* Ambient concentric ripples */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden rounded-[inherit]" aria-hidden>
        <div className="absolute -top-24 -right-16 w-[520px] h-[520px] bg-[radial-gradient(circle_at_center,rgba(255,77,45,0.28),rgba(249,115,22,0.1)_40%,transparent_68%)]" />
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="absolute top-[70px] right-[130px] w-52 h-52 rounded-full border border-[#ff4d2d]/40"
            style={{ animation: 'ping-ring 5s ease-out infinite', animationDelay: `${i * 1.6}s` }}
          />
        ))}
        <svg className="absolute inset-0 w-full h-full opacity-[0.5]" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="none">
          <defs>
            <linearGradient id="hdrLine" x1="0" x2="1">
              <stop offset="0" stopColor="#ff4d2d" stopOpacity="0" />
              <stop offset="0.7" stopColor="#ff4d2d" stopOpacity="0.5" />
              <stop offset="1" stopColor="#f97316" stopOpacity="0" />
            </linearGradient>
          </defs>
          <rect x="0" y="0" width="100%" height="1" fill="url(#hdrLine)" />
        </svg>
      </div>

      <div className="relative z-10 p-6 lg:p-7 space-y-6">
        {/* Title row */}
        <div className="flex items-start justify-between gap-6 flex-wrap">
          <div className="flex items-center gap-4 min-w-0">
            <div className="relative w-14 h-14 rounded-2xl grid place-items-center text-[#ff4d2d] bg-gradient-to-br from-[#ff4d2d]/20 to-[#f97316]/5 border border-[#ff4d2d]/30 shadow-[0_0_40px_-8px_rgba(255,77,45,0.6)]">
              <Activity size={26} />
              {isRunning && <span className="absolute inset-0 rounded-2xl border border-[#ff4d2d] animate-ping opacity-40" />}
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2.5 mb-1.5 flex-wrap">
                <span className="eyebrow">Incident command</span>
                <span className={`chip ${stateTone}`}>
                  {isRunning && <span className="live-dot !w-1.5 !h-1.5" />}
                  {stateLabel}
                </span>
              </div>
              <h1 className="text-[28px] font-extrabold tracking-tight text-[var(--text-primary)] leading-none">
                Incident <span className="gradient-text">Investigation</span>
              </h1>
              <p className="text-[13px] text-[var(--text-muted)] font-medium mt-2">
                Investigate, explain and resolve incidents using your company&apos;s graph.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2.5 flex-wrap">
            <button onClick={onOpenScenarioDrawer} className="btn-soft h-10">
              <FolderOpen size={14} className="text-[#ff4d2d]" />
              Load scenario
            </button>
            <Button
              size="sm"
              onClick={onRunCrew}
              disabled={isRunning}
              className={`btn-ripple-primary h-10 px-5 text-[13px] gap-2 ${isRunning ? 'is-loading' : ''}`}
            >
              {isRunning ? <RefreshCw size={14} className="animate-spin" /> : <Play size={13} fill="currentColor" />}
              <span>{isRunning ? 'Running…' : 'Run Agent Crew'}</span>
            </Button>
          </div>
        </div>

        {/* KPI tiles */}
        <div className="grid grid-cols-2 xl:grid-cols-4 gap-3">
          <div className="inset-well p-4">
            <div className="eyebrow mb-2">Incident</div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-lg font-bold text-[var(--text-primary)]">{currentIncidentId || 'INC-4029'}</span>
              <ChevronDown size={14} className="text-[var(--text-muted)]" />
            </div>
            <div className="font-mono text-xs font-semibold text-[#ff4d2d] mt-1.5 truncate">{customService || 'paymentservice'}</div>
          </div>

          <div className="inset-well p-4 relative overflow-hidden">
            <div className="absolute inset-0 bg-gradient-to-br from-rose-500/10 to-transparent" />
            <div className="eyebrow mb-2 relative">Severity</div>
            <div className="flex items-center gap-2 relative">
              <Flame size={20} className="text-rose-500" />
              <span className="text-lg font-extrabold text-rose-500 tracking-tight">P1</span>
            </div>
            <div className="text-xs font-semibold text-[var(--text-secondary)] mt-1.5 relative">High error rate</div>
          </div>

          <div className="inset-well p-4">
            <div className="eyebrow mb-2">{isRunning ? 'Elapsed' : 'Time to triage'}</div>
            <div className="flex items-center gap-2">
              <Timer size={18} className="text-[var(--text-muted)]" />
              <span className="font-mono text-lg font-bold text-[var(--text-primary)] tabular-nums">{formatTimer(elapsedSeconds)}</span>
            </div>
            <div className="text-xs font-semibold text-[var(--text-secondary)] mt-1.5 uppercase tracking-wide">
              {isRunning ? activePhase : hasHypotheses ? 'Complete' : 'Awaiting run'}
            </div>
          </div>

          <div className="inset-well p-4">
            <div className="eyebrow mb-2">Suspected blast radius</div>
            <div className="flex items-center gap-2">
              <Radio size={18} className="text-[#ff4d2d] animate-pulse" />
              <span className="text-lg font-extrabold text-[var(--text-primary)]">4</span>
              <span className="text-xs font-semibold text-[var(--text-secondary)]">services impacted</span>
            </div>
            <div className="flex mt-2 -space-x-1.5">
              {['p', 'c', 'a', 'x'].map((l, i) => (
                <span
                  key={i}
                  className={`w-5 h-5 rounded-full border-2 border-[var(--bg-inset)] grid place-items-center text-[8px] font-bold text-white ${i === 0 ? 'bg-rose-500' : 'bg-orange-500'}`}
                >
                  {l.toUpperCase()}
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* Pipeline stepper */}
        <div className="grid grid-cols-4 gap-2 sm:gap-3">
          {PHASES.map((p, i) => {
            const Icon = p.icon;
            const done = i < reached || (!isRunning && hasHypotheses && i <= reached && i < 1);
            const active = isRunning ? i === phaseIdx : i === reached && hasHypotheses;
            return (
              <div key={p.id} className="relative">
                <div
                  className={`relative flex items-center gap-3 p-3 rounded-2xl border transition-all duration-500 ${
                    active
                      ? 'border-[#ff4d2d]/60 bg-[#ff4d2d]/10 shadow-[0_0_30px_-8px_rgba(255,77,45,0.6)]'
                      : done
                      ? 'border-emerald-500/30 bg-emerald-500/[0.06]'
                      : 'border-[var(--border-default)] bg-[var(--bg-inset)]'
                  }`}
                >
                  <span
                    className={`w-9 h-9 rounded-xl grid place-items-center shrink-0 transition-colors ${
                      active
                        ? 'bg-gradient-to-br from-[#ff4d2d] to-[#f97316] text-white'
                        : done
                        ? 'bg-emerald-500/20 text-emerald-500'
                        : 'bg-[var(--bg-tertiary)] text-[var(--text-muted)]'
                    }`}
                  >
                    {done ? <Check size={16} /> : <Icon size={16} className={active && isRunning ? 'animate-pulse' : ''} />}
                  </span>
                  <span className="min-w-0 hidden sm:block">
                    <span className={`block text-[13px] font-bold leading-tight ${active || done ? 'text-[var(--text-primary)]' : 'text-[var(--text-secondary)]'}`}>{p.label}</span>
                    <span className="block text-[11px] text-[var(--text-muted)] leading-tight mt-0.5 truncate">{p.desc}</span>
                  </span>
                  {active && isRunning && <span className="absolute left-4 right-4 bottom-0 h-[2px] rounded-full overflow-hidden"><span className="block h-full w-full skeleton !rounded-none bg-[#ff4d2d]" /></span>}
                </div>
              </div>
            );
          })}
        </div>

        {/* Alert context */}
        <div className="flex flex-col lg:flex-row lg:items-stretch gap-3">
          <div className="flex-1 min-w-0 flex items-start gap-3 p-4 rounded-2xl bg-[var(--bg-inset)] border border-[var(--border-default)]">
            <Quote size={18} className="text-[#ff4d2d] shrink-0 mt-0.5" />
            <div className="min-w-0">
              <p className="text-[14px] font-semibold text-[var(--text-primary)] leading-snug">
                {customAlertText || 'High HTTP 500 error rate on checkout payment authorize'}
              </p>
              <div className="flex items-center gap-2 mt-2.5 flex-wrap">
                <span className="chip chip-mono">{selectedScenario?.id || 'sc_repeated_01'}</span>
                <span className="chip chip-cyan chip-mono uppercase tracking-wide">{selectedScenario?.family || 'repeated'}</span>
                <span className="chip chip-mono text-[#ff4d2d]">{customService || 'paymentservice'}</span>
              </div>
            </div>
          </div>

          <div className="flex lg:flex-col gap-2.5 lg:w-[260px] flex-wrap lg:flex-nowrap">
            <div className="relative flex-1">
              <select
                value={tenant}
                onChange={(e) => onChangeTenant(e.target.value)}
                className="field appearance-none !pr-9 !py-2.5 !text-xs font-semibold cursor-pointer"
              >
                <option value="storefront">Env: tenant_storefront (Prod)</option>
                <option value="payments">Env: tenant_payments (Finance)</option>
                <option value="smoke">Env: tenant_smoke (Test)</option>
              </select>
              <ChevronDown size={13} className="absolute right-3.5 top-1/2 -translate-y-1/2 pointer-events-none text-[var(--text-muted)]" />
            </div>
            <div className="flex items-center gap-2 flex-1">
              <span className={`chip ${healthOk ? 'chip-green' : 'chip-amber'} flex-1 justify-center py-2`}>
                <Database size={12} />
                FalkorDB {healthOk ? 'connected' : 'connecting'}
              </span>
              <button
                onClick={() => onToggleMode(mode === 'replay' ? 'live' : 'replay')}
                className="chip chip-mono cursor-pointer hover:border-[#ff4d2d]/50 flex-1 justify-center py-2"
                title="Toggle replay cache / live LLM"
              >
                {mode === 'replay' ? 'Replay cache' : 'Live LLM'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};
