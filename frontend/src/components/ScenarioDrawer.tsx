import React, { useState, useMemo, useEffect, useRef } from 'react';
import { X, Search, AlertTriangle, FolderOpen, CornerDownLeft, Layers, CheckCircle2, ArrowUp, ArrowDown } from 'lucide-react';
import type { ScenarioItem } from '../api';

interface ScenarioDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  scenarios: ScenarioItem[];
  selectedScenarioId: string;
  onSelectScenario: (id: string) => void;
}

const FAMILY_CHIP: Record<string, string> = {
  repeated: 'chip-blue',
  variant: 'chip-amber',
  novel: 'chip-cyan',
  stale_trap: 'chip-red',
  trap: 'chip-red',
  misleading: 'chip-violet',
  misleading_memory: 'chip-violet',
};

export const ScenarioDrawer: React.FC<ScenarioDrawerProps> = ({
  isOpen,
  onClose,
  scenarios,
  selectedScenarioId,
  onSelectScenario,
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedFamily, setSelectedFamily] = useState<string>('all');
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const families = useMemo(() => {
    const fams = new Set<string>();
    scenarios.forEach((s) => s.family && fams.add(s.family));
    return Array.from(fams);
  }, [scenarios]);

  const filteredScenarios = useMemo(() => {
    const q = searchTerm.toLowerCase();
    return scenarios.filter((sc) => {
      const matchesSearch =
        sc.id.toLowerCase().includes(q) ||
        sc.description.toLowerCase().includes(q) ||
        sc.alert.service.toLowerCase().includes(q) ||
        sc.alert.text.toLowerCase().includes(q);
      return matchesSearch && (selectedFamily === 'all' || sc.family === selectedFamily);
    });
  }, [scenarios, searchTerm, selectedFamily]);

  useEffect(() => {
    if (isOpen) {
      setCursor(0);
      setTimeout(() => inputRef.current?.focus(), 30);
    }
  }, [isOpen]);

  useEffect(() => setCursor(0), [searchTerm, selectedFamily]);

  useEffect(() => {
    listRef.current?.querySelector<HTMLElement>(`[data-idx="${cursor}"]`)?.scrollIntoView({ block: 'nearest' });
  }, [cursor]);

  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
      else if (e.key === 'ArrowDown') {
        e.preventDefault();
        setCursor((c) => Math.min(c + 1, Math.max(filteredScenarios.length - 1, 0)));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setCursor((c) => Math.max(c - 1, 0));
      } else if (e.key === 'Enter') {
        const sc = filteredScenarios[cursor];
        if (sc) {
          onSelectScenario(sc.id);
          onClose();
        }
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isOpen, filteredScenarios, cursor, onClose, onSelectScenario]);

  if (!isOpen) return null;

  return (
    <div className="overlay flex items-start justify-center pt-[9vh] px-4" onClick={onClose}>
      <div
        className="modal w-[720px] max-w-full max-h-[78vh] flex flex-col overflow-hidden text-[var(--text-primary)]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Search */}
        <div className="flex items-center gap-3 px-5 py-4 border-b border-[var(--border-default)]">
          <Search size={18} className="text-[#ff4d2d] shrink-0" />
          <input
            ref={inputRef}
            type="text"
            placeholder="Search scenarios by ID, service or symptom…"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="flex-1 bg-transparent outline-none text-[15px] font-medium placeholder:text-[var(--text-muted)]"
          />
          <kbd className="kbd">ESC</kbd>
          <button onClick={onClose} className="icon-btn !w-8 !h-8"><X size={16} /></button>
        </div>

        {/* Families */}
        <div className="flex items-center gap-1.5 px-5 py-3 overflow-x-auto border-b border-[var(--border-subtle)] bg-[var(--bg-inset)]/50">
          <FolderOpen size={14} className="text-[var(--text-muted)] shrink-0 mr-1" />
          {['all', ...families].map((fam) => {
            const count = fam === 'all' ? scenarios.length : scenarios.filter((s) => s.family === fam).length;
            const active = selectedFamily === fam;
            return (
              <button
                key={fam}
                onClick={() => setSelectedFamily(fam)}
                className={`chip capitalize cursor-pointer transition-all ${active ? '!bg-gradient-to-r !from-[#ff4d2d] !to-[#f97316] !text-white !border-transparent' : 'hover:border-[var(--border-strong)]'}`}
              >
                {fam.replace(/_/g, ' ')} <span className="opacity-70">{count}</span>
              </button>
            );
          })}
        </div>

        {/* List */}
        <div ref={listRef} className="flex-1 overflow-y-auto p-3 space-y-1.5">
          {filteredScenarios.length === 0 ? (
            <div className="py-16 text-center text-[var(--text-muted)]">
              <Layers size={30} className="mx-auto mb-2 opacity-50" />
              <p className="text-sm font-medium">No scenarios match your search</p>
            </div>
          ) : (
            filteredScenarios.map((sc, i) => {
              const isSelected = selectedScenarioId === sc.id;
              const isCursor = cursor === i;
              return (
                <div
                  key={sc.id}
                  data-idx={i}
                  onMouseEnter={() => setCursor(i)}
                  onClick={() => {
                    onSelectScenario(sc.id);
                    onClose();
                  }}
                  className={`group p-4 rounded-2xl border transition-all cursor-pointer ${
                    isCursor
                      ? 'bg-[var(--bg-tertiary)] border-[#ff4d2d]/50 shadow-[0_8px_30px_-12px_rgba(255,77,45,0.5)]'
                      : 'border-transparent hover:bg-[var(--bg-tertiary)]/60'
                  }`}
                >
                  <div className="flex items-center justify-between gap-3 mb-2">
                    <div className="flex items-center gap-2 flex-wrap min-w-0">
                      <span className="chip chip-orange chip-mono">{sc.id}</span>
                      <span className={`chip uppercase tracking-wide !text-[10px] ${FAMILY_CHIP[sc.family?.toLowerCase()] || ''}`}>{sc.family?.replace(/_/g, ' ')}</span>
                      <span className="font-mono text-xs font-semibold text-[var(--text-secondary)]">{sc.alert.service}</span>
                    </div>
                    {isSelected ? (
                      <span className="flex items-center gap-1 text-xs text-[#ff4d2d] font-bold shrink-0"><CheckCircle2 size={14} /> Active</span>
                    ) : (
                      <span className={`flex items-center gap-1 text-[11px] text-[var(--text-muted)] shrink-0 transition-opacity ${isCursor ? 'opacity-100' : 'opacity-0'}`}>
                        Load <CornerDownLeft size={12} />
                      </span>
                    )}
                  </div>
                  <p className="text-[13px] font-semibold text-[var(--text-primary)] leading-snug">{sc.description}</p>
                  <div className="mt-2.5 flex items-start gap-2 text-[12px] text-[var(--text-secondary)] leading-relaxed">
                    <AlertTriangle size={13} className="text-amber-500 shrink-0 mt-0.5" />
                    <span>{sc.alert.text}</span>
                  </div>
                  {sc.ground_truth && (
                    <div className="mt-2.5 pt-2.5 border-t border-[var(--border-subtle)] flex items-center gap-4 flex-wrap text-[11px] text-[var(--text-muted)]">
                      <span>Root cause <code className="font-mono text-[var(--text-primary)]">{sc.ground_truth.root_cause_service}</code></span>
                      <span>Runbook <code className="font-mono text-[var(--text-primary)]">{sc.ground_truth.correct_runbook}</code></span>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-[var(--border-default)] bg-[var(--bg-inset)]/60 flex items-center justify-between text-[11.5px] text-[var(--text-muted)]">
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1.5"><kbd className="kbd"><ArrowUp size={10} /></kbd><kbd className="kbd"><ArrowDown size={10} /></kbd> navigate</span>
            <span className="flex items-center gap-1.5"><kbd className="kbd"><CornerDownLeft size={10} /></kbd> load</span>
          </div>
          <span>Loading a scenario seeds the graph &amp; alert.</span>
        </div>
      </div>
    </div>
  );
};
