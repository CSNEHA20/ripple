import React from 'react';
import {
  ShieldAlert,
  Search,
  Wrench,
  CheckCircle,
  ArrowRight,
  AlertOctagon,
  FileQuestion,
  HelpCircle,
  Activity,
  Flame,
} from 'lucide-react';
import type { SSEEvent } from '../api';

interface AgentTimelineProps {
  events: SSEEvent[];
  activePhase: string;
}

export const AgentTimeline: React.FC<AgentTimelineProps> = ({ events, activePhase }) => {
  const getEventIcon = (eventType: string) => {
    switch (eventType) {
      case 'agent_started':
        return <Activity size={14} className="text-cyan" />;
      case 'tool_called':
        return <Search size={14} className="text-blue" />;
      case 'observation_created':
        return <ShieldAlert size={14} className="text-emerald" />;
      case 'hypotheses_ranked':
        return <Flame size={14} className="text-purple" />;
      case 'conflict_flagged':
        return <AlertOctagon size={14} className="text-amber" />;
      case 'evidence_requested':
        return <FileQuestion size={14} className="text-pink" />;
      case 'handoff':
        return <ArrowRight size={14} className="text-cyan" />;
      case 'action_proposed':
      case 'approval_needed':
        return <Wrench size={14} className="text-amber" />;
      case 'outcome_verified':
      case 'incident_closed':
        return <CheckCircle size={14} className="text-emerald" />;
      default:
        return <HelpCircle size={14} className="text-muted" />;
    }
  };

  const formatEventText = (ev: SSEEvent) => {
    const d = ev.data || {};
    switch (ev.event) {
      case 'incident_opened':
        return `Incident opened for service '${d.service}'`;
      case 'agent_started':
        return `Agent ${d.agent} started role [${d.role}]`;
      case 'tool_called':
        return `Tool '${d.tool}' executed (found ${d.result_count ?? 1} items)`;
      case 'observation_created':
        return d.text || `Observation recorded on graph`;
      case 'hypotheses_ranked':
        return `Ranked ${d.count} competing hypotheses (Top: ${d.top_hypothesis?.service || 'service'})`;
      case 'conflict_flagged':
        return `Conflict flagged: ${d.conflict?.reason || 'Margin threshold within limits'}`;
      case 'evidence_requested':
        return `Evidence request created for ${d.task?.payload?.hypothesis_service || 'hypothesis'}`;
      case 'handoff':
        return `Handoff: [${d.from}] → [${d.to}]`;
      case 'action_proposed':
        return `Responder proposed ${d.action_class || 'action'} (${d.runbook_id || 'runbook'})`;
      case 'approval_needed':
        return `APPROVAL REQUIRED: ${d.description || 'Needs operator confirmation'}`;
      case 'outcome_verified':
        return `Verifier confirmed outcome: ${d.outcome || 'resolved'}`;
      case 'incident_closed':
        return `Incident successfully closed and stored in episodic memory`;
      default:
        return JSON.stringify(d);
    }
  };

  return (
    <div className="agent-timeline glass-panel">
      <div className="panel-header">
        <div className="panel-title-with-badge">
          <h3>Blackboard Agent Timeline</h3>
          <span className="live-pulse-badge">
            <span className="pulse-dot"></span>
            LIVE SSE
          </span>
        </div>
        <div className="phase-indicators">
          {['triage', 'investigator', 'responder', 'verifier'].map((p) => (
            <span
              key={p}
              className={`phase-badge ${activePhase === p ? 'active' : ''}`}
            >
              {p}
            </span>
          ))}
        </div>
      </div>

      <div className="timeline-scroll-container">
        {events.length === 0 ? (
          <div className="empty-timeline">
            <Activity size={24} className="text-muted spin-slow" />
            <p>Awaiting alert trigger. Launch the crew to stream live graph events.</p>
          </div>
        ) : (
          <div className="timeline-items">
            {events.map((ev, index) => (
              <div key={index} className="timeline-entry">
                <div className="timeline-icon-box">{getEventIcon(ev.event)}</div>
                <div className="timeline-content">
                  <div className="timeline-top-row">
                    <span className="timeline-event-name">{ev.event.replace('_', ' ')}</span>
                    <span className="timeline-time">
                      {new Date(ev.ts * 1000).toLocaleTimeString()}
                    </span>
                  </div>
                  <p className="timeline-detail">{formatEventText(ev)}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
