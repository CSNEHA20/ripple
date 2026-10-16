import React, { useState } from 'react';
import {
  BarChart2,
  TrendingUp,
  ShieldCheck,
  Zap,
  Play,
  RotateCcw,
  CheckCircle,
  XCircle,
  AlertTriangle,
} from 'lucide-react';
import type { BenchmarkReportResponse } from '../api';

interface BenchmarkTabProps {
  reportData: BenchmarkReportResponse | null;
  onRunBenchmark: () => Promise<void>;
  isRunning: boolean;
}

export const BenchmarkTab: React.FC<BenchmarkTabProps> = ({
  reportData,
  onRunBenchmark,
  isRunning,
}) => {
  const [filterFamily, setFilterFamily] = useState<string>('all');
  const bench = reportData?.benchmark;
  const summary = bench?.summary;
  const memOn = summary?.memory_on;
  const memOff = summary?.memory_off;
  const runs = bench?.runs || [];

  const filteredRuns = filterFamily === 'all' ? runs : runs.filter((r) => r.family === filterFamily);

  return (
    <div className="benchmark-tab glass-panel">
      <div className="panel-header">
        <div className="panel-title-with-badge">
          <BarChart2 size={16} className="text-cyan" />
          <h3>Pre-Registered Benchmark &amp; Calibration</h3>
        </div>
        <div className="bench-header-actions">
          <span className="protocol-tag">Protocol: {bench?.benchmark_protocol_version || 'v2.0'}</span>
          <button
            className="run-bench-btn"
            onClick={onRunBenchmark}
            disabled={isRunning}
          >
            <Play size={13} fill="currentColor" />
            <span>{isRunning ? 'Running Benchmark...' : 'Run Benchmark (A/B)'}</span>
          </button>
        </div>
      </div>

      {/* Calibration Check Banner */}
      {bench?.calibration_status && (
        <div className="calibration-banner">
          <div className="calib-status-row">
            <span className={`calib-badge ${bench.calibration_status.passed ? 'pass' : 'pending'}`}>
              Calibration: {bench.calibration_status.passed ? 'PASSED' : 'PENDING'}
            </span>
            <span className="calib-basis">{bench.calibration_status.basis}</span>
          </div>
          <span className="confidence-policy-note">
            Confidence Policy: Displayed strictly as <code>{bench.calibration_status.score_label}</code> (never raw percentage).
          </span>
        </div>
      )}

      {/* Comparison Metric Cards */}
      {summary && (
        <div className="benchmark-metrics-grid">
          <div className="metric-comparison-card">
            <span className="metric-title">Diagnosis Correctness</span>
            <div className="metric-comparison-bars">
              <div className="bar-row">
                <span className="bar-label">Memory ON</span>
                <div className="bar-outer">
                  <div
                    className="bar-fill cyan"
                    style={{ width: `${(memOn?.diagnosis_correctness || 0) * 100}%` }}
                  ></div>
                </div>
                <span className="bar-val">{((memOn?.diagnosis_correctness || 0) * 100).toFixed(0)}%</span>
              </div>
              <div className="bar-row">
                <span className="bar-label">Memory OFF</span>
                <div className="bar-outer">
                  <div
                    className="bar-fill gray"
                    style={{ width: `${(memOff?.diagnosis_correctness || 0) * 100}%` }}
                  ></div>
                </div>
                <span className="bar-val">{((memOff?.diagnosis_correctness || 0) * 100).toFixed(0)}%</span>
              </div>
            </div>
          </div>

          <div className="metric-comparison-card">
            <span className="metric-title">Recommendation Correctness</span>
            <div className="metric-comparison-bars">
              <div className="bar-row">
                <span className="bar-label">Memory ON</span>
                <div className="bar-outer">
                  <div
                    className="bar-fill purple"
                    style={{ width: `${(memOn?.recommendation_correctness || 0) * 100}%` }}
                  ></div>
                </div>
                <span className="bar-val">{((memOn?.recommendation_correctness || 0) * 100).toFixed(0)}%</span>
              </div>
              <div className="bar-row">
                <span className="bar-label">Memory OFF</span>
                <div className="bar-outer">
                  <div
                    className="bar-fill gray"
                    style={{ width: `${(memOff?.recommendation_correctness || 0) * 100}%` }}
                  ></div>
                </div>
                <span className="bar-val">{((memOff?.recommendation_correctness || 0) * 100).toFixed(0)}%</span>
              </div>
            </div>
          </div>

          <div className="metric-comparison-card">
            <span className="metric-title">Unsafe Fix Recommendation Rate</span>
            <div className="metric-comparison-bars">
              <div className="bar-row">
                <span className="bar-label">Memory ON</span>
                <div className="bar-outer">
                  <div
                    className="bar-fill emerald"
                    style={{ width: `${(memOn?.unsafe_recommendation_rate || 0) * 100}%` }}
                  ></div>
                </div>
                <span className="bar-val">{((memOn?.unsafe_recommendation_rate || 0) * 100).toFixed(0)}% (Zero Stale)</span>
              </div>
              <div className="bar-row">
                <span className="bar-label">Memory OFF</span>
                <div className="bar-outer">
                  <div
                    className="bar-fill red"
                    style={{ width: `${(memOff?.unsafe_recommendation_rate || 0) * 100}%` }}
                  ></div>
                </div>
                <span className="bar-val">{((memOff?.unsafe_recommendation_rate || 0) * 100).toFixed(0)}%</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Filter and Scenarios Table */}
      <div className="scenarios-table-section">
        <div className="table-controls">
          <span className="table-title">Scenario Evaluation Runs ({filteredRuns.length})</span>
          <div className="family-filter-buttons">
            {['all', 'repeated', 'variant', 'novel', 'stale_trap', 'misleading_memory'].map((f) => (
              <button
                key={f}
                className={`filter-btn ${filterFamily === f ? 'active' : ''}`}
                onClick={() => setFilterFamily(f)}
              >
                {f.replace('_', ' ')}
              </button>
            ))}
          </div>
        </div>

        <div className="bench-table-wrapper">
          <table className="bench-table">
            <thead>
              <tr>
                <th>Scenario</th>
                <th>Family</th>
                <th>Condition</th>
                <th>Diagnosis</th>
                <th>Recommendation</th>
                <th>Safety</th>
                <th>Tools</th>
                <th>Score</th>
              </tr>
            </thead>
            <tbody>
              {filteredRuns.map((r, idx) => (
                <tr key={`${r.scenario_id}-${r.memory_mode}-${idx}`}>
                  <td><code>{r.scenario_id}</code></td>
                  <td><span className="family-pill-sm">{r.family}</span></td>
                  <td><span className={`mode-tag ${r.memory_mode}`}>{r.memory_mode}</span></td>
                  <td>
                    {r.diagnosis_correct ? (
                      <span className="status-cell pass"><CheckCircle size={12} /> Correct</span>
                    ) : (
                      <span className="status-cell fail"><XCircle size={12} /> Fail</span>
                    )}
                  </td>
                  <td>
                    {r.recommendation_correct ? (
                      <span className="status-cell pass"><CheckCircle size={12} /> {r.recommended_runbook}</span>
                    ) : (
                      <span className="status-cell fail"><XCircle size={12} /> {r.recommended_runbook}</span>
                    )}
                  </td>
                  <td>
                    {r.is_unsafe_recommendation ? (
                      <span className="safety-tag unsafe">UNSAFE</span>
                    ) : (
                      <span className="safety-tag safe">SAFE</span>
                    )}
                  </td>
                  <td>{r.tool_calls}</td>
                  <td>{r.evidence_score?.toFixed(2) || '0.00'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
