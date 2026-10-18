import React, { useState, useEffect, useRef } from 'react';
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import './App.css';
import {
  checkHealth,
  getScenarios,
  loadScenario,
  runIncidentCrew,
  getIncident,
  approveAction,
  rejectAction,
  getGraphSubgraph,
  getCounterfactual,
  askBrain,
  getBenchmarkReport,
  runBenchmark,
  subscribeIncidentStream,
  getSystemStatus,
  type ScenarioItem,
  type SSEEvent,
  type GraphNode,
  type GraphEdge,
  type HypothesisItem,
  type HypothesisEvidence,
  type MemoryRecallData,
  type PendingAction,
  type CounterfactualResponse,
  type BenchmarkReportResponse,
  type TraceStep,
} from './api';

import { Sidebar, type ViewId } from './components/Sidebar';
import { TopNav } from './components/TopNav';
import { ServicesView, IncidentsView, MemoryView, SettingsView, ModuleView } from './components/ExplorerViews';
import { AgentTimeline } from './components/AgentTimeline';
import { GraphCanvas } from './components/GraphCanvas';
import { HypothesisBoard } from './components/HypothesisBoard';
import { MemoryPanel } from './components/MemoryPanel';
import { CounterfactualPanel } from './components/CounterfactualPanel';
import { BenchmarkTab } from './components/BenchmarkTab';
import { AskBrainDrawer } from './components/AskBrainDrawer';
import { InspectorDrawer } from './components/InspectorDrawer';
import { ApprovalGate } from './components/ApprovalGate';
import { ScenarioDrawer } from './components/ScenarioDrawer';
import { RippleFooter } from './components/RippleFooter';
import { IncidentHeader } from './components/IncidentHeader';
import { SystemScene3D } from './components/SystemScene3D';
import { IncidentFlowPanel } from './components/IncidentFlowPanel';
import { TracePanel } from './components/TracePanel';

const PATH_TO_VIEW_MAP: Record<string, ViewId> = {
  '': 'incident',
  'investigation': 'incident',
  'counterfactual': 'counterfactual',
  'benchmark': 'benchmark',
  'services': 'services',
  'incidents': 'incidents',
  'memory': 'memory',
  'runbooks': 'runbooks',
  'people': 'people',
  'docs': 'docs',
  'settings': 'settings',
};

const VIEW_TO_PATH_MAP: Record<ViewId, string> = {
  incident: '/',
  counterfactual: '/counterfactual',
  benchmark: '/benchmark',
  services: '/services',
  incidents: '/incidents',
  memory: '/memory',
  runbooks: '/runbooks',
  people: '/people',
  docs: '/docs',
  settings: '/settings',
};

export default function App() {
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [copiedToast, setCopiedToast] = useState(false);

  // Theme state: defaults to dark matching Image 2, toggleable to light matching Image 1
  const [theme, setTheme] = useState<'dark' | 'light'>('dark');

  // Navigation & View Mode
  const [activeTab, setActiveTab] = useState<ViewId>('incident');
  const [tenant, setTenant] = useState<string>('storefront');
  const [mode, setMode] = useState<'replay' | 'live'>('replay');
  const [healthOk, setHealthOk] = useState<boolean>(true);
  const [viewMode, setViewMode] = useState<'3d' | 'graph' | 'list'>('graph');
  const [activeSubTab, setActiveSubTab] = useState<'system' | 'timeline' | 'hypotheses' | 'evidence' | 'runbook' | 'counterfactuals'>('system');

  // Scenarios & Alert Selection
  const [scenarios, setScenarios] = useState<ScenarioItem[]>([]);
  const [selectedScenarioId, setSelectedScenarioId] = useState<string>('sc_repeated_01');
  const [customService, setCustomService] = useState<string>('paymentservice');
  const [customAlertText, setCustomAlertText] = useState<string>(
    'High HTTP 500 error rate on checkout payment authorize'
  );
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [elapsedSeconds, setElapsedSeconds] = useState<number>(0);
  const [isScenarioDrawerOpen, setIsScenarioDrawerOpen] = useState<boolean>(false);

  // Active Incident State
  const [currentIncidentId, setCurrentIncidentId] = useState<string>('inc_active_01');
  const [activePhase, setActivePhase] = useState<string>('triage');
  const [events, setEvents] = useState<SSEEvent[]>([]);
  const [hypotheses, setHypotheses] = useState<HypothesisItem[]>([]);
  const [selectedHypothesisId, setSelectedHypothesisId] = useState<string | null>(null);
  const [pendingEvidenceRequest, setPendingEvidenceRequest] = useState<any>(null);
  const [memoryData, setMemoryData] = useState<MemoryRecallData | null>(null);
  const [pendingActions, setPendingActions] = useState<PendingAction[]>([]);
  const [isProcessingAction, setIsProcessingAction] = useState<boolean>(false);
  const [systemStatus, setSystemStatus] = useState<any>(null);
  const streamCleanupRef = useRef<(() => void) | null>(null);
  const lastEventIdRef = useRef<string | null>(null);

  // Graph State & Entity Filter
  const [graphNodes, setGraphNodes] = useState<GraphNode[]>([]);
  const [graphEdges, setGraphEdges] = useState<GraphEdge[]>([]);
  const [highlightedNodes, setHighlightedNodes] = useState<Set<string>>(new Set());
  const [highlightedEdges, setHighlightedEdges] = useState<Set<string>>(new Set());
  const [selectedNodeFilter, setSelectedNodeFilter] = useState<string | null>(null);
  const [asOfNow, setAsOfNow] = useState<boolean>(false);
  const [isReplaying, setIsReplaying] = useState<boolean>(false);
  const fullTraceRef = useRef<any>(null);

  // Drawers
  const [isAskDrawerOpen, setIsAskDrawerOpen] = useState<boolean>(false);
  const [isInspectorOpen, setIsInspectorOpen] = useState<boolean>(false);
  const [selectedTraceStep, setSelectedTraceStep] = useState<TraceStep | null>(null);
  const [selectedEvidence, setSelectedEvidence] = useState<HypothesisEvidence | null>(null);
  const [selectedGraphNode, setSelectedGraphNode] = useState<any | null>(null);

  // Counterfactual State
  const [counterfactualResult, setCounterfactualResult] = useState<CounterfactualResponse | null>(null);
  const [isCfLoading, setIsCfLoading] = useState<boolean>(false);

  // Benchmark State
  const [benchmarkReport, setBenchmarkReport] = useState<BenchmarkReportResponse | null>(null);
  const [isBenchRunning, setIsBenchRunning] = useState<boolean>(false);

  // Sync route on mount & location changes
  useEffect(() => {
    const rawPath = location.pathname.replace(/^\/+|\/+$/g, '').toLowerCase();

    if (rawPath.startsWith('incidents/')) {
      const parts = rawPath.split('/');
      if (parts[1]) {
        setCurrentIncidentId(parts[1].toUpperCase());
      }
      setActiveTab('incident');
    } else {
      const targetView = PATH_TO_VIEW_MAP[rawPath] || 'incident';
      setActiveTab(targetView);
    }
  }, [location.pathname]);

  // Sync search params with tabs, views, and filters
  useEffect(() => {
    const tabParam = searchParams.get('tab');
    if (
      tabParam &&
      ['system', 'timeline', 'hypotheses', 'evidence', 'runbook', 'counterfactuals'].includes(tabParam)
    ) {
      setActiveSubTab(tabParam as any);
    }

    const viewParam = searchParams.get('view');
    if (viewParam && ['3d', 'graph', 'list'].includes(viewParam)) {
      setViewMode(viewParam as any);
    }

    const tenantParam = searchParams.get('tenant');
    if (tenantParam) {
      setTenant(tenantParam);
    }

    const svcParam = searchParams.get('service');
    if (svcParam) {
      setSelectedNodeFilter(svcParam);
      setHighlightedNodes(new Set([svcParam]));
    }
  }, [searchParams]);

  // Navigation Handlers
  const handleSelectTab = (tab: ViewId) => {
    const targetPath = VIEW_TO_PATH_MAP[tab] || '/';
    navigate({
      pathname: targetPath,
      search: searchParams.toString(),
    });
  };

  const handleChangeSubTab = (subTab: typeof activeSubTab) => {
    setActiveSubTab(subTab);
    const nextParams = new URLSearchParams(searchParams);
    if (subTab === 'system') {
      nextParams.delete('tab');
    } else {
      nextParams.set('tab', subTab);
    }
    setSearchParams(nextParams, { replace: true });
  };

  const handleChangeViewMode = (mode: '3d' | 'graph' | 'list') => {
    setViewMode(mode);
    const nextParams = new URLSearchParams(searchParams);
    if (mode === 'graph') {
      nextParams.delete('view');
    } else {
      nextParams.set('view', mode);
    }
    setSearchParams(nextParams, { replace: true });
  };

  const handleShareUrl = () => {
    const url = window.location.href;
    navigator.clipboard.writeText(url).then(() => {
      setCopiedToast(true);
      setTimeout(() => setCopiedToast(false), 3000);
    });
  };

  // Sync theme class on document element
  useEffect(() => {
    if (theme === 'dark') {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [theme]);

  const toggleTheme = () => {
    setTheme((prev) => (prev === 'dark' ? 'light' : 'dark'));
  };

  const mainContentRef = useRef<HTMLDivElement>(null);

  // Scroll to top whenever the view changes
  useEffect(() => {
    if (mainContentRef.current) {
      mainContentRef.current.scrollTo({ top: 0, behavior: 'smooth' });
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, [activeTab]);

  const VIEW_TITLES: Record<ViewId, string> = {
    incident: 'Incident Investigation',
    counterfactual: 'Counterfactual (What-If)',
    benchmark: 'Benchmark & Calibration',
    services: 'Services',
    incidents: 'Incidents',
    memory: 'Memory',
    runbooks: 'Runbooks',
    people: 'People',
    docs: 'Docs & PRs',
    settings: 'Settings',
  };

  // Keyboard shortcut Ctrl+K to open scenario drawer / search
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        setIsScenarioDrawerOpen((prev) => !prev);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Load functions
  const loadInitialGraph = async () => {
    try {
      const data = await getGraphSubgraph({ radius: 3 }, tenant);
      setGraphNodes(data.nodes);
      setGraphEdges(data.edges);
    } catch (err) {
      console.error('Failed to load graph:', err);
    }
  };

  const loadBenchmarkData = async () => {
    try {
      const report = await getBenchmarkReport();
      setBenchmarkReport(report);
    } catch (err) {
      console.warn('Benchmark report not pre-computed yet:', err);
    }
  };

  // Live timer while crew is running
  useEffect(() => {
    let timer: any;
    if (isRunning) {
      timer = setInterval(() => {
        setElapsedSeconds((prev) => prev + 1);
      }, 1000);
    }
    return () => clearInterval(timer);
  }, [isRunning]);

  // Initial load
  useEffect(() => {
    checkHealth()
      .then(() => setHealthOk(true))
      .catch(() => setHealthOk(false));

    getScenarios(tenant)
      .then((scs) => {
        setScenarios(scs);
        if (scs.length > 0 && !selectedScenarioId) {
          setSelectedScenarioId(scs[0].id);
          setCustomService(scs[0].alert.service);
          setCustomAlertText(scs[0].alert.text);
        }
      })
      .catch((err) => console.error('Failed to load scenarios:', err));

    getSystemStatus()
      .then(setSystemStatus)
      .catch(console.warn);

    loadInitialGraph();
    loadBenchmarkData();

    return () => {
      if (streamCleanupRef.current) {
        streamCleanupRef.current();
      }
    };
  }, [tenant]);

  const handleSelectScenario = (id: string) => {
    setSelectedScenarioId(id);
    const sc = scenarios.find((s) => s.id === id);
    if (sc) {
      setCustomService(sc.alert.service);
      setCustomAlertText(sc.alert.text);
      setHypotheses([]);
      setMemoryData(null);
      setEvents([]);
      setSelectedNodeFilter(null);
    }
  };

  // Launch Agent Crew in Real Time with SSE streaming
  const handleRunCrew = async () => {
    // Switch to incident view immediately so user sees the run
    setActiveTab('incident');
    navigate({ pathname: '/', search: searchParams.toString() });

    if (streamCleanupRef.current) {
      streamCleanupRef.current();
      streamCleanupRef.current = null;
    }
    setIsRunning(true);
    setElapsedSeconds(0);
    setEvents([]);
    setPendingActions([]);
    setPendingEvidenceRequest(null);
    setHighlightedNodes(new Set());
    setHighlightedEdges(new Set());
    setActivePhase('triage');
    lastEventIdRef.current = null;

    try {
      // 1. If scenario selected, seed graph
      if (selectedScenarioId) {
        try {
          await loadScenario(selectedScenarioId, tenant);
        } catch (e) {
          console.warn('Scenario load warning (proceeding anyway):', e);
        }
      }

      // 2. Start Crew (Async 202 Accepted)
      const alertPayload = {
        service: customService || 'cartservice',
        text: customAlertText || 'Degraded latency detected',
      };

      const resp = await runIncidentCrew(
        {
          alert: alertPayload,
          scenario_id: selectedScenarioId || undefined,
          mode: mode,
          auto_approve: false,
          sync: false,
        },
        tenant
      );

      const incId = resp.incident_id || resp.data?.incident_id;
      if (!incId) {
        throw new Error('Failed to start incident: No incident ID returned from server.');
      }
      setCurrentIncidentId(incId);

      // Helper to sync latest incident state from blackboard
      const syncIncidentState = async () => {
        try {
          const state = await getIncident(incId, tenant);
          if (state.blackboard?.hypotheses && state.blackboard.hypotheses.length > 0) {
            setHypotheses(state.blackboard.hypotheses);
            if (!selectedHypothesisId) {
              setSelectedHypothesisId(state.blackboard.hypotheses[0].id);
            }
          }
          if (state.pending_actions && state.pending_actions.length > 0) {
            setPendingActions(state.pending_actions);
            setActivePhase('awaiting_approval');
          }
          if (state.incident?.status === 'resolved' || state.incident?.status === 'closed') {
            setIsRunning(false);
            setActivePhase('closed');
          }
        } catch (err) {
          console.warn('Sync poll warning:', err);
        }
      };

      // 3. Subscribe to real-time live SSE stream
      streamCleanupRef.current = subscribeIncidentStream(
        incId,
        tenant,
        lastEventIdRef.current,
        (sseEv: SSEEvent) => {
          if ((sseEv as any).id) lastEventIdRef.current = (sseEv as any).id;
          if (sseEv.event === 'ping') return;

          setEvents((prev) => [...prev, sseEv]);

          if (sseEv.event === 'agent_started') {
            const role = (sseEv.data?.role || '').toLowerCase();
            if (role === 'triage') setActivePhase('triage');
            else if (role === 'investigator') setActivePhase('investigator');
            else if (role === 'responder') setActivePhase('responder');
            else if (role === 'verifier') setActivePhase('verifier');
          } else if (sseEv.event === 'tool_called') {
            if (sseEv.data?.node_ids) setHighlightedNodes(new Set(sseEv.data.node_ids));
          } else if (sseEv.event === 'hypotheses_ranked') {
            syncIncidentState();
          } else if (sseEv.event === 'approval_needed') {
            setActivePhase('awaiting_approval');
            syncIncidentState();
          } else if (sseEv.event === 'action_executed') {
            setActivePhase('verifier');
            syncIncidentState();
          } else if (sseEv.event === 'incident_closed') {
            setIsRunning(false);
            setActivePhase('closed');
            syncIncidentState();
            loadInitialGraph();
          }
        },
        (err) => {
          console.warn('Live SSE stream notice:', err);
        }
      );

      // Background periodic polling as fallback for proxy buffering
      const pollTimer = setInterval(async () => {
        await syncIncidentState();
      }, 1500);

      // Stop polling after 45 seconds max
      setTimeout(() => clearInterval(pollTimer), 45000);

      // Refresh topology for newly seeded/discovered nodes
      await loadInitialGraph();
    } catch (err: any) {
      console.error('Run crew error:', err);
      setIsRunning(false);
      alert(`Failed to start Agent Crew: ${err?.message || err}`);
    }
  };

  // Safe Action Gate: Approve
  const handleApproveAction = async (actionId: string) => {
    setIsProcessingAction(true);
    try {
      await approveAction(currentIncidentId, actionId, selectedScenarioId, tenant);
      setPendingActions([]);
      setActivePhase('verifier');
      const updated = await getIncident(currentIncidentId, tenant);
      if (updated.blackboard?.hypotheses) {
        setHypotheses(updated.blackboard.hypotheses);
      }
    } catch (err) {
      console.error('Approval failed:', err);
    } finally {
      setIsProcessingAction(false);
    }
  };

  // Safe Action Gate: Reject
  const handleRejectAction = async (actionId: string) => {
    setIsProcessingAction(true);
    try {
      await rejectAction(currentIncidentId, actionId, 'Rejected by operator', tenant);
      setPendingActions([]);
    } catch (err) {
      console.error('Rejection failed:', err);
    } finally {
      setIsProcessingAction(false);
    }
  };

  // "Why" Replay Animation
  const handleStartWhyReplay = () => {
    const steps = fullTraceRef.current?.steps || [];
    if (steps.length === 0) return;

    setIsReplaying(true);
    let stepIdx = 0;

    const interval = setInterval(() => {
      if (stepIdx >= steps.length) {
        clearInterval(interval);
        setIsReplaying(false);
        return;
      }
      const st = steps[stepIdx];
      setSelectedTraceStep(st);
      if (st.node_ids) setHighlightedNodes(new Set(st.node_ids));
      if (st.edge_ids) setHighlightedEdges(new Set(st.edge_ids));
      stepIdx++;
    }, 1200);
  };

  // Counterfactual What-If
  const handleRunCounterfactual = async (hypotheticalService: string) => {
    setIsCfLoading(true);
    try {
      const res = await getCounterfactual(
        currentIncidentId || 'inc_sc_repeated_01',
        hypotheticalService,
        asOfNow ? 'now' : 'incident_time',
        tenant
      );
      setCounterfactualResult(res);
      return res;
    } finally {
      setIsCfLoading(false);
    }
  };

  // Benchmark Run
  const handleExecuteBenchmark = async () => {
    setIsBenchRunning(true);
    try {
      await runBenchmark();
      await loadBenchmarkData();
    } catch (err) {
      console.error('Benchmark execution failed:', err);
    } finally {
      setIsBenchRunning(false);
    }
  };

  // Inspect Handlers
  const handleInspectEvidence = (ev: HypothesisEvidence) => {
    setSelectedEvidence(ev);
    setIsInspectorOpen(true);
  };

  const handleSelectGraphNode = (node: any) => {
    const nodeName = node.name || node.id;
    setSelectedNodeFilter(nodeName);
    setHighlightedNodes(new Set([nodeName]));

    const matchingHyp = hypotheses.find((h) => h.service?.toLowerCase() === nodeName?.toLowerCase());
    if (matchingHyp) {
      setSelectedHypothesisId(matchingHyp.id);
    }
    setSelectedGraphNode(node);
  };

  return (
    <div className="ripple-app-layout">
      {/* Immersive ambient backdrop */}
      <div className="ambient-bg" aria-hidden>
        <div className="ambient-orb a" />
        <div className="ambient-orb b" />
      </div>

      {/* 1. Left Sidebar Navigation */}
      <Sidebar
        activeTab={activeTab}
        onChangeTab={handleSelectTab}
        onOpenAskBrain={() => setIsAskDrawerOpen(true)}
        tenant={tenant}
        onChangeTenant={(t) => {
          setTenant(t);
          const nextParams = new URLSearchParams(searchParams);
          nextParams.set('tenant', t);
          setSearchParams(nextParams, { replace: true });
        }}
        healthOk={healthOk}
      />

      {/* 2. Main Workspace Layout */}
      <div className="ripple-main-content" ref={mainContentRef}>
        {/* Top Header Bar */}
        <TopNav
          theme={theme}
          onToggleTheme={toggleTheme}
          isRunning={isRunning}
          onRunCrew={handleRunCrew}
          onOpenSearch={() => setIsScenarioDrawerOpen(true)}
          viewTitle={VIEW_TITLES[activeTab]}
          mode={mode}
          onToggleMode={setMode}
          tenant={tenant}
        />

        {/* Scrollable Workspace Body */}
        <div className="main-scroll-body">
          {/* Degraded mode banner if no live LLM API keys configured */}
          {systemStatus?.llm_status === 'degraded' && (
            <div className="bg-amber-950/40 border border-amber-600/30 rounded-xl px-4 py-2 text-xs text-amber-200 flex items-center justify-between gap-3 mb-4">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
                <span><b>Degraded Mode</b>: No live LLM API keys configured. Ripple is reasoning deterministically over graph topology, telemetry evidence, and procedural memory.</span>
              </div>
              <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-amber-500/20 text-amber-300">Deterministic Active</span>
            </div>
          )}

          {activeTab === 'incident' && (
            <div className="flex flex-col gap-5">
              {/* Incident Header with Breadcrumb, Heartbeat, Title, Metadata & View Controls */}
              <IncidentHeader
                incidentId={currentIncidentId}
                severity="P1"
                title={customService === 'paymentservice' ? 'Checkout payment authorization failing' : `Incident on ${customService}`}
                subtitle={customAlertText || 'High HTTP 500 error rate on checkout payment authorize. 4 services impacted.'}
                startedTime="14:24:17"
                startedAgo={elapsedSeconds > 0 ? `${elapsedSeconds}s ago` : '12m ago'}
                status={isRunning ? 'Investigating (Live)' : hypotheses.length > 0 ? 'Root cause identified' : 'Investigating (Live)'}
                tenant={tenant}
                onChangeTenant={(t) => {
                  setTenant(t);
                  const nextParams = new URLSearchParams(searchParams);
                  nextParams.set('tenant', t);
                  setSearchParams(nextParams, { replace: true });
                }}
                activeSubTab={activeSubTab}
                onChangeSubTab={(tab) => {
                  handleChangeSubTab(tab);
                  if (tab === 'counterfactuals') handleSelectTab('counterfactual');
                }}
                viewMode={viewMode}
                onChangeViewMode={handleChangeViewMode}
                onShare={handleShareUrl}
              />

              {/* Operational Approval Gate if safe action proposed */}
              {pendingActions.length > 0 && (
                <ApprovalGate
                  pendingActions={pendingActions}
                  incidentId={currentIncidentId}
                  onApprove={handleApproveAction}
                  onReject={handleRejectAction}
                  isProcessing={isProcessingAction}
                />
              )}

              {/* Specific SubTab: Runbook */}
              {activeSubTab === 'runbook' && (
                <div className="workspace-split-grid">
                  <div className="split-left-col">
                    <MemoryPanel
                      memoryData={memoryData}
                      hasHypotheses={hypotheses.length > 0}
                      onExecuteRunbook={() => {
                        if (pendingActions.length > 0) {
                          handleApproveAction(pendingActions[0].id);
                        } else {
                          handleRunCrew();
                        }
                      }}
                      isExecuting={isProcessingAction}
                    />
                  </div>
                  <div className="split-right-col">
                    <HypothesisBoard
                      hypotheses={hypotheses}
                      selectedHypothesisId={selectedHypothesisId}
                      onSelectHypothesis={(id) => {
                        setSelectedHypothesisId(id);
                        const h = hypotheses.find((x) => x.id === id);
                        if (h?.service) {
                          setHighlightedNodes(new Set([h.service]));
                          setSelectedNodeFilter(h.service);
                        }
                      }}
                      pendingEvidenceRequest={pendingEvidenceRequest}
                      onInspectEvidence={handleInspectEvidence}
                    />
                  </div>
                </div>
              )}

              {/* Default Main Cinematic Layout (System View & Diagnostics) */}
              {activeSubTab !== 'runbook' && (
                <>
                  {/* Center Row: Interactive 3D System View (or 2D Fallback) + Incident Flow Panel */}
                  <div className="incident-dashboard-center-grid">
                    <div className="min-w-0">
                      {viewMode === '3d' && (
                        <SystemScene3D
                          nodes={graphNodes}
                          edges={graphEdges}
                          highlightedNodes={highlightedNodes}
                          highlightedEdges={highlightedEdges}
                          alertingService={customService}
                          selectedNodeFilter={selectedNodeFilter}
                          onSelectNode={handleSelectGraphNode}
                          onOpenInspector={() => setIsInspectorOpen(true)}
                          height={640}
                        />
                      )}
                      {viewMode === 'graph' && (
                        <GraphCanvas
                          nodes={graphNodes}
                          edges={graphEdges}
                          highlightedNodes={highlightedNodes}
                          highlightedEdges={highlightedEdges}
                          alertingService={customService}
                          selectedNodeFilter={selectedNodeFilter}
                          asOfNow={asOfNow}
                          onToggleTimeTravel={() => setAsOfNow(!asOfNow)}
                          onSelectNode={handleSelectGraphNode}
                          onStartWhyReplay={handleStartWhyReplay}
                          isReplaying={isReplaying}
                          height={580}
                        />
                      )}
                      {viewMode === 'list' && (
                        <ServicesView
                          nodes={graphNodes}
                          edges={graphEdges}
                          alertingService={customService}
                          onOpen={(n) => {
                            handleSelectGraphNode(n);
                            setIsInspectorOpen(true);
                          }}
                        />
                      )}
                    </div>

                    <div className="min-w-0">
                      <IncidentFlowPanel
                        alertingService={customService}
                        onFocusService={(svc) => {
                          setHighlightedNodes(new Set([svc]));
                          setSelectedNodeFilter(svc);
                        }}
                        onOpenBlastRadiusDrawer={() => setIsScenarioDrawerOpen(true)}
                      />
                    </div>
                  </div>

                  {/* Bottom Multi-Panel Diagnostic Row: Agent Activity Timeline | Current Trace | Top Hypotheses */}
                  <div className="incident-dashboard-bottom-grid">
                    {/* Column 1: Agent Activity Timeline */}
                    <div className="min-w-0">
                      <AgentTimeline
                        events={events}
                        activePhase={activePhase}
                        selectedNodeFilter={selectedNodeFilter}
                        onClearNodeFilter={() => {
                          setSelectedNodeFilter(null);
                          setHighlightedNodes(new Set());
                        }}
                      />
                    </div>

                    {/* Column 2: Current Trace Panel */}
                    <div className="min-w-0">
                      <TracePanel
                        traceId="9f3c...a2d1"
                        onOpenFullTrace={() => setIsInspectorOpen(true)}
                        onSelectService={(svc) => {
                          setHighlightedNodes(new Set([svc]));
                          setSelectedNodeFilter(svc);
                        }}
                        selectedService={selectedNodeFilter}
                      />
                    </div>

                    {/* Column 3: Top Hypotheses */}
                    <div className="min-w-0">
                      <HypothesisBoard
                        hypotheses={hypotheses}
                        selectedHypothesisId={selectedHypothesisId}
                        onSelectHypothesis={(id) => {
                          setSelectedHypothesisId(id);
                          const h = hypotheses.find((x) => x.id === id);
                          if (h?.service) {
                            setHighlightedNodes(new Set([h.service]));
                            setSelectedNodeFilter(h.service);
                          }
                        }}
                        pendingEvidenceRequest={pendingEvidenceRequest}
                        onInspectEvidence={handleInspectEvidence}
                      />
                    </div>
                  </div>
                </>
              )}
            </div>
          )}

          {/* Tab 2: Counterfactual Simulator Workspace */}
          {activeTab === 'counterfactual' && (
            <div className="workspace-split-grid">
              <div className="split-left-col">
                <GraphCanvas
                  nodes={graphNodes}
                  edges={graphEdges}
                  highlightedNodes={highlightedNodes}
                  highlightedEdges={highlightedEdges}
                  alertingService={customService}
                  counterfactualMode={{
                    active: !!counterfactualResult,
                    observedSet: new Set(counterfactualResult?.only_observed || []),
                    hypotheticalSet: new Set(counterfactualResult?.only_hypothetical || []),
                    bothSet: new Set(counterfactualResult?.both || []),
                  }}
                  asOfNow={asOfNow}
                  onToggleTimeTravel={() => setAsOfNow(!asOfNow)}
                  onSelectNode={handleSelectGraphNode}
                  title="Counterfactual Overlay"
                  height={620}
                />
              </div>
              <div className="split-right-col">
                <CounterfactualPanel
                  services={scenarios.map((s) => s.alert.service).filter(Boolean)}
                  currentIncidentId={currentIncidentId}
                  onRunCounterfactual={handleRunCounterfactual}
                  counterfactualResult={counterfactualResult}
                  isLoading={isCfLoading}
                />
              </div>
            </div>
          )}

          {/* Tab 3: Benchmark & Calibration Workspace */}
          {activeTab === 'benchmark' && (
            <BenchmarkTab
              reportData={benchmarkReport}
              onRunBenchmark={handleExecuteBenchmark}
              isRunning={isBenchRunning}
            />
          )}

          {activeTab === 'services' && (
            <ServicesView
              nodes={graphNodes}
              edges={graphEdges}
              alertingService={customService}
              onOpen={(n) => {
                handleSelectGraphNode(n);
                setIsInspectorOpen(true);
              }}
            />
          )}

          {activeTab === 'incidents' && (
            <IncidentsView
              scenarios={scenarios}
              selectedScenarioId={selectedScenarioId}
              onLoad={(id) => {
                handleSelectScenario(id);
                handleSelectTab('incident');
              }}
            />
          )}

          {activeTab === 'memory' && <MemoryView memoryData={memoryData} onGo={() => handleSelectTab('incident')} />}

          {activeTab === 'settings' && (
            <SettingsView
              theme={theme}
              onToggleTheme={toggleTheme}
              mode={mode}
              onChangeMode={setMode}
              tenant={tenant}
              onChangeTenant={setTenant}
            />
          )}

          {(activeTab === 'runbooks' || activeTab === 'people' || activeTab === 'docs') && (
            <ModuleView view={activeTab} onAskBrain={() => setIsAskDrawerOpen(true)} />
          )}
        </div>

        {/* Premium Animated Dark SaaS Footer with Giant Wordmark */}
        <RippleFooter
          activeTab={activeTab}
          onChangeTab={handleSelectTab}
          onOpenAskBrain={() => setIsAskDrawerOpen(true)}
          healthOk={healthOk}
        />
      </div>

      {/* Scenario Library Modal / Drawer */}
      <ScenarioDrawer
        isOpen={isScenarioDrawerOpen}
        onClose={() => setIsScenarioDrawerOpen(false)}
        scenarios={scenarios}
        selectedScenarioId={selectedScenarioId}
        onSelectScenario={handleSelectScenario}
      />

      {/* Ask Company Brain Drawer */}
      <AskBrainDrawer
        isOpen={isAskDrawerOpen}
        onClose={() => setIsAskDrawerOpen(false)}
        onAsk={(q) => askBrain(q, mode, tenant)}
        onSelectNodeId={(nid) => {
          setHighlightedNodes(new Set([nid]));
          setSelectedNodeFilter(nid);
          setIsAskDrawerOpen(false);
        }}
      />

      {/* Provenance Deep Trace Inspector Drawer */}
      <InspectorDrawer
        isOpen={isInspectorOpen}
        onClose={() => setIsInspectorOpen(false)}
        selectedStep={selectedTraceStep}
        selectedEvidence={selectedEvidence}
        selectedNode={selectedGraphNode}
      />

      {/* Deep-link URL Copied Toast */}
      {copiedToast && (
        <div
          role="status"
          aria-live="polite"
          className="fixed bottom-6 right-6 z-50 flex items-center gap-2.5 px-4 py-2.5 rounded-xl bg-[#171714] border border-[#FF642D] text-[#F5F1E8] shadow-[0_12px_32px_rgba(0,0,0,0.85)] text-[13px] font-medium animate-in fade-in slide-in-from-bottom-2"
        >
          <span className="w-2.5 h-2.5 rounded-full bg-[#35C98A] shadow-[0_0_8px_#35C98A]" />
          <span>Incident investigation link copied to clipboard!</span>
        </div>
      )}
    </div>
  );
}
