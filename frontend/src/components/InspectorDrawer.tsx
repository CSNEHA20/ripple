import React from 'react';
import { Search, Code, Database, Layers, X, Clock, Hash } from 'lucide-react';
import type { TraceStep, HypothesisEvidence } from '../api';

interface InspectorDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  selectedStep: TraceStep | null;
  selectedEvidence: HypothesisEvidence | null;
  selectedNode: any | null;
}

const Row: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div className="flex items-start justify-between gap-4 py-2.5 border-b border-[var(--border-subtle)] last:border-0">
    <span className="text-[12px] text-[var(--text-muted)] font-medium shrink-0">{label}</span>
    <span className="text-[12.5px] text-[var(--text-primary)] text-right min-w-0 break-words">{children}</span>
  </div>
);

const Section: React.FC<{ icon: React.ReactNode; title: React.ReactNode; children: React.ReactNode }> = ({ icon, title, children }) => (
  <section className="space-y-3 anim-fade-up">
    <div className="flex items-center gap-2.5">
      <span className="panel-icon !w-7 !h-7">{icon}</span>
      <h4 className="text-[13px] font-bold text-[var(--text-primary)]">{title}</h4>
    </div>
    {children}
  </section>
);

export const InspectorDrawer: React.FC<InspectorDrawerProps> = ({
  isOpen,
  onClose,
  selectedStep,
  selectedEvidence,
  selectedNode,
}) => {
  if (!isOpen) return null;
  const empty = !selectedStep && !selectedEvidence && !selectedNode;

  return (
    <div className="overlay flex justify-end" onClick={onClose}>
      <div className="drawer w-[560px] max-w-[94vw] h-full flex flex-col" onClick={(e) => e.stopPropagation()}>
        <div className="relative px-6 py-5 border-b border-[var(--border-default)] overflow-hidden">
          <div className="absolute -top-16 -right-10 w-48 h-48 bg-[#ff4d2d]/20 rounded-full blur-3xl pointer-events-none" />
          <div className="relative flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className="w-10 h-10 rounded-2xl grid place-items-center bg-gradient-to-br from-[#ff4d2d] to-[#f97316] text-white shadow-[0_8px_24px_-6px_rgba(255,77,45,0.8)]">
                <Search size={18} />
              </span>
              <div>
                <h3 className="font-bold text-[16px] tracking-tight text-[var(--text-primary)] leading-none">Provenance Inspector</h3>
                <p className="text-[12px] text-[var(--text-muted)] mt-1.5">M10 deep trace · every fact, with its source</p>
              </div>
            </div>
            <button className="icon-btn" onClick={onClose}><X size={17} /></button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-7">
          {empty && <p className="text-sm text-[var(--text-muted)] text-center py-16">Select evidence, a trace step or a graph node to inspect it.</p>}

          {selectedStep && (
            <Section icon={<Code size={13} />} title={<>Tool invocation <code className="chip chip-orange chip-mono ml-1">{selectedStep.tool}</code></>}>
              <p className="text-[13px] text-[var(--text-secondary)] leading-relaxed">{selectedStep.summary}</p>

              {selectedStep.cypher && (
                <div className="rounded-xl bg-[var(--bg-inset)] border border-[var(--border-default)] overflow-hidden">
                  <div className="flex items-center justify-between px-3 py-2 border-b border-[var(--border-subtle)] bg-black/10">
                    <span className="text-[10px] font-bold tracking-widest uppercase text-[var(--text-muted)]">FalkorDB Cypher</span>
                    {selectedStep.duration_ms && (
                      <span className="chip chip-green chip-mono !py-0 !text-[10px]"><Clock size={10} />{selectedStep.duration_ms.toFixed(1)}ms</span>
                    )}
                  </div>
                  <pre className="font-mono text-[12px] text-[#ff8a5c] p-3.5 overflow-x-auto leading-relaxed">{selectedStep.cypher}</pre>
                </div>
              )}

              {selectedStep.params && Object.keys(selectedStep.params).length > 0 && (
                <div>
                  <div className="eyebrow mb-2">Parameters</div>
                  <pre className="inset-well font-mono text-[11.5px] text-[var(--text-secondary)] p-3 overflow-x-auto">{JSON.stringify(selectedStep.params, null, 2)}</pre>
                </div>
              )}

              <div>
                <div className="eyebrow mb-2">Touched nodes ({selectedStep.node_ids?.length || 0})</div>
                <div className="flex flex-wrap gap-1.5">
                  {selectedStep.node_ids?.map((n) => (
                    <span key={n} className="chip chip-mono !text-[10.5px]">{n}</span>
                  ))}
                </div>
              </div>
            </Section>
          )}

          {selectedEvidence && (
            <Section icon={<Database size={13} />} title="Evidence fact provenance">
              <div className="inset-well px-4 py-1">
                <Row label="Evidence ID"><code className="font-mono text-xs">{selectedEvidence.id}</code></Row>
                <Row label="Type"><span className="chip chip-cyan">{selectedEvidence.type}</span></Row>
                <Row label="Cognitive kind">
                  <span className={`chip ${selectedEvidence.kind === 'observed' ? 'chip-green' : 'chip-violet'}`}>{selectedEvidence.kind}</span>
                </Row>
                <Row label="Summary">{selectedEvidence.summary}</Row>
                {selectedEvidence.freshness !== undefined && (
                  <Row label="Freshness">
                    <span className="flex items-center gap-2 justify-end">
                      <span className="w-24 h-1.5 rounded-full bg-[var(--border-default)] overflow-hidden inline-block">
                        <span className="block h-full bg-gradient-to-r from-[#ff4d2d] to-[#f97316]" style={{ width: `${selectedEvidence.freshness * 100}%` }} />
                      </span>
                      <span className="font-mono text-xs">{(selectedEvidence.freshness * 100).toFixed(1)}%</span>
                    </span>
                  </Row>
                )}
                {selectedEvidence.source_ref && <Row label="Source"><code className="font-mono text-xs">{selectedEvidence.source_ref}</code></Row>}
              </div>
            </Section>
          )}

          {selectedNode && (
            <Section icon={<Layers size={13} />} title={<>Graph node · {selectedNode.name || selectedNode.id}</>}>
              <div className="inset-well px-4 py-1">
                {selectedNode.label && <Row label="Label"><span className="chip chip-violet">{selectedNode.label}</span></Row>}
                {selectedNode.tier && <Row label="Service tier">{selectedNode.tier}</Row>}
                {selectedNode.status && (
                  <Row label="Health"><span className={`chip ${selectedNode.status === 'healthy' ? 'chip-green' : 'chip-amber'}`}>{selectedNode.status}</span></Row>
                )}
                <Row label="ID"><span className="inline-flex items-center gap-1 font-mono text-xs"><Hash size={11} />{selectedNode.id}</span></Row>
              </div>
              <div>
                <div className="eyebrow mb-2">Raw properties</div>
                <pre className="inset-well font-mono text-[11.5px] text-[var(--text-secondary)] p-3 overflow-x-auto max-h-64">
                  {JSON.stringify(selectedNode.props || { id: selectedNode.id, name: selectedNode.name, label: selectedNode.label, tier: selectedNode.tier, status: selectedNode.status }, null, 2)}
                </pre>
              </div>
            </Section>
          )}
        </div>
      </div>
    </div>
  );
};
