import React from 'react';
import {
  Search,
  Code,
  Database,
  Layers,
  Clock,
  CheckCircle,
  X,
  ExternalLink,
} from 'lucide-react';
import type { TraceStep, HypothesisEvidence } from '../api';

interface InspectorDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  selectedStep: TraceStep | null;
  selectedEvidence: HypothesisEvidence | null;
  selectedNode: any | null;
}

export const InspectorDrawer: React.FC<InspectorDrawerProps> = ({
  isOpen,
  onClose,
  selectedStep,
  selectedEvidence,
  selectedNode,
}) => {
  if (!isOpen) return null;

  return (
    <div className="inspector-drawer-backdrop" onClick={onClose}>
      <div className="inspector-drawer glass-panel" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-header">
          <div className="drawer-title-group">
            <Search size={16} className="text-cyan" />
            <h3>Provenance Inspector (M10 Deep Trace)</h3>
          </div>
          <button className="close-btn" onClick={onClose}>
            <X size={16} />
          </button>
        </div>

        <div className="inspector-body">
          {/* Active Trace Step View */}
          {selectedStep && (
            <div className="inspector-section">
              <div className="section-title-sm">
                <Code size={13} />
                <span>Tool Invocation: <code>{selectedStep.tool}</code></span>
              </div>
              <p className="step-summary">{selectedStep.summary}</p>

              {/* Exact Cypher Executed */}
              {selectedStep.cypher && (
                <div className="cypher-block">
                  <div className="code-header">
                    <span>FalkorDB Cypher Query</span>
                    {selectedStep.duration_ms && (
                      <span className="duration-tag">{selectedStep.duration_ms.toFixed(1)}ms</span>
                    )}
                  </div>
                  <pre className="cypher-code">{selectedStep.cypher}</pre>
                </div>
              )}

              {/* Parameters */}
              {selectedStep.params && Object.keys(selectedStep.params).length > 0 && (
                <div className="params-block">
                  <span className="params-title">Parameters:</span>
                  <pre className="params-json">
                    {JSON.stringify(selectedStep.params, null, 2)}
                  </pre>
                </div>
              )}

              {/* Subgraph touched */}
              <div className="touched-subgraph">
                <span className="params-title">Touched Nodes ({selectedStep.node_ids?.length || 0}):</span>
                <div className="tags-row">
                  {selectedStep.node_ids?.map((nid) => (
                    <span key={nid} className="node-tag">{nid}</span>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Evidence Details */}
          {selectedEvidence && (
            <div className="inspector-section">
              <div className="section-title-sm">
                <Database size={13} />
                <span>Evidence Fact Provenance</span>
              </div>
              <div className="evidence-detail-card">
                <div className="detail-row">
                  <span className="detail-label">Evidence ID:</span>
                  <code>{selectedEvidence.id}</code>
                </div>
                <div className="detail-row">
                  <span className="detail-label">Type:</span>
                  <span className="tag tag-cyan">{selectedEvidence.type}</span>
                </div>
                <div className="detail-row">
                  <span className="detail-label">Cognitive Kind:</span>
                  <span className={`kind-tag ${selectedEvidence.kind}`}>{selectedEvidence.kind}</span>
                </div>
                <div className="detail-row">
                  <span className="detail-label">Summary:</span>
                  <span className="detail-val">{selectedEvidence.summary}</span>
                </div>
                {selectedEvidence.freshness !== undefined && (
                  <div className="detail-row">
                    <span className="detail-label">Freshness Score:</span>
                    <span>{(selectedEvidence.freshness * 100).toFixed(1)}%</span>
                  </div>
                )}
                {selectedEvidence.source_ref && (
                  <div className="detail-row">
                    <span className="detail-label">Source Reference:</span>
                    <code>{selectedEvidence.source_ref}</code>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Graph Node Selection */}
          {selectedNode && (
            <div className="inspector-section">
              <div className="section-title-sm">
                <Layers size={13} />
                <span>Selected Graph Node: {selectedNode.name || selectedNode.id}</span>
              </div>
              <div className="node-detail-card">
                <div className="detail-row">
                  <span className="detail-label">Label:</span>
                  <span className="tag tag-purple">{selectedNode.label}</span>
                </div>
                {selectedNode.tier && (
                  <div className="detail-row">
                    <span className="detail-label">Service Tier:</span>
                    <span>{selectedNode.tier}</span>
                  </div>
                )}
                {selectedNode.status && (
                  <div className="detail-row">
                    <span className="detail-label">Health Status:</span>
                    <span className={`status-badge-inline ${selectedNode.status}`}>
                      {selectedNode.status}
                    </span>
                  </div>
                )}
                <div className="props-json-block">
                  <span className="detail-label">Raw Properties:</span>
                  <pre className="props-json">
                    {JSON.stringify(selectedNode.props || selectedNode, null, 2)}
                  </pre>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
