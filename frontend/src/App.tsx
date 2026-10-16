import React, { useState, useEffect, useRef } from 'react';
import './App.css';
import {
  Activity,
  Layers,
  Brain,
  GitCompare,
  BarChart2,
  Search,
  MessageSquare,
  Zap,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
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

import { AlertConsole } from './components/AlertConsole';
import { AgentTimeline } from './components/AgentTimeline';
import { GraphCanvas } from './components/GraphCanvas';
import { HypothesisBoard } from './components/HypothesisBoard';
import { MemoryPanel } from './components/MemoryPanel';
import { CounterfactualPanel } from './components/CounterfactualPanel';
import { BenchmarkTab } from './components/BenchmarkTab';
import { AskBrainDrawer } from './components/AskBrainDrawer';
import { InspectorDrawer } from './components/InspectorDrawer';
import { ApprovalGate } from './components/ApprovalGate';

export default function App() {
  // Navigation & View Mode
  const [activeTab, setActiveTab] = useState<'incident' | 'counterfactual' | 'benchmark'>('incident');
  const [tenant, setTenant] = useState<string>('storefront');
  const [mode, setMode] = useState<'replay' | 'live'>('replay');
  const [healthOk, setHealthOk] = useState<boolean>(true);

  // Scenarios & Alert Selection
  const [scenarios, setScenarios] = useState<ScenarioItem[]>([]);
  const [selectedScenarioId, setSelectedScenarioId] = useState<string>('sc_repeated_01');
  const [customService, setCustomService] = useState<string>('paymentservice');
  const [customAlertText, setCustomAlertText] = useState<string>(
    'High HTTP 500 error rate on checkout payment authorize'
  );
  const [isRunning, setIsRunning] = useState<boolean>(false);

  // Active Incident State
  const [currentIncidentId, setCurrentIncidentId] = useState<string>('');
  const [activePhase, setActivePhase] = useState<string>('triage');
  const [events, setEvents] = useState<SSEEvent[]>([]);
  const [hypotheses, setHypotheses] = useState<HypothesisItem[]>([]);
  const [selectedHypothesisId, setSelectedHypothesisId] = useState<string | null>(null);
  const [pendingEvidenceRequest, setPendingEvidenceRequest] = useState<any>(null);
  const [memoryData, setMemoryData] = useState<MemoryRecallData | null>(null);
  const [pendingActions, setPendingActions] = useState<PendingAction[]>([]);
  const [isProcessingAction, setIsProcessingAction] = useState<boolean>(false);

  // Graph State
  const [graphNodes, setGraphNodes] = useState<GraphNode[]>([]);
  const [graphEdges, setGraphEdges] = useState<GraphEdge[]>([]);
  const [highlightedNodes, setHighlightedNodes] = useState<Set<string>>(new Set());
  const [highlightedEdges, setHighlightedEdges] = useState<Set<string>>(new Set());
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

  const handleSelectScenario = (id: string) => {
    setSelectedScenarioId(id);
    const sc = scenarios.find((s) => s.id === id);
    if (sc) {
      setCustomService(sc.alert.service);
      setCustomAlertText(sc.alert.text);
    }
  };

  // Launch Agent Crew
  const handleRunCrew = async () => {
    setIsRunning(true);
    setEvents([]);
    setPendingActions([]);
    setPendingEvidenceRequest(null);
    setHighlightedNodes(new Set());
    setHighlightedEdges(new Set());

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

      const incId = resp.data?.incident_id;
      setCurrentIncidentId(incId);
      fullTraceRef.current = resp.trace;

      // Highlight trace nodes
      if (resp.trace?.nodes) {
        setHighlightedNodes(new Set(resp.trace.nodes));
      }
      if (resp.trace?.edges) {
        setHighlightedEdges(new Set(resp.trace.edges));
      }

      // Process Investigation Hypotheses
      const invHypotheses = resp.data?.investigation?.hypotheses || [];
      setHypotheses(invHypotheses);
      if (invHypotheses.length > 0) {
        setSelectedHypothesisId(invHypotheses[0].id);
      }

      if (resp.data?.investigation?.evidence_request_task) {
        setPendingEvidenceRequest(resp.data.investigation.evidence_request_task);
      }

      // Process Memory Recall
      if (resp.data?.triage?.recalled_memory) {
        setMemoryData(resp.data.triage.recalled_memory);
      }

      // Check for pending actions awaiting approval
      if (resp.data?.response?.action?.status === 'proposed') {
        setPendingActions([resp.data.response.action]);
        setActivePhase('responder');
      } else if (resp.data?.status === 'closed') {
        setActivePhase('verifier');
      }

      // Refresh graph to show touched state
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
      // Fetch latest incident state
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
      await rejectAction(currentIncidentId, actionId, 'Rejected by SRE on-call operator', tenant);
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
    setSelectedGraphNode(node);
    setIsInspectorOpen(true);
  };

  return (
    <div className="ripple-dashboard">
      {/* Top Navbar */}
      <header className="top-nav">
        <div className="brand-section">
          <div className="brand-logo-container">
            <span className="brand-name">RippleAI</span>
          </div>

          {/* Center Soundwave Pulse Motif from SonicAI reference */}
          <div className="center-waveform">
            <div className="waveform-bars">
              <div className="wave-bar" />
              <div className="wave-bar" />
              <div className="wave-bar" />
              <div className="wave-bar" />
              <div className="wave-bar" />
              <div className="wave-bar" />
            </div>
            <span>Graph Pulse Active</span>
          </div>
        </div>

        {/* Navigation Tabs */}
        <nav className="nav-tabs">
          <button
            className={`tab-btn ${activeTab === 'incident' ? 'active' : ''}`}
            onClick={() => setActiveTab('incident')}
          >
            <Activity size={14} />
            <span>Incident Investigation</span>
          </button>
          <button
            className={`tab-btn ${activeTab === 'counterfactual' ? 'active' : ''}`}
            onClick={() => setActiveTab('counterfactual')}
          >
            <GitCompare size={14} />
            <span>Counterfactual (What-If)</span>
          </button>
          <button
            className={`tab-btn ${activeTab === 'benchmark' ? 'active' : ''}`}
            onClick={() => setActiveTab('benchmark')}
          >
            <BarChart2 size={14} />
            <span>Benchmark &amp; Calibration</span>
          </button>
        </nav>

        <div className="nav-actions">
          <Button
            variant="outline"
            size="sm"
            className="rounded-full gap-2 border-white/20 bg-transparent hover:bg-white/10 text-white cursor-pointer"
            onClick={() => setIsAskDrawerOpen(true)}
          >
            <MessageSquare size={14} />
            <span>Ask Company Brain</span>
          </Button>
        </div>
      </header>

      {/* Main Container */}
      <main className="dashboard-main">
        {/* SonicAI Hero Section */}
        <section className="sonic-hero-section">
          <div className="sonic-hero-top">
            <div className="sonic-hero-headline-box">
              <h1 className="sonic-hero-title">
                Your AI-Powered <br />
                <span className="sonic-highlight-cream">on-call, your way</span>
              </h1>
            </div>

            <div className="sonic-hero-desc-box">
              <p className="sonic-hero-text">
                Orchestrate autonomous incident triage, root cause diagnosis, and runbook execution
                with our graph-native SRE crew. Triage, simulate counterfactuals, and learn across
                outages effortlessly.
              </p>
              <div className="sonic-hero-cta-row">
                <Button
                  size="default"
                  className="sonic-btn-primary rounded-full cursor-pointer hover:scale-105 transition-all"
                  onClick={handleRunCrew}
                  disabled={isRunning}
                >
                  {isRunning ? 'Investigating...' : 'Start Crew Run'}
                </Button>
                <Button
                  variant="outline"
                  size="default"
                  className="sonic-btn-secondary rounded-full cursor-pointer hover:bg-white/10"
                  onClick={() => setIsAskDrawerOpen(true)}
                >
                  Ask Brain
                </Button>
              </div>
            </div>
          </div>

          {/* Trio Feature Cards with Icons */}
          <div className="sonic-feature-trio">
            <div className="sonic-feature-item">
              <div className="feature-icon-badge">
                <Layers size={14} />
              </div>
              <div className="feature-item-text">
                <strong>Full Graph Blackboard</strong>
                <span>Real-time Cypher execution tracing &amp; causal DAG traversal</span>
              </div>
            </div>

            <div className="sonic-feature-item">
              <div className="feature-icon-badge">
                <Brain size={14} />
              </div>
              <div className="feature-item-text">
                <strong>Outcome Memory Engine</strong>
                <span>Past failure-mode suppression &amp; calibrated runbooks</span>
              </div>
            </div>

            <div className="sonic-feature-item">
              <div className="feature-icon-badge">
                <GitCompare size={14} />
              </div>
              <div className="feature-item-text">
                <strong>Counterfactual Sandbox</strong>
                <span>Live what-if hypothetical diffing &amp; PageRank blast radius</span>
              </div>
            </div>
          </div>

          {/* Editorial Tagline from Reference Image */}
          <div className="sonic-tagline-strip">
            <span className="tagline-eyebrow">EXPERIENCE AUTONOMOUS INCIDENT RESPONSE</span>
            <p className="tagline-headline">
              Incident response that feels truly intelligent. Your infrastructure, your way—<span className="text-cream">Intelligent, Intuitive, Yours</span>
            </p>
          </div>
        </section>

        {/* Alert Console */}
        <AlertConsole
          scenarios={scenarios}
          selectedScenarioId={selectedScenarioId}
          onSelectScenario={handleSelectScenario}
          customAlertText={customAlertText}
          onChangeCustomAlertText={setCustomAlertText}
          customService={customService}
          onChangeCustomService={setCustomService}
          tenant={tenant}
          onChangeTenant={setTenant}
          mode={mode}
          onToggleMode={setMode}
          isRunning={isRunning}
          onRunCrew={handleRunCrew}
          healthOk={healthOk}
        />

        {/* Operational Approval Gate if action proposed */}
        <ApprovalGate
          pendingActions={pendingActions}
          incidentId={currentIncidentId}
          onApprove={handleApproveAction}
          onReject={handleRejectAction}
          isProcessing={isProcessingAction}
        />

        {/* Tab 1: Incident Investigation Workspace */}
        {activeTab === 'incident' && (
          <div className="workspace-grid">
            {/* Left Column: Graph Canvas & Timeline */}
            <div className="workspace-left-col">
              <GraphCanvas
                nodes={graphNodes}
                edges={graphEdges}
                highlightedNodes={highlightedNodes}
                highlightedEdges={highlightedEdges}
                asOfNow={asOfNow}
                onToggleTimeTravel={() => setAsOfNow(!asOfNow)}
                onSelectNode={handleSelectGraphNode}
                onStartWhyReplay={handleStartWhyReplay}
                isReplaying={isReplaying}
              />
              <AgentTimeline events={events} activePhase={activePhase} />
            </div>

            {/* Right Column: Hypothesis Board & Memory Panel */}
            <div className="workspace-right-col">
              <HypothesisBoard
                hypotheses={hypotheses}
                selectedHypothesisId={selectedHypothesisId}
                onSelectHypothesis={(id) => {
                  setSelectedHypothesisId(id);
                  const h = hypotheses.find((x) => x.id === id);
                  if (h?.service) {
                    setHighlightedNodes(new Set([h.service]));
                  }
                }}
                pendingEvidenceRequest={pendingEvidenceRequest}
                onInspectEvidence={handleInspectEvidence}
              />
              <MemoryPanel memoryData={memoryData} />
            </div>
          </div>
        )}

        {/* Tab 2: Counterfactual Simulator Workspace */}
        {activeTab === 'counterfactual' && (
          <div className="workspace-grid">
            <div className="workspace-left-col">
              <GraphCanvas
                nodes={graphNodes}
                edges={graphEdges}
                highlightedNodes={highlightedNodes}
                highlightedEdges={highlightedEdges}
                counterfactualMode={{
                  active: !!counterfactualResult,
                  observedSet: new Set(counterfactualResult?.only_observed || []),
                  hypotheticalSet: new Set(counterfactualResult?.only_hypothetical || []),
                  bothSet: new Set(counterfactualResult?.both || []),
                }}
                asOfNow={asOfNow}
                onToggleTimeTravel={() => setAsOfNow(!asOfNow)}
                onSelectNode={handleSelectGraphNode}
              />
            </div>
            <div className="workspace-right-col">
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
      </main>

      {/* Drawers */}
      <AskBrainDrawer
        isOpen={isAskDrawerOpen}
        onClose={() => setIsAskDrawerOpen(false)}
        onAsk={(q) => askBrain(q, mode, tenant)}
        onSelectNodeId={(nid) => {
          setHighlightedNodes(new Set([nid]));
          setIsAskDrawerOpen(false);
        }}
      />

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
