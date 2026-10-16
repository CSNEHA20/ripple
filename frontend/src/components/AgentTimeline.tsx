import React, { useState, useMemo } from 'react';
import {
  Activity,
  AlertTriangle,
  User,
  Search,
  Share2,
  FileText,
  Copy,
  Check,
  ListTree,
  Brain,
  Wrench,
  type LucideIcon,
} from 'lucide-react';
import type { SSEEvent } from '../api';

interface AgentTimelineProps {
  events: SSEEvent[];
  activePhase: string;
  selectedNodeFilter?: string | null;
  onClearNodeFilter?: () => void;
}

interface TimelineItem {
  time: string;
  type: string;
  title: string;
  desc: string;
  cypher?: string;
  tag: string;
  latency?: string;
  icon: LucideIcon;
  tone: 'red' | 'orange' | 'blue' | 'green' | 'violet';
}

const TONES: Record<TimelineItem['tone'], string> = {
  red: 'text-rose-500 bg-rose-500/10 border-rose-500/40 shadow-[0_0_18px_-4px_rgba(244,63,94,0.7)]',
  orange: 'text-orange-500 bg-orange-500/10 border-orange-500/40 shadow-[0_0_18px_-4px_rgba(249,115,22,0.6)]',
  blue: 'text-sky-500 bg-sky-500/10 border-sky-500/40 shadow-[0_0_18px_-4px_rgba(14,165,233,0.6)]',
  green: 'text-emerald-500 bg-emerald-500/10 border-emerald-500/40 shadow-[0_0_18px_-4px_rgba(16,185,129,0.6)]',
  violet: 'text-violet-500 bg-violet-500/10 border-violet-500/40 shadow-[0_0_18px_-4px_rgba(139,92,246,0.6)]',
};

const DEFAULT_TIMELINE_ITEMS: TimelineItem[] = [
  {
    time: '14:24:17',
    type: 'incident_opened',
    title: 'Incident opened',
    desc: 'High HTTP 500 error rate on checkout payment authorize (paymentservice)',
    tag: 'System',
    icon: AlertTriangle,
    tone: 'red',
  },
  {
    time: '14:24:18',
    type: 'agent_started',
    title: 'Agent triage_agent started role [triage]',
    desc: 'Classifying incident and identifying affected services.',
    tag: 'Triage',
    icon: User,
    tone: 'orange',
  },
  {
    time: '14:24:19',
    type: 'tool_called',
    title: 'Tool called blast_radius executed (found 4 items)',
    desc: '',
    cypher: "MATCH (s:Service {name: 'paymentservice'})-[:DEPENDS_ON*1..3]->(d)\nRETURN d.name, d.type, d.criticality",
    tag: 'Investigator',
    latency: '1.2s',
    icon: Search,
    tone: 'blue',
  },
  {
    time: '14:24:20',
    type: 'tool_called',
    title: 'Tool called criticality_ranking executed',
    desc: 'Calculated PageRank-based impact scores for affected services.',
    tag: 'Investigator',
    latency: '0.8s',
    icon: Share2,
    tone: 'blue',
  },
  {
    time: '14:24:21',
    type: 'similar_found',
    title: 'Found similar incidents (5 items)',
    desc: 'Retrieved historical incidents with similar symptoms.',
    tag: 'Investigator',
    latency: '0.6s',
    icon: FileText,
    tone: 'violet',
  },
];

// Lightweight Cypher syntax highlighting
const CYPHER_KEYWORDS = /\b(MATCH|RETURN|WHERE|WITH|ORDER BY|LIMIT|CREATE|MERGE|OPTIONAL|AS|AND|OR|NOT|IN)\b/g;
const HighlightedCypher: React.FC<{ code: string }> = ({ code }) => {
  const parts = code.split(/(\b(?:MATCH|RETURN|WHERE|WITH|ORDER BY|LIMIT|CREATE|MERGE|OPTIONAL|AS|AND|OR|NOT|IN)\b|'[^']*'|\[[^\]]*\]|:[A-Za-z_]+)/g);
  return (
    <>
      {parts.map((p, i) => {
        if (!p) return null;
        if (CYPHER_KEYWORDS.test(p)) {
          CYPHER_KEYWORDS.lastIndex = 0;
          return <span key={i} className="text-[#ff6339] font-bold">{p}</span>;
        }
        CYPHER_KEYWORDS.lastIndex = 0;
        if (p.startsWith("'")) return <span key={i} className="text-emerald-400">{p}</span>;
        if (p.startsWith('[') || p.startsWith(':')) return <span key={i} className="text-sky-400">{p}</span>;
        return <span key={i}>{p}</span>;
      })}
    </>
  );
};

const FILTERS = ['all', 'system', 'triage', 'investigator', 'responder', 'verifier'] as const;

export const AgentTimeline: React.FC<AgentTimelineProps> = ({
  events,
  activePhase: _activePhase,
  selectedNodeFilter,
  onClearNodeFilter,
}) => {
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);

  const handleCopy = (text: string, idx: number) => {
    navigator.clipboard.writeText(text);
    setCopiedIndex(idx);
    setTimeout(() => setCopiedIndex(null), 2000);
  };

  const timelineData: TimelineItem[] = useMemo(() => {
    if (events.length > 0) {
      return events.map((ev, idx) => {
        const timeStr = new Date(ev.ts * 1000).toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
        const d = ev.data || {};
        const name = ev.event;
        const isTool = name.includes('tool');
        const isOpen = name.includes('incident');
        const isHyp = name.includes('hypoth');
        const isRespond = name.includes('action') || name.includes('respond');
        const isVerify = name.includes('verif');
        const tag = isVerify ? 'Verifier' : isRespond ? 'Responder' : name.includes('triage') || (name.includes('agent') && d.role === 'triage') ? 'Triage' : isTool || isHyp || name.includes('evidence') ? 'Investigator' : 'System';
        const title = isTool && d.tool ? `Tool called ${d.tool}` : name.replace(/_/g, ' ').replace(/^\w/, (c: string) => c.toUpperCase());
        return {
          time: timeStr,
          type: name,
          title,
          desc: typeof d === 'string' ? d : d.text || d.summary || (isHyp ? `${d.count} hypotheses ranked` : JSON.stringify(d)),
          cypher: d.cypher,
          tag,
          latency: d.latency || (isTool ? `${(0.4 + idx * 0.2).toFixed(1)}s` : undefined),
          icon: isTool ? Search : isOpen ? AlertTriangle : isHyp ? Brain : isRespond ? Wrench : User,
          tone: isOpen ? 'red' : isTool ? 'blue' : isHyp ? 'violet' : isVerify ? 'green' : 'orange',
        } as TimelineItem;
      });
    }
    return DEFAULT_TIMELINE_ITEMS;
  }, [events]);

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: timelineData.length };
    timelineData.forEach((i) => {
      const k = i.tag.toLowerCase();
      c[k] = (c[k] || 0) + 1;
    });
    return c;
  }, [timelineData]);

  const filteredItems = useMemo(() => {
    if (selectedCategory === 'all') return timelineData;
    return timelineData.filter((item) => item.tag.toLowerCase() === selectedCategory);
  }, [timelineData, selectedCategory]);

  return (
    <div className="surface flex flex-col overflow-hidden anim-fade-up" style={{ ['--i' as string]: 3 }}>
      <div className="panel-head flex-wrap">
        <div className="flex items-center gap-3">
          <span className="panel-icon"><Activity size={15} /></span>
          <div>
            <h2 className="panel-title leading-none">Agent Activity Timeline &amp; Cypher Traces</h2>
            <span className="panel-sub block mt-1">{filteredItems.length} events · streamed from the agent crew</span>
          </div>
          <span className="chip chip-green chip-mono !text-[10px] tracking-wide">
            <span className="live-dot !w-1.5 !h-1.5" /> LIVE SSE
          </span>
        </div>

        <div className="flex items-center gap-1.5 flex-wrap">
          {selectedNodeFilter && (
            <button onClick={onClearNodeFilter} className="chip chip-orange cursor-pointer" title="Clear graph filter">
              {selectedNodeFilter} ✕
            </button>
          )}
          <div className="seg !flex-wrap">
            {FILTERS.map((f) => (
              <button key={f} className="seg-item !capitalize" data-active={selectedCategory === f} onClick={() => setSelectedCategory(f)}>
                {f}
                <span className={`text-[10px] px-1.5 rounded-md font-bold ${selectedCategory === f ? 'bg-black/20' : 'bg-[var(--bg-inset)]'}`}>
                  {counts[f] || 0}
                </span>
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="px-5 py-5 max-h-[460px] overflow-y-auto">
        {filteredItems.length === 0 ? (
          <div className="py-12 text-center text-[var(--text-muted)]">
            <ListTree size={28} className="mx-auto mb-2 opacity-50" />
            <p className="text-sm font-medium">No events in this phase yet</p>
          </div>
        ) : (
          <ol className="relative">
            {filteredItems.map((item, idx) => {
              const Icon = item.icon;
              const last = idx === filteredItems.length - 1;
              return (
                <li key={`${item.time}-${idx}`} className="relative flex gap-4 pb-6 last:pb-0 anim-fade-up" style={{ ['--i' as string]: Math.min(idx, 8) }}>
                  <span className="font-mono text-[11.5px] text-[var(--text-muted)] w-[62px] shrink-0 pt-1.5 text-right font-medium tabular-nums">
                    {item.time}
                  </span>

                  {/* Rail + node */}
                  <div className="relative flex flex-col items-center shrink-0">
                    <span className={`w-8 h-8 rounded-full grid place-items-center border z-10 bg-[var(--bg-card)] ${TONES[item.tone]}`}>
                      <Icon size={14} />
                    </span>
                    {!last && <span className="absolute top-8 -bottom-6 w-px bg-gradient-to-b from-[var(--border-strong)] to-[var(--border-subtle)]" />}
                  </div>

                  <div className="flex-1 min-w-0 pt-1">
                    <div className="flex items-start justify-between gap-3 flex-wrap">
                      <span className="font-semibold text-[13.5px] text-[var(--text-primary)] leading-snug">{item.title}</span>
                      <div className="flex items-center gap-2 shrink-0">
                        <span className="chip !text-[10.5px] !py-0.5">{item.tag}</span>
                        {item.latency && <span className="font-mono text-[11px] text-[var(--text-muted)] tabular-nums">{item.latency}</span>}
                      </div>
                    </div>

                    {item.desc && <p className="text-[12.5px] text-[var(--text-secondary)] mt-1 leading-relaxed">{item.desc}</p>}

                    {item.cypher && (
                      <div className="mt-2.5 rounded-xl bg-[var(--bg-inset)] border border-[var(--border-default)] overflow-hidden">
                        <div className="flex items-center justify-between px-3 py-1.5 border-b border-[var(--border-subtle)] bg-black/10">
                          <span className="text-[10px] font-bold tracking-widest uppercase text-[var(--text-muted)]">Cypher · FalkorDB</span>
                          <button
                            onClick={() => handleCopy(item.cypher!, idx)}
                            className="flex items-center gap-1.5 text-[11px] font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
                            title="Copy Cypher query"
                          >
                            {copiedIndex === idx ? (
                              <><Check size={12} className="text-emerald-400" /> Copied</>
                            ) : (
                              <><Copy size={12} /> Copy</>
                            )}
                          </button>
                        </div>
                        <pre className="font-mono text-[11.5px] text-[var(--text-secondary)] overflow-x-auto whitespace-pre leading-relaxed p-3 select-all">
                          <HighlightedCypher code={item.cypher} />
                        </pre>
                      </div>
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </div>
    </div>
  );
};
