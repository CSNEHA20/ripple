import React, { useMemo, useState } from 'react';
import {
  Layers,
  AlertCircle,
  Database,
  BookOpen,
  Users,
  FileText,
  Settings,
  Search,
  ArrowRight,
  Sun,
  Moon,
  Sparkles,
  type LucideIcon,
} from 'lucide-react';
import { getToolsList, type GraphNode, type GraphEdge, type ScenarioItem, type MemoryRecallData } from '../api';
import type { ViewId } from './Sidebar';

const ViewHero: React.FC<{ icon: LucideIcon; eyebrow: string; title: string; accent: string; sub: string; right?: React.ReactNode }> = ({
  icon: Icon,
  eyebrow,
  title,
  accent,
  sub,
  right,
}) => (
  <section className="surface overflow-hidden anim-fade-up">
    <div className="absolute -top-20 right-0 w-[460px] h-[300px] bg-[radial-gradient(circle,rgba(255,77,45,0.2),transparent_65%)] pointer-events-none" />
    <div className="relative p-6 lg:p-7 flex items-center justify-between gap-6 flex-wrap">
      <div className="flex items-center gap-4">
        <div className="w-14 h-14 rounded-2xl grid place-items-center text-[#ff4d2d] bg-gradient-to-br from-[#ff4d2d]/20 to-[#f97316]/5 border border-[#ff4d2d]/30 shadow-[0_0_40px_-8px_rgba(255,77,45,0.6)]">
          <Icon size={26} />
        </div>
        <div>
          <div className="eyebrow mb-1.5">{eyebrow}</div>
          <h2 className="text-[28px] font-extrabold tracking-tight leading-none text-[var(--text-primary)]">
            {title} <span className="gradient-text">{accent}</span>
          </h2>
          <p className="text-[13px] text-[var(--text-muted)] font-medium mt-2">{sub}</p>
        </div>
      </div>
      {right}
    </div>
  </section>
);

/* ------------------------------- Services ------------------------------- */
export const ServicesView: React.FC<{
  nodes: GraphNode[];
  edges: GraphEdge[];
  alertingService: string;
  onOpen: (node: GraphNode) => void;
}> = ({ nodes, edges, alertingService, onOpen }) => {
  const [q, setQ] = useState('');
  const degree = useMemo(() => {
    const m = new Map<string, { in: number; out: number }>();
    const get = (id: string) => m.get(id) || (m.set(id, { in: 0, out: 0 }), m.get(id)!);
    edges.forEach((e) => {
      const s = (typeof e.source === 'object' ? (e.source as any).id : e.source) as string;
      const t = (typeof e.target === 'object' ? (e.target as any).id : e.target) as string;
      get(s).out++;
      get(t).in++;
    });
    return m;
  }, [edges]);

  const rows = nodes.filter((n) => (n.name || n.id).toLowerCase().includes(q.toLowerCase()));

  return (
    <div className="space-y-5">
      <ViewHero
        icon={Layers}
        eyebrow="Service catalog"
        title="Service"
        accent="Map"
        sub={`${nodes.length} services · ${edges.length} dependencies in the live graph`}
        right={
          <div className="relative w-72 max-w-full">
            <Search size={14} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[var(--text-muted)]" />
            <input className="field !pl-10" placeholder="Filter services…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
        }
      />

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-4">
        {rows.map((n, i) => {
          const id = n.name || n.id;
          const d = degree.get(n.id) || { in: 0, out: 0 };
          const alerting = id.toLowerCase() === alertingService.toLowerCase();
          return (
            <button
              key={n.id}
              onClick={() => onOpen(n)}
              className="surface surface-interactive text-left p-5 anim-fade-up group"
              style={{ ['--i' as string]: Math.min(i, 10) }}
            >
              <div className="flex items-start justify-between gap-3">
                <span className={`w-10 h-10 rounded-xl grid place-items-center font-extrabold text-white ${alerting ? 'bg-gradient-to-br from-rose-500 to-orange-500 shadow-[0_0_24px_-4px_rgba(244,63,94,0.8)]' : 'bg-gradient-to-br from-teal-500 to-emerald-500'}`}>
                  {id.charAt(0).toUpperCase()}
                </span>
                <span className={`chip ${alerting ? 'chip-red' : 'chip-green'}`}>
                  <span className="live-dot !w-1.5 !h-1.5" />
                  {alerting ? 'Alerting' : 'Healthy'}
                </span>
              </div>
              <div className="font-mono font-bold text-[14px] text-[var(--text-primary)] mt-4 truncate">{id}</div>
              <div className="text-[12px] text-[var(--text-muted)] mt-0.5">{n.label || 'Service'}{n.tier ? ` · ${n.tier}` : ''}</div>
              <div className="flex items-center gap-4 mt-4 pt-4 border-t border-[var(--border-subtle)] text-[12px] text-[var(--text-secondary)]">
                <span><b className="text-[var(--text-primary)] tabular-nums">{d.in}</b> upstream</span>
                <span><b className="text-[var(--text-primary)] tabular-nums">{d.out}</b> downstream</span>
                <ArrowRight size={14} className="ml-auto text-[var(--text-dim)] group-hover:text-[#ff4d2d] group-hover:translate-x-1 transition-all" />
              </div>
            </button>
          );
        })}
        {rows.length === 0 && <div className="col-span-full surface p-12 text-center text-[var(--text-muted)]">No services found</div>}
      </div>
    </div>
  );
};

/* ------------------------------- Incidents ------------------------------ */
export const IncidentsView: React.FC<{
  scenarios: ScenarioItem[];
  selectedScenarioId: string;
  onLoad: (id: string) => void;
}> = ({ scenarios, selectedScenarioId, onLoad }) => (
  <div className="space-y-5">
    <ViewHero
      icon={AlertCircle}
      eyebrow="Incident library"
      title="Incident"
      accent="Scenarios"
      sub="Pre-registered outages. Load one to investigate it in the workspace."
    />
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {scenarios.map((sc, i) => {
        const active = sc.id === selectedScenarioId;
        return (
          <button
            key={sc.id}
            onClick={() => onLoad(sc.id)}
            className={`surface surface-interactive text-left p-5 anim-fade-up group ${active ? '!border-[#ff4d2d]/60' : ''}`}
            style={{ ['--i' as string]: Math.min(i, 10) }}
          >
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <div className="flex items-center gap-2">
                <span className="chip chip-orange chip-mono">{sc.id}</span>
                <span className="chip chip-cyan uppercase !text-[10px] tracking-wide">{sc.family?.replace(/_/g, ' ')}</span>
              </div>
              <span className="font-mono text-xs font-semibold text-[var(--text-secondary)]">{sc.alert.service}</span>
            </div>
            <p className="text-[14px] font-bold text-[var(--text-primary)] mt-3 leading-snug">{sc.description}</p>
            <p className="text-[12.5px] text-[var(--text-secondary)] mt-1.5 leading-relaxed">{sc.alert.text}</p>
            <div className="flex items-center mt-4 text-[12px] font-semibold text-[#ff4d2d]">
              {active ? 'Loaded in workspace' : 'Investigate'} <ArrowRight size={13} className="ml-1.5 group-hover:translate-x-1 transition-transform" />
            </div>
          </button>
        );
      })}
      {scenarios.length === 0 && <div className="col-span-full surface p-12 text-center text-[var(--text-muted)]">No scenarios loaded</div>}
    </div>
  </div>
);

/* ------------------------------- Memory --------------------------------- */
export const MemoryView: React.FC<{ memoryData: MemoryRecallData | null; onGo: () => void }> = ({ memoryData, onGo }) => {
  const sims = memoryData?.similar_incidents || [];
  const facts = memoryData?.known_facts || [];
  return (
    <div className="space-y-5">
      <ViewHero icon={Database} eyebrow="Graph memory" title="Episodic &" accent="Procedural" sub="What the crew remembers: similar incidents, known facts, runbook outcomes." />
      {!memoryData ? (
        <EmptyCard icon={Database} title="Nothing recalled yet" body="Run the agent crew on an incident to populate memory recall." cta="Go to investigation" onClick={onGo} />
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
          <div className="surface p-5 space-y-3">
            <div className="eyebrow">Similar incidents</div>
            {sims.map((s) => (
              <div key={s.incident_id} className="inset-well p-4 flex items-center gap-3">
                <span className="chip chip-mono">{s.incident_id}</span>
                <span className="text-[13px] font-semibold flex-1 truncate text-[var(--text-primary)]">{s.title || s.winning_hypothesis || 'Historical incident'}</span>
                <span className="chip chip-violet chip-mono">{Math.round(((s.similarity ?? s.score ?? 0) as number) * 100)}%</span>
              </div>
            ))}
            {sims.length === 0 && <p className="text-sm text-[var(--text-muted)]">No similar incidents.</p>}
          </div>
          <div className="surface p-5 space-y-3">
            <div className="eyebrow">Known facts</div>
            {facts.map((f) => (
              <div key={f.id} className="inset-well p-4">
                <div className="flex items-center gap-2 mb-1">
                  <span className="chip chip-mono !text-[10.5px]">{f.service}</span>
                  <span className="chip chip-cyan !text-[10.5px]">{f.kind}</span>
                </div>
                <p className="text-[12.5px] text-[var(--text-secondary)] leading-relaxed">{f.text}</p>
              </div>
            ))}
            {facts.length === 0 && <p className="text-sm text-[var(--text-muted)]">No stored facts.</p>}
          </div>
        </div>
      )}
    </div>
  );
};

/* ------------------------------- Settings ------------------------------- */
export const SettingsView: React.FC<{
  theme: 'dark' | 'light';
  onToggleTheme: () => void;
  mode: 'replay' | 'live';
  onChangeMode: (m: 'replay' | 'live') => void;
  tenant: string;
  onChangeTenant: (t: string) => void;
}> = ({ theme, onToggleTheme, mode, onChangeMode, tenant, onChangeTenant }) => {
  const [tools, setTools] = useState<any[]>([]);

  React.useEffect(() => {
    getToolsList(tenant).then(setTools).catch(() => {});
  }, [tenant]);

  return (
    <div className="space-y-5">
      <ViewHero icon={Settings} eyebrow="Preferences" title="Workspace" accent="Settings" sub="Appearance, execution mode, tenant, and MCP tools." />
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className="surface p-5 space-y-4">
          <div className="eyebrow">Appearance</div>
          <div className="seg w-full">
            <button className="seg-item flex-1 justify-center" data-active={theme === 'light'} onClick={() => theme !== 'light' && onToggleTheme()}><Sun size={13} /> Light</button>
            <button className="seg-item flex-1 justify-center" data-active={theme === 'dark'} onClick={() => theme !== 'dark' && onToggleTheme()}><Moon size={13} /> Dark</button>
          </div>
        </div>
        <div className="surface p-5 space-y-4">
          <div className="eyebrow">Execution mode</div>
          <div className="seg w-full">
            <button className="seg-item flex-1 justify-center" data-active={mode === 'replay'} onClick={() => onChangeMode('replay')}>Replay cache</button>
            <button className="seg-item flex-1 justify-center" data-active={mode === 'live'} onClick={() => onChangeMode('live')}>Live LLM</button>
          </div>
          <p className="text-[12px] text-[var(--text-muted)] leading-relaxed">Replay serves deterministic cached runs. Live calls the model.</p>
        </div>
        <div className="surface p-5 space-y-4">
          <div className="eyebrow">Tenant</div>
          <select className="field font-mono cursor-pointer" value={tenant} onChange={(e) => onChangeTenant(e.target.value)}>
            <option value="storefront">tenant_storefront (Prod)</option>
            <option value="payments">tenant_payments (Finance)</option>
            <option value="smoke">tenant_smoke (Test)</option>
          </select>
        </div>
      </div>

      <div className="surface p-6 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="eyebrow">Model Context Protocol (MCP) Tools</div>
            <h3 className="text-base font-bold text-[var(--text-primary)] mt-1">Available Agent Tools ({tools.length || 11})</h3>
          </div>
          <span className="chip chip-mono chip-cyan">MCP 2.0 / stdio</span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5">
          {(tools.length > 0 ? tools : [
            { name: 'blast_radius', description: 'Downstream traversal for failure impact.' },
            { name: 'upstream_suspects', description: 'Upstream dependencies causing alert.' },
            { name: 'recent_changes', description: 'Recent deployments and PR changes.' },
            { name: 'service_health', description: 'Real-time telemetry and metric status.' },
            { name: 'who_knows', description: 'Owner and expert recency-weighted scoring.' },
            { name: 'similar_incidents', description: 'Semantic vector similarity and graph re-rank.' },
            { name: 'criticality_ranking', description: 'PageRank topological centrality.' },
            { name: 'path_between', description: 'Shortest causal dependency path.' },
            { name: 'rank_runbooks', description: 'Laplace-smoothed outcome success rate.' },
            { name: 'check_applicability', description: 'Graph topology verification of assumptions.' },
            { name: 'counterfactual_blast', description: 'What-if failure comparative diff.' }
          ]).map((t: any) => (
            <div key={t.name} className="inset-well p-4 space-y-1.5">
              <span className="chip chip-mono !text-[11px] font-bold text-[#ff4d2d]">{t.name}</span>
              <p className="text-[12px] text-[var(--text-secondary)] leading-relaxed">{t.description}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

/* --------------------- Modules not yet wired to data -------------------- */
const MODULES: Partial<Record<ViewId, { icon: LucideIcon; eyebrow: string; title: string; accent: string; sub: string; body: string }>> = {
  runbooks: { icon: BookOpen, eyebrow: 'Procedural memory', title: 'Runbook', accent: 'Library', sub: 'Remediation playbooks and their historical success.', body: 'Runbooks are recommended inside each investigation. A standalone library is coming soon.' },
  people: { icon: Users, eyebrow: 'Ownership', title: 'People &', accent: 'Teams', sub: 'Who owns and who actually knows each service.', body: 'Ask the Company Brain "Who owns the payment service?" for live ownership answers.' },
  docs: { icon: FileText, eyebrow: 'Knowledge', title: 'Docs &', accent: 'PRs', sub: 'Documents and pull requests linked to the graph.', body: 'Cited docs appear as graph citations in Ask Company Brain. A browser view is coming soon.' },
};

const EmptyCard: React.FC<{ icon: LucideIcon; title: string; body: string; cta: string; onClick: () => void }> = ({ icon: Icon, title, body, cta, onClick }) => (
  <div className="surface p-14 text-center anim-fade-up">
    <div className="w-16 h-16 rounded-3xl mx-auto mb-4 grid place-items-center text-[#ff4d2d] bg-[#ff4d2d]/10 border border-[#ff4d2d]/25">
      <Icon size={28} />
    </div>
    <h3 className="text-lg font-bold text-[var(--text-primary)]">{title}</h3>
    <p className="text-sm text-[var(--text-muted)] mt-1.5 max-w-sm mx-auto leading-relaxed">{body}</p>
    <button className="btn-soft mt-5" onClick={onClick}>{cta} <ArrowRight size={13} /></button>
  </div>
);

export const ModuleView: React.FC<{ view: ViewId; onAskBrain: () => void }> = ({ view, onAskBrain }) => {
  const m = MODULES[view];
  if (!m) return null;
  return (
    <div className="space-y-5">
      <ViewHero icon={m.icon} eyebrow={m.eyebrow} title={m.title} accent={m.accent} sub={m.sub} />
      <EmptyCard icon={Sparkles} title="Coming soon" body={m.body} cta="Ask Company Brain" onClick={onAskBrain} />
    </div>
  );
};
