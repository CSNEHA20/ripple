import React from 'react';
import { AlertTriangle, Play, RefreshCw, Cpu, Database, CheckCircle2 } from 'lucide-react';
import type { ScenarioItem } from '../api';

interface AlertConsoleProps {
  scenarios: ScenarioItem[];
  selectedScenarioId: string;
  onSelectScenario: (id: string) => void;
  customAlertText: string;
  onChangeCustomAlertText: (text: string) => void;
  customService: string;
  onChangeCustomService: (svc: string) => void;
  tenant: string;
  onChangeTenant: (tenant: string) => void;
  mode: 'replay' | 'live';
  onToggleMode: (m: 'replay' | 'live') => void;
  isRunning: boolean;
  onRunCrew: () => void;
  healthOk: boolean;
}

export const AlertConsole: React.FC<AlertConsoleProps> = ({
  scenarios,
  selectedScenarioId,
  onSelectScenario,
  customAlertText,
  onChangeCustomAlertText,
  customService,
  onChangeCustomService,
  tenant,
  onChangeTenant,
  mode,
  onToggleMode,
  isRunning,
  onRunCrew,
  healthOk,
}) => {
  const selectedScenario = scenarios.find((s) => s.id === selectedScenarioId);

  return (
    <div className="alert-console glass-panel">
      {/* Top Bar: Tenant & Engine Mode */}
      <div className="console-header">
        <div className="console-title-group">
          <div className="brand-badge">
            <span className="brand-dot"></span>
            RIPPLE ON-CALL
          </div>
          <span className="tenant-tag">Graph Tenant:</span>
          <select
            className="tenant-select"
            value={tenant}
            onChange={(e) => onChangeTenant(e.target.value)}
          >
            <option value="storefront">tenant_storefront (Prod)</option>
            <option value="payments">tenant_payments (Financial)</option>
            <option value="smoke">tenant_smoke (Test)</option>
          </select>
        </div>

        <div className="console-controls">
          <div className="mode-toggle">
            <button
              className={`mode-btn ${mode === 'replay' ? 'active' : ''}`}
              onClick={() => onToggleMode('replay')}
            >
              Replay Cache
            </button>
            <button
              className={`mode-btn ${mode === 'live' ? 'active' : ''}`}
              onClick={() => onToggleMode('live')}
            >
              Live LLM
            </button>
          </div>

          <div className={`connection-status ${healthOk ? 'ok' : 'err'}`}>
            <Database size={13} />
            <span>{healthOk ? 'FalkorDB Connected' : 'Connecting...'}</span>
          </div>
        </div>
      </div>

      {/* Main Form: Scenario Selector / Alert Input */}
      <div className="console-body">
        <div className="scenario-selector-section">
          <label className="section-label">Simulated Scenario Library (13 Pre-Registered)</label>
          <select
            className="scenario-select"
            value={selectedScenarioId}
            onChange={(e) => onSelectScenario(e.target.value)}
          >
            <option value="">-- Or Paste Custom Incident Alert --</option>
            {scenarios.map((sc) => (
              <option key={sc.id} value={sc.id}>
                [{sc.family.toUpperCase()}] {sc.id}: {sc.alert.service} - {sc.description.slice(0, 60)}...
              </option>
            ))}
          </select>

          {selectedScenario && (
            <div className="scenario-meta-banner">
              <span className="family-pill">{selectedScenario.family}</span>
              <span className="meta-text">{selectedScenario.description}</span>
            </div>
          )}
        </div>

        <div className="alert-inputs-row">
          <div className="service-field">
            <label className="section-label">Alerting Service</label>
            <input
              type="text"
              className="console-input"
              placeholder="e.g. paymentservice"
              value={customService}
              onChange={(e) => onChangeCustomService(e.target.value)}
            />
          </div>

          <div className="alert-text-field">
            <label className="section-label">Alert Description / Symptoms</label>
            <input
              type="text"
              className="console-input"
              placeholder="e.g. High HTTP 500 error rate on checkout payment authorize..."
              value={customAlertText}
              onChange={(e) => onChangeCustomAlertText(e.target.value)}
            />
          </div>

          <button
            className={`run-crew-btn ${isRunning ? 'running' : ''}`}
            onClick={onRunCrew}
            disabled={isRunning || (!customService && !selectedScenarioId)}
          >
            {isRunning ? (
              <>
                <RefreshCw size={16} className="spin" />
                <span>Crew Investigating...</span>
              </>
            ) : (
              <>
                <Play size={16} fill="currentColor" />
                <span>Launch Crew</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};
