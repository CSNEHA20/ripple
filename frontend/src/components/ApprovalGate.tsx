import React from 'react';
import {
  ShieldAlert,
  CheckCircle,
  XCircle,
  AlertOctagon,
  Clock,
  UserCheck,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
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
          <h4 className="font-bold tracking-tight">Operational Approval Gate · Safe Action Safeguard</h4>
        </div>
        <Badge variant="destructive" className="font-bold text-[10px] tracking-wider uppercase">
          Human Approval Required
        </Badge>
      </div>

      <div className="pending-actions-list">
        {pendingActions.map((action) => (
          <div key={action.id} className="action-approval-card">
            <div className="action-info">
              <div className="action-tags flex gap-2">
                <Badge variant="secondary" className="text-xs">
                  {action.action_class}
                </Badge>
                <Badge variant="outline" className="text-xs">
                  Target: {action.target_service}
                </Badge>
                <Badge variant="outline" className="text-xs">
                  Runbook: {action.runbook_id}
                </Badge>
              </div>
              <p className="action-desc mt-2">
                {action.description || 'Intervention requires operator confirmation before simulated execution.'}
              </p>
            </div>

            <div className="action-buttons flex gap-3">
              <Button
                variant="destructive"
                size="sm"
                className="gap-1.5 cursor-pointer"
                onClick={() => onReject(action.id)}
                disabled={isProcessing}
              >
                <XCircle size={15} />
                <span>Reject</span>
              </Button>
              <Button
                variant="default"
                size="sm"
                className="gap-1.5 bg-[#08130c] text-white hover:bg-[#122819] cursor-pointer"
                onClick={() => onApprove(action.id)}
                disabled={isProcessing}
              >
                <CheckCircle size={15} />
                <span>Approve &amp; Resume Crew</span>
              </Button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
