import React, { useState } from 'react';
import { GitCompare, AlertTriangle, Users, Play, Layers, ArrowRight, Info } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { CounterfactualResponse } from '../api';

interface CounterfactualPanelProps {
  services: string[];
  currentIncidentId: string;
  onRunCounterfactual: (hypotheticalService: string) => Promise<CounterfactualResponse>;
  counterfactualResult: CounterfactualResponse | null;
  isLoading: boolean;
  onClose?: () => void;
}

const DiffCard: React.FC<{
  tone: 'red' | 'amber' | 'blue';
  count: number;
  label: string;
  sub: string;
  items: string[];
  idx: number;
}> = ({ tone, count, label, sub, items, idx }) => {
  const map = {
    red: { chip: 'chip-red', text: 'text-rose-500', glow: 'from-rose-500/15' },
    amber: { chip: 'chip-amber', text: 'text-amber-500', glow: 'from-amber-500/15' },
    blue: { chip: 'chip-blue', text: 'text-sky-500', glow: 'from-sky-500/15' },
  }[tone];
  return (
    <div className="relative inset-well p-4 overflow-hidden anim-fade-up" style={{ ['--i' as string]: idx }}>
      <div className={`absolute inset-0 bg-gradient-to-br ${map.glow} to-transparent pointer-events-none`} />
      <div className="relative flex items-end justify-between gap-3">
        <div>
          <div className="eyebrow">{label}</div>
          <div className="text-[11.5px] text-[var(--text-muted)] mt-0.5">{sub}</div>
        </div>
        <div className={`text-4xl font-extrabold tabular-nums leading-none ${map.text}`}>{count}</div>
      </div>
      <div className="relative flex flex-wrap gap-1.5 mt-3 min-h-[24px]">
        {items.length === 0 ? (
          <span className="text-[11.5px] text-[var(--text-dim)] italic">None</span>
        ) : (
          items.map((s) => (
            <span key={s} className={`chip chip-mono !text-[10.5px] !py-0.5 ${map.chip}`}>{s}</span>
          ))
        )}
      </div>
    </div>
  );
};

export const CounterfactualPanel: React.FC<CounterfactualPanelProps> = ({
  services,
  currentIncidentId,
  onRunCounterfactual,
  counterfactualResult,
  isLoading,
}) => {
  const uniq = Array.from(new Set(services));
  const [selectedService, setSelectedService] = useState<string>(uniq[0] || 'checkoutservice');

  const handleRun = () => {
    if (selectedService) onRunCounterfactual(selectedService);
  };

  return (
    <div className="surface flex flex-col overflow-hidden anim-fade-up" style={{ ['--i' as string]: 2 }}>
      <div className="panel-head">
        <div className="flex items-center gap-3">
          <span className="panel-icon !text-violet-500 !bg-violet-500/15 !border-violet-500/30"><GitCompare size={15} /></span>
          <div>
            <h3 className="panel-title leading-none">Counterfactual Simulator</h3>
            <span className="panel-sub block mt-1">What if a different service had failed?</span>
          </div>
        </div>
        <span className="chip chip-violet">M9 · Multi-hop reliability</span>
      </div>

      <div className="p-5 space-y-5">
        <div>
          <div className="eyebrow mb-2.5">Hypothetical service to fail instead</div>
          <div className="flex flex-wrap gap-2">
            {uniq.length === 0 && <span className="text-sm text-[var(--text-muted)]">Load a scenario to pick a service.</span>}
            {uniq.map((svc) => (
              <button
                key={svc}
                onClick={() => setSelectedService(svc)}
                className={`chip chip-mono !text-xs !px-3 !py-1.5 transition-all ${
                  selectedService === svc ? '!bg-gradient-to-r !from-[#ff4d2d] !to-[#f97316] !text-white !border-transparent shadow-[0_6px_18px_-6px_rgba(255,77,45,0.7)]' : 'hover:border-[var(--border-strong)]'
                }`}
              >
                {svc}
              </button>
            ))}
          </div>
        </div>

        <Button
          className={`btn-ripple-primary w-full h-11 text-[13.5px] gap-2 ${isLoading ? 'is-loading' : ''}`}
          onClick={handleRun}
          disabled={isLoading || !currentIncidentId}
        >
          <Play size={14} fill="currentColor" />
          <span>{isLoading ? 'Computing diff…' : 'Run What-If Diff'}</span>
          {!isLoading && <ArrowRight size={14} />}
        </Button>

        {!counterfactualResult ? (
          <div className="rounded-2xl border border-dashed border-[var(--border-strong)] p-8 text-center bg-[var(--bg-inset)]/40">
            <div className="w-12 h-12 rounded-2xl mx-auto mb-3 grid place-items-center bg-violet-500/10 text-violet-500 border border-violet-500/25">
              <Layers size={22} />
            </div>
            <p className="text-sm font-semibold text-[var(--text-primary)]">No simulation yet</p>
            <p className="text-xs text-[var(--text-muted)] mt-1 max-w-xs mx-auto leading-relaxed">
              Pick a service and run the diff. The graph will overlay observed vs hypothetical blast radius.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="grid gap-3">
              <DiffCard idx={0} tone="red" count={counterfactualResult.only_observed.length} label="Observed only" sub="Avoided in hypothetical" items={counterfactualResult.only_observed} />
              <DiffCard idx={1} tone="amber" count={counterfactualResult.both.length} label="Both impacted" sub="Shared core" items={counterfactualResult.both} />
              <DiffCard idx={2} tone="blue" count={counterfactualResult.only_hypothetical.length} label="Hypothetical only" sub="New blast" items={counterfactualResult.only_hypothetical} />
            </div>

            {counterfactualResult.uncertainty && (
              <div className="flex gap-3 p-4 rounded-2xl bg-amber-500/10 border border-amber-500/30">
                <AlertTriangle size={17} className="text-amber-500 shrink-0 mt-0.5" />
                <div>
                  <strong className="text-[13px] text-amber-500">Uncertainty: lower bound</strong>
                  <p className="text-[12px] text-[var(--text-secondary)] mt-1 leading-relaxed">{counterfactualResult.uncertainty.note}</p>
                </div>
              </div>
            )}

            {counterfactualResult.critical_owners && counterfactualResult.critical_owners.length > 0 && (
              <div>
                <div className="flex items-center gap-2 eyebrow mb-2.5"><Users size={12} /> PageRank critical owners</div>
                <div className="space-y-2">
                  {counterfactualResult.critical_owners.map((o, i) => (
                    <div key={o.service} className="inset-well px-4 py-3 flex items-center gap-3 anim-fade-up" style={{ ['--i' as string]: i }}>
                      <span className="font-mono text-[13px] font-bold text-[var(--text-primary)] flex-1 truncate">{o.service}</span>
                      <span className="chip chip-orange chip-mono !text-[10.5px]">PR {o.pagerank_score.toFixed(3)}</span>
                      <span className="text-[12px] text-[var(--text-secondary)] truncate max-w-[40%]">{o.owners?.join(', ') || 'Team SRE'}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="flex items-center gap-2 text-[11.5px] text-[var(--text-muted)]">
              <Info size={12} /> Dashed rings on the graph mark each category.
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
