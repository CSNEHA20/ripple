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

// Draw crisp 2D vector icons on high-res canvas
function drawServiceVectorIcon(
  ctx: CanvasRenderingContext2D,
  iconType: string,
  cx: number,
  cy: number,
  color: string
) {
  ctx.save();
  ctx.strokeStyle = color;
  ctx.fillStyle = color;
  ctx.lineWidth = 8;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';

  if (iconType === 'users') {
    // Two user avatars
    ctx.beginPath();
    ctx.arc(cx - 20, cy - 20, 20, 0, Math.PI * 2);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(cx - 20, cy + 44, 36, Math.PI * 1.15, Math.PI * 1.85);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(cx + 28, cy - 8, 14, 0, Math.PI * 2);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(cx + 28, cy + 44, 28, Math.PI * 1.15, Math.PI * 1.85);
    ctx.stroke();
  } else if (iconType === 'gateway') {
    // Router / Gateway network hub with branching nodes
    ctx.beginPath();
    ctx.arc(cx, cy, 18, 0, Math.PI * 2);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(cx - 40, cy - 32, 10, 0, Math.PI * 2);
    ctx.moveTo(cx - 30, cy - 24);
    ctx.lineTo(cx - 14, cy - 12);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(cx + 40, cy - 32, 10, 0, Math.PI * 2);
    ctx.moveTo(cx + 30, cy - 24);
    ctx.lineTo(cx + 14, cy - 12);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(cx, cy + 44, 10, 0, Math.PI * 2);
    ctx.moveTo(cx, cy + 18);
    ctx.lineTo(cx, cy + 34);
    ctx.stroke();
  } else if (iconType === 'shield') {
    // Security Shield
    ctx.beginPath();
    ctx.moveTo(cx, cy - 44);
    ctx.lineTo(cx + 40, cy - 24);
    ctx.lineTo(cx + 40, cy + 12);
    ctx.quadraticCurveTo(cx + 40, cy + 44, cx, cy + 56);
    ctx.quadraticCurveTo(cx - 40, cy + 44, cx - 40, cy + 12);
    ctx.lineTo(cx - 40, cy - 24);
    ctx.closePath();
    ctx.stroke();
    // Inner checkmark
    ctx.beginPath();
    ctx.moveTo(cx - 16, cy + 4);
    ctx.lineTo(cx - 4, cy + 16);
    ctx.lineTo(cx + 18, cy - 8);
    ctx.stroke();
  } else if (iconType === 'database') {
    // Server database cylinder stack (for paymentservice & redis-cart)
    const w = 44;
    const h = 16;
    // Top ellipse
    ctx.beginPath();
    ctx.ellipse(cx, cy - 24, w, h, 0, 0, Math.PI * 2);
    ctx.stroke();
    // Middle rib
    ctx.beginPath();
    ctx.ellipse(cx, cy + 4, w, h, 0, 0, Math.PI);
    ctx.stroke();
    // Bottom ellipse
    ctx.beginPath();
    ctx.ellipse(cx, cy + 32, w, h, 0, 0, Math.PI);
    ctx.stroke();
    // Vertical side lines
    ctx.beginPath();
    ctx.moveTo(cx - w, cy - 24);
    ctx.lineTo(cx - w, cy + 32);
    ctx.moveTo(cx + w, cy - 24);
    ctx.lineTo(cx + w, cy + 32);
    ctx.stroke();
  } else if (iconType === 'cart') {
    // Shopping cart
    ctx.beginPath();
    ctx.moveTo(cx - 44, cy - 32);
    ctx.lineTo(cx - 28, cy - 32);
    ctx.lineTo(cx - 12, cy + 12);
    ctx.lineTo(cx + 36, cy + 12);
    ctx.lineTo(cx + 44, cy - 16);
    ctx.lineTo(cx - 18, cy - 16);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(cx - 8, cy + 32, 8, 0, Math.PI * 2);
    ctx.arc(cx + 30, cy + 32, 8, 0, Math.PI * 2);
    ctx.fill();
  } else if (iconType === 'monitor') {
    // Desktop monitor
    ctx.beginPath();
    ctx.roundRect(cx - 44, cy - 36, 88, 56, 8);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(cx, cy + 20);
    ctx.lineTo(cx, cy + 36);
    ctx.moveTo(cx - 24, cy + 36);
    ctx.lineTo(cx + 24, cy + 36);
    ctx.stroke();
  } else if (iconType === 'currency') {
    // Dollar coin
    ctx.beginPath();
    ctx.arc(cx, cy, 40, 0, Math.PI * 2);
    ctx.stroke();
    ctx.font = 'bold 48px Inter, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('$', cx, cy + 2);
  } else if (iconType === 'truck') {
    // Delivery truck
    ctx.beginPath();
    ctx.rect(cx - 44, cy - 24, 52, 40);
    ctx.moveTo(cx + 8, cy - 4);
    ctx.lineTo(cx + 28, cy - 4);
    ctx.lineTo(cx + 40, cy + 12);
    ctx.lineTo(cx + 40, cy + 16);
    ctx.lineTo(cx + 8, cy + 16);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(cx - 22, cy + 32, 8, 0, Math.PI * 2);
    ctx.arc(cx + 26, cy + 32, 8, 0, Math.PI * 2);
    ctx.fill();
  } else if (iconType === 'grid') {
    // Recommendations 2x2 grid
    const s = 24;
    ctx.beginPath();
    ctx.roundRect(cx - 32, cy - 32, s, s, 6);
    ctx.roundRect(cx + 8, cy - 32, s, s, 6);
    ctx.roundRect(cx - 32, cy + 8, s, s, 6);
    ctx.roundRect(cx + 8, cy + 8, s, s, 6);
    ctx.stroke();
  } else if (iconType === 'mail') {
    // Mail envelope
    ctx.beginPath();
    ctx.rect(cx - 40, cy - 28, 80, 56);
    ctx.moveTo(cx - 40, cy - 28);
    ctx.lineTo(cx, cy + 4);
    ctx.lineTo(cx + 40, cy - 28);
    ctx.stroke();
  } else {
    // Default server chassis
    ctx.beginPath();
    ctx.roundRect(cx - 32, cy - 32, 64, 64, 10);
    ctx.stroke();
  }
  ctx.restore();
}

// Generate the 1024x1024 ultra-crisp station front face texture
function createStationFaceTexture(
  name: string,
  iconType: string,
  status: 'critical' | 'warning' | 'healthy' | 'unknown'
) {
  const canvas = document.createElement('canvas');
  canvas.width = 1024;
  canvas.height = 1024;
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;

  // Dark obsidian chassis plate
  ctx.fillStyle = '#11110F';
  ctx.fillRect(0, 0, 1024, 1024);

  // Subtle metallic diagonal sheen
  const grad = ctx.createLinearGradient(0, 0, 1024, 1024);
  grad.addColorStop(0, 'rgba(255, 255, 255, 0.08)');
  grad.addColorStop(0.5, 'rgba(255, 255, 255, 0.01)');
  grad.addColorStop(1, 'rgba(0, 0, 0, 0.5)');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, 1024, 1024);

  const accentColor =
    status === 'critical'
      ? '#FF453A'
      : status === 'warning'
      ? '#F5A623'
      : status === 'healthy'
      ? '#35C98A'
      : '#706E67';

  // Outer Glowing Accent Rim
  ctx.strokeStyle = accentColor;
  ctx.lineWidth = status === 'critical' ? 24 : 16;
  ctx.beginPath();
  ctx.roundRect(32, 32, 960, 960, 48);
  ctx.stroke();

  // Top Accent LED strip
  ctx.fillStyle = accentColor;
  ctx.beginPath();
  ctx.roundRect(256, 44, 512, 12, 6);
  ctx.fill();

  // Central Service Vector Icon
  drawServiceVectorIcon(ctx, iconType, 512, 330, accentColor);

  // Service Name in bold crisp typography
  ctx.fillStyle = '#FFFFFF';
  ctx.font = 'bold 64px Inter, sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'alphabetic';
  ctx.fillText(name, 512, 600);

  // Status Pill at Bottom
  const pillWidth = 480;
  const pillHeight = 112;
  const pillX = (1024 - pillWidth) / 2;
  const pillY = 720;

  ctx.fillStyle =
    status === 'critical'
      ? 'rgba(255, 69, 58, 0.22)'
      : status === 'warning'
      ? 'rgba(245, 166, 35, 0.22)'
      : status === 'healthy'
      ? 'rgba(53, 201, 138, 0.22)'
      : 'rgba(112, 110, 103, 0.22)';
  ctx.beginPath();
  ctx.roundRect(pillX, pillY, pillWidth, pillHeight, 56);
  ctx.fill();

  ctx.strokeStyle = accentColor;
  ctx.lineWidth = 6;
  ctx.stroke();

  // Glowing status dot
  ctx.fillStyle = accentColor;
  ctx.beginPath();
  ctx.arc(pillX + 80, pillY + 56, 18, 0, Math.PI * 2);
  ctx.fill();

  // Status Label Text
  const statusLabel =
    status === 'critical'
      ? 'Failing'
      : status === 'warning'
      ? 'Degraded'
      : status === 'healthy'
      ? 'Healthy'
      : 'Unaffected';

  ctx.fillStyle = accentColor;
  ctx.font = 'bold 50px Inter, sans-serif';
  ctx.textAlign = 'left';
  ctx.textBaseline = 'middle';
  ctx.fillText(statusLabel, pillX + 128, pillY + 58);

  const texture = new THREE.CanvasTexture(canvas);
  texture.needsUpdate = true;
  return texture;
}

// Generate the large floating Holographic Sparkline HUD Card for paymentservice
function createHolographicSparklineTexture() {
  const canvas = document.createElement('canvas');
  canvas.width = 600;
  canvas.height = 240;
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;

  // Translucent dark plate with glowing red rim
  ctx.fillStyle = 'rgba(15, 15, 13, 0.94)';
  ctx.beginPath();
  ctx.roundRect(12, 12, 576, 216, 24);
  ctx.fill();

  ctx.strokeStyle = '#FF453A';
  ctx.lineWidth = 6;
  ctx.stroke();

  // Top Header: "500s" (left) and "68%" (right)
  ctx.fillStyle = '#FF453A';
  ctx.font = 'bold 56px Inter, sans-serif';
  ctx.textAlign = 'left';
  ctx.fillText('500s', 48, 88);

  ctx.textAlign = 'right';
  ctx.fillText('68%', 552, 88);

  // Sub-row: "p95 2.5s"
  ctx.fillStyle = '#A6A197';
  ctx.font = 'bold 30px monospace';
  ctx.textAlign = 'left';
  ctx.fillText('p95 2.5s', 48, 170);

  // Sparkline Chart Waveform
  ctx.strokeStyle = '#FF453A';
  ctx.lineWidth = 5;
  ctx.beginPath();
  const sparkPoints = [
    [260, 180],
    [290, 175],
    [320, 182],
    [350, 158],
    [380, 170],
    [410, 138],
    [440, 152],
    [470, 120],
    [500, 142],
    [530, 128],
    [550, 134],
  ];
  sparkPoints.forEach(([x, y], idx) => {
    if (idx === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();

  // Subtle gradient fill under sparkline
  ctx.lineTo(550, 196);
  ctx.lineTo(260, 196);
  ctx.closePath();
  ctx.fillStyle = 'rgba(255, 69, 58, 0.25)';
  ctx.fill();

  const texture = new THREE.CanvasTexture(canvas);
  texture.needsUpdate = true;
  return texture;
}

// Generate floating metric badge pill
function createMetricBadgeTexture(text: string, colorHex: string) {
  const canvas = document.createElement('canvas');
  canvas.width = 380;
  canvas.height = 110;
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;

  ctx.fillStyle = 'rgba(15, 15, 13, 0.94)';
  ctx.beginPath();
  ctx.roundRect(10, 10, 360, 90, 45);
  ctx.fill();

  ctx.strokeStyle = colorHex;
  ctx.lineWidth = 5;
  ctx.stroke();

  ctx.fillStyle = '#FFFFFF';
  ctx.font = 'bold 38px Inter, sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(text, 190, 56);

  const texture = new THREE.CanvasTexture(canvas);
  texture.needsUpdate = true;
  return texture;
}

// Generate tiled metallic floor texture
function createFloorTileTexture() {
  const canvas = document.createElement('canvas');
  canvas.width = 512;
  canvas.height = 512;
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;

  // Tile background
  ctx.fillStyle = '#0B0B0A';
  ctx.fillRect(0, 0, 512, 512);

  // 4 floor tiles with beveled seams
  const tileSize = 256;
  for (let r = 0; r < 2; r++) {
    for (let c = 0; c < 2; c++) {
      const x = c * tileSize;
      const y = r * tileSize;
      ctx.fillStyle = '#10100E';
      ctx.fillRect(x + 2, y + 2, tileSize - 4, tileSize - 4);

      // Fine metallic grid border
      ctx.strokeStyle = '#1C1C18';
      ctx.lineWidth = 2;
      ctx.strokeRect(x + 2, y + 2, tileSize - 4, tileSize - 4);
    }
  }

  const texture = new THREE.CanvasTexture(canvas);
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  texture.repeat.set(12, 12);
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
  height = 620,
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

  // Deterministic Diamond Layout matching reference image
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

    // Exact Spatial Coordinates matching the reference composition
    const fixedCoords: Record<string, [number, number, number]> = {
      // Centerpiece: elevated focal point
      paymentservice: [0, 1.2, 0],

      // Back row
      'auth-service': [-8.5, 0.4, -9.5],
      'redis-cart': [8.5, 0.4, -9.5],
      frontend: [18.5, 0.4, -6],

      // Middle row
      usertraffic: [-20, 0.4, 3],
      'api-gateway': [-10, 0.4, 2],
      checkoutservice: [10, 0.4, 2],

      // Front row
      currencyservice: [-9, 0.4, 11],
      shippingservice: [1, 0.4, 12],
      recommendationservice: [10.5, 0.4, 12],
      emailservice: [20, 0.4, 11],

      // Peripheral services
      cartservice: [-1, 0.4, -10.5],
      productcatalogservice: [19, 0.4, 3],
    };

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
        tierLabel: 'External Ingress',
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
        tierLabel: 'Security Auth',
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
        tierLabel: 'Notifications',
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
        tierLabel: 'Catalog Store',
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
        tierLabel: 'Domain Service',
        status: isAlerting ? 'critical' : 'healthy',
        badge: isAlerting ? 'Failing' : 'Healthy',
        latency: isAlerting ? '2.5s' : '42ms',
        errorRate: isAlerting ? '68%' : '0.01%',
        throughput: '450 req/s',
      };

      let pos: [number, number, number] = fixedCoords[id] || [
        ((idx % 4) - 1.5) * 11,
        0.4,
        Math.floor(idx / 4) * 9 - 9,
      ];

      if (isAlerting && id !== 'paymentservice') {
        pos = [0, 1.2, 0];
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
    const width = containerRef.current.clientWidth || 960;
    const sceneHeight = height;

    renderer.setSize(width, sceneHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.15;

    // Cinematic Isometric Camera Framing
    const camera = new THREE.PerspectiveCamera(38, width / sceneHeight, 0.5, 1000);
    camera.position.set(0, 22, 28);
    cameraRef.current = camera;

    // OrbitControls
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.maxPolarAngle = Math.PI / 2.05;
    controls.minDistance = 12;
    controls.maxDistance = 80;
    controls.target.set(0, 1.0, 0);
    controls.update();
    controlsRef.current = controls;

    // Fit View function
    const fitTopology = () => {
      controls.target.set(0, 1.0, 0);
      camera.position.set(0, 22, 28);
      controls.update();
    };
    fitTopologyRef.current = fitTopology;

    // Lighting
    const ambientLight = new THREE.AmbientLight(0xf5f1e8, 0.7);
    scene.add(ambientLight);

    const dirLight = new THREE.DirectionalLight(0xfff7ed, 1.4);
    dirLight.position.set(24, 45, 26);
    scene.add(dirLight);

    const coolFill = new THREE.DirectionalLight(0x38bdf8, 0.35);
    coolFill.position.set(-24, 30, -20);
    scene.add(coolFill);

    // Powerful Core PointLights for dramatic local illumination
    const failurePointLight = new THREE.PointLight(0xff453a, 5.5, 32);
    scene.add(failurePointLight);

    const warningPointLight = new THREE.PointLight(0xf5a623, 3.2, 24);
    warningPointLight.position.set(10, 2, 2);
    scene.add(warningPointLight);

    // Dark Tiled Industrial Floor
    const floorTexture = createFloorTileTexture();
    const floorGeo = new THREE.PlaneGeometry(80, 80);
    const floorMat = new THREE.MeshStandardMaterial({
      map: floorTexture || undefined,
      color: 0x0c0c0a,
      roughness: 0.75,
      metalness: 0.6,
    });
    const floor = new THREE.Mesh(floorGeo, floorMat);
    floor.rotation.x = -Math.PI / 2;
    floor.position.y = -0.05;
    scene.add(floor);

    // Node Meshes & Overhead Sprites
    const stationGroup = new THREE.Group();
    scene.add(stationGroup);

    const stationMeshMap = new Map<string, THREE.Mesh>();
    const stationSprites: THREE.Sprite[] = [];
    const boxGeo = new THREE.BoxGeometry(4.4, 3.0, 4.4);
    const plinthGeo = new THREE.BoxGeometry(5.2, 0.5, 5.2);

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

      // Base Plinth Pedestal
      const plinthMat = new THREE.MeshStandardMaterial({
        color: 0x0a0a08,
        roughness: 0.7,
        metalness: 0.8,
        transparent: true,
        opacity,
      });
      const plinth = new THREE.Mesh(plinthGeo, plinthMat);
      plinth.position.set(station.position[0], station.position[1] + 0.25, station.position[2]);
      stationGroup.add(plinth);

      // Main Station Server Cube
      const faceTexture = createStationFaceTexture(station.name, station.iconType, station.status);
      const frontMat = faceTexture
        ? new THREE.MeshStandardMaterial({
            map: faceTexture,
            roughness: 0.3,
            metalness: 0.7,
            transparent: true,
            opacity,
          })
        : new THREE.MeshStandardMaterial({ color: 0x11110f });

      const sideMat = new THREE.MeshStandardMaterial({
        color: isCritical ? 0x22100e : isSelected ? 0x2b1c15 : 0x141412,
        roughness: 0.35,
        metalness: 0.85,
        emissive: accentHex,
        emissiveIntensity: isCritical ? 0.7 : isSelected ? 0.6 : isWarning ? 0.45 : isHighlighted ? 0.3 : 0.08,
        transparent: true,
        opacity,
      });

      // Front, back, and sides
      const materials = [sideMat, sideMat, sideMat, sideMat, frontMat, frontMat];
      const mesh = new THREE.Mesh(boxGeo, materials);
      mesh.position.set(station.position[0], station.position[1] + 1.8, station.position[2]);
      mesh.userData = { station };
      stationGroup.add(mesh);
      stationMeshMap.set(station.id, mesh);

      // Glowing Floor Aura under critical failure node
      if (isCritical) {
        failurePointLight.position.set(station.position[0], station.position[1] + 2.5, station.position[2]);

        const floorDecalGeo = new THREE.RingGeometry(3.0, 7.5, 32);
        const floorDecalMat = new THREE.MeshBasicMaterial({
          color: 0xff453a,
          transparent: true,
          opacity: 0.45,
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
          holoSprite.position.set(station.position[0], station.position[1] + 5.2, station.position[2]);
          holoSprite.scale.set(6.4, 2.5, 1);
          scene.add(holoSprite);
          stationSprites.push(holoSprite);
        }
      } else {
        // Floating Metric Pill for other nodes
        const colorHex = isWarning ? '#F5A623' : station.status === 'healthy' ? '#35C98A' : '#706E67';
        const badgeTex = createMetricBadgeTexture(station.overheadMetric, colorHex);
        if (badgeTex) {
          const badgeMat = new THREE.SpriteMaterial({ map: badgeTex, transparent: true, opacity });
          const badgeSprite = new THREE.Sprite(badgeMat);
          badgeSprite.position.set(station.position[0], station.position[1] + 4.2, station.position[2]);
          badgeSprite.scale.set(4.0, 1.15, 1);
          scene.add(badgeSprite);
          stationSprites.push(badgeSprite);
        }
      }
    });

    // Connecting Directional Tubes & Particle Traffic
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
            { source: 'paymentservice', target: 'shippingservice', type: 'DEPENDS_ON' },
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
        p1.y = 0.7;
        const p2 = tgtMesh.position.clone();
        p2.y = 0.7;

        // Realistic curve with gentle sag
        const mid = p1.clone().add(p2).multiplyScalar(0.5);
        mid.y += 0.45;

        const curve = new THREE.CatmullRomCurve3([p1, mid, p2]);
        const tubeGeo = new THREE.TubeGeometry(curve, 28, 0.12, 10, false);

        const isFailureEdge =
          srcId === alertingService.toLowerCase() ||
          tgtId === alertingService.toLowerCase() ||
          (srcId === 'checkoutservice' && tgtId === 'paymentservice');

        let edgeOpacity = 0.55;
        if (visMode === 'impact') {
          edgeOpacity = isFailureEdge ? 1.0 : 0.18;
        } else if (visMode === 'causal') {
          edgeOpacity = isFailureEdge ? 1.0 : 0.08;
        }

        const pipeMat = new THREE.MeshStandardMaterial({
          color: isFailureEdge ? 0xff453a : 0x333b3d,
          emissive: isFailureEdge ? 0xff453a : 0x164e63,
          emissiveIntensity: isFailureEdge ? 1.2 : 0.25,
          roughness: 0.3,
          metalness: 0.85,
          transparent: true,
          opacity: edgeOpacity,
        });

        const pipeMesh = new THREE.Mesh(tubeGeo, pipeMat);
        edgeGroup.add(pipeMesh);

        // Direction Indicator Cone at 75% along curve pointing towards target
        const arrowProgress = 0.75;
        const arrowPos = curve.getPointAt(arrowProgress);
        const arrowTangent = curve.getTangentAt(arrowProgress).normalize();

        const coneGeo = new THREE.ConeGeometry(0.32, 0.8, 12);
        const coneMat = new THREE.MeshBasicMaterial({
          color: isFailureEdge ? 0xff453a : 0xa6a197,
          transparent: true,
          opacity: edgeOpacity,
        });
        const coneMesh = new THREE.Mesh(coneGeo, coneMat);
        coneMesh.position.copy(arrowPos);
        coneMesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), arrowTangent);
        edgeGroup.add(coneMesh);

        // Animated Traffic Light Pulses (bound strictly to this curve)
        const particleCount = isFailureEdge ? 3 : 2;
        for (let k = 0; k < particleCount; k++) {
          const particleGeo = new THREE.SphereGeometry(0.26, 12, 12);
          const particleMat = new THREE.MeshBasicMaterial({
            color: isFailureEdge ? 0xff642d : 0x38bdf8,
          });
          const particleMesh = new THREE.Mesh(particleGeo, particleMat);
          scene.add(particleMesh);

          pulseTracks.push({
            curve,
            mesh: particleMesh,
            progress: (k / particleCount) + Math.random() * 0.1,
            speed: 0.004 + Math.random() * 0.0015,
          });
        }
      }
    });

    // Initial Framing
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
          controls.target.set(station.position[0], station.position[1] + 1.8, station.position[2]);
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
      failurePointLight.intensity = 4.8 + Math.sin(time * 3.5) * 1.4;

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

      {/* Top HUD Overlay: Mode Selector, Counts, Controls */}
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
                controlsRef.current.target.set(0, 1.0, 0);
                cameraRef.current.position.set(0, 22, 28);
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

      {/* Top Legend Bar positioned directly underneath mode buttons on left matching Image 2 */}
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

      {/* Dedicated Service Inspection Drawer */}
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
