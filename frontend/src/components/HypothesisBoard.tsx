import React from 'react';
import { Flame, CheckCircle2, XCircle, FileText, Clock, ChevronRight, Crown } from 'lucide-react';
import type { HypothesisItem, HypothesisEvidence } from '../api';

interface HypothesisBoardProps {
  hypotheses: HypothesisItem[];
  selectedHypothesisId: string | null;
  onSelectHypothesis: (id: string) => void;
  pendingEvidenceRequest?: any;
  onInspectEvidence?: (ev: HypothesisEvidence) => void;
}

interface DisplayHypothesisItem {
  id: string;
  rank: number;
  title: string;
  service: string;
  level: 'high' | 'medium' | 'low';
  confidenceBadge: string;
  score: number;
  progressPercent: number;
  desc: string;
  supporting: number;
  contradicting: number;
  sources: number;
  timeAgo: string;
  rawEvidence?: HypothesisEvidence;
}

const LEVEL_STYLE = {
  high: { chip: 'chip-red', stroke: '#ff4d2d', from: '#ff4d2d', to: '#f97316' },
  medium: { chip: 'chip-amber', stroke: '#f59e0b', from: '#f59e0b', to: '#fbbf24' },
  low: { chip: '', stroke: '#64748b', from: '#64748b', to: '#94a3b8' },
} as const;

const Ring: React.FC<{ percent: number; color: string; score: number }> = ({ percent, color, score }) => {
  const r = 24;
  const len = 2 * Math.PI * r;
  return (
    <div className="relative w-[62px] h-[62px] shrink-0">
      <svg viewBox="0 0 60 60" className="w-full h-full -rotate-90">
        <circle cx="30" cy="30" r={r} fill="none" stroke="var(--border-default)" strokeWidth="5" />
        <circle
          cx="30"
          cy="30"
          r={r}
          fill="none"
          stroke={color}
          strokeWidth="5"
          strokeLinecap="round"
          strokeDasharray={len}
          strokeDashoffset={len - (len * percent) / 100}
          style={{ ['--ring-len' as string]: len, animation: 'ringDraw 1.2s cubic-bezier(0.16,1,0.3,1) both', filter: `drop-shadow(0 0 5px ${color}88)` }}
        />
      </svg>
      <div className="absolute inset-0 grid place-items-center">
        <span className="font-mono text-[13px] font-bold text-[var(--text-primary)] tabular-nums">{score.toFixed(2)}</span>
      </div>
    </div>
  );
};

export const HypothesisBoard: React.FC<HypothesisBoardProps> = ({
  hypotheses,
  selectedHypothesisId,
  onSelectHypothesis,
  onInspectEvidence,
}) => {
  const defaultHypotheses: DisplayHypothesisItem[] = [
    {
      id: 'hyp_1', rank: 1, title: 'Database connection pool exhaustion', service: 'paymentservice',
      level: 'high', confidenceBadge: 'High confidence', score: 0.78, progressPercent: 78,
      desc: 'Increased DB connection usage, timeouts in logs, and recent deployment match the incident pattern.',
      supporting: 4, contradicting: 1, sources: 3, timeAgo: '12m ago',
    },
    {
      id: 'hyp_2', rank: 2, title: 'Recent deployment in paymentservice', service: 'paymentservice',
      level: 'medium', confidenceBadge: 'Medium', score: 0.61, progressPercent: 61,
      desc: 'Deployment 12 minutes ago introduced changes to payment authorization flow.',
      supporting: 3, contradicting: 1, sources: 4, timeAgo: '12m ago',
    },
    {
      id: 'hyp_3', rank: 3, title: 'External payment provider latency', service: 'paymentservice',
      level: 'low', confidenceBadge: 'Low', score: 0.42, progressPercent: 42,
      desc: 'Increased latency from provider, but not enough evidence to fully explain 500 errors.',
      supporting: 2, contradicting: 2, sources: 2, timeAgo: '18m ago',
    },
  ];

  const items: DisplayHypothesisItem[] =
    hypotheses.length > 0
      ? hypotheses.map((h, idx) => {
          const score = h.evidence_score || 0.5;
          const level = score >= 0.7 ? 'high' : score >= 0.5 ? 'medium' : 'low';
          return {
            id: h.id,
            rank: idx + 1,
            title: h.statement || `Hypothesis for ${h.service}`,
            service: h.service,
            level,
            confidenceBadge: level === 'high' ? 'High confidence' : level === 'medium' ? 'Medium' : 'Low',
            score: Number(score.toFixed(2)),
            progressPercent: Math.round(score * 100),
            desc: h.statement,
            supporting: h.supporting_evidence?.length || 2,
            contradicting: h.contradicting_evidence?.length || 0,
            sources: (h.supporting_evidence?.length || 0) + (h.contradicting_evidence?.length || 0),
            timeAgo: 'Just now',
            rawEvidence: h.supporting_evidence?.[0],
          } as DisplayHypothesisItem;
        })
      : defaultHypotheses;

  return (
    <div className="surface flex flex-col overflow-hidden anim-fade-up" style={{ ['--i' as string]: 3 }}>
      <div className="panel-head">
        <div className="flex items-center gap-3">
          <span className="panel-icon"><Flame size={15} /></span>
          <div>
            <h2 className="panel-title leading-none">Ranked Hypotheses &amp; Evidence Engine</h2>
            <span className="panel-sub block mt-1">Click a card to focus the graph &amp; inspect evidence</span>
          </div>
        </div>
        <span className="chip chip-mono">{items.length} hypotheses</span>
      </div>

      <div className="p-4 space-y-3">
        {items.map((item, idx) => {
          const isSelected = selectedHypothesisId === item.id;
          const st = LEVEL_STYLE[item.level];
          return (
            <div
              key={item.id}
              onClick={() => {
                onSelectHypothesis(item.id);
                if (item.rawEvidence) onInspectEvidence?.(item.rawEvidence);
              }}
              className={`group relative p-4 rounded-2xl border transition-all duration-300 cursor-pointer flex items-center gap-4 anim-fade-up overflow-hidden ${
                isSelected
                  ? 'bg-[var(--bg-tertiary)] border-[#ff4d2d]/60 shadow-[0_0_0_1px_rgba(255,77,45,0.25),0_16px_40px_-16px_rgba(255,77,45,0.5)]'
                  : 'bg-[var(--bg-inset)]/60 border-[var(--border-default)] hover:border-[var(--border-strong)] hover:bg-[var(--bg-tertiary)] hover:-translate-y-0.5'
              }`}
              style={{ ['--i' as string]: idx + 4 }}
            >
              {isSelected && <span className="absolute left-0 top-0 bottom-0 w-1 bg-gradient-to-b from-[#ff6339] to-[#f97316]" />}

              <Ring percent={item.progressPercent} color={st.stroke} score={item.score} />

              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1 flex-wrap">
                  <span className="text-[10.5px] font-bold text-[var(--text-muted)] tracking-wider">#{item.rank}</span>
                  {item.rank === 1 && (
                    <span className="flex items-center gap-1 text-[10px] font-bold text-amber-500 uppercase tracking-wider">
                      <Crown size={11} /> Top
                    </span>
                  )}
                  <span className={`chip ${st.chip} !text-[10.5px] !py-0.5 ml-auto`}>{item.confidenceBadge}</span>
                </div>
                <h3 className="text-[14px] font-bold text-[var(--text-primary)] leading-snug">{item.title}</h3>
                <p className="text-[12px] text-[var(--text-secondary)] leading-relaxed mt-1 line-clamp-2">{item.desc}</p>

                <div className="h-1 rounded-full bg-[var(--border-default)] overflow-hidden mt-3">
                  <div
                    className="h-full rounded-full bar-grow"
                    style={{ width: `${item.progressPercent}%`, background: `linear-gradient(90deg, ${st.from}, ${st.to})` }}
                  />
                </div>

                <div className="flex items-center gap-2 mt-3 flex-wrap">
                  <span className="chip chip-green !text-[10.5px] !py-0.5"><CheckCircle2 size={11} /> {item.supporting} supporting</span>
                  <span className="chip chip-red !text-[10.5px] !py-0.5"><XCircle size={11} /> {item.contradicting} contradicting</span>
                  <span className="chip !text-[10.5px] !py-0.5"><FileText size={11} /> {item.sources} sources</span>
                  <span className="flex items-center gap-1 text-[11px] text-[var(--text-muted)] ml-auto">
                    <Clock size={11} /> {item.timeAgo}
                  </span>
                </div>
              </div>

              <ChevronRight size={18} className="shrink-0 text-[var(--text-dim)] group-hover:text-[#ff4d2d] group-hover:translate-x-1 transition-all" />
            </div>
          );
        })}
      </div>
    </div>
  );
};
