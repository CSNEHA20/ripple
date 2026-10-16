import React, { useState } from 'react';
import {
  Activity,
  GitCompare,
  BarChart2,
  Sparkles,
  Layers,
  AlertCircle,
  Database,
  BookOpen,
  Users,
  FileText,
  Settings,
  ChevronDown,
  PanelLeftClose,
  PanelLeftOpen,
  type LucideIcon,
} from 'lucide-react';

export type ViewId =
  | 'incident'
  | 'counterfactual'
  | 'benchmark'
  | 'services'
  | 'incidents'
  | 'memory'
  | 'runbooks'
  | 'people'
  | 'docs'
  | 'settings';

interface SidebarProps {
  activeTab: ViewId;
  onChangeTab: (tab: ViewId) => void;
  onOpenAskBrain: () => void;
  tenant: string;
  onChangeTenant: (t: string) => void;
  healthOk: boolean;
}

interface NavEntry {
  id: ViewId;
  icon: LucideIcon;
  label: string;
  hint?: string;
}

const WORKSPACE_NAV: NavEntry[] = [
  { id: 'incident', icon: Activity, label: 'Incident Investigation', hint: 'Live' },
  { id: 'counterfactual', icon: GitCompare, label: 'Counterfactual (What-If)' },
  { id: 'benchmark', icon: BarChart2, label: 'Benchmark & Calibration' },
];

const SYSTEM_NAV: NavEntry[] = [
  { id: 'services', icon: Layers, label: 'Services' },
  { id: 'incidents', icon: AlertCircle, label: 'Incidents' },
  { id: 'memory', icon: Database, label: 'Memory' },
  { id: 'runbooks', icon: BookOpen, label: 'Runbooks' },
  { id: 'people', icon: Users, label: 'People' },
  { id: 'docs', icon: FileText, label: 'Docs & PRs' },
  { id: 'settings', icon: Settings, label: 'Settings' },
];

const RippleMark: React.FC<{ size?: number }> = ({ size = 30 }) => (
  <svg width={size} height={size} viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="M4 16C4 9.37258 9.37258 4 16 4" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
    <path d="M8 16C8 11.5817 11.5817 8 16 8" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
    <path d="M12 16C12 13.7909 13.7909 12 16 12" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
    <circle cx="16" cy="16" r="2.2" fill="currentColor" />
    <path d="M16 28C22.6274 28 28 22.6274 28 16" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
    <path d="M16 24C20.4183 24 24 20.4183 24 16" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
  </svg>
);

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  onChangeTab,
  onOpenAskBrain,
  tenant,
  onChangeTenant,
  healthOk,
}) => {
  const [collapsed, setCollapsed] = useState(false);

  const renderItem = (item: NavEntry) => {
    const Icon = item.icon;
    return (
      <button
        key={item.id}
        data-active={activeTab === item.id}
        onClick={() => onChangeTab(item.id)}
        title={collapsed ? item.label : undefined}
        className={`nav-item ${collapsed ? 'justify-center !px-0' : ''}`}
      >
        <Icon size={17} className="shrink-0" />
        {!collapsed && <span className="truncate flex-1">{item.label}</span>}
        {!collapsed && item.hint && (
          <span className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider opacity-80">
            <span className="live-dot !w-1.5 !h-1.5 text-emerald-400" />
          </span>
        )}
      </button>
    );
  };

  return (
    <aside
      className={`ripple-sidebar ${collapsed ? 'w-[76px]' : 'w-[272px]'} shrink-0 h-screen sticky top-0 flex flex-col justify-between px-4 py-5 z-30 select-none overflow-y-auto overflow-x-hidden`}
    >
      <div className="space-y-7">
        {/* Brand */}
        <div className={`flex items-center ${collapsed ? 'justify-center' : 'gap-3 px-1'}`}>
          <div className="relative w-11 h-11 rounded-2xl grid place-items-center shrink-0 text-[var(--sidebar-logo-color)] bg-white/[0.06] border border-white/10 shadow-[0_0_28px_-6px_rgba(255,77,45,0.6)]">
            <RippleMark size={26} />
          </div>
          {!collapsed && (
            <div className="min-w-0">
              <div className="font-extrabold text-[19px] tracking-tight leading-none text-[var(--sidebar-text)]">Ripple</div>
              <div className="text-[9.5px] font-bold tracking-[0.18em] text-[var(--sidebar-text-muted)] mt-1.5 uppercase">
                Reliability Intelligence
              </div>
            </div>
          )}
        </div>

        {/* Ask Brain CTA */}
        <button
          onClick={onOpenAskBrain}
          title="Ask Company Brain"
          className={`group relative w-full flex items-center ${collapsed ? 'justify-center p-2.5' : 'gap-3 px-3.5 py-3'} rounded-2xl overflow-hidden border border-white/15 bg-gradient-to-br from-white/[0.12] to-white/[0.03] hover:from-white/[0.2] transition-all text-[var(--sidebar-text)]`}
        >
          <span className="absolute -right-6 -top-6 w-20 h-20 rounded-full bg-[#ff4d2d]/30 blur-2xl group-hover:bg-[#ff4d2d]/50 transition-colors" />
          <span className="relative w-8 h-8 rounded-xl grid place-items-center bg-gradient-to-br from-[#ff4d2d] to-[#f97316] text-white shadow-lg shrink-0">
            <Sparkles size={16} />
          </span>
          {!collapsed && (
            <span className="relative text-left min-w-0">
              <span className="block text-[13px] font-bold leading-tight">Ask Company Brain</span>
              <span className="block text-[11px] text-[var(--sidebar-text-muted)] leading-tight mt-0.5">Graph-grounded Q&amp;A</span>
            </span>
          )}
        </button>

        <nav className="space-y-1.5">
          {!collapsed && <div className="px-3 pb-1 text-[10px] font-bold uppercase tracking-[0.16em] text-[var(--sidebar-text-muted)] opacity-70">Workspace</div>}
          {WORKSPACE_NAV.map(renderItem)}
        </nav>

        <nav className="space-y-1">
          {!collapsed && <div className="px-3 pb-1 text-[10px] font-bold uppercase tracking-[0.16em] text-[var(--sidebar-text-muted)] opacity-70">System</div>}
          {SYSTEM_NAV.map(renderItem)}
        </nav>
      </div>

      {/* Bottom */}
      <div className="space-y-3 pt-6">
        {!collapsed && (
          <div className="p-3 rounded-2xl bg-black/20 border border-[var(--sidebar-border)] backdrop-blur">
            <div className="flex items-center justify-between mb-2.5">
              <span className="flex items-center gap-2 text-[12px] font-bold text-[var(--sidebar-text)]">
                <Database size={13} /> FalkorDB
              </span>
              <span className={`flex items-center gap-1.5 text-[10.5px] font-semibold ${healthOk ? 'text-emerald-400' : 'text-amber-300'}`}>
                <span className="live-dot !w-1.5 !h-1.5" />
                {healthOk ? 'Connected' : 'Connecting…'}
              </span>
            </div>
            <div className="relative">
              <select
                value={tenant}
                onChange={(e) => onChangeTenant(e.target.value)}
                className="w-full appearance-none bg-black/30 border border-white/10 hover:border-white/25 rounded-xl px-3 py-2 text-xs text-[var(--sidebar-text)] font-mono outline-none cursor-pointer pr-8 transition-colors"
              >
                <option value="storefront">tenant_storefront (Prod)</option>
                <option value="payments">tenant_payments (Finance)</option>
                <option value="smoke">tenant_smoke (Test)</option>
              </select>
              <ChevronDown size={13} className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none text-[var(--sidebar-text-muted)]" />
            </div>
          </div>
        )}

        <div className={`flex items-center ${collapsed ? 'flex-col gap-3' : 'justify-between'} p-2 rounded-2xl hover:bg-white/5 transition-colors`}>
          <div className="flex items-center gap-3 min-w-0">
            <div className="relative w-9 h-9 rounded-full bg-gradient-to-br from-[#ff6339] to-[#e11d48] grid place-items-center font-bold text-sm text-white shadow-lg shrink-0">
              V
              <span className="absolute -right-0.5 -bottom-0.5 w-3 h-3 rounded-full bg-emerald-400 border-2 border-[#0e1017]" />
            </div>
            {!collapsed && (
              <div className="text-left min-w-0">
                <div className="text-[13px] font-bold leading-none text-[var(--sidebar-text)]">Vishal</div>
                <div className="text-[10.5px] text-[var(--sidebar-text-muted)] mt-1 leading-none font-mono truncate">vishal@ripple.dev</div>
              </div>
            )}
          </div>
          <button
            onClick={() => setCollapsed((c) => !c)}
            className="p-1.5 rounded-lg text-[var(--sidebar-text-muted)] hover:text-[var(--sidebar-text)] hover:bg-white/10 transition-colors"
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
          </button>
        </div>
      </div>
    </aside>
  );
};
