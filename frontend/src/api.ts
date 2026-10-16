export interface ScenarioItem {
  id: string;
  family: string;
  description: string;
  alert: {
    service: string;
    text: string;
    severity?: string;
  };
  ground_truth?: {
    root_cause_service: string;
    root_cause_type: string;
    correct_runbook: string;
  };
}

export interface RunbookItem {
  id: string;
  title: string;
  description?: string;
  success_count?: number;
  fail_count?: number;
  historical_success_rate?: number;
  assumes?: string[];
}

export interface SSEEvent {
  incident_id: string;
  event: string;
  data: any;
  ts: number;
}

export interface TraceStep {
  id: string;
  tool: string;
  cypher: string;
  params: Record<string, any>;
  node_ids: string[];
  edge_ids: string[];
  summary: string;
  rows_count?: number;
  rows?: any[][];
  duration_ms?: number;
}

export interface TraceData {
  steps: TraceStep[];
  nodes: string[];
  edges: string[];
  total_steps?: number;
}

export interface HypothesisEvidence {
  id: string;
  type: string;
  kind: 'observed' | 'inferred';
  summary: string;
  source_ref?: string;
  observed_ts?: number;
  freshness?: number;
  weight?: number;
}

export interface HypothesisItem {
  id: string;
  statement: string;
  service: string;
  kind: 'inferred';
  status: string;
  evidence_score: number;
  margin?: number;
  supporting_evidence: HypothesisEvidence[];
  contradicting_evidence: HypothesisEvidence[];
}

export interface SimilarIncident {
  incident_id: string;
  title?: string;
  similarity?: number;
  score?: number;
  winning_hypothesis?: string;
  runbook_id?: string;
  outcome?: string;
}

export interface MemoryRecallData {
  similar_incidents: SimilarIncident[];
  recommended_runbook?: {
    id: string;
    title: string;
    historical_success_rate: number;
    applicable?: boolean;
    reason?: string;
  };
  rejected_runbooks?: Array<{
    id: string;
    title: string;
    reason: string;
    historical_success_rate?: number;
    changed_edge?: string;
  }>;
  known_facts?: Array<{
    id: string;
    service: string;
    text: string;
    kind: string;
    weight: number;
  }>;
}

export interface GraphNode {
  id: string;
  name?: string;
  label: string;
  tier?: string;
  status?: string;
  kind?: string;
  props?: Record<string, any>;
  color?: string;
  val?: number;
}

export interface GraphEdge {
  id?: string;
  source: string;
  target: string;
  type: string;
  protocol?: string;
  verified?: boolean;
  color?: string;
  dashed?: boolean;
}

export interface SubgraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface PendingAction {
  id: string;
  action_class: string;
  target_service: string;
  runbook_id: string;
  status: string;
  description: string;
}

export interface BlackboardState {
  incident_id: string;
  tasks: any[];
  agent_runs: any[];
  hypotheses: HypothesisItem[];
  observations: any[];
  conflicts: any[];
  actions: PendingAction[];
}

export interface IncidentStateResponse {
  incident: {
    id: string;
    title: string;
    status: string;
    opened_ts: number;
    resolved_ts?: number;
  };
  blackboard: BlackboardState;
  pending_actions: PendingAction[];
}

export interface CounterfactualResponse {
  only_observed: string[];
  only_hypothetical: string[];
  both: string[];
  observed_blast: {
    service: string;
    total_affected: number;
    affected_services: Array<{ service: string; hops: number }>;
  };
  hypothetical_blast: {
    service: string;
    total_affected: number;
    affected_services: Array<{ service: string; hops: number }>;
  };
  critical_owners?: Array<{
    service: string;
    pagerank_score: number;
    owners: string[];
  }>;
  uncertainty?: {
    unverified_edges_count: number;
    is_lower_bound: boolean;
    note: string;
  };
}

export interface AskBrainResponse {
  question: string;
  answer: string;
  intent: string;
  sources: Array<{
    id: string;
    title?: string;
    type?: string;
    label?: string;
    stale?: boolean;
    superseded?: boolean;
  }>;
  cypher_executed?: string;
}

export interface BenchmarkReportResponse {
  status: string;
  benchmark: {
    benchmark_protocol_version: string;
    timestamp: number;
    calibration_status: {
      passed: boolean;
      basis: string;
      score_label: string;
    };
    summary: {
      memory_on?: {
        total_scenarios: number;
        diagnosis_correctness: number;
        recommendation_correctness: number;
        unsafe_recommendation_rate: number;
        avg_tool_calls: number;
        avg_duration_seconds: number;
      };
      memory_off?: {
        total_scenarios: number;
        diagnosis_correctness: number;
        recommendation_correctness: number;
        unsafe_recommendation_rate: number;
        avg_tool_calls: number;
        avg_duration_seconds: number;
      };
    };
    runs: Array<{
      scenario_id: string;
      family: string;
      memory_mode: string;
      diagnosis_correct: boolean;
      top_hypothesis_service: string;
      ground_truth_service: string;
      recommendation_correct: boolean;
      recommended_runbook: string;
      ground_truth_runbook: string;
      is_unsafe_recommendation: boolean;
      tool_calls: number;
      duration_seconds: number;
      evidence_score: number;
    }>;
  };
  markdown_report: string;
}

// API client functions
export async function getScenarios(tenant: string = 'storefront'): Promise<ScenarioItem[]> {
  const res = await fetch('/scenarios', { headers: { 'X-Tenant': tenant } });
  if (!res.ok) throw new Error('Failed to load scenarios');
  const data = await res.json();
  return data.scenarios || [];
}

export async function loadScenario(scenarioId: string, tenant: string = 'storefront') {
  const res = await fetch(`/scenarios/${scenarioId}/load`, {
    method: 'POST',
    headers: { 'X-Tenant': tenant, 'Content-Type': 'application/json' },
  });
  if (!res.ok) throw new Error(`Failed to load scenario ${scenarioId}`);
  return res.json();
}

export async function runIncidentCrew(
  payload: {
    alert: { service: string; text: string };
    scenario_id?: string;
    mode?: string;
    auto_approve?: boolean;
  },
  tenant: string = 'storefront'
) {
  const res = await fetch('/incidents', {
    method: 'POST',
    headers: { 'X-Tenant': tenant, 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error('Failed to run incident crew');
  return res.json();
}

export async function getIncident(incidentId: string, tenant: string = 'storefront'): Promise<IncidentStateResponse> {
  const res = await fetch(`/incidents/${incidentId}`, { headers: { 'X-Tenant': tenant } });
  if (!res.ok) throw new Error(`Failed to fetch incident ${incidentId}`);
  return res.json();
}

export async function approveAction(incidentId: string, actionId: string, scenarioId?: string, tenant: string = 'storefront') {
  const res = await fetch(`/incidents/${incidentId}/actions/${actionId}/approve`, {
    method: 'POST',
    headers: { 'X-Tenant': tenant, 'Content-Type': 'application/json' },
    body: JSON.stringify({ scenario_id: scenarioId }),
  });
  if (!res.ok) throw new Error(`Failed to approve action ${actionId}`);
  return res.json();
}

export async function rejectAction(incidentId: string, actionId: string, reason: string = 'Rejected by operator', tenant: string = 'storefront') {
  const res = await fetch(`/incidents/${incidentId}/actions/${actionId}/reject`, {
    method: 'POST',
    headers: { 'X-Tenant': tenant, 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason }),
  });
  if (!res.ok) throw new Error(`Failed to reject action ${actionId}`);
  return res.json();
}

export async function getGraphSubgraph(params: {
  nodes?: string[];
  service?: string;
  radius?: number;
  as_of?: number;
}, tenant: string = 'storefront'): Promise<SubgraphResponse> {
  const q = new URLSearchParams();
  if (params.nodes && params.nodes.length > 0) q.set('nodes', params.nodes.join(','));
  if (params.service) q.set('service', params.service);
  if (params.radius) q.set('radius', String(params.radius));
  if (params.as_of) q.set('as_of', String(params.as_of));

  const res = await fetch(`/graph/subgraph?${q.toString()}`, { headers: { 'X-Tenant': tenant } });
  if (!res.ok) throw new Error('Failed to fetch subgraph');
  const json = await res.json();
  return json.data || { nodes: [], edges: [] };
}

export async function getCounterfactual(
  observedIncidentId: string,
  hypotheticalService: string,
  asOf: string = 'incident_time',
  tenant: string = 'storefront'
): Promise<CounterfactualResponse> {
  const res = await fetch('/counterfactual', {
    method: 'POST',
    headers: { 'X-Tenant': tenant, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      observed_incident_id: observedIncidentId,
      hypothetical_service: hypotheticalService,
      as_of: asOf,
      compare_with_now: true,
    }),
  });
  if (!res.ok) throw new Error('Counterfactual analysis failed');
  const json = await res.json();
  return json.data;
}

export async function askBrain(question: string, mode: string = 'replay', tenant: string = 'storefront'): Promise<AskBrainResponse> {
  const res = await fetch('/ask', {
    method: 'POST',
    headers: { 'X-Tenant': tenant, 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, mode }),
  });
  if (!res.ok) throw new Error('Ask-the-Brain query failed');
  const json = await res.json();
  return json.data;
}

export async function getInspectStep(stepId: string, tenant: string = 'storefront'): Promise<any> {
  const res = await fetch(`/inspect/${stepId}`, { headers: { 'X-Tenant': tenant } });
  if (!res.ok) throw new Error(`Failed to inspect step ${stepId}`);
  const json = await res.json();
  return json.data;
}

export async function getInspectReplay(trace: any, tenant: string = 'storefront'): Promise<any> {
  const res = await fetch('/inspect/replay', {
    method: 'POST',
    headers: { 'X-Tenant': tenant, 'Content-Type': 'application/json' },
    body: JSON.stringify({ trace }),
  });
  if (!res.ok) throw new Error('Failed to generate why replay frames');
  return res.json();
}

export async function getBenchmarkReport(): Promise<BenchmarkReportResponse> {
  const res = await fetch('/benchmark/report');
  if (!res.ok) throw new Error('Failed to fetch benchmark report');
  return res.json();
}

export async function runBenchmark(scenarios?: string[], modes?: string[]): Promise<any> {
  const res = await fetch('/benchmark/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scenarios, modes, mode: 'replay' }),
  });
  if (!res.ok) throw new Error('Failed to run benchmark');
  return res.json();
}

export async function getMemoryStats(tenant: string = 'storefront'): Promise<any> {
  const res = await fetch('/memory/stats', { headers: { 'X-Tenant': tenant } });
  if (!res.ok) throw new Error('Failed to fetch memory stats');
  const json = await res.json();
  return json.data;
}

export async function checkHealth(): Promise<any> {
  const res = await fetch('/health');
  if (!res.ok) throw new Error('Health check failed');
  return res.json();
}
