import React from 'react';
import { AlertTriangle, Play, RefreshCw, Cpu, Database, CheckCircle2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
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
          <Badge variant="outline" className="border-emerald-500/30 text-emerald-400 gap-1.5 py-1 px-3">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
            RIPPLE ON-CALL
          </Badge>
          <span className="tenant-tag text-xs text-muted-foreground">Graph Tenant:</span>
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

        <div className="console-controls flex items-center gap-3">
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

          <Badge variant={healthOk ? "outline" : "destructive"} className="gap-1.5 text-xs">
            <Database size={13} />
            <span>{healthOk ? 'FalkorDB Connected' : 'Connecting...'}</span>
          </Badge>
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
            <div className="scenario-meta-banner flex items-center gap-2 mt-2">
              <Badge variant="secondary" className="uppercase font-bold tracking-wider text-[10px]">
                {selectedScenario.family}
              </Badge>
              <span className="meta-text text-xs text-secondary-foreground">{selectedScenario.description}</span>
            </div>
          )}
        </div>

        <div className="alert-inputs-row flex gap-3 mt-3 items-end">
          <div className="service-field w-1/4">
            <label className="section-label">Alerting Service</label>
            <Input
              type="text"
              placeholder="e.g. paymentservice"
              value={customService}
              onChange={(e) => onChangeCustomService(e.target.value)}
              className="bg-[rgba(13,30,21,0.6)] border-white/10"
            />
          </div>

          <div className="alert-text-field flex-1">
            <label className="section-label">Alert Description / Symptoms</label>
            <Input
              type="text"
              placeholder="e.g. High HTTP 500 error rate on checkout payment authorize..."
              value={customAlertText}
              onChange={(e) => onChangeCustomAlertText(e.target.value)}
              className="bg-[rgba(13,30,21,0.6)] border-white/10"
            />
          </div>

          <Button
            size="lg"
            className="sonic-btn-primary h-9 px-6 rounded-full font-bold cursor-pointer transition-all hover:scale-105"
            onClick={onRunCrew}
            disabled={isRunning || (!customService && !selectedScenarioId)}
          >
            {isRunning ? (
              <>
                <RefreshCw size={16} className="animate-spin" />
                <span>Crew Investigating...</span>
              </>
            ) : (
              <>
                <Play size={16} fill="currentColor" />
                <span>Launch Crew</span>
              </>
            )}
          </Button>
        </div>
      </div>
    </div>
  );
};
