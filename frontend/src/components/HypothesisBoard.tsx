import React from 'react';
import {
  Flame,
  CheckCircle,
  XCircle,
  HelpCircle,
  AlertCircle,
  Layers,
  ChevronRight,
  Sparkles,
} from 'lucide-react';
import type { HypothesisItem, HypothesisEvidence } from '../api';

interface HypothesisBoardProps {
  hypotheses: HypothesisItem[];
  selectedHypothesisId: string | null;
  onSelectHypothesis: (id: string) => void;
  pendingEvidenceRequest?: any;
  onInspectEvidence?: (ev: HypothesisEvidence) => void;
}

export const HypothesisBoard: React.FC<HypothesisBoardProps> = ({
  hypotheses,
  selectedHypothesisId,
  onSelectHypothesis,
  pendingEvidenceRequest,
  onInspectEvidence,
}) => {
  // Check if top hypothesis has insufficient evidence
  const isInsufficient = hypotheses.length > 0 && hypotheses[0].supporting_evidence.length < 2;

  return (
    <div className="hypothesis-board glass-panel">
      <div className="board-header">
        <div className="board-title-group">
          <h3>Ranked Hypotheses &amp; Evidence Engine</h3>
          <span className="calibrated-label">Track 1 Core · Exponential Decay Scored</span>
        </div>
        {hypotheses.length > 1 && (
          <div className="margin-indicator">
            <span className="margin-title">Score Margin:</span>
            <span className="margin-value">
              +{(hypotheses[0].evidence_score - hypotheses[1].evidence_score).toFixed(2)}
            </span>
          </div>
        )}
      </div>

      {/* Insufficient Evidence Warning Banner */}
      {isInsufficient && (
        <div className="insufficient-evidence-banner">
          <AlertCircle size={16} className="text-amber" />
          <div className="banner-text">
            <strong>Insufficient Evidence for Conclusive Diagnosis</strong>
            <p>
              Top hypothesis has fewer than 2 supporting items. Agent created an evidence request task to gather
              clarifying signals.
            </p>
          </div>
        </div>
      )}

      {/* Pending Evidence Request Card */}
      {pendingEvidenceRequest && (
        <div className="evidence-request-card">
          <div className="request-header">
            <HelpCircle size={14} className="text-pink" />
            <span>Active Evidence Request Task</span>
          </div>
          <p className="request-body">
            {pendingEvidenceRequest.payload?.alert_text ||
              pendingEvidenceRequest.payload?.hypothesis_service ||
              JSON.stringify(pendingEvidenceRequest.payload)}
          </p>
        </div>
      )}

      {/* Hypotheses List */}
      <div className="hypotheses-list">
        {hypotheses.length === 0 ? (
          <div className="empty-hypotheses">
            <Layers size={22} className="text-muted" />
            <p>No hypotheses generated yet. Run the crew on an alert to rank suspects.</p>
          </div>
        ) : (
          hypotheses.map((hyp, index) => {
            const isSelected = selectedHypothesisId === hyp.id;
            return (
              <div
                key={hyp.id}
                className={`hypothesis-card ${isSelected ? 'selected' : ''} ${index === 0 ? 'top-rank' : ''}`}
                onClick={() => onSelectHypothesis(hyp.id)}
              >
                <div className="hyp-card-header">
                  <div className="hyp-rank-badge">{String(index + 1).padStart(2, '0')}</div>
                  <div className="hyp-title-group">
                    <span className="hyp-service">{hyp.service}</span>
                    <span className="badge-inferred">INFERRED</span>
                  </div>
                  <div className="hyp-score-box">
                    <span className="score-num">{hyp.evidence_score.toFixed(2)}</span>
                    <span className="score-label">evidence score</span>
                  </div>
                </div>

                <p className="hyp-statement">{hyp.statement}</p>

                {/* Evidence Lists */}
                <div className="evidence-sections">
                  {/* Supporting */}
                  <div className="evidence-column">
                    <div className="evidence-col-title text-emerald">
                      <CheckCircle size={12} />
                      <span>Supporting ({hyp.supporting_evidence.length})</span>
                    </div>
                    <div className="evidence-items">
                      {hyp.supporting_evidence.map((ev) => (
                        <div
                          key={ev.id}
                          className="evidence-chip supporting"
                          onClick={(e) => {
                            e.stopPropagation();
                            onInspectEvidence?.(ev);
                          }}
                          title="Click to view full provenance in Inspector Drawer"
                        >
                          <span className={`kind-tag ${ev.kind}`}>{ev.kind}</span>
                          <span className="chip-text">{ev.summary}</span>
                          {ev.freshness !== undefined && (
                            <span className="freshness-tag">
                              {(ev.freshness * 100).toFixed(0)}% fresh
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Contradicting */}
                  <div className="evidence-column">
                    <div className="evidence-col-title text-red">
                      <XCircle size={12} />
                      <span>Contradicting ({hyp.contradicting_evidence.length})</span>
                    </div>
                    <div className="evidence-items">
                      {hyp.contradicting_evidence.length === 0 ? (
                        <span className="no-contra">No active contradictions found</span>
                      ) : (
                        hyp.contradicting_evidence.map((ev) => (
                          <div
                            key={ev.id}
                            className="evidence-chip contradicting"
                            onClick={(e) => {
                              e.stopPropagation();
                              onInspectEvidence?.(ev);
                            }}
                            title="Click to view full provenance in Inspector Drawer"
                          >
                            <span className={`kind-tag ${ev.kind}`}>{ev.kind}</span>
                            <span className="chip-text">{ev.summary}</span>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
