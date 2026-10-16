import React from 'react';
import { ArrowRight, AlertTriangle } from 'lucide-react';
import './TracePanel.css';

interface TraceSpan {
  id: string;
  idx: number;
  service: string;
  duration: string;
  durationMs: number;
  status: 'error' | 'warning' | 'ok';
  annotation?: string;
  percent: number;
}

interface TracePanelProps {
  traceId?: string;
  onOpenFullTrace?: () => void;
  onSelectService?: (serviceName: string) => void;
  selectedService?: string | null;
}

const DEFAULT_SPANS: TraceSpan[] = [
  { id: 'span_1', idx: 1, service: 'api-gateway', duration: '42ms', durationMs: 42, status: 'ok', percent: 8 },
  { id: 'span_2', idx: 2, service: 'auth-service', duration: '38ms', durationMs: 38, status: 'ok', percent: 7 },
  {
    id: 'span_3',
    idx: 3,
    service: 'paymentservice',
    duration: '2.5s',
    durationMs: 2500,
    status: 'error',
    annotation: '0.5s Connection pool exhausted',
    percent: 88,
  },
  { id: 'span_4', idx: 4, service: 'redis-cart', duration: '118ms', durationMs: 118, status: 'ok', percent: 14 },
  {
    id: 'span_5',
    idx: 5,
    service: 'checkoutservice',
    duration: '1.8s',
    durationMs: 1800,
    status: 'warning',
    annotation: 'High latency',
    percent: 64,
  },
  { id: 'span_6', idx: 6, service: 'currencyservice', duration: '320ms', durationMs: 320, status: 'ok', percent: 22 },
];

export const TracePanel: React.FC<TracePanelProps> = ({
  traceId = '9f3c...a2d1',
  onOpenFullTrace,
  onSelectService,
  selectedService,
}) => {
  return (
    <div className="trace-panel-root">
      {/* Header */}
      <div className="trace-panel-header">
        <div className="trace-header-left">
          <h2 className="trace-panel-title">Current Trace</h2>
          <span className="trace-status-chip error">500s</span>
          <span className="trace-id-label">Trace ID {traceId}</span>
        </div>
        <button
          type="button"
          className="trace-view-full-btn"
          onClick={onOpenFullTrace}
          title="Open Deep Provenance Trace Inspector"
        >
          <span>View Full Trace</span>
          <ArrowRight size={13} />
        </button>
      </div>

      {/* Waterfall Spans */}
      <div className="trace-spans-list">
        {DEFAULT_SPANS.map((span) => {
          const isSelected = selectedService === span.service;
          return (
            <div
              key={span.id}
              className={`trace-span-row ${span.status} ${isSelected ? 'selected' : ''}`}
              onClick={() => onSelectService?.(span.service)}
              role="button"
              tabIndex={0}
              title={`Focus ${span.service} in 3D System View`}
            >
              <span className="trace-span-idx">{span.idx}</span>
              <span className="trace-span-service">{span.service}</span>
              <span className="trace-span-duration">{span.duration}</span>

              {/* Waterfall Duration Bar */}
              <div className="trace-waterfall-track">
                <div
                  className={`trace-waterfall-fill ${span.status}`}
                  style={{ width: `${Math.max(span.percent, 8)}%` }}
                />
              </div>

              {/* Annotation Tag */}
              {span.annotation && (
                <span className={`trace-span-tag ${span.status}`}>
                  {span.status === 'error' && <AlertTriangle size={11} className="inline mr-1" />}
                  {span.annotation}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
