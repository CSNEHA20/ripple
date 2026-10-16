import React, { useState } from 'react';
import {
  GitCompare,
  AlertTriangle,
  Users,
  Route,
  Play,
  RotateCcw,
  Sparkles,
  Layers,
} from 'lucide-react';
import type { CounterfactualResponse } from '../api';

interface CounterfactualPanelProps {
  services: string[];
  currentIncidentId: string;
  onRunCounterfactual: (hypotheticalService: string) => Promise<CounterfactualResponse>;
  counterfactualResult: CounterfactualResponse | null;
  isLoading: boolean;
  onClose?: () => void;
}

export const CounterfactualPanel: React.FC<CounterfactualPanelProps> = ({
  services,
  currentIncidentId,
  onRunCounterfactual,
  counterfactualResult,
  isLoading,
  onClose,
}) => {
  const [selectedService, setSelectedService] = useState<string>(services[0] || 'checkoutservice');

  const handleRun = () => {
    if (selectedService) {
      onRunCounterfactual(selectedService);
    }
  };

  return (
    <div className="counterfactual-panel glass-panel">
      <div className="panel-header">
        <div className="panel-title-with-badge">
          <GitCompare size={16} className="text-purple" />
          <h3>Counterfactual Simulator (What-If)</h3>
        </div>
        <span className="tenant-tag">M9 Multi-Hop Reliability Engine</span>
      </div>

      <div className="cf-control-row">
        <div className="cf-input-group">
          <label className="section-label">Hypothetical Service to Fail Instead:</label>
          <select
            className="cf-select"
            value={selectedService}
            onChange={(e) => setSelectedService(e.target.value)}
          >
            {services.map((svc) => (
              <option key={svc} value={svc}>
                {svc}
              </option>
            ))}
          </select>
        </div>

        <button
          className="run-cf-btn"
          onClick={handleRun}
          disabled={isLoading || !currentIncidentId}
        >
          <Play size={14} fill="currentColor" />
          <span>{isLoading ? 'Computing Diff...' : 'Run What-If Diff'}</span>
        </button>
      </div>

      {counterfactualResult && (
        <div className="cf-results-grid">
          {/* 3-Color Overlay Summary */}
          <div className="cf-diff-summary">
            <div className="diff-card observed">
              <span className="diff-count">{counterfactualResult.only_observed.length}</span>
              <span className="diff-label">Observed Only (Avoided)</span>
              <div className="diff-tags">
                {counterfactualResult.only_observed.map((s) => (
                  <span key={s} className="tag tag-red">{s}</span>
                ))}
              </div>
            </div>

            <div className="diff-card both">
              <span className="diff-count">{counterfactualResult.both.length}</span>
              <span className="diff-label">Both Impacted (Shared Core)</span>
              <div className="diff-tags">
                {counterfactualResult.both.map((s) => (
                  <span key={s} className="tag tag-amber">{s}</span>
                ))}
              </div>
            </div>

            <div className="diff-card hypothetical">
              <span className="diff-count">{counterfactualResult.only_hypothetical.length}</span>
              <span className="diff-label">Hypothetical Only (New Blast)</span>
              <div className="diff-tags">
                {counterfactualResult.only_hypothetical.map((s) => (
                  <span key={s} className="tag tag-blue">{s}</span>
                ))}
              </div>
            </div>
          </div>

          {/* Uncertainty Lower-Bound Warning */}
          {counterfactualResult.uncertainty && (
            <div className="cf-uncertainty-banner">
              <AlertTriangle size={15} className="text-amber" />
              <div className="banner-text">
                <strong>Uncertainty Assessment: Lower Bound</strong>
                <p>{counterfactualResult.uncertainty.note}</p>
              </div>
            </div>
          )}

          {/* Critical Owners ranked by PageRank */}
          {counterfactualResult.critical_owners && (
            <div className="critical-owners-section">
              <div className="section-title-sm">
                <Users size={13} />
                <span>PageRank Critical Owners in Affected Region</span>
              </div>
              <div className="owners-table">
                {counterfactualResult.critical_owners.map((ownerItem) => (
                  <div key={ownerItem.service} className="owner-row">
                    <span className="owner-svc">{ownerItem.service}</span>
                    <span className="owner-pr">PR: {ownerItem.pagerank_score.toFixed(3)}</span>
                    <span className="owner-people">
                      {ownerItem.owners?.join(', ') || 'Team SRE'}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
