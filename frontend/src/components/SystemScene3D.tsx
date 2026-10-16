import React, { useRef, useEffect, useState, useMemo } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import {
  Layers,
  Flame,
  GitBranch,
  Crosshair,
  Maximize2,
  Zap,
  Tag,
  Eye,
  X,
  ExternalLink,
  Filter,
} from 'lucide-react';
import type { GraphNode, GraphEdge } from '../api';
import './SystemScene3D.css';

export type VisMode = 'overview' | 'impact' | 'causal';

interface SystemScene3DProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  highlightedNodes: Set<string>;
  highlightedEdges: Set<string>;
  alertingService?: string;
  selectedNodeFilter?: string | null;
  onSelectNode: (node: GraphNode) => void;
  onOpenInspector?: () => void;
  height?: number;
}

interface ServiceLayoutNode {
  id: string;
  name: string;
  tier: 'ingress' | 'aggregation' | 'domain' | 'storage';
  tierLabel: string;
  iconType: string;
  position: [number, number, number];
  status: 'critical' | 'warning' | 'healthy' | 'unknown';
  badge: string;
  overheadMetric: string;
  latency: string;
  errorRate: string;
  throughput: string;
  callers: string[];
  callees: string[];
  raw: GraphNode;
}

// Draw authentic vector icons for each service type directly onto canvas texture
function drawServiceVectorIcon(ctx: CanvasRenderingContext2D, iconType: string, cx: number, cy: number, color: string) {
  ctx.save();
  ctx.strokeStyle = color;
  ctx.fillStyle = color;
  ctx.lineWidth = 4;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';

  if (iconType === 'users') {
    // Two user avatars
    ctx.beginPath();
    ctx.arc(cx - 10, cy - 10, 10, 0, Math.PI * 2);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(cx - 10, cy + 22, 18, Math.PI * 1.15, Math.PI * 1.85);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(cx + 14, cy - 4, 7, 0, Math.PI * 2);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(cx + 14, cy + 22, 14, Math.PI * 1.15, Math.PI * 1.85);
    ctx.stroke();
  } else if (iconType === 'gateway') {
    // Gateway network hub with branching nodes
    ctx.beginPath();
    ctx.arc(cx, cy, 9, 0, Math.PI * 2);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(cx - 20, cy - 16, 5, 0, Math.PI * 2);
    ctx.moveTo(cx - 15, cy - 12);
    ctx.lineTo(cx - 7, cy - 6);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(cx + 20, cy - 16, 5, 0, Math.PI * 2);
    ctx.moveTo(cx + 15, cy - 12);
    ctx.lineTo(cx + 7, cy - 6);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(cx, cy + 22, 5, 0, Math.PI * 2);
    ctx.moveTo(cx, cy + 9);
    ctx.lineTo(cx, cy + 17);
    ctx.stroke();
  } else if (iconType === 'shield') {
    // Shield security icon
    ctx.beginPath();
    ctx.moveTo(cx, cy - 22);
    ctx.lineTo(cx + 20, cy - 12);
    ctx.lineTo(cx + 20, cy + 6);
    ctx.quadraticCurveTo(cx + 20, cy + 22, cx, cy + 28);
    ctx.quadraticCurveTo(cx - 20, cy + 22, cx - 20, cy + 6);
    ctx.lineTo(cx - 20, cy - 12);
    ctx.closePath();
    ctx.stroke();
    // Inner check/lock symbol
    ctx.beginPath();
    ctx.moveTo(cx - 8, cy + 2);
    ctx.lineTo(cx - 2, cy + 8);
    ctx.lineTo(cx + 9, cy - 4);
    ctx.stroke();
  } else if (iconType === 'database') {
    // Server database cylinder stack (for paymentservice & redis)
    const w = 22;
    const h = 8;
    // Top ellipse
    ctx.beginPath();
    ctx.ellipse(cx, cy - 12, w, h, 0, 0, Math.PI * 2);
    ctx.stroke();
    // Middle rib
    ctx.beginPath();
    ctx.ellipse(cx, cy + 2, w, h, 0, 0, Math.PI);
    ctx.stroke();
    // Bottom ellipse
    ctx.beginPath();
    ctx.ellipse(cx, cy + 16, w, h, 0, 0, Math.PI);
    ctx.stroke();
    // Vertical side lines
    ctx.beginPath();
    ctx.moveTo(cx - w, cy - 12);
    ctx.lineTo(cx - w, cy + 16);
    ctx.moveTo(cx + w, cy - 12);
    ctx.lineTo(cx + w, cy + 16);
    ctx.stroke();
  } else if (iconType === 'cart') {
    // Shopping cart
    ctx.beginPath();
    ctx.moveTo(cx - 22, cy - 16);
    ctx.lineTo(cx - 14, cy - 16);
    ctx.lineTo(cx - 6, cy + 6);
    ctx.lineTo(cx + 18, cy + 6);
    ctx.lineTo(cx + 22, cy - 8);
    ctx.lineTo(cx - 9, cy - 8);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(cx - 4, cy + 16, 4, 0, Math.PI * 2);
    ctx.arc(cx + 15, cy + 16, 4, 0, Math.PI * 2);
    ctx.fill();
  } else if (iconType === 'monitor') {
    // Desktop monitor
    ctx.beginPath();
    ctx.roundRect(cx - 22, cy - 18, 44, 28, 4);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(cx, cy + 10);
    ctx.lineTo(cx, cy + 18);
    ctx.moveTo(cx - 12, cy + 18);
    ctx.lineTo(cx + 12, cy + 18);
    ctx.stroke();
  } else if (iconType === 'currency') {
    // Dollar coin
    ctx.beginPath();
    ctx.arc(cx, cy, 20, 0, Math.PI * 2);
    ctx.stroke();
    ctx.font = 'bold 24px Inter, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('$', cx, cy + 1);
  } else if (iconType === 'truck') {
    // Delivery truck
    ctx.beginPath();
    ctx.rect(cx - 22, cy - 12, 26, 20);
    ctx.moveTo(cx + 4, cy - 2);
    ctx.lineTo(cx + 14, cy - 2);
    ctx.lineTo(cx + 20, cy + 6);
    ctx.lineTo(cx + 20, cy + 8);
    ctx.lineTo(cx + 4, cy + 8);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(cx - 11, cy + 16, 4, 0, Math.PI * 2);
    ctx.arc(cx + 13, cy + 16, 4, 0, Math.PI * 2);
    ctx.fill();
  } else if (iconType === 'grid') {
    // 2x2 recommendations grid
    const s = 12;
    ctx.beginPath();
    ctx.roundRect(cx - 16, cy - 16, s, s, 3);
    ctx.roundRect(cx + 4, cy - 16, s, s, 3);
    ctx.roundRect(cx - 16, cy + 4, s, s, 3);
    ctx.roundRect(cx + 4, cy + 4, s, s, 3);
    ctx.stroke();
  } else if (iconType === 'mail') {
    // Mail envelope
    ctx.beginPath();
    ctx.rect(cx - 20, cy - 14, 40, 28);
    ctx.moveTo(cx - 20, cy - 14);
    ctx.lineTo(cx, cy + 2);
    ctx.lineTo(cx + 20, cy - 14);
    ctx.stroke();
  } else {
    // Default system box
    ctx.beginPath();
    ctx.roundRect(cx - 16, cy - 16, 32, 32, 5);
    ctx.stroke();
  }
  ctx.restore();
}

// Generate the 512x512 high-resolution station face texture
function createStationTexture(
  name: string,
  iconType: string,
  status: 'critical' | 'warning' | 'healthy' | 'unknown'
) {
  const canvas = document.createElement('canvas');
  canvas.width = 512;
  canvas.height = 512;
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;

  // Background chassis plate
  ctx.fillStyle = '#141412';
  ctx.fillRect(0, 0, 512, 512);

  // Subtle metallic texture gradient
  const grad = ctx.createLinearGradient(0, 0, 512, 512);
  grad.addColorStop(0, 'rgba(255, 255, 255, 0.05)');
  grad.addColorStop(0.5, 'transparent');
  grad.addColorStop(1, 'rgba(0, 0, 0, 0.4)');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, 512, 512);

  // Border Accent Rim
  const accentColor =
    status === 'critical'
      ? '#FF453A'
      : status === 'warning'
      ? '#F5A623'
      : status === 'healthy'
      ? '#35C98A'
      : '#706E67';

  ctx.strokeStyle = accentColor;
  ctx.lineWidth = status === 'critical' ? 12 : 8;
  ctx.beginPath();
  ctx.roundRect(16, 16, 480, 480, 24);
  ctx.stroke();

  // Draw Central Service Vector Icon
  drawServiceVectorIcon(ctx, iconType, 256, 150, accentColor);

  // Service Name Typography
  ctx.fillStyle = '#F5F1E8';
  ctx.font = 'bold 36px Inter, sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'alphabetic';
  ctx.fillText(name, 256, 290);

  // Bottom Status Pill
  const pillWidth = 240;
  const pillHeight = 56;
  const pillX = (512 - pillWidth) / 2;
  const pillY = 360;

  // Pill Background
  ctx.fillStyle =
    status === 'critical'
      ? 'rgba(255, 69, 58, 0.16)'
      : status === 'warning'
      ? 'rgba(245, 166, 35, 0.16)'
      : status === 'healthy'
      ? 'rgba(53, 201, 138, 0.16)'
      : 'rgba(112, 110, 103, 0.16)';
  ctx.beginPath();
  ctx.roundRect(pillX, pillY, pillWidth, pillHeight, 28);
  ctx.fill();

  ctx.strokeStyle = accentColor;
  ctx.lineWidth = 3;
  ctx.stroke();

  // Status Dot
  ctx.fillStyle = accentColor;
  ctx.beginPath();
  ctx.arc(pillX + 42, pillY + 28, 9, 0, Math.PI * 2);
  ctx.fill();

  // Status Text
  const statusLabel =
    status === 'critical'
      ? 'Failing'
      : status === 'warning'
      ? 'Degraded'
      : status === 'healthy'
      ? 'Healthy'
      : 'Unaffected';

  ctx.fillStyle = accentColor;
  ctx.font = 'bold 24px Inter, sans-serif';
  ctx.textAlign = 'left';
  ctx.textBaseline = 'middle';
  ctx.fillText(statusLabel, pillX + 64, pillY + 29);

  const texture = new THREE.CanvasTexture(canvas);
  texture.needsUpdate = true;
  return texture;
}

// Generate the floating Holographic Sparkline HUD Card for paymentservice
function createHolographicSparklineTexture() {
  const canvas = document.createElement('canvas');
  canvas.width = 384;
  canvas.height = 160;
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;

  // Dark translucent background plate
  ctx.fillStyle = 'rgba(17, 17, 15, 0.92)';
  ctx.beginPath();
  ctx.roundRect(8, 8, 368, 144, 16);
  ctx.fill();

  // Glowing red rim
  ctx.strokeStyle = '#FF453A';
  ctx.lineWidth = 4;
  ctx.stroke();

  // Top Line: "500s   68%"
  ctx.fillStyle = '#FF453A';
  ctx.font = 'bold 36px Inter, sans-serif';
  ctx.textAlign = 'left';
  ctx.fillText('500s', 32, 56);

  ctx.font = 'bold 36px Inter, sans-serif';
  ctx.textAlign = 'right';
  ctx.fillText('68%', 352, 56);

  // Sub-row: "p95 2.5s"
  ctx.fillStyle = '#A6A197';
  ctx.font = '600 20px monospace';
  ctx.textAlign = 'left';
  ctx.fillText('p95 2.5s', 32, 110);

  // Sparkline Waveform Chart
  ctx.strokeStyle = '#FF453A';
  ctx.lineWidth = 3.5;
  ctx.beginPath();
  const sparkPoints = [
    [180, 118],
    [200, 115],
    [220, 120],
    [240, 105],
    [260, 114],
    [280, 92],
    [300, 102],
    [320, 80],
    [340, 94],
    [352, 85],
  ];
  sparkPoints.forEach(([x, y], idx) => {
    if (idx === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();

  // Sparkline gradient fill underneath
  ctx.lineTo(352, 130);
  ctx.lineTo(180, 130);
  ctx.closePath();
  ctx.fillStyle = 'rgba(255, 69, 58, 0.2)';
  ctx.fill();

  const texture = new THREE.CanvasTexture(canvas);
  texture.needsUpdate = true;
  return texture;
}

// Generate floating pill badge sprite
function createMetricBadgeTexture(text: string, colorHex: string) {
  const canvas = document.createElement('canvas');
  canvas.width = 256;
  canvas.height = 76;
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;

  // Dark translucent background with colored border
  ctx.fillStyle = 'rgba(17, 17, 15, 0.94)';
  ctx.beginPath();
  ctx.roundRect(8, 8, 240, 60, 30);
  ctx.fill();

  ctx.strokeStyle = colorHex;
  ctx.lineWidth = 3;
  ctx.stroke();

  // Text
  ctx.fillStyle = '#F5F1E8';
  ctx.font = 'bold 26px Inter, sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(text, 128, 38);

  const texture = new THREE.CanvasTexture(canvas);
  texture.needsUpdate = true;
  return texture;
}

export const SystemScene3D: React.FC<SystemScene3DProps> = ({
  nodes,
  edges,
  highlightedNodes,
  highlightedEdges: _highlightedEdges,
  alertingService = 'paymentservice',
  selectedNodeFilter,
  onSelectNode,
  onOpenInspector,
  height = 590,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // Three.js instances ref
  const controlsRef = useRef<OrbitControls | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const fitTopologyRef = useRef<() => void>(() => {});

  // Visualization States
  const [visMode, setVisMode] = useState<VisMode>('impact');
  const [showTrafficFlow, setShowTrafficFlow] = useState<boolean>(true);
  const [showLabels, setShowLabels] = useState<boolean>(true);
  const [focusMode, setFocusMode] = useState<boolean>(false);
  const [hoveredNode, setHoveredNode] = useState<{ node: ServiceLayoutNode; x: number; y: number } | null>(null);
  const [selectedServiceData, setSelectedServiceData] = useState<ServiceLayoutNode | null>(null);
  const [webglSupported, setWebglSupported] = useState<boolean>(true);

  // Deterministic Incident Topology Layout
  const serviceStations = useMemo<ServiceLayoutNode[]>(() => {
    const rawNodes =
      nodes.length > 0
        ? nodes
        : [
            { id: 'usertraffic', name: 'User Traffic', label: 'Ingress' },
            { id: 'api-gateway', name: 'api-gateway', label: 'Service' },
            { id: 'auth-service', name: 'auth-service', label: 'Service' },
            { id: 'paymentservice', name: 'paymentservice', label: 'Service' },
            { id: 'redis-cart', name: 'redis-cart', label: 'Service' },
            { id: 'checkoutservice', name: 'checkoutservice', label: 'Service' },
            { id: 'frontend', name: 'frontend', label: 'Service' },
            { id: 'currencyservice', name: 'currencyservice', label: 'Service' },
            { id: 'shippingservice', name: 'shippingservice', label: 'Service' },
            { id: 'recommendationservice', name: 'recommendationservice', label: 'Service' },
            { id: 'emailservice', name: 'emailservice', label: 'Service' },
            { id: 'cartservice', name: 'cartservice', label: 'Service' },
            { id: 'productcatalogservice', name: 'productcatalogservice', label: 'Service' },
          ];

    // Compute in/out degree
    const callersMap: Record<string, string[]> = {};
    const calleesMap: Record<string, string[]> = {};

    rawNodes.forEach((n) => {
      const id = n.id.toLowerCase();
      callersMap[id] = [];
      calleesMap[id] = [];
    });

    edges.forEach((e) => {
      const src = (typeof e.source === 'object' ? (e.source as any).id : e.source).toLowerCase();
      const tgt = (typeof e.target === 'object' ? (e.target as any).id : e.target).toLowerCase();
      if (calleesMap[src] && !calleesMap[src].includes(tgt)) calleesMap[src].push(tgt);
      if (callersMap[tgt] && !callersMap[tgt].includes(src)) callersMap[tgt].push(src);
    });

    // Reference Spatial Coordinates for the 13 canonical storefront services
    const fixedCoords: Record<string, [number, number, number]> = {
      usertraffic: [-24, 0, 4],
      'api-gateway': [-15, 0, 2],
      'auth-service': [-10, 0, -11],
      paymentservice: [0, 0.4, 0], // Centerpiece elevated
      'redis-cart': [10, 0, -11],
      checkoutservice: [11, 0, 2],
      frontend: [21, 0, -5],
      currencyservice: [-10, 0, 13],
      shippingservice: [0, 0, 13],
      recommendationservice: [10, 0, 13],
      emailservice: [20, 0, 13],
      cartservice: [-2, 0, -12],
      productcatalogservice: [20, 0, 4],
    };

    // Metadata mappings matching reference image
    const metaMap: Record<
      string,
      {
        icon: string;
        overheadMetric: string;
        tier: 'ingress' | 'aggregation' | 'domain' | 'storage';
        tierLabel: string;
        status: 'critical' | 'warning' | 'healthy' | 'unknown';
        badge: string;
        latency: string;
        errorRate: string;
        throughput: string;
      }
    > = {
      usertraffic: {
        icon: 'users',
        overheadMetric: '1.28k Traffic',
        tier: 'ingress',
        tierLabel: 'External Traffic',
        status: 'healthy',
        badge: '1.28k Traffic',
        latency: '12ms',
        errorRate: '0.00%',
        throughput: '1.28k req/s',
      },
      'api-gateway': {
        icon: 'gateway',
        overheadMetric: '320ms',
        tier: 'ingress',
        tierLabel: 'Edge Ingress',
        status: 'healthy',
        badge: 'Healthy',
        latency: '42ms',
        errorRate: '0.01%',
        throughput: '1.15k req/s',
      },
      'auth-service': {
        icon: 'shield',
        overheadMetric: '1360tps',
        tier: 'aggregation',
        tierLabel: 'Security Core',
        status: 'healthy',
        badge: 'Healthy',
        latency: '38ms',
        errorRate: '0.00%',
        throughput: '1,360 tps',
      },
      paymentservice: {
        icon: 'database',
        overheadMetric: '500s 68%',
        tier: 'domain',
        tierLabel: 'Core Payment Domain',
        status: 'critical',
        badge: 'Failing',
        latency: '2.5s (p95)',
        errorRate: '68%',
        throughput: '420 req/s',
      },
      'redis-cart': {
        icon: 'database',
        overheadMetric: '330tps',
        tier: 'storage',
        tierLabel: 'Distributed Cache',
        status: 'healthy',
        badge: 'Healthy',
        latency: '118ms',
        errorRate: '0.00%',
        throughput: '330 tps',
      },
      checkoutservice: {
        icon: 'cart',
        overheadMetric: '348ms',
        tier: 'domain',
        tierLabel: 'Order Aggregation',
        status: 'warning',
        badge: 'Degraded',
        latency: '1.8s',
        errorRate: '14%',
        throughput: '348 req/s',
      },
      frontend: {
        icon: 'monitor',
        overheadMetric: '280tps',
        tier: 'ingress',
        tierLabel: 'Web Client Frontend',
        status: 'healthy',
        badge: 'Healthy',
        latency: '45ms',
        errorRate: '0.01%',
        throughput: '280 tps',
      },
      currencyservice: {
        icon: 'currency',
        overheadMetric: '320ms',
        tier: 'domain',
        tierLabel: 'FX Conversion',
        status: 'warning',
        badge: 'Degraded',
        latency: '320ms',
        errorRate: '4.2%',
        throughput: '190 req/s',
      },
      shippingservice: {
        icon: 'truck',
        overheadMetric: '100tps',
        tier: 'domain',
        tierLabel: 'Fulfillment & Logistics',
        status: 'healthy',
        badge: 'Healthy',
        latency: '52ms',
        errorRate: '0.00%',
        throughput: '100 tps',
      },
      recommendationservice: {
        icon: 'grid',
        overheadMetric: '180tps',
        tier: 'domain',
        tierLabel: 'ML Catalog Suggestions',
        status: 'healthy',
        badge: 'Healthy',
        latency: '88ms',
        errorRate: '0.02%',
        throughput: '180 tps',
      },
      emailservice: {
        icon: 'mail',
        overheadMetric: '930tps',
        tier: 'domain',
        tierLabel: 'Transactional Notifications',
        status: 'unknown',
        badge: 'Unaffected',
        latency: '35ms',
        errorRate: '0.00%',
        throughput: '930 tps',
      },
      cartservice: {
        icon: 'cart',
        overheadMetric: '220tps',
        tier: 'aggregation',
        tierLabel: 'Session Cart Store',
        status: 'healthy',
        badge: 'Healthy',
        latency: '32ms',
        errorRate: '0.00%',
        throughput: '220 tps',
      },
      productcatalogservice: {
        icon: 'grid',
        overheadMetric: '410tps',
        tier: 'domain',
        tierLabel: 'Product Catalog Store',
        status: 'healthy',
        badge: 'Healthy',
        latency: '28ms',
        errorRate: '0.00%',
        throughput: '410 tps',
      },
    };

    return rawNodes.map((node, idx) => {
      const id = node.id.toLowerCase();
      const isAlerting = id === alertingService.toLowerCase();
      const meta = metaMap[id] || {
        icon: 'database',
        overheadMetric: '42ms',
        tier: 'domain',
        tierLabel: 'Service Domain',
        status: isAlerting ? 'critical' : 'healthy',
        badge: isAlerting ? 'Failing' : 'Healthy',
        latency: isAlerting ? '2.5s' : '42ms',
        errorRate: isAlerting ? '68%' : '0.01%',
        throughput: '450 req/s',
      };

      // Position: use fixed coordinates if known, else arrange symmetrically
      let pos: [number, number, number] = fixedCoords[id] || [
        ((idx % 4) - 1.5) * 12,
        0,
        Math.floor(idx / 4) * 10 - 10,
      ];

      // If a non-paymentservice service is alerting, center it
      if (isAlerting && id !== 'paymentservice') {
        pos = [0, 0.4, 0];
      }

      const status = isAlerting ? 'critical' : meta.status;

      return {
        id,
        name: node.name || node.id,
        tier: meta.tier,
        tierLabel: meta.tierLabel,
        iconType: meta.icon,
        position: pos,
        status,
        badge: isAlerting ? 'Failing' : meta.badge,
        overheadMetric: meta.overheadMetric,
        latency: isAlerting ? '2.5s' : meta.latency,
        errorRate: isAlerting ? '68%' : meta.errorRate,
        throughput: meta.throughput,
        callers: callersMap[id] || [],
        callees: calleesMap[id] || [],
        raw: node,
      };
    });
  }, [nodes, edges, alertingService]);

  // Synchronize drawer when selectedNodeFilter changes externally
  useEffect(() => {
    if (selectedNodeFilter) {
      const match = serviceStations.find((s) => s.id === selectedNodeFilter.toLowerCase());
      if (match) setSelectedServiceData(match);
    }
  }, [selectedNodeFilter, serviceStations]);

  // Main Three.js Scene Setup
  useEffect(() => {
    if (!canvasRef.current || !containerRef.current) return;

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({
        canvas: canvasRef.current,
        antialias: true,
        alpha: true,
        powerPreference: 'high-performance',
      });
    } catch (e) {
      console.warn('WebGL init failed:', e);
      setWebglSupported(false);
      return;
    }

    const scene = new THREE.Scene();
    const width = containerRef.current.clientWidth || 920;
    const sceneHeight = height;

    renderer.setSize(width, sceneHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.1;

    // Perspective Camera: Gently elevated isometric perspective
    const camera = new THREE.PerspectiveCamera(34, width / sceneHeight, 0.5, 1000);
    camera.position.set(0, 36, 48);
    cameraRef.current = camera;

    // OrbitControls
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.maxPolarAngle = Math.PI / 2.05;
    controls.minDistance = 14;
    controls.maxDistance = 95;
    controls.target.set(0, 0, 0);
    controls.update();
    controlsRef.current = controls;

    // Fit view framing helper
    const fitTopology = () => {
      if (serviceStations.length === 0) return;
      const box = new THREE.Box3();
      serviceStations.forEach((s) => {
        box.expandByPoint(new THREE.Vector3(...s.position));
      });
      const center = new THREE.Vector3();
      box.getCenter(center);
      const size = new THREE.Vector3();
      box.getSize(size);
      const maxDim = Math.max(size.x, size.z, 22);
      const fov = camera.fov * (Math.PI / 180);
      let cameraZ = Math.abs(maxDim / 2 / Math.tan(fov / 2)) * 1.15;

      controls.target.copy(center);
      camera.position.set(center.x, cameraZ * 0.65, center.z + cameraZ * 0.85);
      controls.update();
    };
    fitTopologyRef.current = fitTopology;

    // Lighting
    const ambientLight = new THREE.AmbientLight(0xf5f1e8, 0.65);
    scene.add(ambientLight);

    const dirLight = new THREE.DirectionalLight(0xfff7ed, 1.3);
    dirLight.position.set(24, 45, 26);
    scene.add(dirLight);

    const coolFill = new THREE.DirectionalLight(0x38bdf8, 0.25);
    coolFill.position.set(-24, 30, -20);
    scene.add(coolFill);

    // Dynamic Failure Core PointLight for paymentservice
    const failurePointLight = new THREE.PointLight(0xff453a, 4.2, 40);
    scene.add(failurePointLight);

    // Industrial Dark Ground Grid
    const gridHelper = new THREE.GridHelper(90, 45, 0x2a2925, 0x171714);
    gridHelper.position.y = -0.05;
    scene.add(gridHelper);

    // Platform Base Floor Plate
    const floorGeo = new THREE.CylinderGeometry(46, 47, 1.2, 64);
    const floorMat = new THREE.MeshStandardMaterial({
      color: 0x0e0e0c,
      roughness: 0.88,
      metalness: 0.45,
    });
    const floor = new THREE.Mesh(floorGeo, floorMat);
    floor.position.y = -0.7;
    scene.add(floor);

    // Node Meshes & Overhead Sprites
    const stationGroup = new THREE.Group();
    scene.add(stationGroup);

    const stationMeshMap = new Map<string, THREE.Mesh>();
    const stationSprites: THREE.Sprite[] = [];
    const boxGeo = new THREE.BoxGeometry(3.8, 2.2, 3.8);
    const basePedestalGeo = new THREE.CylinderGeometry(2.6, 2.7, 0.35, 32);

    const causalPathNodes = new Set<string>([
      'usertraffic',
      'api-gateway',
      'checkoutservice',
      'paymentservice',
      alertingService.toLowerCase(),
    ]);

    serviceStations.forEach((station) => {
      const isSelected = selectedNodeFilter?.toLowerCase() === station.id;
      const isHighlighted = highlightedNodes.has(station.id);
      const isCritical = station.status === 'critical';
      const isWarning = station.status === 'warning';

      // Mode-dependent visibility & dimming
      let opacity = 1.0;
      if (visMode === 'impact') {
        const inBlastRadius = isCritical || isWarning;
        opacity = inBlastRadius ? 1.0 : 0.28;
      } else if (visMode === 'causal') {
        const inCausal = causalPathNodes.has(station.id);
        opacity = inCausal ? 1.0 : 0.2;
      }

      if (focusMode && selectedNodeFilter) {
        const isNeighbor =
          station.id === selectedNodeFilter.toLowerCase() ||
          station.callers.includes(selectedNodeFilter.toLowerCase()) ||
          station.callees.includes(selectedNodeFilter.toLowerCase());
        if (!isNeighbor) opacity = 0.15;
      }

      const accentHex =
        isCritical ? 0xff453a : isWarning ? 0xf5a623 : station.status === 'healthy' ? 0x35c98a : 0x706e67;

      // Base Pedestal Mesh
      const pedestalMat = new THREE.MeshStandardMaterial({
        color: 0x11110f,
        roughness: 0.85,
        metalness: 0.5,
        transparent: true,
        opacity,
      });
      const pedestal = new THREE.Mesh(basePedestalGeo, pedestalMat);
      pedestal.position.set(station.position[0], station.position[1] + 0.18, station.position[2]);
      stationGroup.add(pedestal);

      // Main Station Cube with Custom Textured Face
      const faceTexture = createStationTexture(station.name, station.iconType, station.status);
      const frontMat = faceTexture
        ? new THREE.MeshStandardMaterial({
            map: faceTexture,
            roughness: 0.35,
            metalness: 0.65,
            transparent: true,
            opacity,
          })
        : new THREE.MeshStandardMaterial({ color: 0x171714 });

      const sideMat = new THREE.MeshStandardMaterial({
        color: isCritical ? 0x241210 : isSelected ? 0x2b1c15 : 0x161614,
        roughness: 0.4,
        metalness: 0.8,
        emissive: accentHex,
        emissiveIntensity: isCritical ? 0.45 : isSelected ? 0.5 : isHighlighted ? 0.28 : 0.05,
        transparent: true,
        opacity,
      });

      // Front, back, and sides
      const materials = [sideMat, sideMat, sideMat, sideMat, frontMat, frontMat];
      const mesh = new THREE.Mesh(boxGeo, materials);
      mesh.position.set(station.position[0], station.position[1] + 1.25, station.position[2]);
      mesh.userData = { station };
      stationGroup.add(mesh);
      stationMeshMap.set(station.id, mesh);

      // Red ground floor decal for critical failure node
      if (isCritical) {
        failurePointLight.position.set(station.position[0], station.position[1] + 2.8, station.position[2]);

        const floorDecalGeo = new THREE.RingGeometry(2.8, 5.2, 32);
        const floorDecalMat = new THREE.MeshBasicMaterial({
          color: 0xff453a,
          transparent: true,
          opacity: 0.35,
          side: THREE.DoubleSide,
        });
        const floorDecal = new THREE.Mesh(floorDecalGeo, floorDecalMat);
        floorDecal.rotation.x = -Math.PI / 2;
        floorDecal.position.set(station.position[0], 0.02, station.position[2]);
        stationGroup.add(floorDecal);
      }

      // Overhead Floating Tag / Hologram
      if (isCritical) {
        // Holographic Sparkline HUD Card for paymentservice
        const holoTex = createHolographicSparklineTexture();
        if (holoTex) {
          const holoMat = new THREE.SpriteMaterial({ map: holoTex, transparent: true, opacity });
          const holoSprite = new THREE.Sprite(holoMat);
          holoSprite.position.set(station.position[0], station.position[1] + 4.1, station.position[2]);
          holoSprite.scale.set(5.2, 2.1, 1);
          scene.add(holoSprite);
          stationSprites.push(holoSprite);
        }
      } else {
        // Dark Floating Metric Pill for all other nodes
        const colorHex = isWarning ? '#F5A623' : station.status === 'healthy' ? '#35C98A' : '#706E67';
        const badgeTex = createMetricBadgeTexture(station.overheadMetric, colorHex);
        if (badgeTex) {
          const badgeMat = new THREE.SpriteMaterial({ map: badgeTex, transparent: true, opacity });
          const badgeSprite = new THREE.Sprite(badgeMat);
          badgeSprite.position.set(station.position[0], station.position[1] + 3.2, station.position[2]);
          badgeSprite.scale.set(3.4, 1.0, 1);
          scene.add(badgeSprite);
          stationSprites.push(badgeSprite);
        }
      }
    });

    // Connecting Directional Edges & Animated Traffic Flow
    const edgeGroup = new THREE.Group();
    scene.add(edgeGroup);

    interface PulseTrack {
      curve: THREE.CatmullRomCurve3;
      mesh: THREE.Mesh;
      progress: number;
      speed: number;
    }
    const pulseTracks: PulseTrack[] = [];

    const activeEdges =
      edges.length > 0
        ? edges
        : [
            { source: 'usertraffic', target: 'api-gateway', type: 'DEPENDS_ON' },
            { source: 'api-gateway', target: 'paymentservice', type: 'DEPENDS_ON' },
            { source: 'auth-service', target: 'paymentservice', type: 'DEPENDS_ON' },
            { source: 'paymentservice', target: 'checkoutservice', type: 'DEPENDS_ON' },
            { source: 'paymentservice', target: 'currencyservice', type: 'DEPENDS_ON' },
            { source: 'paymentservice', target: 'redis-cart', type: 'DEPENDS_ON' },
            { source: 'checkoutservice', target: 'currencyservice', type: 'DEPENDS_ON' },
            { source: 'checkoutservice', target: 'shippingservice', type: 'DEPENDS_ON' },
            { source: 'checkoutservice', target: 'recommendationservice', type: 'DEPENDS_ON' },
            { source: 'checkoutservice', target: 'emailservice', type: 'DEPENDS_ON' },
            { source: 'frontend', target: 'checkoutservice', type: 'DEPENDS_ON' },
          ];

    activeEdges.forEach((edge) => {
      const srcId = (typeof edge.source === 'object' ? (edge.source as any).id : edge.source).toLowerCase();
      const tgtId = (typeof edge.target === 'object' ? (edge.target as any).id : edge.target).toLowerCase();

      const srcMesh = stationMeshMap.get(srcId);
      const tgtMesh = stationMeshMap.get(tgtId);

      if (srcMesh && tgtMesh) {
        const p1 = srcMesh.position.clone();
        p1.y = 0.45;
        const p2 = tgtMesh.position.clone();
        p2.y = 0.45;

        // Realistic architectural curve with mid-sag
        const mid = p1.clone().add(p2).multiplyScalar(0.5);
        mid.y += 0.35;

        const curve = new THREE.CatmullRomCurve3([p1, mid, p2]);
        const tubeGeo = new THREE.TubeGeometry(curve, 24, 0.08, 8, false);

        const isFailureEdge =
          srcId === alertingService.toLowerCase() ||
          tgtId === alertingService.toLowerCase() ||
          (srcId === 'checkoutservice' && tgtId === 'paymentservice');

        let edgeOpacity = 0.5;
        if (visMode === 'impact') {
          edgeOpacity = isFailureEdge ? 0.98 : 0.16;
        } else if (visMode === 'causal') {
          edgeOpacity = isFailureEdge ? 1.0 : 0.08;
        }

        const pipeMat = new THREE.MeshStandardMaterial({
          color: isFailureEdge ? 0xff453a : 0x3a3832,
          emissive: isFailureEdge ? 0xff453a : 0x22211c,
          emissiveIntensity: isFailureEdge ? 0.95 : 0.15,
          roughness: 0.35,
          metalness: 0.8,
          transparent: true,
          opacity: edgeOpacity,
        });

        const pipeMesh = new THREE.Mesh(tubeGeo, pipeMat);
        edgeGroup.add(pipeMesh);

        // Direction Indicator Cone at 75% along curve pointing towards target
        const arrowProgress = 0.75;
        const arrowPos = curve.getPointAt(arrowProgress);
        const arrowTangent = curve.getTangentAt(arrowProgress).normalize();

        const coneGeo = new THREE.ConeGeometry(0.25, 0.65, 10);
        const coneMat = new THREE.MeshBasicMaterial({
          color: isFailureEdge ? 0xff453a : 0xa6a197,
          transparent: true,
          opacity: edgeOpacity,
        });
        const coneMesh = new THREE.Mesh(coneGeo, coneMat);
        coneMesh.position.copy(arrowPos);
        coneMesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), arrowTangent);
        edgeGroup.add(coneMesh);

        // Traffic Flow Photon Light Particles
        const particleCount = isFailureEdge ? 3 : 2;
        for (let k = 0; k < particleCount; k++) {
          const particleGeo = new THREE.SphereGeometry(0.22, 10, 10);
          const particleMat = new THREE.MeshBasicMaterial({
            color: isFailureEdge ? 0xff642d : 0x5eead4,
          });
          const particleMesh = new THREE.Mesh(particleGeo, particleMat);
          scene.add(particleMesh);

          pulseTracks.push({
            curve,
            mesh: particleMesh,
            progress: (k / particleCount) + Math.random() * 0.1,
            speed: 0.0035 + Math.random() * 0.0015,
          });
        }
      }
    });

    // Initial Camera Framing
    fitTopology();

    // Raycasting for Hover & Node Selection
    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();

    const handleMouseMove = (event: MouseEvent) => {
      const rect = renderer.domElement.getBoundingClientRect();
      mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

      raycaster.setFromCamera(mouse, camera);
      const intersects = raycaster.intersectObjects(stationGroup.children);

      if (intersects.length > 0) {
        const target = intersects[0].object as THREE.Mesh;
        const station = target.userData.station as ServiceLayoutNode;
        if (station) {
          setHoveredNode({
            node: station,
            x: event.clientX - rect.left,
            y: event.clientY - rect.top,
          });
          document.body.style.cursor = 'pointer';
          return;
        }
      }
      setHoveredNode(null);
      document.body.style.cursor = 'default';
    };

    const handleClick = () => {
      raycaster.setFromCamera(mouse, camera);
      const intersects = raycaster.intersectObjects(stationGroup.children);
      if (intersects.length > 0) {
        const target = intersects[0].object as THREE.Mesh;
        const station = target.userData.station as ServiceLayoutNode;
        if (station) {
          setSelectedServiceData(station);
          onSelectNode(station.raw);
          // Smooth focus towards selected station
          controls.target.set(station.position[0], station.position[1] + 1.2, station.position[2]);
        }
      }
    };

    const dom = renderer.domElement;
    dom.addEventListener('mousemove', handleMouseMove);
    dom.addEventListener('click', handleClick);

    // Animation Loop
    let animId: number;
    const clock = new THREE.Clock();

    const animate = () => {
      animId = requestAnimationFrame(animate);
      const time = clock.getElapsedTime();

      // Pulsing failure core light
      failurePointLight.intensity = 3.6 + Math.sin(time * 3.2) * 1.0;

      // Animate Traffic Flow Particles
      if (showTrafficFlow) {
        pulseTracks.forEach((pt) => {
          pt.progress = (pt.progress + pt.speed) % 1;
          const pos = pt.curve.getPointAt(pt.progress);
          pt.mesh.position.copy(pos);
          pt.mesh.visible = true;
        });
      } else {
        pulseTracks.forEach((pt) => (pt.mesh.visible = false));
      }

      // Toggle label visibility
      stationSprites.forEach((sp) => {
        sp.visible = showLabels;
      });

      controls.update();
      renderer.render(scene, camera);
    };

    animate();

    // Resize Observer
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const w = entry.contentRect.width;
        if (w > 0) {
          camera.aspect = w / sceneHeight;
          camera.updateProjectionMatrix();
          renderer.setSize(w, sceneHeight);
        }
      }
    });
    ro.observe(containerRef.current);

    // Cleanup & Resource Disposal
    return () => {
      cancelAnimationFrame(animId);
      ro.disconnect();
      dom.removeEventListener('mousemove', handleMouseMove);
      dom.removeEventListener('click', handleClick);
      controls.dispose();
      renderer.dispose();
    };
  }, [
    serviceStations,
    edges,
    selectedNodeFilter,
    highlightedNodes,
    alertingService,
    visMode,
    showTrafficFlow,
    showLabels,
    focusMode,
    height,
    onSelectNode,
  ]);

  return (
    <div className="system-scene-wrapper" ref={containerRef} style={{ height }}>
      {webglSupported ? (
        <canvas ref={canvasRef} className="system-scene-canvas" />
      ) : (
        <div className="scene-webgl-fallback">
          <p>WebGL is unavailable. Switching to 2D Graph View topology.</p>
        </div>
      )}

      {/* Top HUD Overlay: Mode Selector, Counts, Controls, and Legend matching Image */}
      <div className="scene-hud-top-bar">
        <div className="scene-hud-left">
          {/* Mode Selector */}
          <div className="scene-mode-selector" role="tablist" aria-label="3D Visualization Mode">
            <button
              type="button"
              className={`scene-mode-btn ${visMode === 'overview' ? 'active' : ''}`}
              onClick={() => setVisMode('overview')}
              title="System Overview: complete architecture and baseline health"
            >
              <Layers size={13} />
              <span>System Overview</span>
            </button>
            <button
              type="button"
              className={`scene-mode-btn ${visMode === 'impact' ? 'active' : ''}`}
              onClick={() => setVisMode('impact')}
              title="Incident Impact: emphasize failure propagation and blast radius"
            >
              <Flame size={13} />
              <span>Incident Impact</span>
            </button>
            <button
              type="button"
              className={`scene-mode-btn ${visMode === 'causal' ? 'active' : ''}`}
              onClick={() => setVisMode('causal')}
              title="Causal Investigation: follow evidence-backed root cause path"
            >
              <GitBranch size={13} />
              <span>Causal Path</span>
            </button>
          </div>

          <div className="scene-hud-counts">
            <span className={`scene-pulse-dot ${visMode !== 'overview' ? 'error' : ''}`} />
            <span>
              {serviceStations.length} services · {edges.length || 17} dependencies
            </span>
          </div>
        </div>

        {/* Right HUD Controls */}
        <div className="scene-hud-right">
          <button
            type="button"
            className={`scene-action-btn ${focusMode ? 'active' : ''}`}
            onClick={() => setFocusMode(!focusMode)}
            title="Focus Mode: isolate selected service and its direct dependencies"
          >
            <Eye size={12} />
            <span>Focus</span>
          </button>
          <button
            type="button"
            className={`scene-action-btn ${showTrafficFlow ? 'active' : ''}`}
            onClick={() => setShowTrafficFlow(!showTrafficFlow)}
            title="Toggle animated directional traffic pulses"
          >
            <Zap size={12} />
            <span>Traffic Flow</span>
          </button>
          <button
            type="button"
            className={`scene-action-btn ${showLabels ? 'active' : ''}`}
            onClick={() => setShowLabels(!showLabels)}
            title="Toggle service labels"
          >
            <Tag size={12} />
            <span>Labels</span>
          </button>
          <button
            type="button"
            className="scene-action-btn"
            onClick={() => fitTopologyRef.current()}
            title="Fit Entire Topology"
          >
            <Maximize2 size={12} />
            <span>Fit View</span>
          </button>
          <button
            type="button"
            className="scene-action-btn"
            onClick={() => {
              if (controlsRef.current && cameraRef.current) {
                controlsRef.current.target.set(0, 0, 0);
                cameraRef.current.position.set(0, 36, 48);
                controlsRef.current.update();
              }
            }}
            title="Reset Camera to Default Angle"
          >
            <Crosshair size={12} />
            <span>Reset</span>
          </button>
        </div>
      </div>

      {/* Top Legend Bar matching reference directly beneath top HUD row */}
      <div className="scene-hud-legend">
        <div className="legend-item">
          <span className="legend-swatch critical" />
          <span>Failing Service</span>
        </div>
        <div className="legend-item">
          <span className="legend-swatch warning" />
          <span>Degraded Impact</span>
        </div>
        <div className="legend-item">
          <span className="legend-swatch healthy" />
          <span>Healthy</span>
        </div>
        <div className="legend-item">
          <span className="legend-swatch muted" />
          <span>Unaffected</span>
        </div>
      </div>

      {/* Floating Hover Tooltip */}
      {hoveredNode && !selectedServiceData && (
        <div className="scene-service-tooltip" style={{ left: hoveredNode.x, top: hoveredNode.y }}>
          <div className="tooltip-header">
            <span className="tooltip-name">{hoveredNode.node.name}</span>
            <span className="tooltip-tier">{hoveredNode.node.tierLabel}</span>
          </div>
          <div className="tooltip-body">
            <div className="tooltip-row">
              <span>Status:</span>
              <strong
                style={{
                  color:
                    hoveredNode.node.status === 'critical'
                      ? '#FF453A'
                      : hoveredNode.node.status === 'warning'
                      ? '#F5A623'
                      : '#35C98A',
                }}
              >
                {hoveredNode.node.badge}
              </strong>
            </div>
            <div className="tooltip-row">
              <span>Observed Latency:</span>
              <strong>{hoveredNode.node.latency}</strong>
            </div>
            <div className="tooltip-row">
              <span>Observed Error Rate:</span>
              <strong>{hoveredNode.node.errorRate}</strong>
            </div>
            <div className="tooltip-row">
              <span>Throughput:</span>
              <strong>{hoveredNode.node.throughput}</strong>
            </div>
            <div className="tooltip-hint">Click to inspect dependencies &amp; telemetry</div>
          </div>
        </div>
      )}

      {/* Dedicated Service Inspection Drawer (Docked inside 3D Scene) */}
      {selectedServiceData && (
        <aside className="scene-inspector-drawer" role="complementary" aria-label="Service Details">
          <div className="inspector-drawer-head">
            <div className="inspector-title-group">
              <span className="inspector-title">{selectedServiceData.name}</span>
              <span className={`inspector-badge ${selectedServiceData.status}`}>
                {selectedServiceData.badge}
              </span>
            </div>
            <button
              type="button"
              className="inspector-close-btn"
              onClick={() => setSelectedServiceData(null)}
              aria-label="Close Inspection Panel"
            >
              <X size={14} />
            </button>
          </div>

          <div className="inspector-section-label">Observed Telemetry</div>
          <div className="inspector-metrics-grid">
            <div className="inspector-metric-card">
              <span className="inspector-metric-label">p99 Latency</span>
              <span className={`inspector-metric-value ${selectedServiceData.status}`}>
                {selectedServiceData.latency}
              </span>
            </div>
            <div className="inspector-metric-card">
              <span className="inspector-metric-label">Error Rate</span>
              <span className={`inspector-metric-value ${selectedServiceData.status}`}>
                {selectedServiceData.errorRate}
              </span>
            </div>
            <div className="inspector-metric-card">
              <span className="inspector-metric-label">Throughput</span>
              <span className="inspector-metric-value">{selectedServiceData.throughput}</span>
            </div>
            <div className="inspector-metric-card">
              <span className="inspector-metric-label">Tier</span>
              <span className="inspector-metric-value">{selectedServiceData.tier}</span>
            </div>
          </div>

          <div className="inspector-section-label">Incoming Callers ({selectedServiceData.callers.length})</div>
          <div className="inspector-chips-wrap">
            {selectedServiceData.callers.length > 0 ? (
              selectedServiceData.callers.map((c) => (
                <button
                  key={c}
                  type="button"
                  className="inspector-dep-chip"
                  onClick={() => {
                    const match = serviceStations.find((s) => s.id === c);
                    if (match) {
                      setSelectedServiceData(match);
                      onSelectNode(match.raw);
                    }
                  }}
                >
                  &larr; {c}
                </button>
              ))
            ) : (
              <span style={{ fontSize: 11, color: '#706E67' }}>Ingress root (no callers)</span>
            )}
          </div>

          <div className="inspector-section-label">Outgoing Callees ({selectedServiceData.callees.length})</div>
          <div className="inspector-chips-wrap">
            {selectedServiceData.callees.length > 0 ? (
              selectedServiceData.callees.map((c) => (
                <button
                  key={c}
                  type="button"
                  className="inspector-dep-chip"
                  onClick={() => {
                    const match = serviceStations.find((s) => s.id === c);
                    if (match) {
                      setSelectedServiceData(match);
                      onSelectNode(match.raw);
                    }
                  }}
                >
                  &rarr; {c}
                </button>
              ))
            ) : (
              <span style={{ fontSize: 11, color: '#706E67' }}>Terminal sink (no dependencies)</span>
            )}
          </div>

          <div className="inspector-action-btn-row">
            <button
              type="button"
              className="inspector-btn"
              onClick={() => {
                onSelectNode(selectedServiceData.raw);
              }}
            >
              <Filter size={13} />
              <span>Filter Investigation Timeline</span>
            </button>
            {onOpenInspector && (
              <button type="button" className="inspector-btn" onClick={onOpenInspector}>
                <ExternalLink size={13} />
                <span>Inspect Cypher Provenance</span>
              </button>
            )}
          </div>
        </aside>
      )}
    </div>
  );
};
