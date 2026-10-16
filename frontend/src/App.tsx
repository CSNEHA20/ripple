import { useState, useEffect } from 'react'
import './App.css'
import { checkHealth, runSmokeTest } from './api'
import type { HealthResponse, SmokeResponse } from './api'

export default function App() {
  const [tenant, setTenant] = useState<string>('storefront')
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [healthLoading, setHealthLoading] = useState<boolean>(true)
  const [healthError, setHealthError] = useState<string | null>(null)

  const [smokeResult, setSmokeResult] = useState<SmokeResponse | null>(null)
  const [smokeLoading, setSmokeLoading] = useState<boolean>(false)
  const [smokeError, setSmokeError] = useState<string | null>(null)

  const fetchHealth = async () => {
    setHealthLoading(true)
    setHealthError(null)
    try {
      const data = await checkHealth()
      setHealth(data)
    } catch (err: any) {
      setHealthError(err.message || 'Failed to connect to backend')
    } finally {
      setHealthLoading(false)
    }
  }

  const handleSmokeTest = async () => {
    setSmokeLoading(true)
    setSmokeError(null)
    try {
      const data = await runSmokeTest(tenant)
      setSmokeResult(data)
    } catch (err: any) {
      setSmokeError(err.message || 'Smoke test failed')
    } finally {
      setSmokeLoading(false)
    }
  }

  useEffect(() => {
    fetchHealth()
    const interval = setInterval(fetchHealth, 10000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="ripple-app">
      {/* Header */}
      <header className="header">
        <div className="brand">
          <div className="logo-badge">R</div>
          <div className="title-group">
            <h1>Ripple</h1>
            <p>On-Call Autonomous Agent Crew with FalkorDB Brain</p>
          </div>
        </div>

        <div className="header-actions">
          <label htmlFor="tenant-select" style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
            Active Tenant:
          </label>
          <select
            id="tenant-select"
            className="tenant-select"
            value={tenant}
            onChange={(e) => setTenant(e.target.value)}
          >
            <option value="storefront">tenant_storefront (Prod)</option>
            <option value="payments">tenant_payments (Payments)</option>
            <option value="smoke">tenant_smoke (Test)</option>
            <option value="demo">tenant_demo (Demo)</option>
          </select>
        </div>
      </header>

      {/* Status Cards */}
      <div className="status-grid">
        {/* Backend Status */}
        <div className="status-card">
          <div className="status-card-header">
            <span className="status-card-title">Backend API</span>
            <span
              className={`status-badge ${
                healthLoading ? 'checking' : healthError ? 'error' : 'ok'
              }`}
            >
              ● {healthLoading ? 'Checking...' : healthError ? 'Error' : 'Healthy'}
            </span>
          </div>
          <div className="status-value">
            {health ? `${health.service} v${health.version}` : 'FastAPI'}
          </div>
          <div className="status-detail">
            Port 8000 · REST &amp; SSE Gateway
          </div>
        </div>

        {/* FalkorDB Status */}
        <div className="status-card">
          <div className="status-card-header">
            <span className="status-card-title">FalkorDB Engine</span>
            <span
              className={`status-badge ${
                health?.falkordb === 'connected' ? 'connected' : 'disconnected'
              }`}
            >
              ● {health?.falkordb === 'connected' ? 'Connected' : 'Offline'}
            </span>
          </div>
          <div className="status-value">FalkorDB Graph Engine</div>
          <div className="status-detail">
            Host: {health?.falkordb_host || 'falkordb'}:{health?.falkordb_port || 6379}
          </div>
        </div>

        {/* Multitenancy Boundary */}
        <div className="status-card">
          <div className="status-card-header">
            <span className="status-card-title">Tenant Isolation</span>
            <span className="status-badge connected">● Active</span>
          </div>
          <div className="status-value">tenant_{tenant}</div>
          <div className="status-detail">
            Strict TenantGraph boundary per org
          </div>
        </div>

        {/* Verification & Smoke */}
        <div className="status-card">
          <div className="status-card-header">
            <span className="status-card-title">M0 Status</span>
            <span className="status-badge connected">● Ready</span>
          </div>
          <div className="status-value">Docker Compose Slice</div>
          <div className="status-detail">
            FalkorDB + Backend + Frontend
          </div>
        </div>
      </div>

      {/* Interactive Smoke Test Section */}
      <section className="interactive-section">
        <div className="section-head">
          <div>
            <h2>Graph Connection &amp; Smoke Test</h2>
            <p style={{ color: 'var(--text-muted)', fontSize: '13px', margin: '4px 0 0 0' }}>
              Connects to FalkorDB via <code>TenantGraph("{tenant}")</code>, creates test nodes and dependencies, and verifies Cypher query execution.
            </p>
          </div>
          <button
            id="run-smoke-test-btn"
            className="btn-primary"
            onClick={handleSmokeTest}
            disabled={smokeLoading}
          >
            {smokeLoading ? 'Running Cypher...' : 'Run Smoke Test'}
          </button>
        </div>

        {smokeError && (
          <div style={{ color: 'var(--accent-rose)', fontSize: '13px', marginTop: '12px' }}>
            ⚠️ {smokeError}
          </div>
        )}

        {smokeResult && (
          <div className="result-box">
            <div style={{ color: 'var(--accent-emerald)', fontWeight: 600, marginBottom: '8px' }}>
              ✓ {smokeResult.message}
            </div>
            <div>
              <strong>Tenant Graph:</strong> tenant_{smokeResult.tenant}
            </div>
            <div style={{ marginTop: '8px' }}>
              <strong>Verified Relationships:</strong>
              <pre style={{ margin: '4px 0', color: 'var(--accent-cyan)' }}>
                {JSON.stringify(smokeResult.verified, null, 2)}
              </pre>
            </div>
          </div>
        )}

        {/* Quick Links */}
        <div className="quick-links">
          <a
            href="http://localhost:3000"
            target="_blank"
            rel="noreferrer"
            className="btn-secondary"
          >
            🧭 FalkorDB Browser (Port 3000)
          </a>
          <a
            href="http://localhost:8000/docs"
            target="_blank"
            rel="noreferrer"
            className="btn-secondary"
          >
            📖 FastAPI Swagger Docs (Port 8000/docs)
          </a>
          <a
            href="http://localhost:8000/health"
            target="_blank"
            rel="noreferrer"
            className="btn-secondary"
          >
            🩺 Health Endpoint (JSON)
          </a>
        </div>
      </section>

      {/* Implementation Roadmap */}
      <section className="roadmap-section">
        <h2 style={{ fontSize: '18px', margin: 0 }}>Ripple Implementation Roadmap</h2>
        <div className="roadmap-grid">
          <div className="roadmap-card active">
            <div className="roadmap-title">
              <span>M0: Setup &amp; Smoke Test</span>
              <span style={{ color: 'var(--accent-emerald)' }}>✓</span>
            </div>
            <div className="roadmap-desc">FalkorDB, backend, frontend, docker-compose, /health</div>
          </div>
          <div className="roadmap-card">
            <div className="roadmap-title">
              <span>M1: Schema &amp; Tenancy</span>
              <span>Next</span>
            </div>
            <div className="roadmap-desc">TenantGraph, temporal edges, indexes, isolation</div>
          </div>
          <div className="roadmap-card">
            <div className="roadmap-title">
              <span>M2: Data Ingestion</span>
              <span>Pending</span>
            </div>
            <div className="roadmap-desc">Real repo services, GitHub PRs, docs, decisions</div>
          </div>
          <div className="roadmap-card">
            <div className="roadmap-title">
              <span>M3: Scenario Simulator</span>
              <span>Pending</span>
            </div>
            <div className="roadmap-desc">Alert generation, metric snapshots, interventions</div>
          </div>
          <div className="roadmap-card">
            <div className="roadmap-title">
              <span>M4: Graph Tools</span>
              <span>Pending</span>
            </div>
            <div className="roadmap-desc">Blast radius, root cause, who knows, PageRank</div>
          </div>
          <div className="roadmap-card">
            <div className="roadmap-title">
              <span>M5: Hypothesis Engine</span>
              <span>Pending</span>
            </div>
            <div className="roadmap-desc">Supporting &amp; contradicting evidence ranking</div>
          </div>
          <div className="roadmap-card">
            <div className="roadmap-title">
              <span>M6: Outcome Memory</span>
              <span>Pending</span>
            </div>
            <div className="roadmap-desc">Episodic &amp; procedural memory, applicability gate</div>
          </div>
          <div className="roadmap-card">
            <div className="roadmap-title">
              <span>M7: Agent Crew</span>
              <span>Pending</span>
            </div>
            <div className="roadmap-desc">Triage, Investigator, Responder, Blackboard</div>
          </div>
        </div>
      </section>
    </div>
  )
}
