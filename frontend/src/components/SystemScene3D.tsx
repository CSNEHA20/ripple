import React, { useRef, useEffect, useState, useMemo } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { Radio, Crosshair, Tag, Zap } from 'lucide-react';
import type { GraphNode, GraphEdge } from '../api';
import './SystemScene3D.css';

interface SystemScene3DProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  highlightedNodes: Set<string>;
  highlightedEdges: Set<string>;
  alertingService?: string;
  selectedNodeFilter?: string | null;
  onSelectNode: (node: GraphNode) => void;
  height?: number;
}

interface ServiceLayoutNode {
  id: string;
  name: string;
  position: [number, number, number];
  status: 'critical' | 'warning' | 'healthy';
  badge: string;
  latency: string;
  errorRate: string;
  throughput: string;
  raw: GraphNode;
}

// Fixed positions matching the industrial modular layout in the reference image
const REFERENCE_POSITIONS: Record<string, [number, number, number]> = {
  paymentservice: [0, 0, 0],
  checkoutservice: [10.5, 0, 4.5],
  currencyservice: [-14, 0, 14],
  shippingservice: [-4, 0, 15],
  recommendationservice: [6.5, 0, 15.5],
  checkout: [17, 0, 15],
  checkoutservice_pad: [17, 0, 15],
  'api-gateway': [-11, 0, -6.5],
  'auth-service': [-11, 0, 5],
  'redis-cart': [10.5, 0, -9.5],
  frontend: [20.5, 0, -4.5],
  cartservice: [0, 0, -10],
  productcatalogservice: [-4.5, 0, -13],
  emailservice: [18, 0, 5.5],
  adservice: [22, 0, 7.5],
  loadgenerator: [25, 0, -11],
};

function createServiceTexture(name: string, status: 'critical' | 'warning' | 'healthy', badge: string) {
  const canvas = document.createElement('canvas');
  canvas.width = 512;
  canvas.height = 256;
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;

  // Background chassis plate
  ctx.fillStyle = '#171714';
  ctx.fillRect(0, 0, 512, 256);

  // Border & Grid
  const accentColor = status === 'critical' ? '#FF453A' : status === 'warning' ? '#F5A623' : '#35C98A';
  ctx.strokeStyle = accentColor;
  ctx.lineWidth = 6;
  ctx.strokeRect(8, 8, 496, 240);

  // Status Glow Ring / Core
  ctx.fillStyle = accentColor;
  ctx.beginPath();
  ctx.arc(256, 75, 26, 0, Math.PI * 2);
  ctx.fill();

  // Core icon symbol
  ctx.fillStyle = '#0B0B0A';
  ctx.beginPath();
  ctx.arc(256, 75, 14, 0, Math.PI * 2);
  ctx.fill();

  // Name
  ctx.fillStyle = '#F5F1E8';
  ctx.font = 'bold 36px Inter, sans-serif';
  ctx.textAlign = 'center';
  ctx.fillText(name, 256, 150);

  // Status Badge
  ctx.fillStyle = accentColor;
  ctx.font = 'bold 24px monospace';
  ctx.fillText(badge, 256, 195);

  const texture = new THREE.CanvasTexture(canvas);
  texture.needsUpdate = true;
  return texture;
}

export const SystemScene3D: React.FC<SystemScene3DProps> = ({
  nodes,
  edges,
  highlightedNodes,
  alertingService = 'paymentservice',
  selectedNodeFilter,
  onSelectNode,
  height = 580,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [showBlastRadius, setShowBlastRadius] = useState<boolean>(true);
  const [showTrafficFlow, setShowTrafficFlow] = useState<boolean>(true);
  const [showLabels, setShowLabels] = useState<boolean>(true);
  const [hoveredNode, setHoveredNode] = useState<{ node: ServiceLayoutNode; x: number; y: number } | null>(null);
  const [webglSupported, setWebglSupported] = useState<boolean>(true);

  // Map graph nodes to 3D service stations
  const serviceStations = useMemo<ServiceLayoutNode[]>(() => {
    const rawNodes = nodes.length > 0 ? nodes : [
      { id: 'paymentservice', label: 'Service', name: 'paymentservice' },
      { id: 'checkoutservice', label: 'Service', name: 'checkoutservice' },
      { id: 'currencyservice', label: 'Service', name: 'currencyservice' },
      { id: 'shippingservice', label: 'Service', name: 'shippingservice' },
      { id: 'recommendationservice', label: 'Service', name: 'recommendationservice' },
      { id: 'api-gateway', label: 'Service', name: 'api-gateway' },
      { id: 'auth-service', label: 'Service', name: 'auth-service' },
      { id: 'redis-cart', label: 'Service', name: 'redis-cart' },
      { id: 'frontend', label: 'Service', name: 'frontend' },
      { id: 'cartservice', label: 'Service', name: 'cartservice' },
      { id: 'productcatalogservice', label: 'Service', name: 'productcatalogservice' },
      { id: 'emailservice', label: 'Service', name: 'emailservice' },
      { id: 'checkout', label: 'Service', name: 'checkout' },
    ];

    return rawNodes.map((n, idx) => {
      const id = (n.id || n.name || '').toLowerCase();
      let pos = REFERENCE_POSITIONS[id];
      if (!pos) {
        // Compute circular offset around perimeter for unrecognized nodes
        const angle = (idx / rawNodes.length) * Math.PI * 2;
        const rad = 22;
        pos = [Math.cos(angle) * rad, 0, Math.sin(angle) * rad];
      }

      const isAlerting = id === alertingService.toLowerCase();
      const isDegraded = ['checkoutservice', 'currencyservice', 'shippingservice'].includes(id);

      const status: 'critical' | 'warning' | 'healthy' = isAlerting
        ? 'critical'
        : isDegraded
        ? 'warning'
        : 'healthy';

      const badge = isAlerting
        ? '500s'
        : isDegraded
        ? (id === 'checkoutservice' || id === 'currencyservice' ? 'High latency' : 'Partial errors')
        : 'Healthy';

      const latency = isAlerting ? '2.5s' : isDegraded ? '1.8s' : '42ms';
      const errorRate = isAlerting ? '68%' : isDegraded ? '14%' : '0.01%';
      const throughput = isAlerting ? '1.2K rps' : '850 rps';

      return {
        id,
        name: n.name || id,
        position: pos,
        status,
        badge,
        latency,
        errorRate,
        throughput,
        raw: n,
      };
    });
  }, [nodes, alertingService]);

  // Main Three.js Scene Setup & Animation Loop
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
      console.warn('WebGL initialization failed, falling back:', e);
      setWebglSupported(false);
      return;
    }

    const scene = new THREE.Scene();
    const width = containerRef.current.clientWidth || 900;
    const sceneHeight = height;

    renderer.setSize(width, sceneHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.1;

    // Perspective Camera matching the industrial angle in reference image
    const camera = new THREE.PerspectiveCamera(38, width / sceneHeight, 0.1, 1000);
    camera.position.set(0, 36, 44);

    // Orbit Controls
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.maxPolarAngle = Math.PI / 2.05; // do not go below platform
    controls.minDistance = 18;
    controls.maxDistance = 85;
    controls.target.set(0, 1.5, 2);
    controls.update();

    // 1. Lighting Setup
    const ambientLight = new THREE.AmbientLight(0xf5f1e8, 0.45);
    scene.add(ambientLight);

    const dirLight = new THREE.DirectionalLight(0xfff5ea, 1.3);
    dirLight.position.set(24, 45, 24);
    scene.add(dirLight);

    const coolFillLight = new THREE.DirectionalLight(0x3b82f6, 0.35);
    coolFillLight.position.set(-24, 25, -20);
    scene.add(coolFillLight);

    // Red failure point light at center
    const redFailureLight = new THREE.PointLight(0xff453a, 4.2, 32);
    redFailureLight.position.set(0, 4, 0);
    scene.add(redFailureLight);

    // 2. Dark Industrial Platform Grid Floor
    const gridHelper = new THREE.GridHelper(80, 40, 0x383630, 0x1f1e1a);
    gridHelper.position.y = -0.05;
    scene.add(gridHelper);

    const floorGeo = new THREE.CylinderGeometry(42, 43, 1.2, 64);
    const floorMat = new THREE.MeshStandardMaterial({
      color: 0x0e0e0c,
      roughness: 0.75,
      metalness: 0.65,
    });
    const floor = new THREE.Mesh(floorGeo, floorMat);
    floor.position.y = -0.65;
    scene.add(floor);

    // Outer warm perimeter ring
    const ringGeo = new THREE.RingGeometry(41.5, 42.5, 64);
    const ringMat = new THREE.MeshBasicMaterial({
      color: 0xff642d,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.25,
    });
    const perimeterRing = new THREE.Mesh(ringGeo, ringMat);
    perimeterRing.rotation.x = -Math.PI / 2;
    perimeterRing.position.y = 0.01;
    scene.add(perimeterRing);

    // 3. Service Chassis Stations
    const chassisGroup = new THREE.Group();
    scene.add(chassisGroup);

    const stationMeshMap = new Map<string, THREE.Mesh>();
    const stationLabelSprites: THREE.Sprite[] = [];

    const boxGeo = new THREE.BoxGeometry(4.8, 2.6, 4.8);

    serviceStations.forEach((station) => {
      const isSelected = selectedNodeFilter === station.id;
      const isHighlighted = highlightedNodes.has(station.id);
      const isCritical = station.status === 'critical';
      const isWarning = station.status === 'warning';

      const accentHex = isCritical ? 0xff453a : isWarning ? 0xf5a623 : 0x35c98a;

      // Base materials for 6 cube faces
      const texture = createServiceTexture(station.name, station.status, station.badge);
      const frontMat = texture
        ? new THREE.MeshStandardMaterial({ map: texture, roughness: 0.3, metalness: 0.7 })
        : new THREE.MeshStandardMaterial({ color: 0x171714 });

      const sideMat = new THREE.MeshStandardMaterial({
        color: isCritical ? 0x2e1210 : isSelected ? 0x351f15 : 0x171714,
        roughness: 0.35,
        metalness: 0.85,
        emissive: accentHex,
        emissiveIntensity: isCritical ? 0.35 : isSelected ? 0.45 : isHighlighted ? 0.3 : 0.05,
      });

      const materials = [sideMat, sideMat, sideMat, sideMat, frontMat, sideMat];
      const mesh = new THREE.Mesh(boxGeo, materials);
      mesh.position.set(station.position[0], 1.3, station.position[2]);
      mesh.userData = { station };
      chassisGroup.add(mesh);
      stationMeshMap.set(station.id, mesh);

      // Station Base Pad
      const padGeo = new THREE.CylinderGeometry(3.6, 3.8, 0.4, 32);
      const padMat = new THREE.MeshStandardMaterial({
        color: 0x141412,
        roughness: 0.6,
        metalness: 0.9,
      });
      const pad = new THREE.Mesh(padGeo, padMat);
      pad.position.set(station.position[0], 0.2, station.position[2]);
      scene.add(pad);

      // Floating status badge billboard sprite above station
      const spriteCanvas = document.createElement('canvas');
      spriteCanvas.width = 256;
      spriteCanvas.height = 84;
      const sCtx = spriteCanvas.getContext('2d');
      if (sCtx) {
        sCtx.fillStyle = isCritical ? 'rgba(255, 69, 58, 0.95)' : isWarning ? 'rgba(245, 166, 35, 0.95)' : 'rgba(53, 201, 138, 0.95)';
        sCtx.beginPath();
        sCtx.roundRect(10, 10, 236, 64, 16);
        sCtx.fill();

        sCtx.fillStyle = '#0B0B0A';
        sCtx.font = 'bold 30px Inter, sans-serif';
        sCtx.textAlign = 'center';
        sCtx.fillText(station.badge, 128, 52);

        const sTexture = new THREE.CanvasTexture(spriteCanvas);
        const spriteMat = new THREE.SpriteMaterial({ map: sTexture, transparent: true });
        const sprite = new THREE.Sprite(spriteMat);
        sprite.position.set(station.position[0], 4.2, station.position[2]);
        sprite.scale.set(3.2, 1.1, 1);
        sprite.userData = { isBadge: true };
        scene.add(sprite);
        stationLabelSprites.push(sprite);
      }
    });

    // 4. Connecting Conduits / Tracks & Animated Flow Pulses
    const conduitGroup = new THREE.Group();
    scene.add(conduitGroup);

    interface PulseParticle {
      curve: THREE.CatmullRomCurve3;
      mesh: THREE.Mesh;
      progress: number;
      speed: number;
    }
    const flowPulses: PulseParticle[] = [];

    // Derive edges from backend data or standard reference connections
    const rawEdges = edges.length > 0 ? edges : [
      { source: 'checkoutservice', target: 'paymentservice', type: 'DEPENDS_ON' },
      { source: 'frontend', target: 'checkoutservice', type: 'DEPENDS_ON' },
      { source: 'checkoutservice', target: 'currencyservice', type: 'DEPENDS_ON' },
      { source: 'checkoutservice', target: 'shippingservice', type: 'DEPENDS_ON' },
      { source: 'cartservice', target: 'redis-cart', type: 'DEPENDS_ON' },
      { source: 'frontend', target: 'cartservice', type: 'DEPENDS_ON' },
      { source: 'frontend', target: 'recommendationservice', type: 'DEPENDS_ON' },
      { source: 'api-gateway', target: 'paymentservice', type: 'DEPENDS_ON' },
      { source: 'auth-service', target: 'paymentservice', type: 'DEPENDS_ON' },
      { source: 'recommendationservice', target: 'productcatalogservice', type: 'DEPENDS_ON' },
      { source: 'checkoutservice', target: 'emailservice', type: 'DEPENDS_ON' },
    ];

    rawEdges.forEach((edge) => {
      const srcId = (typeof edge.source === 'object' ? (edge.source as any).id : edge.source).toLowerCase();
      const tgtId = (typeof edge.target === 'object' ? (edge.target as any).id : edge.target).toLowerCase();

      const srcMesh = stationMeshMap.get(srcId);
      const tgtMesh = stationMeshMap.get(tgtId);

      if (srcMesh && tgtMesh) {
        const p1 = srcMesh.position.clone();
        p1.y = 0.5;
        const p2 = tgtMesh.position.clone();
        p2.y = 0.5;

        // Create curved conduit line arching slightly over the ground
        const mid = p1.clone().add(p2).multiplyScalar(0.5);
        mid.y += 0.4;

        const curve = new THREE.CatmullRomCurve3([p1, mid, p2]);
        const tubeGeo = new THREE.TubeGeometry(curve, 20, 0.22, 8, false);

        const isFailingPath = srcId === alertingService.toLowerCase() || tgtId === alertingService.toLowerCase();
        const pipeMat = new THREE.MeshStandardMaterial({
          color: isFailingPath ? 0xd93829 : 0x2a2925,
          emissive: isFailingPath ? 0xff453a : 0xff642d,
          emissiveIntensity: isFailingPath ? 0.8 : 0.25,
          roughness: 0.3,
          metalness: 0.8,
        });

        const pipeMesh = new THREE.Mesh(tubeGeo, pipeMat);
        conduitGroup.add(pipeMesh);

        // Animated Traffic Light Pulse
        const pulseGeo = new THREE.SphereGeometry(0.35, 12, 12);
        const pulseMat = new THREE.MeshBasicMaterial({
          color: isFailingPath ? 0xff453a : 0xffa07a,
        });
        const pulseMesh = new THREE.Mesh(pulseGeo, pulseMat);
        scene.add(pulseMesh);

        flowPulses.push({
          curve,
          mesh: pulseMesh,
          progress: Math.random(),
          speed: 0.0035 + Math.random() * 0.003,
        });
      }
    });

    // 5. Raycasting for Service Hover & Selection
    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();

    const handleMouseMove = (event: MouseEvent) => {
      const rect = renderer.domElement.getBoundingClientRect();
      mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

      raycaster.setFromCamera(mouse, camera);
      const intersects = raycaster.intersectObjects(chassisGroup.children);

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
      const intersects = raycaster.intersectObjects(chassisGroup.children);
      if (intersects.length > 0) {
        const target = intersects[0].object as THREE.Mesh;
        const station = target.userData.station as ServiceLayoutNode;
        if (station) {
          onSelectNode(station.raw);
          // Smoothly pan controls target towards clicked node
          controls.target.set(station.position[0], 1.5, station.position[2]);
        }
      }
    };

    const domElem = renderer.domElement;
    domElem.addEventListener('mousemove', handleMouseMove);
    domElem.addEventListener('click', handleClick);

    // 6. Animation Loop
    let animId: number;
    let clock = new THREE.Clock();

    const animate = () => {
      animId = requestAnimationFrame(animate);
      const _delta = clock.getDelta();
      const time = clock.getElapsedTime();

      // Ambient red light pulse at paymentservice
      redFailureLight.intensity = 3.6 + Math.sin(time * 3.5) * 1.2;

      // Animate Traffic Flow Pulses along pipes
      if (showTrafficFlow) {
        flowPulses.forEach((p) => {
          p.progress = (p.progress + p.speed) % 1;
          const pos = p.curve.getPointAt(p.progress);
          p.mesh.position.copy(pos);
          p.mesh.visible = true;
        });
      } else {
        flowPulses.forEach((p) => (p.mesh.visible = false));
      }

      // Toggle label sprites
      stationLabelSprites.forEach((s) => {
        s.visible = showLabels;
      });

      controls.update();
      renderer.render(scene, camera);
    };

    animate();

    // 7. Resize Observer
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

    // Cleanup
    return () => {
      cancelAnimationFrame(animId);
      ro.disconnect();
      domElem.removeEventListener('mousemove', handleMouseMove);
      domElem.removeEventListener('click', handleClick);
      controls.dispose();
      renderer.dispose();
    };
  }, [serviceStations, edges, selectedNodeFilter, highlightedNodes, alertingService, showTrafficFlow, showLabels, height, onSelectNode]);

  return (
    <div className="system-scene-wrapper" ref={containerRef} style={{ height }}>
      {webglSupported ? (
        <canvas ref={canvasRef} className="system-scene-canvas" />
      ) : (
        <div className="scene-webgl-fallback">
          <p>WebGL is unavailable. Switching to 2D Graph View topology.</p>
        </div>
      )}

      {/* Top-Left Telemetry HUD */}
      <div className="scene-hud-top-left">
        <div className="scene-hud-badge-row">
          <span className="scene-live-dot" />
          <span className="scene-live-text">Live System</span>
        </div>
        <div className="scene-counts-text">
          {serviceStations.length} services · {edges.length || 17} dependencies
        </div>
        <div className="scene-metrics-row">
          <div className="scene-metric-item">
            <span className="scene-metric-label">Requests/sec</span>
            <div className="scene-metric-val-wrap">
              <span className="scene-metric-val">1.2K</span>
              <svg className="scene-sparkline" viewBox="0 0 48 16" fill="none">
                <path d="M0 12 L10 10 L20 14 L30 6 L40 9 L48 4" stroke="#35C98A" strokeWidth="2" strokeLinecap="round" />
              </svg>
            </div>
          </div>
          <div className="scene-metric-item">
            <span className="scene-metric-label">Error rate</span>
            <div className="scene-metric-val-wrap">
              <span className="scene-metric-val error">2.5%</span>
              <svg className="scene-sparkline" viewBox="0 0 48 16" fill="none">
                <path d="M0 14 L12 12 L24 8 L36 3 L48 2" stroke="#FF453A" strokeWidth="2" strokeLinecap="round" />
              </svg>
            </div>
          </div>
          <div className="scene-metric-item">
            <span className="scene-metric-label">Latency p99</span>
            <div className="scene-metric-val-wrap">
              <span className="scene-metric-val error">2.5s</span>
            </div>
          </div>
        </div>
      </div>

      {/* Top-Right HUD Controls */}
      <div className="scene-hud-top-right">
        <button
          type="button"
          className={`scene-ctrl-btn ${showBlastRadius ? 'active' : ''}`}
          onClick={() => setShowBlastRadius(!showBlastRadius)}
          title="Toggle blast radius highlight"
        >
          <Radio size={13} />
          <span>Blast Radius</span>
        </button>
        <button
          type="button"
          className={`scene-ctrl-btn ${showTrafficFlow ? 'active' : ''}`}
          onClick={() => setShowTrafficFlow(!showTrafficFlow)}
          title="Toggle live traffic flow pulses"
        >
          <Zap size={13} />
          <span>Traffic Flow</span>
        </button>
        <button
          type="button"
          className={`scene-ctrl-btn ${showLabels ? 'active' : ''}`}
          onClick={() => setShowLabels(!showLabels)}
          title="Toggle service labels"
        >
          <Tag size={13} />
          <span>Labels</span>
        </button>
        <button
          type="button"
          className="scene-ctrl-btn"
          onClick={() => {
            if (canvasRef.current) {
              canvasRef.current.dispatchEvent(new Event('dblclick'));
            }
          }}
          title="Reset Camera"
        >
          <Crosshair size={13} />
          <span>Reset Camera</span>
        </button>
      </div>

      {/* Floating Raycast Tooltip */}
      {hoveredNode && (
        <div
          className="scene-service-tooltip"
          style={{ left: hoveredNode.x, top: hoveredNode.y }}
        >
          <div className="scene-tooltip-header">
            <span className="scene-tooltip-title">{hoveredNode.node.name}</span>
            <span
              className={`scene-tooltip-badge ${
                hoveredNode.node.status === 'critical' ? 'red' : hoveredNode.node.status === 'warning' ? 'amber' : 'green'
              }`}
            >
              {hoveredNode.node.badge}
            </span>
          </div>
          <div className="scene-tooltip-body">
            <div className="scene-tooltip-row">
              <span>Latency:</span>
              <strong>{hoveredNode.node.latency}</strong>
            </div>
            <div className="scene-tooltip-row">
              <span>Error Rate:</span>
              <strong>{hoveredNode.node.errorRate}</strong>
            </div>
            <div className="scene-tooltip-row">
              <span>Throughput:</span>
              <strong>{hoveredNode.node.throughput}</strong>
            </div>
            <div className="scene-tooltip-row" style={{ marginTop: 4, opacity: 0.7 }}>
              <span>Click to inspect &amp; filter timeline</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
