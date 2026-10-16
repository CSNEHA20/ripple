import React, { useState } from 'react';
import { BarChart2, Play, CheckCircle, XCircle, ShieldCheck, ShieldAlert, Gauge, Brain, Target } from 'lucide-react';
import type { BenchmarkReportResponse } from '../api';

interface BenchmarkTabProps {
  reportData: BenchmarkReportResponse | null;
  onRunBenchmark: () => Promise<void>;
  isRunning: boolean;
}

const pct = (v?: number) => Math.round((v || 0) * 100);

const MetricCard: React.FC<{
  title: string;
  icon: React.ReactNode;
  on?: number;
  off?: number;
  invert?: boolean;
  idx: number;
  onSuffix?: string;
}> = ({ title, icon, on, off, invert, idx, onSuffix }) => {
  const onGood = invert ? 'from-emerald-500 to-emerald-400' : 'from-[#ff4d2d] to-[#f97316]';
  const offBad = invert ? 'from-rose-500 to-rose-400' : 'from-slate-500 to-slate-400';
  const delta = invert ? pct(off) - pct(on) : pct(on) - pct(off);
  return (
    <div className="surface p-5 anim-fade-up" style={{ ['--i' as string]: idx }}>
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-2.5">
          <span className="panel-icon">{icon}</span>
          <span className="text-[13px] font-bold text-[var(--text-primary)]">{title}</span>
        </div>
        <span className={`chip ${delta > 0 ? 'chip-green' : ''} chip-mono`}>{delta > 0 ? '+' : ''}{delta} pts</span>
      </div>

      <div className="flex items-end gap-2 mb-5">
        <span className="text-5xl font-extrabold tracking-tight tabular-nums gradient-text leading-none">{pct(on)}</span>
        <span className="text-xl font-bold text-[var(--text-muted)] pb-1">%</span>
        <span className="text-[11.5px] text-[var(--text-muted)] pb-1.5 ml-1">{onSuffix || 'with memory'}</span>
      </div>

      <div className="space-y-3">
        {[
          { label: 'Memory ON', v: on, grad: onGood },
          { label: 'Memory OFF', v: off, grad: offBad },
        ].map((row) => (
          <div key={row.label} className="flex items-center gap-3">
            <span className="w-[84px] text-[11.5px] font-semibold text-[var(--text-secondary)]">{row.label}</span>
            <div className="flex-1 h-2.5 rounded-full bg-[var(--bg-inset)] border border-[var(--border-subtle)] overflow-hidden">
              <div className={`h-full rounded-full bg-gradient-to-r ${row.grad} bar-grow`} style={{ width: `${pct(row.v)}%` }} />
            </div>
            <span className="w-10 text-right font-mono text-xs font-bold text-[var(--text-primary)] tabular-nums">{pct(row.v)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
};

export const BenchmarkTab: React.FC<BenchmarkTabProps> = ({ reportData, onRunBenchmark, isRunning }) => {
  const [filterFamily, setFilterFamily] = useState<string>('all');
  const bench = reportData?.benchmark;
  const summary = bench?.summary;
  const memOn = summary?.memory_on;
  const memOff = summary?.memory_off;
  const runs = bench?.runs || [];
  const filteredRuns = filterFamily === 'all' ? runs : runs.filter((r) => r.family === filterFamily);

  return (
    <div className="space-y-5">
      {/* Hero */}
      <section className="surface overflow-hidden anim-fade-up">
        <div className="absolute -top-20 right-0 w-[460px] h-[300px] bg-[radial-gradient(circle,rgba(255,77,45,0.22),transparent_65%)] pointer-events-none" />
        <div className="relative p-6 lg:p-7 flex items-center justify-between gap-6 flex-wrap">
          <div className="flex items-center gap-4">
            <div className="w-14 h-14 rounded-2xl grid place-items-center text-[#ff4d2d] bg-gradient-to-br from-[#ff4d2d]/20 to-[#f97316]/5 border border-[#ff4d2d]/30 shadow-[0_0_40px_-8px_rgba(255,77,45,0.6)]">
              <BarChart2 size={26} />
            </div>
            <div>
              <div className="flex items-center gap-2 mb-1.5">
                <span className="eyebrow">Evaluation</span>
                <span className="chip chip-mono">Protocol {bench?.benchmark_protocol_version || 'v2.0'}</span>
              </div>
              <h2 className="text-[28px] font-extrabold tracking-tight leading-none text-[var(--text-primary)]">
                Benchmark <span className="gradient-text">&amp; Calibration</span>
              </h2>
              <p className="text-[13px] text-[var(--text-muted)] font-medium mt-2">Pre-registered A/B evidence that memory improves diagnosis, safely.</p>
            </div>
          </div>

          <button
            onClick={onRunBenchmark}
            disabled={isRunning}
            className={`btn-ripple-primary h-11 px-6 text-[13px] inline-flex items-center gap-2 ${isRunning ? 'is-loading' : ''}`}
          >
            <Play size={13} fill="currentColor" />
            {isRunning ? 'Running benchmark…' : 'Run Benchmark (A/B)'}
          </button>
        </div>

        {bench?.calibration_status && (
          <div className="relative border-t border-[var(--border-default)] px-6 lg:px-7 py-4 flex items-center gap-4 flex-wrap bg-[var(--bg-inset)]/40">
            <span className={`chip ${bench.calibration_status.passed ? 'chip-green' : 'chip-amber'}`}>
              {bench.calibration_status.passed ? <ShieldCheck size={13} /> : <Gauge size={13} />}
              Calibration {bench.calibration_status.passed ? 'passed' : 'pending'}
            </span>
            <span className="text-[12.5px] text-[var(--text-secondary)]">{bench.calibration_status.basis}</span>
            <span className="text-[12px] text-[var(--text-muted)] ml-auto">
              Confidence shown only as <code className="chip chip-mono !py-0.5">{bench.calibration_status.score_label}</code>
            </span>
          </div>
        )}
      </section>

      {!summary ? (
        <div className="surface p-14 text-center anim-fade-up">
          <div className="w-16 h-16 rounded-3xl mx-auto mb-4 grid place-items-center text-[#ff4d2d] bg-[#ff4d2d]/10 border border-[#ff4d2d]/25">
            <BarChart2 size={28} />
          </div>
          <h3 className="text-lg font-bold text-[var(--text-primary)]">No benchmark report yet</h3>
          <p className="text-sm text-[var(--text-muted)] mt-1.5 max-w-sm mx-auto">Run the A/B benchmark to compare the agent crew with and without graph memory.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
          <MetricCard idx={1} title="Diagnosis correctness" icon={<Brain size={15} />} on={memOn?.diagnosis_correctness} off={memOff?.diagnosis_correctness} />
          <MetricCard idx={2} title="Recommendation correctness" icon={<Target size={15} />} on={memOn?.recommendation_correctness} off={memOff?.recommendation_correctness} />
          <MetricCard idx={3} title="Unsafe fix rate" icon={<ShieldAlert size={15} />} on={memOn?.unsafe_recommendation_rate} off={memOff?.unsafe_recommendation_rate} invert onSuffix="with memory (zero stale)" />
        </div>
      )}

      {/* Runs table */}
      <section className="surface overflow-hidden anim-fade-up" style={{ ['--i' as string]: 4 }}>
        <div className="panel-head flex-wrap">
          <div className="panel-title">
            Scenario evaluation runs <span className="chip chip-mono">{filteredRuns.length}</span>
          </div>
          <div className="seg !flex-wrap">
            {['all', 'repeated', 'variant', 'novel', 'stale_trap', 'misleading_memory'].map((f) => (
              <button key={f} className="seg-item !capitalize" data-active={filterFamily === f} onClick={() => setFilterFamily(f)}>
                {f.replace(/_/g, ' ')}
              </button>
            ))}
          </div>
        </div>

        <div className="overflow-auto max-h-[520px]">
          <table className="data-table">
            <thead>
              <tr>
                <th>Scenario</th>
                <th>Family</th>
                <th>Condition</th>
                <th>Diagnosis</th>
                <th>Recommendation</th>
                <th>Safety</th>
                <th>Tools</th>
                <th>Score</th>
              </tr>
            </thead>
            <tbody>
              {filteredRuns.length === 0 && (
                <tr>
                  <td colSpan={8} className="!py-12 text-center text-[var(--text-muted)]">No runs to display</td>
                </tr>
              )}
              {filteredRuns.map((r, idx) => (
                <tr key={`${r.scenario_id}-${r.memory_mode}-${idx}`}>
                  <td><code className="font-mono font-semibold text-[var(--text-primary)]">{r.scenario_id}</code></td>
                  <td><span className="chip chip-cyan !py-0.5 !text-[10.5px] capitalize">{r.family?.replace(/_/g, ' ')}</span></td>
                  <td><span className={`chip chip-mono !py-0.5 !text-[10.5px] ${String(r.memory_mode).includes('on') ? 'chip-orange' : ''}`}>{r.memory_mode}</span></td>
                  <td>
                    {r.diagnosis_correct ? (
                      <span className="inline-flex items-center gap-1.5 text-emerald-500 font-semibold"><CheckCircle size={14} /> Correct</span>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 text-rose-500 font-semibold"><XCircle size={14} /> Fail</span>
                    )}
                  </td>
                  <td>
                    <span className={`inline-flex items-center gap-1.5 font-semibold ${r.recommendation_correct ? 'text-emerald-500' : 'text-rose-500'}`}>
                      {r.recommendation_correct ? <CheckCircle size={14} /> : <XCircle size={14} />}
                      <span className="font-mono text-xs">{r.recommended_runbook}</span>
                    </span>
                  </td>
                  <td>{r.is_unsafe_recommendation ? <span className="chip chip-red !py-0.5 !text-[10.5px]">UNSAFE</span> : <span className="chip chip-green !py-0.5 !text-[10.5px]">SAFE</span>}</td>
                  <td className="font-mono tabular-nums">{r.tool_calls}</td>
                  <td className="font-mono font-bold text-[var(--text-primary)] tabular-nums">{r.evidence_score?.toFixed(2) || '0.00'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
};
