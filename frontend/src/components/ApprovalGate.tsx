import React from 'react';
import {
  ShieldAlert,
  CheckCircle,
  XCircle,
  AlertOctagon,
  Clock,
  UserCheck,
} from 'lucide-react';
import type { PendingAction } from '../api';

interface ApprovalGateProps {
  pendingActions: PendingAction[];
  incidentId: string;
  onApprove: (actionId: string) => Promise<void>;
  onReject: (actionId: string) => Promise<void>;
  isProcessing: boolean;
}

export const ApprovalGate: React.FC<ApprovalGateProps> = ({
  pendingActions,
  incidentId,
  onApprove,
  onReject,
  isProcessing,
}) => {
  if (pendingActions.length === 0) return null;

  return (
    <div className="approval-gate-banner glass-panel">
      <div className="gate-header">
        <div className="gate-title-group">
          <AlertOctagon size={18} className="text-amber pulse-anim" />
          <h4>Operational Approval Gate · Safe Action Safeguard</h4>
        </div>
        <span className="gate-badge">HUMAN APPROVAL REQUIRED</span>
      </div>

      <div className="pending-actions-list">
        {pendingActions.map((action) => (
          <div key={action.id} className="action-approval-card">
            <div className="action-info">
              <div className="action-tags">
                <span className="action-class-pill">{action.action_class}</span>
                <span className="target-svc-pill">Target: {action.target_service}</span>
                <span className="runbook-pill">Runbook: {action.runbook_id}</span>
              </div>
              <p className="action-desc">
                {action.description || 'Intervention requires operator confirmation before simulated execution.'}
              </p>
            </div>

            <div className="action-buttons">
              <button
                className="reject-btn"
                onClick={() => onReject(action.id)}
                disabled={isProcessing}
              >
                <XCircle size={15} />
                <span>Reject</span>
              </button>
              <button
                className="approve-btn"
                onClick={() => onApprove(action.id)}
                disabled={isProcessing}
              >
                <CheckCircle size={15} />
                <span>Approve &amp; Resume Crew</span>
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
