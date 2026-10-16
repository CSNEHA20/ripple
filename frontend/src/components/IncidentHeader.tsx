import React from 'react';
import { Activity, Share2, MoreHorizontal, ChevronDown, Box, Network, List } from 'lucide-react';
import './IncidentHeader.css';

interface IncidentHeaderProps {
  incidentId: string;
  severity?: string;
  title: string;
  subtitle: string;
  startedTime?: string;
  startedAgo?: string;
  status?: string;
  tenant: string;
  onChangeTenant?: (t: string) => void;
  activeSubTab: 'system' | 'timeline' | 'hypotheses' | 'evidence' | 'runbook' | 'counterfactuals';
  onChangeSubTab: (tab: 'system' | 'timeline' | 'hypotheses' | 'evidence' | 'runbook' | 'counterfactuals') => void;
  viewMode: '3d' | 'graph' | 'list';
  onChangeViewMode: (mode: '3d' | 'graph' | 'list') => void;
  onShare?: () => void;
}

export const IncidentHeader: React.FC<IncidentHeaderProps> = ({
  incidentId = 'INC-4829',
  severity = 'P1',
  title = 'Checkout payment authorization failing',
  subtitle = 'High HTTP 500 error rate on checkout payment authorize. 4 services impacted.',
  startedTime = '14:24:17',
  startedAgo = '12m ago',
  status = 'Investigating (Live)',
  tenant = 'storefront',
  onChangeTenant,
  activeSubTab,
  onChangeSubTab,
  viewMode,
  onChangeViewMode,
  onShare,
}) => {
  return (
    <div className="incident-header-root">
      {/* Top Details Row */}
      <div className="incident-header-main">
        {/* Left: Breadcrumb, Heartbeat, Title & Subtitle */}
        <div className="incident-header-left">
          <div className="incident-breadcrumb-row">
            <span className="incident-breadcrumb-base">Incidents</span>
            <span className="incident-breadcrumb-sep">&gt;</span>
            <span className="incident-breadcrumb-id">{incidentId}</span>
            <span className="incident-severity-badge">{severity}</span>
          </div>

          <div className="incident-title-row">
            {/* Heartbeat pulse waveform */}
            <div className="incident-heartbeat-wrap" aria-hidden="true">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#FF453A" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
              </svg>
            </div>
            <h1 className="incident-main-title">{title}</h1>
          </div>

          <p className="incident-subtitle">{subtitle}</p>
        </div>

        {/* Right: Metadata Columns & Actions */}
        <div className="incident-header-right">
          <div className="incident-meta-grid">
            <div className="incident-meta-col">
              <span className="incident-meta-label">Started</span>
              <div className="incident-meta-val">
                <span className="font-mono">{startedTime}</span>
                <span className="incident-meta-ago">({startedAgo})</span>
              </div>
            </div>

            <div className="incident-meta-col">
              <span className="incident-meta-label">Status</span>
              <div className="incident-meta-val status">
                <span className="incident-status-dot" />
                <span>{status}</span>
              </div>
            </div>

            <div className="incident-meta-col">
              <span className="incident-meta-label">Environment</span>
              <div className="incident-env-select-wrap">
                <select
                  value={tenant}
                  onChange={(e) => onChangeTenant?.(e.target.value)}
                  className="incident-env-select"
                >
                  <option value="storefront">tenant_storefront (Prod)</option>
                  <option value="payments">tenant_payments (Finance)</option>
                  <option value="smoke">tenant_smoke (Test)</option>
                </select>
                <ChevronDown size={12} className="incident-env-caret" />
              </div>
            </div>
          </div>

          <div className="incident-actions-row">
            <button
              type="button"
              className="incident-action-btn"
              onClick={onShare}
              title="Share Incident Investigation URL"
            >
              <Share2 size={13} />
              <span>Share</span>
            </button>
            <button
              type="button"
              className="incident-icon-action-btn"
              title="Incident Options"
            >
              <MoreHorizontal size={15} />
            </button>
          </div>
        </div>
      </div>

      {/* Navigation Sub-Tabs & View Mode Switcher */}
      <div className="incident-nav-bar">
        {/* Left Sub-Tabs */}
        <div className="incident-tabs-group" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={activeSubTab === 'system'}
            className={`incident-nav-tab ${activeSubTab === 'system' ? 'active' : ''}`}
            onClick={() => onChangeSubTab('system')}
          >
            <Activity size={14} />
            <span>System View</span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeSubTab === 'timeline'}
            className={`incident-nav-tab ${activeSubTab === 'timeline' ? 'active' : ''}`}
            onClick={() => onChangeSubTab('timeline')}
          >
            <span>Agent Timeline</span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeSubTab === 'hypotheses'}
            className={`incident-nav-tab ${activeSubTab === 'hypotheses' ? 'active' : ''}`}
            onClick={() => onChangeSubTab('hypotheses')}
          >
            <span>Hypotheses</span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeSubTab === 'evidence'}
            className={`incident-nav-tab ${activeSubTab === 'evidence' ? 'active' : ''}`}
            onClick={() => onChangeSubTab('evidence')}
          >
            <span>Evidence</span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeSubTab === 'runbook'}
            className={`incident-nav-tab ${activeSubTab === 'runbook' ? 'active' : ''}`}
            onClick={() => onChangeSubTab('runbook')}
          >
            <span>Runbook</span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeSubTab === 'counterfactuals'}
            className={`incident-nav-tab ${activeSubTab === 'counterfactuals' ? 'active' : ''}`}
            onClick={() => onChangeSubTab('counterfactuals')}
          >
            <span>Counterfactuals</span>
          </button>
        </div>

        {/* Right View Mode Switcher */}
        <div className="incident-view-mode-group" role="group" aria-label="Topology View Mode">
          <button
            type="button"
            className={`incident-view-mode-btn ${viewMode === '3d' ? 'active' : ''}`}
            onClick={() => onChangeViewMode('3d')}
            title="Interactive 3D System View"
          >
            <Box size={13} />
            <span>3D View</span>
          </button>
          <button
            type="button"
            className={`incident-view-mode-btn ${viewMode === 'graph' ? 'active' : ''}`}
            onClick={() => onChangeViewMode('graph')}
            title="2D Force Graph View"
          >
            <Network size={13} />
            <span>Graph View</span>
          </button>
          <button
            type="button"
            className={`incident-view-mode-btn ${viewMode === 'list' ? 'active' : ''}`}
            onClick={() => onChangeViewMode('list')}
            title="List Table View"
          >
            <List size={13} />
            <span>List View</span>
          </button>
        </div>
      </div>
    </div>
  );
};
