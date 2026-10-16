import React, { useState, useEffect, useRef } from 'react';
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

export default function App() {
  // Theme state: defaults to dark matching Image 2, toggleable to light matching Image 1
  const [theme, setTheme] = useState<'dark' | 'light'>('dark');

  // Navigation & View Mode
  const [activeTab, setActiveTab] = useState<ViewId>('incident');
  const [tenant, setTenant] = useState<string>('storefront');
  const [mode, setMode] = useState<'replay' | 'live'>('replay');
  const [healthOk, setHealthOk] = useState<boolean>(true);
  const [viewMode, setViewMode] = useState<'3d' | 'graph' | 'list'>('3d');
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
  const [currentIncidentId, setCurrentIncidentId] = useState<string>('INC-4029');
  const [activePhase, setActivePhase] = useState<string>('triage');
  const [events, setEvents] = useState<SSEEvent[]>([]);
  const [hypotheses, setHypotheses] = useState<HypothesisItem[]>([]);
  const [selectedHypothesisId, setSelectedHypothesisId] = useState<string | null>(null);
  const [pendingEvidenceRequest, setPendingEvidenceRequest] = useState<any>(null);
  const [memoryData, setMemoryData] = useState<MemoryRecallData | null>(null);
  const [pendingActions, setPendingActions] = useState<PendingAction[]>([]);
  const [isProcessingAction, setIsProcessingAction] = useState<boolean>(false);

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

  // Scroll to top whenever the view changes
  useEffect(() => {
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

    loadInitialGraph();
    loadBenchmarkData();
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

  // Launch Agent Crew
  const handleRunCrew = async () => {
    setIsRunning(true);
    setElapsedSeconds(0);
    setEvents([]);
    setPendingActions([]);
    setPendingEvidenceRequest(null);
    setHighlightedNodes(new Set());
    setHighlightedEdges(new Set());
    setActivePhase('triage');

    try {
      // 1. If scenario selected, seed graph
      if (selectedScenarioId) {
        await loadScenario(selectedScenarioId, tenant);
      }

      // 2. Run Crew
      const resp = await runIncidentCrew(
        {
          alert: { service: customService, text: customAlertText },
          scenario_id: selectedScenarioId || undefined,
          mode: mode,
          auto_approve: false,
        },
        tenant
      );

      const incId = resp.data?.incident_id || `INC-${Math.floor(1000 + Math.random() * 9000)}`;
      setCurrentIncidentId(incId);
      fullTraceRef.current = resp.trace;

      if (resp.trace?.nodes) setHighlightedNodes(new Set(resp.trace.nodes));
      if (resp.trace?.edges) setHighlightedEdges(new Set(resp.trace.edges));

      const newEvents: SSEEvent[] = [
        {
          incident_id: incId,
          event: 'incident_opened',
          data: { service: customService, text: customAlertText },
          ts: Date.now() / 1000 - 4,
        },
        {
          incident_id: incId,
          event: 'agent_started',
          data: { agent: 'triage_agent', role: 'triage' },
          ts: Date.now() / 1000 - 3,
        },
      ];

      if (resp.trace?.steps) {
        resp.trace.steps.forEach((st: TraceStep, idx: number) => {
          newEvents.push({
            incident_id: incId,
            event: 'tool_called',
            data: {
              tool: st.tool,
              cypher: st.cypher,
              result_count: st.rows_count || 1,
              summary: st.summary,
            },
            ts: Date.now() / 1000 - 2 + idx * 0.2,
          });
        });
      }

      const invHypotheses = resp.data?.investigation?.hypotheses || [];
      setHypotheses(invHypotheses);
      if (invHypotheses.length > 0) {
        setSelectedHypothesisId(invHypotheses[0].id);
        newEvents.push({
          incident_id: incId,
          event: 'hypotheses_ranked',
          data: {
            count: invHypotheses.length,
            top_hypothesis: invHypotheses[0],
          },
          ts: Date.now() / 1000 - 1,
        });
      }

      if (resp.data?.investigation?.evidence_request_task) {
        setPendingEvidenceRequest(resp.data.investigation.evidence_request_task);
        newEvents.push({
          incident_id: incId,
          event: 'evidence_requested',
          data: { task: resp.data.investigation.evidence_request_task },
          ts: Date.now() / 1000 - 0.5,
        });
      }

      if (resp.data?.triage?.recalled_memory) {
        setMemoryData(resp.data.triage.recalled_memory);
      }

      if (resp.data?.response?.action?.status === 'proposed') {
        setPendingActions([resp.data.response.action]);
        setActivePhase('responder');
      } else if (resp.data?.status === 'closed') {
        setActivePhase('verifier');
      }

      setEvents(newEvents);
      await loadInitialGraph();
    } catch (err) {
      console.error('Run crew error:', err);
    } finally {
      setIsRunning(false);
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
        onChangeTab={setActiveTab}
        onOpenAskBrain={() => setIsAskDrawerOpen(true)}
        tenant={tenant}
        onChangeTenant={setTenant}
        healthOk={healthOk}
      />

      {/* 2. Main Workspace Layout */}
      <div className="ripple-main-content">
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
                onChangeTenant={setTenant}
                activeSubTab={activeSubTab}
                onChangeSubTab={(tab) => {
                  setActiveSubTab(tab);
                  if (tab === 'counterfactuals') setActiveTab('counterfactual');
                }}
                viewMode={viewMode}
                onChangeViewMode={setViewMode}
                onShare={() => {
                  navigator.clipboard?.writeText(window.location.href);
                  alert('Incident investigation URL copied to clipboard');
                }}
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
                          height={580}
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
                setActiveTab('incident');
              }}
            />
          )}

          {activeTab === 'memory' && <MemoryView memoryData={memoryData} onGo={() => setActiveTab('incident')} />}

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
          onChangeTab={setActiveTab}
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
    </div>
  );
}
