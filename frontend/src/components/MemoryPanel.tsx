import React from 'react';
import {
  Brain,
  History,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  ArrowUpRight,
  TrendingUp,
  ShieldCheck,
  Ban,
} from 'lucide-react';
import type { MemoryRecallData } from '../api';

interface MemoryPanelProps {
  memoryData: MemoryRecallData | null;
  onSelectRunbook?: (id: string) => void;
}

export const MemoryPanel: React.FC<MemoryPanelProps> = ({ memoryData, onSelectRunbook }) => {
  const similar = memoryData?.similar_incidents || [];
  const recommended = memoryData?.recommended_runbook;
  const rejected = memoryData?.rejected_runbooks || [];
  const facts = memoryData?.known_facts || [];

  return (
    <div className="memory-panel glass-panel">
      <div className="panel-header">
        <div className="panel-title-with-badge">
          <Brain size={16} className="text-cyan" />
          <h3>Graph Memory Layer</h3>
        </div>
        <span className="tenant-tag">Track 2 · Episodic, Procedural, Outcome</span>
      </div>

      <div className="memory-content-grid">
        {/* Recommended Runbook Card */}
        {recommended && (
          <div className="recommended-runbook-card">
            <div className="rec-header">
              <div className="rec-badge">
                <ShieldCheck size={14} />
                <span>Recommended Runbook</span>
              </div>
              <span className="success-rate-pill">
                {((recommended.historical_success_rate || 0.8) * 100).toFixed(0)}% Observed Success Rate
              </span>
            </div>
            <h4 className="rec-title">{recommended.title}</h4>
            <p className="rec-id">ID: <code>{recommended.id}</code></p>
            {recommended.applicable && (
              <div className="applicability-pass">
                <CheckCircle2 size={13} className="text-emerald" />
                <span>Applicability verified: all assumed dependencies exist in current graph.</span>
              </div>
            )}
          </div>
        )}

        {/* Why Not Recommended Card (Killer Feature: Stale & Failed Fixes) */}
        {rejected.length > 0 && (
          <div className="why-not-recommended-card">
            <div className="rejected-header text-amber">
              <Ban size={14} />
              <span>Why Not Recommended (Blocked Fixes)</span>
            </div>
            <div className="rejected-list">
              {rejected.map((rb) => (
                <div key={rb.id} className="rejected-item">
                  <div className="rejected-top">
                    <strong>{rb.title}</strong>
                    <code className="text-muted">{rb.id}</code>
                  </div>
                  <p className="rejected-reason text-amber">{rb.reason}</p>
                  {rb.changed_edge && (
                    <span className="invalidated-edge">
                      Invalidated edge: <code>{rb.changed_edge}</code>
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Similar Past Incidents */}
        <div className="similar-incidents-section">
          <div className="section-title-sm">
            <History size={13} />
            <span>Similar Past Incidents ({similar.length})</span>
          </div>
          <div className="similar-list">
            {similar.length === 0 ? (
              <p className="empty-subtext">No prior matching incidents found in graph memory.</p>
            ) : (
              similar.map((inc) => (
                <div key={inc.incident_id} className="similar-card">
                  <div className="similar-top">
                    <span className="inc-id">{inc.incident_id}</span>
                    {inc.score !== undefined && (
                      <span className="sim-score">{(inc.score * 100).toFixed(0)}% match</span>
                    )}
                  </div>
                  <p className="sim-title">{inc.title || 'Historical incident'}</p>
                  {inc.winning_hypothesis && (
                    <div className="sim-meta">
                      <span>Root cause: {inc.winning_hypothesis}</span>
                    </div>
                  )}
                  {inc.outcome && (
                    <div className="sim-outcome">
                      <span className={`outcome-tag ${inc.outcome}`}>{inc.outcome}</span>
                      {inc.runbook_id && <span className="sim-rb">via {inc.runbook_id}</span>}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </div>

        {/* Known Semantic Facts */}
        {facts.length > 0 && (
          <div className="semantic-facts-section">
            <div className="section-title-sm">
              <TrendingUp size={13} />
              <span>Active Semantic Observations ({facts.length})</span>
            </div>
            <div className="facts-list">
              {facts.slice(0, 4).map((f) => (
                <div key={f.id} className="fact-chip">
                  <span className="badge-observed">{f.service}</span>
                  <span className="fact-text">{f.text}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
