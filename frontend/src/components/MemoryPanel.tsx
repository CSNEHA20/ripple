import React, { useState } from 'react';
import { BookOpen, ArrowRight, ChevronDown, Layers, CheckCircle2, Zap, History, ShieldCheck } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { MemoryRecallData } from '../api';

interface MemoryPanelProps {
  memoryData: MemoryRecallData | null;
  hasHypotheses: boolean;
  onExecuteRunbook?: () => void;
  isExecuting?: boolean;
}

export const MemoryPanel: React.FC<MemoryPanelProps> = ({
  memoryData,
  hasHypotheses: _hasHypotheses,
  onExecuteRunbook,
  isExecuting,
}) => {
  const [isWhyExpanded, setIsWhyExpanded] = useState(false);

  const sim = memoryData?.similar_incidents?.[0];
  const rb = memoryData?.recommended_runbook;

  const simId = sim?.incident_id || 'INC-3127';
  const simTitle = sim?.title || 'Paymentservice DB connection pool exhaustion';
  const simScore = Math.round(((sim?.similarity ?? sim?.score ?? 0.92) as number) * 100);
  const rbTitle = rb?.title || 'Increase DB connection pool size';
  const rbRate = Math.round((rb?.historical_success_rate ?? 0.86) * 100);

  return (
    <div className="surface flex flex-col overflow-hidden anim-fade-up" style={{ ['--i' as string]: 5 }}>
      <div className="panel-head">
        <div className="flex items-center gap-3">
          <span className="panel-icon"><BookOpen size={15} /></span>
          <div>
            <h2 className="panel-title leading-none">Graph Memory &amp; Runbook</h2>
            <span className="panel-sub block mt-1">Episodic &amp; procedural memory</span>
          </div>
        </div>
        <span className="chip chip-violet"><History size={11} /> Recall</span>
      </div>

      <div className="p-4 space-y-5">
        {/* Similar incident */}
        <div className="space-y-2.5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-[12.5px] font-semibold text-[var(--text-primary)]">
              <Layers size={14} className="text-[var(--text-muted)]" />
              Similar historical incident found
            </div>
            <button className="flex items-center gap-1 text-[11.5px] font-medium text-[var(--text-muted)] hover:text-[#ff4d2d] transition-colors group">
              View all <ArrowRight size={12} className="group-hover:translate-x-0.5 transition-transform" />
            </button>
          </div>

          <div className="surface-interactive surface !rounded-2xl p-4 space-y-3 !bg-[var(--bg-inset)]/60">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <div className="flex items-center gap-2.5 min-w-0">
                <span className="chip chip-mono font-bold !text-[var(--text-primary)]">{simId}</span>
                <span className="text-[13px] font-bold text-[var(--text-primary)] truncate">{simTitle}</span>
              </div>
              <span className="chip chip-green">Resolved</span>
            </div>

            <div className="flex items-center gap-3">
              <div className="flex-1 h-1.5 rounded-full bg-[var(--border-default)] overflow-hidden">
                <div className="h-full rounded-full bar-grow bg-gradient-to-r from-violet-500 to-fuchsia-400" style={{ width: `${simScore}%` }} />
              </div>
              <span className="font-mono text-xs font-bold text-[var(--text-primary)] tabular-nums">{simScore}% match</span>
            </div>

            <p className="text-[12.5px] text-[var(--text-secondary)] leading-relaxed">
              High latency and 500 errors due to exhausted DB connection pool during peak checkout traffic.
            </p>

            <div className="flex items-center gap-1.5 flex-wrap">
              {['paymentservice', 'database', 'connection-pool', 'high-traffic'].map((tag) => (
                <span key={tag} className="chip chip-mono !text-[10.5px] !py-0.5">{tag}</span>
              ))}
              <span className="text-[11px] text-[var(--text-muted)] ml-auto">Aug 14, 2026</span>
            </div>
          </div>
        </div>

        {/* Runbook */}
        <div className="space-y-2.5">
          <div className="flex items-center gap-2 text-[12.5px] font-semibold text-[var(--text-primary)]">
            <Zap size={14} className="text-[#ff4d2d]" />
            Recommended runbook
          </div>

          <div className="relative p-4 rounded-2xl border border-[#ff4d2d]/30 overflow-hidden bg-gradient-to-br from-[#ff4d2d]/[0.09] via-transparent to-transparent">
            <div className="absolute -top-10 -right-10 w-32 h-32 rounded-full bg-[#ff4d2d]/20 blur-3xl pointer-events-none" />
            <div className="relative flex items-start justify-between gap-4 flex-wrap">
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-[14px] font-bold text-[var(--text-primary)]">{rbTitle}</span>
                  <span className="chip chip-amber !py-0.5"><span className="w-1.5 h-1.5 rounded-full bg-amber-500" />Recommended</span>
                </div>
                <p className="text-[12.5px] text-[var(--text-secondary)] leading-relaxed mt-1.5 max-w-md">
                  Previous similar incident resolved by increasing the connection pool from 100 to 200. No schema changes required.
                </p>
              </div>

              <Button
                size="sm"
                onClick={onExecuteRunbook}
                disabled={isExecuting}
                className={`btn-ripple-primary h-10 px-6 text-[13px] gap-2 shrink-0 ${isExecuting ? 'is-loading' : ''}`}
              >
                <Zap size={13} fill="currentColor" />
                {isExecuting ? 'Applying…' : 'Apply'}
              </Button>
            </div>

            <div className="relative mt-3 flex items-center gap-2">
              <ShieldCheck size={13} className="text-emerald-500" />
              <span className="text-[11.5px] text-[var(--text-secondary)]">
                <b className="text-emerald-500">{rbRate}%</b> historical success rate · requires human approval
              </span>
            </div>

            <button
              onClick={() => setIsWhyExpanded(!isWhyExpanded)}
              className="relative mt-3 flex items-center gap-1.5 text-[12px] font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
            >
              <ChevronDown size={13} className={`transition-transform duration-300 ${isWhyExpanded ? 'rotate-180' : '-rotate-90'}`} />
              Why this recommendation?
            </button>

            <div className={`grid transition-all duration-300 ${isWhyExpanded ? 'grid-rows-[1fr] mt-2.5' : 'grid-rows-[0fr]'}`}>
              <div className="overflow-hidden">
                <div className="inset-well p-3 text-[12px] text-[var(--text-secondary)] space-y-1.5">
                  <div className="flex items-center gap-1.5 text-emerald-500 font-semibold">
                    <CheckCircle2 size={13} />
                    Historical success rate: {rbRate}% across 5 matching incidents
                  </div>
                  <div>Graph analysis confirms zero schema regressions or unverified database dependency changes since sprint 42.</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
