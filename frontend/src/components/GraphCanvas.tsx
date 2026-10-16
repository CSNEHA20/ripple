import React, { useRef, useEffect, useState, useMemo } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { Eye, Clock, Maximize2, RotateCcw, Zap } from 'lucide-react';
import type { GraphNode, GraphEdge } from '../api';

interface GraphCanvasProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  highlightedNodes: Set<string>;
  highlightedEdges: Set<string>;
  counterfactualMode?: {
    active: boolean;
    observedSet: Set<string>;
    hypotheticalSet: Set<string>;
    bothSet: Set<string>;
  };
  asOfNow: boolean;
  onToggleTimeTravel: () => void;
  onSelectNode: (node: GraphNode) => void;
  onStartWhyReplay?: () => void;
  isReplaying?: boolean;
}

export const GraphCanvas: React.FC<GraphCanvasProps> = ({
  nodes,
  edges,
  highlightedNodes,
  highlightedEdges,
  counterfactualMode,
  asOfNow,
  onToggleTimeTravel,
  onSelectNode,
  onStartWhyReplay,
  isReplaying,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const fgRef = useRef<any>(null);
  const [dimensions, setDimensions] = useState({ width: 600, height: 420 });

  useEffect(() => {
    if (!containerRef.current) return;
    const updateSize = () => {
      if (containerRef.current) {
        setDimensions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight || 420,
        });
      }
    };
    updateSize();
    window.addEventListener('resize', updateSize);
    return () => window.removeEventListener('resize', updateSize);
  }, []);

  const graphData = useMemo(() => {
    return {
      nodes: nodes.map((n) => ({
        ...n,
        id: n.id || (n as any).name,
        name: n.name || n.id,
      })),
      links: edges.map((e) => ({
        ...e,
        source: typeof e.source === 'object' ? (e.source as any).id : e.source,
        target: typeof e.target === 'object' ? (e.target as any).id : e.target,
      })),
    };
  }, [nodes, edges]);

  // Color selection logic based on node tier and counterfactual overlay
  const getNodeColor = (node: any) => {
    const id = node.id || node.name;

    // Counterfactual overlay has highest visual priority
    if (counterfactualMode?.active) {
      if (counterfactualMode.bothSet.has(id)) return '#f59e0b'; // Amber (Both)
      if (counterfactualMode.observedSet.has(id)) return '#ef4444'; // Red (Observed only)
      if (counterfactualMode.hypotheticalSet.has(id)) return '#3b82f6'; // Blue (Hypothetical only)
      return '#374151'; // Dimmed
    }

    // Highlighted during trace navigation
    if (highlightedNodes.size > 0) {
      if (highlightedNodes.has(id)) return '#4ade80'; // Neon lime active highlight
      return '#0e1f16'; // Dim non-trace nodes
    }

    // Label and tier default color
    if (node.label === 'Service') {
      if (node.tier === 'tier-0') return '#4ade80'; // Neon lime
      if (node.tier === 'tier-1') return '#22c55e'; // Emerald green
      return '#e4ebd9'; // Cream bone
    }
    if (node.label === 'Hypothesis') return '#fbbf24';
    if (node.label === 'Evidence') return '#34d399';
    if (node.label === 'Incident') return '#ef4444';
    if (node.label === 'Runbook') return '#e4ebd9';

    return '#a3b8aa';
  };

  const getNodeSize = (node: any) => {
    const id = node.id || node.name;
    if (highlightedNodes.has(id)) return 9;
    if (node.label === 'Incident') return 11;
    if (node.tier === 'tier-0') return 8;
    return 6;
  };

  return (
    <div className="graph-canvas-container glass-panel" ref={containerRef}>
      <div className="canvas-header">
        <div className="canvas-title-group">
          <h3>Interactive System Graph Canvas</h3>
          <span className="node-count-badge">
            {nodes.length} Nodes · {edges.length} Edges
          </span>
        </div>

        <div className="canvas-controls">
          {/* Time travel toggle */}
          <button
            className={`time-travel-btn ${asOfNow ? 'now' : 'incident'}`}
            onClick={onToggleTimeTravel}
            title="Toggle temporal graph between Incident Alert Time vs Current Now"
          >
            <Clock size={13} />
            <span>As of: {asOfNow ? 'Now (Head)' : 'Incident Time'}</span>
          </button>

          {/* Why Replay button */}
          {onStartWhyReplay && (
            <button
              className={`replay-btn ${isReplaying ? 'active' : ''}`}
              onClick={onStartWhyReplay}
              title="Step through investigation provenance trace in order"
            >
              <Zap size={13} />
              <span>{isReplaying ? 'Replaying Trace...' : '"Why" Replay'}</span>
            </button>
          )}

          <button
            className="zoom-reset-btn"
            onClick={() => fgRef.current?.zoomToFit(400, 20)}
            title="Recenter and Fit Graph"
          >
            <Maximize2 size={13} />
          </button>
        </div>
      </div>

      {/* Legend */}
      <div className="canvas-legend">
        {counterfactualMode?.active ? (
          <>
            <span className="legend-item"><span className="legend-dot red"></span> Observed Only</span>
            <span className="legend-item"><span className="legend-dot blue"></span> Hypothetical Only</span>
            <span className="legend-item"><span className="legend-dot amber"></span> Both Impacted</span>
          </>
        ) : (
          <>
            <span className="legend-item"><span className="legend-dot tier0"></span> Tier-0 (Core)</span>
            <span className="legend-item"><span className="legend-dot tier1"></span> Tier-1</span>
            <span className="legend-item"><span className="legend-dot service"></span> Tier-2</span>
            <span className="legend-item"><span className="legend-dot highlight"></span> Active Trace</span>
          </>
        )}
      </div>

      {/* Force Graph */}
      <div className="canvas-viewport">
        <ForceGraph2D
          ref={fgRef}
          width={dimensions.width}
          height={dimensions.height - 48}
          graphData={graphData}
          nodeLabel={(n: any) => `${n.name || n.id} [${n.label || 'Node'}] ${n.tier ? `(${n.tier})` : ''}`}
          nodeColor={getNodeColor}
          nodeVal={getNodeSize}
          linkColor={(link: any) => {
            const edgeKey = `${link.source?.id || link.source}->${link.target?.id || link.target}`;
            if (highlightedEdges.has(edgeKey)) return '#06b6d4';
            if (link.verified === false) return '#f59e0b';
            return 'rgba(255, 255, 255, 0.16)';
          }}
          linkWidth={(link: any) => {
            const edgeKey = `${link.source?.id || link.source}->${link.target?.id || link.target}`;
            return highlightedEdges.has(edgeKey) ? 2.5 : 1;
          }}
          linkDirectionalArrowLength={3.5}
          linkDirectionalArrowRelPos={0.95}
          onNodeClick={(node: any) => onSelectNode(node)}
          cooldownTicks={80}
        />
      </div>
    </div>
  );
};
