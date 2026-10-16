import React from 'react';
import { Search, Sun, Moon, Play, RefreshCw, Bell, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface TopNavProps {
  theme: 'dark' | 'light';
  onToggleTheme: () => void;
  isRunning: boolean;
  onRunCrew: () => void;
  onOpenSearch?: () => void;
  viewTitle?: string;
  mode?: 'replay' | 'live';
  onToggleMode?: (m: 'replay' | 'live') => void;
  tenant?: string;
}

export const TopNav: React.FC<TopNavProps> = ({
  theme,
  onToggleTheme,
  isRunning,
  onRunCrew,
  onOpenSearch,
  viewTitle = 'Incident Investigation',
  mode = 'replay',
  onToggleMode,
  tenant = 'storefront',
}) => {
  return (
    <header className="h-16 px-7 flex items-center justify-between gap-6 sticky top-0 z-20 glass border-x-0 border-t-0">
      {/* Breadcrumb */}
      <div className="hidden md:flex items-center gap-2 text-[13px] min-w-0 shrink-0">
        <span className="text-[var(--text-muted)] font-medium">tenant_{tenant}</span>
        <ChevronRight size={13} className="text-[var(--text-dim)]" />
        <span className="font-semibold text-[var(--text-primary)] truncate">{viewTitle}</span>
      </div>

      {/* Command search */}
      <button
        onClick={onOpenSearch}
        className="group flex-1 max-w-xl flex items-center gap-3 px-4 h-10 rounded-xl bg-[var(--bg-inset)] border border-[var(--border-default)] hover:border-[var(--accent-orange-border)] hover:shadow-[0_0_0_4px_rgba(255,77,45,0.08)] transition-all text-left"
      >
        <Search size={15} className="text-[var(--text-muted)] group-hover:text-[var(--accent-orange)] transition-colors shrink-0" />
        <span className="flex-1 text-[13px] text-[var(--text-muted)] truncate">Search services, incidents, people, docs…</span>
        <span className="flex items-center gap-1 shrink-0">
          <kbd className="kbd">Ctrl</kbd>
          <kbd className="kbd">K</kbd>
        </span>
      </button>

      <div className="flex items-center gap-2.5 shrink-0">
        {/* Replay / Live segmented */}
        <div className="seg hidden lg:inline-flex" role="tablist" aria-label="Execution mode">
          <button className="seg-item" data-active={mode === 'replay'} onClick={() => onToggleMode?.('replay')}>
            Replay
          </button>
          <button className="seg-item" data-active={mode === 'live'} onClick={() => onToggleMode?.('live')}>
            <span className={`live-dot !w-1.5 !h-1.5 ${mode === 'live' ? 'text-white' : 'text-rose-500'}`} />
            Live
          </button>
        </div>

        <button className="icon-btn relative" title="Notifications">
          <Bell size={16} />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-[#ff4d2d] ring-2 ring-[var(--bg-primary)]" />
        </button>

        {/* Theme toggle */}
        <button
          onClick={onToggleTheme}
          className="relative w-[62px] h-9 rounded-full bg-[var(--bg-tertiary)] border border-[var(--border-default)] hover:border-[var(--border-strong)] transition-colors"
          title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
          aria-label="Toggle theme"
        >
          <span
            className="absolute top-[3px] w-[28px] h-[28px] rounded-full bg-gradient-to-br from-[#ff4d2d] to-[#f97316] shadow-[0_4px_14px_-2px_rgba(255,77,45,0.7)] transition-all duration-300"
            style={{ left: theme === 'dark' ? 'calc(100% - 31px)' : '3px' }}
          />
          <Sun size={13} className={`absolute left-[9px] top-1/2 -translate-y-1/2 transition-colors ${theme === 'light' ? 'text-white' : 'text-[var(--text-muted)]'}`} />
          <Moon size={13} className={`absolute right-[9px] top-1/2 -translate-y-1/2 transition-colors ${theme === 'dark' ? 'text-white' : 'text-[var(--text-muted)]'}`} />
        </button>

        <Button
          size="sm"
          onClick={onRunCrew}
          disabled={isRunning}
          className={`btn-ripple-primary h-10 px-5 text-[13px] gap-2 ${isRunning ? 'is-loading' : ''}`}
        >
          {isRunning ? (
            <>
              <RefreshCw size={14} className="animate-spin" />
              <span>Crew running…</span>
            </>
          ) : (
            <>
              <Play size={13} fill="currentColor" />
              <span>Run Agent Crew</span>
            </>
          )}
        </Button>

        {/* User Avatar */}
        <div className="w-9 h-9 rounded-full bg-gradient-to-br from-[#ff642d] to-[#ff3b20] grid place-items-center font-bold text-xs text-white shadow-md select-none shrink-0" title="Vishal (vishal@ripple.dev)">
          V
        </div>
      </div>
    </header>
  );
};
