import React, { useState } from 'react';
import { ChevronDown, AlertCircle, ArrowDown, Activity } from 'lucide-react';
import './IncidentFlowPanel.css';

interface IncidentFlowPanelProps {
  alertingService?: string;
  onFocusService?: (svc: string) => void;
  onOpenBlastRadiusDrawer?: () => void;
}

export const IncidentFlowPanel: React.FC<IncidentFlowPanelProps> = ({
  alertingService = 'paymentservice',
  onFocusService,
  onOpenBlastRadiusDrawer,
}) => {
  const [expanded, setExpanded] = useState<boolean>(false);

  return (
    <aside className="incident-flow-panel-root" aria-label="Incident Propagation Flow">
      <div className="incident-flow-header">
        <h2 className="incident-flow-title">Incident Flow</h2>
        <span className="incident-flow-badge">Active</span>
      </div>

      {/* Downward Tree Flow */}
      <div className="incident-flow-tree">
        {/* Node 1: Primary Failing Service */}
        <div
          className="flow-tree-item critical"
          onClick={() => onFocusService?.('paymentservice')}
          role="button"
          tabIndex={0}
          title="Click to focus paymentservice"
        >
          <div className="flow-tree-indicator red">
            <span className="flow-dot-inner" />
          </div>
          <div className="flow-tree-content">
            <div className="flow-service-name">paymentservice</div>
            <div className="flow-service-sub">500s · 68% error rate</div>
          </div>
        </div>

        {/* Connector 1 */}
        <div className="flow-tree-connector red-amber" />

        {/* Node 2: Downstream 1 */}
        <div
          className="flow-tree-item warning"
          onClick={() => onFocusService?.('checkoutservice')}
          role="button"
          tabIndex={0}
          title="Click to focus checkoutservice"
        >
          <div className="flow-tree-indicator amber">
            <span className="flow-dot-inner" />
          </div>
          <div className="flow-tree-content">
            <div className="flow-service-name">checkoutservice</div>
            <div className="flow-service-sub">High latency (1.8s)</div>
          </div>
        </div>

        {/* Connector 2 */}
        <div className="flow-tree-connector amber" />

        {/* Node 3: Downstream 2 */}
        <div
          className="flow-tree-item warning"
          onClick={() => onFocusService?.('currencyservice')}
          role="button"
          tabIndex={0}
          title="Click to focus currencyservice"
        >
          <div className="flow-tree-indicator amber">
            <span className="flow-dot-inner" />
          </div>
          <div className="flow-tree-content">
            <div className="flow-service-name">currencyservice</div>
            <div className="flow-service-sub">Increased latency (320ms)</div>
          </div>
        </div>

        {/* Connector 3 */}
        <div className="flow-tree-connector muted" />

        {/* Node 4: Transitive Impact */}
        <div
          className="flow-tree-item muted"
          onClick={() => onFocusService?.('shippingservice')}
          role="button"
          tabIndex={0}
        >
          <div className="flow-tree-indicator hollow" />
          <div className="flow-tree-content">
            <div className="flow-service-name">4 downstream services</div>
            <div className="flow-service-sub">impacted in blast radius</div>
          </div>
        </div>
      </div>

      {/* Mini Isometric Blast Radius Diagram matching reference */}
      <div className="flow-isometric-card" aria-hidden="true">
        <svg viewBox="0 0 240 130" className="flow-isometric-svg">
          <defs>
            <linearGradient id="isoPlatform" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#1C1C18" />
              <stop offset="100%" stopColor="#11110F" />
            </linearGradient>
            <linearGradient id="isoRedBox" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#FF453A" />
              <stop offset="100%" stopColor="#B3261E" />
            </linearGradient>
            <linearGradient id="isoAmberBox" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#F5A623" />
              <stop offset="100%" stopColor="#B5740B" />
            </linearGradient>
            <linearGradient id="isoCyanBox" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#35C98A" />
              <stop offset="100%" stopColor="#1D7951" />
            </linearGradient>
          </defs>

          {/* Isometric Platform Plate */}
          <polygon points="120,15 220,60 120,105 20,60" fill="url(#isoPlatform)" stroke="#2A2925" strokeWidth="1.5" />
          <polygon points="20,60 120,105 120,115 20,70" fill="#141412" stroke="#2A2925" strokeWidth="1" />
          <polygon points="120,105 220,60 220,70 120,115" fill="#0E0E0C" stroke="#2A2925" strokeWidth="1" />

          {/* Central Failing Cube (paymentservice) */}
          <g transform="translate(108, 42)">
            <polygon points="12,0 24,7 12,14 0,7" fill="#FF5E54" />
            <polygon points="0,7 12,14 12,28 0,21" fill="url(#isoRedBox)" />
            <polygon points="12,14 24,7 24,21 12,28" fill="#8C1D18" />
          </g>

          {/* Connecting failure paths */}
          <line x1="120" y1="56" x2="68" y2="78" stroke="#FF453A" strokeWidth="1.8" strokeDasharray="3,2" />
          <line x1="120" y1="56" x2="172" y2="78" stroke="#F5A623" strokeWidth="1.8" strokeDasharray="3,2" />
          <line x1="120" y1="56" x2="120" y2="88" stroke="#F5A623" strokeWidth="1.8" strokeDasharray="3,2" />
          <line x1="120" y1="56" x2="152" y2="34" stroke="#35C98A" strokeWidth="1.5" />

          {/* Surrounding Nodes */}
          {/* Node Left (currencyservice) */}
          <g transform="translate(56, 68)">
            <polygon points="10,0 20,6 10,12 0,6" fill="#F8B84E" />
            <polygon points="0,6 10,12 10,22 0,16" fill="url(#isoAmberBox)" />
            <polygon points="10,12 20,6 20,16 10,22" fill="#805106" />
          </g>

          {/* Node Right (checkoutservice) */}
          <g transform="translate(162, 68)">
            <polygon points="10,0 20,6 10,12 0,6" fill="#F8B84E" />
            <polygon points="0,6 10,12 10,22 0,16" fill="url(#isoAmberBox)" />
            <polygon points="10,12 20,6 20,16 10,22" fill="#805106" />
          </g>

          {/* Node Center Bottom */}
          <g transform="translate(110, 78)">
            <polygon points="10,0 20,6 10,12 0,6" fill="#F8B84E" />
            <polygon points="0,6 10,12 10,22 0,16" fill="url(#isoAmberBox)" />
            <polygon points="10,12 20,6 20,16 10,22" fill="#805106" />
          </g>

          {/* Node Top Right (healthy) */}
          <g transform="translate(142, 24)">
            <polygon points="9,0 18,5 9,10 0,5" fill="#58D89E" />
            <polygon points="0,5 9,10 9,18 0,13" fill="url(#isoCyanBox)" />
            <polygon points="9,10 18,5 18,13 9,18" fill="#135237" />
          </g>
        </svg>
      </div>

      {/* Expand Button */}
      <button
        type="button"
        className="flow-expand-btn"
        onClick={() => {
          setExpanded(!expanded);
          onOpenBlastRadiusDrawer?.();
        }}
      >
        <span>View Blast Radius</span>
        <ChevronDown size={14} className={`flow-caret ${expanded ? 'rotate' : ''}`} />
      </button>

      {expanded && (
        <div className="flow-expanded-details">
          <div className="flow-detail-stat">
            <span>Direct impact:</span>
            <strong>3 services</strong>
          </div>
          <div className="flow-detail-stat">
            <span>Transitive:</span>
            <strong>4 services</strong>
          </div>
          <div className="flow-detail-stat">
            <span>Critical paths:</span>
            <strong>checkout &rarr; paymentservice</strong>
          </div>
        </div>
      )}
    </aside>
  );
};
