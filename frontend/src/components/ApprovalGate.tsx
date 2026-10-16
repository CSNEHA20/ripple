import React from 'react';
import { CheckCircle, XCircle, ShieldAlert, Target, BookOpen } from 'lucide-react';
import { Button } from '@/components/ui/button';
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
    <section className="relative rounded-[20px] p-[1.5px] anim-scale-in overflow-hidden">
      <span className="absolute inset-0 bg-[conic-gradient(from_0deg,#ff4d2d,#f97316,#e11d48,#ff4d2d)] animate-[spin_6s_linear_infinite] opacity-70 blur-[2px]" style={{ transform: 'scale(2.5)' }} />
      <div className="relative rounded-[19px] bg-[var(--bg-card)] p-5 space-y-4">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-3">
            <span className="relative w-11 h-11 rounded-2xl grid place-items-center bg-amber-500/15 border border-amber-500/40 text-amber-500">
              <ShieldAlert size={22} />
              <span className="absolute inset-0 rounded-2xl border border-amber-500 animate-ping opacity-40" />
            </span>
            <div>
              <h4 className="font-bold text-[15px] tracking-tight text-[var(--text-primary)] leading-none">Operational approval gate</h4>
              <p className="text-[12px] text-[var(--text-muted)] mt-1.5">
                Safe-action safeguard · incident <span className="font-mono text-[var(--text-secondary)]">{incidentId}</span>
              </p>
            </div>
          </div>
          <span className="chip chip-red uppercase tracking-wider !text-[10.5px] font-bold">
            <span className="live-dot !w-1.5 !h-1.5" /> Human approval required
          </span>
        </div>

        <div className="space-y-3">
          {pendingActions.map((action) => (
            <div key={action.id} className="inset-well p-4 flex items-center justify-between gap-5 flex-wrap">
              <div className="min-w-0 flex-1">
                <div className="flex gap-2 flex-wrap">
                  <span className="chip chip-orange">{action.action_class}</span>
                  <span className="chip"><Target size={11} /> {action.target_service}</span>
                  <span className="chip chip-mono"><BookOpen size={11} /> {action.runbook_id}</span>
                </div>
                <p className="text-[13px] text-[var(--text-secondary)] mt-2.5 leading-relaxed">
                  {action.description || 'Intervention requires operator confirmation before simulated execution.'}
                </p>
              </div>

              <div className="flex gap-2.5 shrink-0">
                <button
                  onClick={() => onReject(action.id)}
                  disabled={isProcessing}
                  className="btn-soft h-10 !px-4 hover:!border-rose-500/60 hover:!text-rose-500"
                >
                  <XCircle size={15} /> Reject
                </button>
                <Button
                  size="sm"
                  onClick={() => onApprove(action.id)}
                  disabled={isProcessing}
                  className="h-10 px-5 gap-2 rounded-xl bg-gradient-to-br from-emerald-500 to-emerald-600 hover:brightness-110 text-white font-bold shadow-[0_8px_24px_-6px_rgba(16,185,129,0.7)] border border-white/20 transition-all"
                >
                  <CheckCircle size={15} />
                  {isProcessing ? 'Working…' : 'Approve & resume crew'}
                </Button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};
