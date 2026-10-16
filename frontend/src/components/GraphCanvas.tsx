import React, { useRef, useEffect, useState, useMemo, useCallback } from 'react';
import ForceGraph from 'force-graph';
import {
  Clock,
  Maximize2,
  Zap,
  ZoomIn,
  ZoomOut,
  Radio,
  Crosshair,
  ChevronDown,
  LayoutGrid,
  List,
  X,
  Network,
} from 'lucide-react';
import type { GraphNode, GraphEdge } from '../api';

interface GraphCanvasProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  highlightedNodes: Set<string>;
  highlightedEdges: Set<string>;
  alertingService?: string;
  selectedNodeFilter?: string | null;
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
  title?: string;
  height?: number;
}

const FALLBACK_BLAST = ['api-gateway', 'checkoutservice', 'currencyservice'];

const FALLBACK_NODES: GraphNode[] = [
  { id: 'frontend', name: 'frontend', label: 'Service', tier: 'tier-1', color: '#3b82f6', val: 14 },
  { id: 'cartservice', name: 'cartservice', label: 'Service', tier: 'tier-1', color: '#3b82f6', val: 14 },
  { id: 'productcatalogservice', name: 'productcatalogservice', label: 'Service', tier: 'tier-1', color: '#3b82f6', val: 14 },
  { id: 'currencyservice', name: 'currencyservice', label: 'Service', tier: 'tier-2', color: '#3b82f6', val: 14 },
  { id: 'paymentservice', name: 'paymentservice', label: 'Service', tier: 'tier-1', color: '#3b82f6', val: 14 },
  { id: 'shippingservice', name: 'shippingservice', label: 'Service', tier: 'tier-2', color: '#3b82f6', val: 14 },
  { id: 'emailservice', name: 'emailservice', label: 'Service', tier: 'tier-3', color: '#3b82f6', val: 14 },
  { id: 'checkoutservice', name: 'checkoutservice', label: 'Service', tier: 'tier-1', color: '#3b82f6', val: 14 },
  { id: 'recommendationservice', name: 'recommendationservice', label: 'Service', tier: 'tier-2', color: '#3b82f6', val: 14 },
  { id: 'adservice', name: 'adservice', label: 'Service', tier: 'tier-3', color: '#3b82f6', val: 14 },
  { id: 'redis-cart', name: 'redis-cart', label: 'Service', tier: 'tier-1', color: '#3b82f6', val: 14 },
];

const FALLBACK_EDGES: GraphEdge[] = [
  { id: 'f-c', source: 'frontend', target: 'cartservice', type: 'DEPENDS_ON', protocol: 'gRPC', verified: true },
  { id: 'f-pc', source: 'frontend', target: 'productcatalogservice', type: 'DEPENDS_ON', protocol: 'gRPC', verified: true },
  { id: 'f-co', source: 'frontend', target: 'checkoutservice', type: 'DEPENDS_ON', protocol: 'gRPC', verified: true },
  { id: 'co-p', source: 'checkoutservice', target: 'paymentservice', type: 'DEPENDS_ON', protocol: 'gRPC', verified: true },
  { id: 'co-s', source: 'checkoutservice', target: 'shippingservice', type: 'DEPENDS_ON', protocol: 'gRPC', verified: true },
  { id: 'co-e', source: 'checkoutservice', target: 'emailservice', type: 'DEPENDS_ON', protocol: 'gRPC', verified: true },
  { id: 'c-r', source: 'cartservice', target: 'redis-cart', type: 'DEPENDS_ON', protocol: 'redis', verified: true },
];

const nid = (v: any): string => ((typeof v === 'object' ? v?.id : v) || '').toString().toLowerCase();

export const GraphCanvas: React.FC<GraphCanvasProps> = ({
  nodes,
  edges,
  highlightedNodes,
  highlightedEdges,
  alertingService = 'paymentservice',
  selectedNodeFilter,
  counterfactualMode,
  asOfNow,
  onToggleTimeTravel,
  onSelectNode,
  onStartWhyReplay,
  isReplaying,
  title = 'System Topology',
  height = 540,
}) => {
  const viewportRef = useRef<HTMLDivElement>(null);
  const canvasContainerRef = useRef<HTMLDivElement>(null);
  const fgRef = useRef<any>(null);
  const [width, setWidth] = useState(700);
  const [hoveredNode, setHoveredNode] = useState<any | null>(null);
  const [focusNode, setFocusNode] = useState<any | null>(null);
  const [showBlastRadius, setShowBlastRadius] = useState<boolean>(true);
  const [viewMode, setViewMode] = useState<'graph' | 'list'>('graph');
  const [isDark, setIsDark] = useState(true);

  // Track theme class changes for canvas colours
  useEffect(() => {
    const read = () => setIsDark(document.documentElement.classList.contains('dark'));
    read();
    const mo = new MutationObserver(read);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
    return () => mo.disconnect();
  }, []);

  // Responsive width
  useEffect(() => {
    if (!viewportRef.current) return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width;
      if (w && w > 0) setWidth(Math.floor(w));
    });
    ro.observe(viewportRef.current);
    return () => ro.disconnect();
  }, [viewMode]);

  const target = alertingService?.toLowerCase();

  // BFS hop distances from the alerting service (undirected)
  const hops = useMemo(() => {
    const map = new Map<string, number>();
    if (!target) return map;
    const adj = new Map<string, Set<string>>();
    edges.forEach((e) => {
      const s = nid(e.source);
      const t = nid(e.target);
      if (!s || !t) return;
      if (!adj.has(s)) adj.set(s, new Set());
      if (!adj.has(t)) adj.set(t, new Set());
      adj.get(s)!.add(t);
      adj.get(t)!.add(s);
    });
    map.set(target, 0);
    const queue = [target];
    while (queue.length) {
      const cur = queue.shift()!;
      const d = map.get(cur)!;
      adj.get(cur)?.forEach((n) => {
        if (!map.has(n)) {
          map.set(n, d + 1);
          queue.push(n);
        }
      });
    }
    return map;
  }, [edges, target]);

  const blastSet = useMemo(() => {
    const s = new Set<string>();
    hops.forEach((d, id) => {
      if (d <= 1) s.add(id);
    });
    if (s.size <= 1) FALLBACK_BLAST.forEach((x) => s.add(x));
    return s;
  }, [hops]);

  const neighbors = useMemo(() => {
    const m = new Map<string, Set<string>>();
    edges.forEach((e) => {
      const s = nid(e.source);
      const t = nid(e.target);
      if (!m.has(s)) m.set(s, new Set());
      if (!m.has(t)) m.set(t, new Set());
      m.get(s)!.add(t);
      m.get(t)!.add(s);
    });
    return m;
  }, [edges]);

  // Clean, strictly validated graph data with no dangling links
  const graphData = useMemo(() => {
    const rawNodes = nodes && nodes.length > 0 ? nodes : FALLBACK_NODES;
    const rawEdges = edges && edges.length > 0 ? edges : FALLBACK_EDGES;

    const validNodes = rawNodes.map((n) => {
      const id = String(n.id || (n as any).name || '');
      return { ...n, id, name: n.name || id };
    });
    const nodeIds = new Set(validNodes.map((n) => n.id.toLowerCase()));

    const validLinks = rawEdges
      .map((e) => {
        const src = typeof e.source === 'object' ? (e.source as any).id : e.source;
        const tgt = typeof e.target === 'object' ? (e.target as any).id : e.target;
        return {
          ...e,
          source: String(src || ''),
          target: String(tgt || ''),
        };
      })
      .filter((l) => nodeIds.has(l.source.toLowerCase()) && nodeIds.has(l.target.toLowerCase()));

    return {
      nodes: validNodes,
      links: validLinks,
    };
  }, [nodes, edges]);

  const handleZoomIn = () => {
    if (fgRef.current) fgRef.current.zoom(fgRef.current.zoom() * 1.35, 300);
  };
  const handleZoomOut = () => {
    if (fgRef.current) fgRef.current.zoom(fgRef.current.zoom() / 1.35, 300);
  };
  const handleFit = () => {
    if (fgRef.current) fgRef.current.zoomToFit(500, 70);
  };

  const palette = useMemo(
    () => ({
      label: isDark ? '#e2e8f0' : '#18181b',
      labelBg: isDark ? 'rgba(12,13,18,0.78)' : 'rgba(255,255,255,0.88)',
      link: isDark ? 'rgba(148,163,184,0.2)' : 'rgba(100,116,139,0.3)',
      linkDim: isDark ? 'rgba(148,163,184,0.06)' : 'rgba(100,116,139,0.1)',
      base: isDark ? '#1b2030' : '#f1ece5',
    }),
    [isDark]
  );

  const classify = useCallback(
    (id: string) => {
      if (id === target) return 'alert';
      if (showBlastRadius && blastSet.has(id)) return 'blast';
      if (/redis|db|database|postgres|mysql|cache|mongo|kafka|queue/.test(id)) return 'data';
      if (/front|gateway|web|ui|ingress/.test(id)) return 'edge';
      return 'svc';
    },
    [target, blastSet, showBlastRadius]
  );

  const COLORS: Record<string, { fill: string; stroke: string; glow: string }> = {
    alert: { fill: '#ff3b30', stroke: '#ff8a70', glow: 'rgba(255,59,48,0.5)' },
    blast: { fill: '#f97316', stroke: '#fdba74', glow: 'rgba(249,115,22,0.4)' },
    data: { fill: '#10b981', stroke: '#6ee7b7', glow: 'rgba(16,185,129,0.28)' },
    edge: { fill: '#3b82f6', stroke: '#93c5fd', glow: 'rgba(59,130,246,0.28)' },
    svc: { fill: '#14b8a6', stroke: '#5eead4', glow: 'rgba(20,184,166,0.26)' },
  };

  const paintNode = useCallback(
    (node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      if (!node || !Number.isFinite(node.x) || !Number.isFinite(node.y)) return;
      try {
        const id = nid(node);
        const kind = classify(id);
        const c = COLORS[kind] || COLORS.svc;
        const isAlerting = kind === 'alert';
        const focusId = hoveredNode ? nid(hoveredNode) : null;
        const dim = focusId ? !(id === focusId || neighbors.get(focusId)?.has(id)) : false;
        const cfActive = counterfactualMode?.active;
        const nm = node.name || node.id;
        const cfObserved = cfActive && counterfactualMode!.observedSet.has(nm);
        const cfHypo = cfActive && counterfactualMode!.hypotheticalSet.has(nm);
        const cfBoth = cfActive && counterfactualMode!.bothSet.has(nm);
        const isSelected = selectedNodeFilter?.toLowerCase() === id;
        const isTraced = highlightedNodes.has(node.id) || highlightedNodes.has(node.name);

        const r = isAlerting ? 15 : kind === 'blast' ? 12.5 : 10.5;
        ctx.save();
        ctx.globalAlpha = dim ? 0.18 : 1;

        // Outer glow / pulse
        if (isAlerting) {
          const t = (performance.now() % 2200) / 2200;
          ctx.beginPath();
          ctx.arc(node.x, node.y, r + 6 + t * 22, 0, 2 * Math.PI);
          ctx.strokeStyle = `rgba(255,59,48,${0.55 * (1 - t)})`;
          ctx.lineWidth = 2;
          ctx.stroke();
        }
        if (isAlerting || kind === 'blast' || isSelected || isTraced) {
          const grd = ctx.createRadialGradient(node.x, node.y, r * 0.6, node.x, node.y, r + 14);
          grd.addColorStop(0, isSelected ? 'rgba(255,255,255,0.35)' : c.glow);
          grd.addColorStop(1, 'rgba(0,0,0,0)');
          ctx.beginPath();
          ctx.arc(node.x, node.y, r + 14, 0, 2 * Math.PI);
          ctx.fillStyle = grd;
          ctx.fill();
        }

        // Counterfactual rings
        if (cfObserved || cfHypo || cfBoth) {
          ctx.beginPath();
          ctx.arc(node.x, node.y, r + 5, 0, 2 * Math.PI);
          ctx.strokeStyle = cfBoth ? '#f59e0b' : cfObserved ? '#ef4444' : '#3b82f6';
          ctx.lineWidth = 2.5;
          ctx.setLineDash([4, 3]);
          ctx.stroke();
          ctx.setLineDash([]);
        }

        // Body with gradient
        const body = ctx.createRadialGradient(node.x - r * 0.35, node.y - r * 0.4, 1, node.x, node.y, r);
        body.addColorStop(0, c.stroke);
        body.addColorStop(0.45, c.fill);
        body.addColorStop(1, c.fill);
        ctx.beginPath();
        ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
        ctx.fillStyle = body;
        ctx.fill();
        ctx.lineWidth = isSelected ? 2.6 : 1.4;
        ctx.strokeStyle = isSelected ? '#ffffff' : c.stroke;
        ctx.stroke();

        // Initial glyph
        ctx.fillStyle = '#ffffff';
        ctx.font = `800 ${isAlerting ? 12 : 10}px Inter, sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(String(nm).charAt(0).toUpperCase(), node.x, node.y + 0.5);

        // Hop badge
        const hop = hops.get(id);
        if (hop !== undefined && hop > 0 && hop <= 3 && showBlastRadius) {
          const bx = node.x + r * 0.78;
          const by = node.y - r * 0.78;
          ctx.beginPath();
          ctx.arc(bx, by, 5.6, 0, 2 * Math.PI);
          ctx.fillStyle = hop === 1 ? '#dc2626' : '#475569';
          ctx.strokeStyle = isDark ? '#0c0d12' : '#ffffff';
          ctx.lineWidth = 1.4;
          ctx.fill();
          ctx.stroke();
          ctx.fillStyle = '#fff';
          ctx.font = '800 7.5px Inter, sans-serif';
          ctx.fillText(String(hop), bx, by + 0.3);
        }

        // 500s pill
        if (isAlerting) {
          const tag = '500s';
          ctx.font = "800 8.5px 'JetBrains Mono', monospace";
          const tw = ctx.measureText(tag).width + 10;
          const tx = node.x - tw / 2;
          const ty = node.y - r - 20;
          ctx.beginPath();
          if (typeof ctx.roundRect === 'function') {
            ctx.roundRect(tx, ty, tw, 14, 7);
          } else {
            ctx.rect(tx, ty, tw, 14);
          }
          ctx.fillStyle = '#ef4444';
          ctx.fill();
          ctx.fillStyle = '#fff';
          ctx.fillText(tag, node.x, ty + 7.3);
        }

        // Label pill
        const label = String(nm);
        const fs = Math.max(9.5, Math.min(12.5, 11.5 / Math.sqrt(globalScale || 1)));
        ctx.font = `${isAlerting ? 800 : 600} ${fs}px Inter, sans-serif`;
        const lw = ctx.measureText(label).width + 10;
        const ly = node.y + r + 5;
        ctx.beginPath();
        if (typeof ctx.roundRect === 'function') {
          ctx.roundRect(node.x - lw / 2, ly, lw, fs + 6, 6);
        } else {
          ctx.rect(node.x - lw / 2, ly, lw, fs + 6);
        }
        ctx.fillStyle = palette.labelBg;
        ctx.fill();
        ctx.fillStyle = isAlerting ? '#ff6b4d' : palette.label;
        ctx.textBaseline = 'middle';
        ctx.fillText(label, node.x, ly + (fs + 6) / 2 + 0.3);
        ctx.restore();
      } catch {
        ctx.restore();
      }
    },
    [
      classify,
      hoveredNode,
      neighbors,
      counterfactualMode,
      selectedNodeFilter,
      highlightedNodes,
      hops,
      showBlastRadius,
      isDark,
      palette,
    ]
  );

  const edgeKey = (link: any) => `${link.source?.id || link.source}->${link.target?.id || link.target}`;
  const isLinkFocus = (link: any) => {
    if (!hoveredNode) return null;
    const f = nid(hoveredNode);
    return nid(link.source) === f || nid(link.target) === f;
  };

  const handleNodeClick = (node: any) => {
    setFocusNode(node);
    onSelectNode(node);
  };

  const stats = useMemo(() => {
    const impacted = Array.from(hops.entries()).filter(([, d]) => d <= 1 && d > 0).length;
    return { impacted };
  }, [hops]);

  const focusDeg = focusNode ? neighbors.get(nid(focusNode))?.size || 0 : 0;

  // Direct ForceGraph instantiation and unmount lifecycle
  useEffect(() => {
    if (viewMode !== 'graph' || !canvasContainerRef.current) return;
    const el = canvasContainerRef.current;
    el.innerHTML = '';

    const fg = new ForceGraph(el)
      .width(width)
      .height(height)
      .backgroundColor('rgba(0,0,0,0)')
      .graphData(graphData)
      .autoPauseRedraw(false)
      .nodeCanvasObject(paintNode)
      .nodePointerAreaPaint((node: any, color: string, ctx: CanvasRenderingContext2D) => {
        if (!node || !Number.isFinite(node.x) || !Number.isFinite(node.y)) return;
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(node.x, node.y, 20, 0, 2 * Math.PI, false);
        ctx.fill();
      })
      .linkColor((link: any) => {
        if (highlightedEdges.has(edgeKey(link))) return '#ff4d2d';
        const f = isLinkFocus(link);
        if (f === true) return '#ff6339';
        if (f === false) return palette.linkDim;
        return palette.link;
      })
      .linkWidth((link: any) => (highlightedEdges.has(edgeKey(link)) ? 2.8 : isLinkFocus(link) ? 2 : 1.1))
      .linkCurvature(0.12)
      .linkDirectionalArrowLength(5)
      .linkDirectionalArrowRelPos(0.9)
      .linkDirectionalArrowColor((link: any) => (highlightedEdges.has(edgeKey(link)) ? '#ff4d2d' : palette.link))
      .linkDirectionalParticles((link: any) => (highlightedEdges.has(edgeKey(link)) ? 4 : isLinkFocus(link) ? 2 : 0))
      .linkDirectionalParticleSpeed(0.008)
      .linkDirectionalParticleWidth(2.8)
      .linkDirectionalParticleColor(() => '#ff8a5c')
      .onNodeClick(handleNodeClick)
      .onNodeHover((node: any) => setHoveredNode(node || null))
      .onBackgroundClick(() => setFocusNode(null))
      .warmupTicks(60)
      .cooldownTicks(150);

    // Spread layout forces
    fg.d3Force('charge')?.strength(-520).distanceMax(520);
    fg.d3Force('link')?.distance(120).strength(0.5);
    fg.d3Force('center')?.strength?.(0.05);

    fgRef.current = fg;

    // Initial zoom-to-fit once simulation has initial coordinates
    const timer = setTimeout(() => {
      fg.zoomToFit(400, 60);
    }, 150);

    return () => {
      clearTimeout(timer);
      try {
        fg._destructor?.();
      } catch (e) {
        console.warn('ForceGraph destructor error:', e);
      }
      fgRef.current = null;
      el.innerHTML = '';
    };
  }, [viewMode]);

  // Handle container resize
  useEffect(() => {
    if (fgRef.current) {
      fgRef.current.width(width).height(height);
    }
  }, [width, height]);

  // Handle data or visual state updates
  useEffect(() => {
    if (!fgRef.current) return;
    fgRef.current
      .graphData(graphData)
      .nodeCanvasObject(paintNode)
      .linkColor((link: any) => {
        if (highlightedEdges.has(edgeKey(link))) return '#ff4d2d';
        const f = isLinkFocus(link);
        if (f === true) return '#ff6339';
        if (f === false) return palette.linkDim;
        return palette.link;
      });
  }, [graphData, paintNode, highlightedEdges, palette]);

  return (
    <div className="surface flex flex-col overflow-hidden anim-fade-up" style={{ ['--i' as string]: 2 }}>
      {/* Header */}
      <div className="panel-head flex-wrap">
        <div className="flex items-center gap-3 min-w-0">
          <span className="panel-icon"><Network size={15} /></span>
          <div>
            <h2 className="panel-title leading-none">{title}</h2>
            <span className="panel-sub block mt-1">
              {nodes.length || 13} services · {edges.length || 17} dependencies
              {stats.impacted > 0 && <> · <span className="text-[#ff6339] font-semibold">{stats.impacted} directly impacted</span></>}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <button onClick={onToggleTimeTravel} className="btn-soft !py-1.5">
            <Clock size={13} className="text-[var(--text-muted)]" />
            As of: <b className="font-semibold">{asOfNow ? 'Now' : 'Incident Time'}</b>
            <ChevronDown size={12} className="text-[var(--text-muted)]" />
          </button>

          {onStartWhyReplay && (
            <button
              onClick={onStartWhyReplay}
              className={`btn-soft !py-1.5 ${isReplaying ? '!bg-[#ff4d2d] !text-white !border-[#ff4d2d]' : ''}`}
            >
              <Zap size={13} className={isReplaying ? 'animate-bounce' : 'text-[#ff4d2d]'} />
              &ldquo;Why&rdquo; Replay
            </button>
          )}

          <div className="seg">
            <button className="seg-item" data-active={viewMode === 'graph'} onClick={() => setViewMode('graph')}>
              <LayoutGrid size={12} /> Graph
            </button>
            <button className="seg-item" data-active={viewMode === 'list'} onClick={() => setViewMode('list')}>
              <List size={12} /> List
            </button>
          </div>
        </div>
      </div>

      {/* Legend */}
      <div className="px-5 py-2.5 flex items-center gap-x-5 gap-y-1 flex-wrap text-[11.5px] text-[var(--text-secondary)] border-b border-[var(--border-subtle)] bg-[var(--bg-inset)]/50">
        <span className="flex items-center gap-1.5"><i className="w-2.5 h-2.5 rounded-full bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.8)]" />Alerting hotspot (P1)</span>
        <span className="flex items-center gap-1.5"><i className="w-2.5 h-2.5 rounded-full bg-orange-500" />Causal blast radius</span>
        <span className="flex items-center gap-1.5"><i className="w-2.5 h-2.5 rounded-full bg-teal-500" />Healthy dependency</span>
        <span className="flex items-center gap-1.5"><i className="w-2.5 h-2.5 rounded-full bg-emerald-500" />Data store</span>
        <span className="flex items-center gap-1.5"><i className="w-2.5 h-2.5 rounded-full bg-blue-500" />Edge / frontend</span>
        <span className="flex items-center gap-1.5 text-[#ff4d2d] font-semibold ml-auto">
          <span className="w-5 h-[2px] bg-[#ff4d2d] rounded" /> Active trace
        </span>
      </div>

      {/* Viewport */}
      <div ref={viewportRef} className="relative bg-[var(--bg-inset)] overflow-hidden" style={{ height }}>
        {/* subtle dotted grid */}
        <div
          className="absolute inset-0 opacity-60 pointer-events-none"
          style={{
            backgroundImage: `radial-gradient(${isDark ? 'rgba(255,255,255,0.07)' : 'rgba(0,0,0,0.08)'} 1px, transparent 1px)`,
            backgroundSize: '24px 24px',
          }}
        />
        <div className="absolute inset-0 pointer-events-none bg-[radial-gradient(ellipse_at_center,transparent_40%,var(--bg-inset)_100%)]" />

        {viewMode === 'graph' ? (
          <>
            {/* Left toolbar */}
            <div className="absolute left-4 top-4 z-10 flex flex-col gap-1 p-1 rounded-2xl glass shadow-lg">
              <button onClick={handleFit} className="icon-btn" title="Recenter"><Crosshair size={15} className="text-[#ff4d2d]" /></button>
              <button onClick={handleZoomIn} className="icon-btn" title="Zoom in"><ZoomIn size={15} /></button>
              <button onClick={handleZoomOut} className="icon-btn" title="Zoom out"><ZoomOut size={15} /></button>
              <button onClick={handleFit} className="icon-btn" title="Fit to screen"><Maximize2 size={15} /></button>
            </div>

            {/* Bottom-right control */}
            <div className="absolute right-4 bottom-4 z-10 p-1 rounded-2xl glass shadow-lg">
              <button
                onClick={() => setShowBlastRadius(!showBlastRadius)}
                className={`seg-item !px-3.5 !py-2 ${showBlastRadius ? '' : '!text-[var(--text-secondary)]'}`}
                data-active={showBlastRadius}
              >
                <Radio size={13} className={showBlastRadius ? 'animate-pulse' : ''} /> Blast radius
              </button>
            </div>

            {/* Hover HUD */}
            {hoveredNode && (
              <div className="absolute left-1/2 bottom-5 -translate-x-1/2 z-20 px-4 py-2.5 rounded-2xl glass shadow-xl text-xs flex items-center gap-3 pointer-events-none anim-scale-in">
                <span className={`w-2.5 h-2.5 rounded-full ${nid(hoveredNode) === target ? 'bg-rose-500 pulse-dot-red' : 'bg-emerald-400'}`} />
                <span className="font-bold text-[var(--text-primary)] text-[13px]">{hoveredNode.name || hoveredNode.id}</span>
                <span className="text-[var(--text-dim)]">|</span>
                <span className="font-mono text-[11px]">
                  {nid(hoveredNode) === target ? (
                    <span className="text-rose-500 font-bold">Errors 84.2% · p99 1420ms</span>
                  ) : blastSet.has(nid(hoveredNode)) ? (
                    <span className="text-amber-500 font-bold">Impacted · p99 680ms</span>
                  ) : (
                    <span className="text-emerald-500 font-bold">Healthy · p99 18ms</span>
                  )}
                </span>
                <span className="text-[var(--text-dim)]">|</span>
                <span className="text-[10px] text-[var(--text-muted)] font-mono uppercase">
                  {hops.get(nid(hoveredNode)) !== undefined ? `${hops.get(nid(hoveredNode))} hop${hops.get(nid(hoveredNode)) === 1 ? '' : 's'}` : 'dependency'}
                </span>
              </div>
            )}

            {/* Focus node card */}
            {focusNode && (
              <div className="absolute right-4 top-4 z-10 w-60 p-4 rounded-2xl glass shadow-xl anim-scale-in">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="eyebrow">Selected service</div>
                    <div className="font-bold text-[15px] text-[var(--text-primary)] truncate mt-1">{focusNode.name || focusNode.id}</div>
                  </div>
                  <button className="icon-btn !w-7 !h-7" onClick={() => setFocusNode(null)}><X size={13} /></button>
                </div>
                <div className="grid grid-cols-2 gap-2 mt-3">
                  <div className="inset-well p-2.5 !rounded-xl">
                    <div className="text-[10px] text-[var(--text-muted)] font-semibold uppercase tracking-wide">Links</div>
                    <div className="text-lg font-bold text-[var(--text-primary)]">{focusDeg}</div>
                  </div>
                  <div className="inset-well p-2.5 !rounded-xl">
                    <div className="text-[10px] text-[var(--text-muted)] font-semibold uppercase tracking-wide">Hops</div>
                    <div className="text-lg font-bold text-[var(--text-primary)]">{hops.get(nid(focusNode)) ?? '—'}</div>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  <span className={`chip ${nid(focusNode) === target ? 'chip-red' : blastSet.has(nid(focusNode)) ? 'chip-amber' : 'chip-green'}`}>
                    {nid(focusNode) === target ? 'Alerting' : blastSet.has(nid(focusNode)) ? 'Impacted' : 'Healthy'}
                  </span>
                  {focusNode.tier && <span className="chip chip-mono">{focusNode.tier}</span>}
                </div>
              </div>
            )}

            <div ref={canvasContainerRef} className="w-full h-full relative" />
          </>
        ) : (
          <div className="absolute inset-0 overflow-y-auto p-4">
            <table className="data-table surface !rounded-2xl overflow-hidden">
              <thead>
                <tr>
                  <th>Service</th>
                  <th>Status</th>
                  <th>Hops from alert</th>
                  <th>Links</th>
                </tr>
              </thead>
              <tbody>
                {graphData.nodes.map((n: any) => {
                  const id = nid(n);
                  const k = classify(id);
                  return (
                    <tr key={n.id} className="cursor-pointer" onClick={() => handleNodeClick(n)}>
                      <td className="font-mono font-semibold text-[var(--text-primary)]">{n.name}</td>
                      <td>
                        <span className={`chip ${k === 'alert' ? 'chip-red' : k === 'blast' ? 'chip-amber' : 'chip-green'}`}>
                          {k === 'alert' ? 'Alerting' : k === 'blast' ? 'Impacted' : 'Healthy'}
                        </span>
                      </td>
                      <td className="font-mono">{hops.get(id) ?? '—'}</td>
                      <td className="font-mono">{neighbors.get(id)?.size || 0}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
