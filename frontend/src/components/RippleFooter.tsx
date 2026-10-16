import React, { useState } from 'react';
import { ArrowRight, X, ShieldCheck, CheckCircle2, AlertCircle } from 'lucide-react';
import type { ViewId } from './Sidebar';
import './RippleFooter.css';

interface RippleFooterProps {
  activeTab?: ViewId;
  onChangeTab?: (tab: ViewId) => void;
  onOpenAskBrain?: () => void;
  healthOk?: boolean;
}

type ModalType = 'privacy' | 'terms' | 'security' | 'contact' | 'status' | null;

/* ==========================================================================
   Ripple Wave Brand Logo (Matching reference circular badge with 4 waves)
   ========================================================================== */
const RippleWaveLogo: React.FC<{ size?: number }> = ({ size = 44 }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 48 48"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className="rf-logo-svg"
    aria-hidden="true"
  >
    <defs>
      <linearGradient id="rf-logo-grad" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stopColor="#FF642D" />
        <stop offset="100%" stopColor="#FF3B20" />
      </linearGradient>
    </defs>
    <circle cx="24" cy="24" r="23" fill="url(#rf-logo-grad)" />
    {/* 4 dark organic wave ripples */}
    <path
      d="M11 16C16 13.5 21 18.5 27 16C31.5 14 34.5 16.5 37 16"
      stroke="#100E0C"
      strokeWidth="2.8"
      strokeLinecap="round"
    />
    <path
      d="M8 23C14.5 19 20.5 27 28 23C33.5 20 37 24.5 40 23"
      stroke="#100E0C"
      strokeWidth="2.8"
      strokeLinecap="round"
    />
    <path
      d="M9 30C15 26 21 34 29 30C34 27.5 37 31.5 39 30"
      stroke="#100E0C"
      strokeWidth="2.8"
      strokeLinecap="round"
    />
    <path
      d="M14 37C19.5 34 25 39.5 31 37C33.5 35.5 35 37 36 37"
      stroke="#100E0C"
      strokeWidth="2.8"
      strokeLinecap="round"
    />
  </svg>
);

/* ==========================================================================
   Social Icons matching reference (X, LinkedIn, GitHub, YouTube)
   ========================================================================== */
const XIcon: React.FC = () => (
  <svg viewBox="0 0 24 24" width="15" height="15" fill="currentColor" aria-hidden="true">
    <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
  </svg>
);

const LinkedInIcon: React.FC = () => (
  <svg viewBox="0 0 24 24" width="15" height="15" fill="currentColor" aria-hidden="true">
    <path d="M19 3a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h14m-.5 15.5v-5.3a3.26 3.26 0 0 0-3.26-3.26c-.85 0-1.84.52-2.28 1.3v-1.11h-2.79v8.37h2.79v-4.93c0-.77.62-1.4 1.39-1.4a1.4 1.4 0 0 1 1.4 1.4v4.93h2.75M6.88 8.56a1.68 1.68 0 0 0 1.68-1.68c0-.93-.75-1.69-1.68-1.69a1.69 1.69 0 0 0-1.69 1.69c0 .93.76 1.68 1.69 1.68m1.39 9.94v-8.37H5.5v8.37h2.77z" />
  </svg>
);

const GitHubIcon: React.FC = () => (
  <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true">
    <path
      fillRule="evenodd"
      clipRule="evenodd"
      d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"
    />
  </svg>
);

const YouTubeIcon: React.FC = () => (
  <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true">
    <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z" />
  </svg>
);

/* ==========================================================================
   Main Ripple Footer Component
   ========================================================================== */
export const RippleFooter: React.FC<RippleFooterProps> = ({
  onChangeTab,
  healthOk = true,
}) => {
  const [activeModal, setActiveModal] = useState<ModalType>(null);
  const currentYear = new Date().getFullYear();

  const handleNavigate = (tab: ViewId) => {
    if (onChangeTab) {
      onChangeTab(tab);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
  };

  return (
    <footer className="rf-footer-root" role="contentinfo" aria-label="Site Footer">
      {/* Restrained Film Grain Texture */}
      <svg className="rf-grain-overlay" aria-hidden="true">
        <filter id="rf-global-grain">
          <feTurbulence type="fractalNoise" baseFrequency="0.75" numOctaves="3" stitchTiles="stitch" />
          <feColorMatrix type="matrix" values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 0.15 0" />
        </filter>
        <rect width="100%" height="100%" filter="url(#rf-global-grain)" />
      </svg>

      <div className="rf-container">
        {/* ==================================================================
            A. Upper Content Area: 3 Columns
            ================================================================== */}
        <div className="rf-upper-grid">
          {/* Column 1 — Brand Identity */}
          <div className="rf-col-brand">
            <div className="rf-brand-header">
              <div className="rf-brand-logo-mark" title="Ripple">
                <RippleWaveLogo size={42} />
              </div>
              <span className="rf-brand-wordmark">Ripple</span>
            </div>

            <p className="rf-copyright">
              © {currentYear} Ripple. All rights reserved.
            </p>

            <div className="rf-social-row" aria-label="Social media links">
              <a
                href="https://x.com"
                target="_blank"
                rel="noopener noreferrer"
                className="rf-social-btn"
                aria-label="Ripple on X"
                title="Follow Ripple on X"
              >
                <XIcon />
              </a>
              <a
                href="https://linkedin.com"
                target="_blank"
                rel="noopener noreferrer"
                className="rf-social-btn"
                aria-label="Ripple on LinkedIn"
                title="Connect on LinkedIn"
              >
                <LinkedInIcon />
              </a>
              <a
                href="https://github.com/Vishallakshmikanthan/ripple"
                target="_blank"
                rel="noopener noreferrer"
                className="rf-social-btn"
                aria-label="Ripple GitHub Repository"
                title="View GitHub Repository"
              >
                <GitHubIcon />
              </a>
              <a
                href="https://youtube.com"
                target="_blank"
                rel="noopener noreferrer"
                className="rf-social-btn"
                aria-label="Ripple on YouTube"
                title="Watch Ripple Demos on YouTube"
              >
                <YouTubeIcon />
              </a>
            </div>

            <div className="rf-brand-tagline-block">
              <div className="rf-tagline-lead">Graph-native reliability intelligence.</div>
              <div className="rf-tagline-sub">Built for explainable incident response.</div>
            </div>
          </div>

          {/* Column 2 — Platform */}
          <div className="rf-col-nav">
            <div className="rf-nav-header">
              <span className="rf-col-idx">01</span>
              <span className="rf-col-title">PLATFORM</span>
            </div>
            <nav aria-label="Platform navigation">
              <ul className="rf-nav-list">
                <li>
                  <button
                    type="button"
                    className="rf-nav-link"
                    onClick={() => handleNavigate('incident')}
                  >
                    <span>Incident Investigation</span>
                    <ArrowRight size={15} className="rf-nav-arrow" />
                  </button>
                </li>
                <li>
                  <button
                    type="button"
                    className="rf-nav-link"
                    onClick={() => handleNavigate('counterfactual')}
                  >
                    <span>Counterfactuals</span>
                    <ArrowRight size={15} className="rf-nav-arrow" />
                  </button>
                </li>
                <li>
                  <button
                    type="button"
                    className="rf-nav-link"
                    onClick={() => handleNavigate('memory')}
                  >
                    <span>Graph Memory</span>
                    <ArrowRight size={15} className="rf-nav-arrow" />
                  </button>
                </li>
                <li>
                  <button
                    type="button"
                    className="rf-nav-link"
                    onClick={() => handleNavigate('benchmark')}
                  >
                    <span>Benchmark & Calibration</span>
                    <ArrowRight size={15} className="rf-nav-arrow" />
                  </button>
                </li>
              </ul>
            </nav>
          </div>

          {/* Column 3 — Resources */}
          <div className="rf-col-nav">
            <div className="rf-nav-header">
              <span className="rf-col-idx">02</span>
              <span className="rf-col-title">RESOURCES</span>
            </div>
            <nav aria-label="Resources navigation">
              <ul className="rf-nav-list">
                <li>
                  <button
                    type="button"
                    className="rf-nav-link"
                    onClick={() => handleNavigate('docs')}
                  >
                    <span>Documentation</span>
                    <ArrowRight size={15} className="rf-nav-arrow" />
                  </button>
                </li>
                <li>
                  <a
                    href="http://localhost:8000/docs"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="rf-nav-link"
                    title="Open FastAPI Swagger Documentation"
                  >
                    <span>API Reference</span>
                    <ArrowRight size={15} className="rf-nav-arrow" />
                  </a>
                </li>
                <li>
                  <button
                    type="button"
                    className="rf-nav-link"
                    onClick={() => setActiveModal('security')}
                  >
                    <span>Security</span>
                    <ArrowRight size={15} className="rf-nav-arrow" />
                  </button>
                </li>
                <li>
                  <button
                    type="button"
                    className="rf-nav-link"
                    onClick={() => setActiveModal('contact')}
                  >
                    <span>Contact</span>
                    <ArrowRight size={15} className="rf-nav-arrow" />
                  </button>
                </li>
              </ul>
            </nav>
          </div>
        </div>

        {/* ==================================================================
            B & C. Giant Wordmark with Animated Light Beam
            ================================================================== */}
        <div className="rf-wordmark-section" aria-label="Ripple wordmark graphic">
          {/* Ambient Warm Glow */}
          <div className="rf-beam-glow" aria-hidden="true" />

          {/* Sweeping Diagonal Light Beam */}
          <div className="rf-beam-streak" aria-hidden="true" />

          {/* Giant SVG Typography */}
          <svg
            className="rf-giant-svg"
            viewBox="0 0 1600 340"
            preserveAspectRatio="xMidYMid meet"
            xmlns="http://www.w3.org/2000/svg"
            aria-hidden="true"
          >
            <defs>
              {/* Deep charcoal bronze base letter fill */}
              <linearGradient id="rf-letter-base" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#221A14" />
                <stop offset="35%" stopColor="#38261C" />
                <stop offset="50%" stopColor="#4A2F22" />
                <stop offset="75%" stopColor="#301F17" />
                <stop offset="100%" stopColor="#1A120D" />
              </linearGradient>

              {/* Diagonal Light Beam intersecting letter contours */}
              <linearGradient id="rf-beam-gradient" x1="15%" y1="90%" x2="85%" y2="10%">
                <stop offset="0%" stopColor="#2A1B14" />
                <stop offset="26%" stopColor="#48271A" />
                <stop offset="40%" stopColor="#D94B1B" />
                <stop offset="49%" stopColor="#FF642D" />
                <stop offset="53%" stopColor="#FFAA75" />
                <stop offset="57%" stopColor="#FF3B20" />
                <stop offset="70%" stopColor="#8C2B14" />
                <stop offset="85%" stopColor="#331A12" />
                <stop offset="100%" stopColor="#1C110C" />
              </linearGradient>

              {/* Specular Letter Highlight */}
              <linearGradient id="rf-beam-highlight" x1="22%" y1="78%" x2="78%" y2="22%">
                <stop offset="0%" stopColor="transparent" />
                <stop offset="47%" stopColor="transparent" />
                <stop offset="51%" stopColor="#FFE4CE" stopOpacity="0.8" />
                <stop offset="54%" stopColor="#FF642D" stopOpacity="0.6" />
                <stop offset="59%" stopColor="transparent" />
                <stop offset="100%" stopColor="transparent" />
              </linearGradient>

              {/* Bottom fade mask */}
              <linearGradient id="rf-fade-mask-grad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#ffffff" stopOpacity="1" />
                <stop offset="60%" stopColor="#ffffff" stopOpacity="0.92" />
                <stop offset="84%" stopColor="#ffffff" stopOpacity="0.35" />
                <stop offset="100%" stopColor="#ffffff" stopOpacity="0" />
              </linearGradient>

              <mask id="rf-wordmark-mask">
                <rect x="0" y="0" width="1600" height="340" fill="url(#rf-fade-mask-grad)" />
              </mask>
            </defs>

            {/* Giant RIPPLE Letterforms */}
            <g mask="url(#rf-wordmark-mask)">
              {/* Layer 1: Base Dark Bronze Charcoal Letters */}
              <text
                x="50%"
                y="77%"
                textAnchor="middle"
                fill="url(#rf-letter-base)"
                fontSize="310"
                fontWeight="900"
                letterSpacing="-0.045em"
                fontFamily="var(--font-sans), 'Geist Variable', 'Inter', -apple-system, sans-serif"
              >
                RIPPLE
              </text>

              {/* Layer 2: Illuminated Diagonal Light Beam Overlay */}
              <text
                x="50%"
                y="77%"
                textAnchor="middle"
                fill="url(#rf-beam-gradient)"
                fontSize="310"
                fontWeight="900"
                letterSpacing="-0.045em"
                fontFamily="var(--font-sans), 'Geist Variable', 'Inter', -apple-system, sans-serif"
                opacity="0.96"
              >
                RIPPLE
              </text>

              {/* Layer 3: Brilliant Specular Streak */}
              <text
                x="50%"
                y="77%"
                textAnchor="middle"
                fill="url(#rf-beam-highlight)"
                fontSize="310"
                fontWeight="900"
                letterSpacing="-0.045em"
                fontFamily="var(--font-sans), 'Geist Variable', 'Inter', -apple-system, sans-serif"
                opacity="0.75"
              >
                RIPPLE
              </text>
            </g>
          </svg>

          {/* Fade to Footer Floor */}
          <div className="rf-bottom-fade" aria-hidden="true" />
        </div>

        {/* ==================================================================
            D. Bottom Legal Bar
            ================================================================== */}
        <div className="rf-legal-bar">
          <div className="rf-legal-links">
            <button
              type="button"
              className="rf-legal-link-btn"
              onClick={() => setActiveModal('privacy')}
            >
              Privacy
            </button>
            <span className="rf-legal-dot">•</span>
            <button
              type="button"
              className="rf-legal-link-btn"
              onClick={() => setActiveModal('terms')}
            >
              Terms
            </button>
            <span className="rf-legal-dot">•</span>
            <button
              type="button"
              className="rf-legal-link-btn"
              onClick={() => setActiveModal('status')}
            >
              Status
            </button>
          </div>

          <div className="rf-tagline-quote">
            <span className="rf-tagline-dash" />
            <span>From graph to resolution.</span>
          </div>
        </div>
      </div>

      {/* ==================================================================
          Modals for Legal, Security, Status & Contact
          ================================================================== */}
      {activeModal && (
        <div
          className="rf-modal-backdrop"
          onClick={() => setActiveModal(null)}
          role="dialog"
          aria-modal="true"
        >
          <div
            className="rf-modal-card"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="rf-modal-header">
              <h3 className="rf-modal-title">
                {activeModal === 'privacy' && 'Privacy Commitment'}
                {activeModal === 'terms' && 'Terms of Evaluation'}
                {activeModal === 'security' && (
                  <>
                    <ShieldCheck size={20} color="#FF642D" />
                    <span>Security Architecture</span>
                  </>
                )}
                {activeModal === 'status' && 'System Health & Engine Status'}
                {activeModal === 'contact' && 'Contact & Community'}
              </h3>
              <button
                type="button"
                className="rf-modal-close-btn"
                onClick={() => setActiveModal(null)}
                aria-label="Close dialog"
              >
                <X size={16} />
              </button>
            </div>

            <div className="rf-modal-body">
              {activeModal === 'privacy' && (
                <>
                  <p>
                    <strong>Tenant Data Isolation:</strong> Ripple operates with strictly isolated FalkorDB graph namespaces (e.g. <code>tenant_storefront</code>, <code>tenant_payments</code>). No cross-tenant topology or incident evidence is ever co-mingled.
                  </p>
                  <p>
                    <strong>Local & On-Premises Execution:</strong> When configured in local LLM mode, prompt telemetry and graph topology remain entirely within your private network perimeter. No external logging or model training is conducted on customer diagnostic traces.
                  </p>
                  <div className="rf-modal-feature-box">
                    <div className="rf-modal-feature-item">
                      <span className="rf-modal-feature-bullet">✓</span>
                      <span>Zero telemetry leaks to third-party providers in local mode.</span>
                    </div>
                    <div className="rf-modal-feature-item">
                      <span className="rf-modal-feature-bullet">✓</span>
                      <span>Cryptographic provenance on all Cypher graph queries and trace steps.</span>
                    </div>
                  </div>
                </>
              )}

              {activeModal === 'terms' && (
                <>
                  <p>
                    Ripple is an open-source autonomous reliability intelligence platform distributed under the <strong>MIT License</strong>.
                  </p>
                  <p>
                    Evaluated for automated triage, hypothesis ranking, and human-in-the-loop operational response. Automated actions are strictly bound by approval gates before executing disruptive runtime commands.
                  </p>
                  <div className="rf-modal-feature-box">
                    <div className="rf-modal-feature-item">
                      <span className="rf-modal-feature-bullet">✓</span>
                      <span>Free for academic, evaluation, and commercial integration.</span>
                    </div>
                    <div className="rf-modal-feature-item">
                      <span className="rf-modal-feature-bullet">✓</span>
                      <span>Pre-registered evaluation scenarios for verifiable benchmark reproducibility.</span>
                    </div>
                  </div>
                </>
              )}

              {activeModal === 'security' && (
                <>
                  <p>
                    Ripple enforces defense-in-depth across the agent execution lifecycle:
                  </p>
                  <div className="rf-modal-feature-box">
                    <div className="rf-modal-feature-item">
                      <span className="rf-modal-feature-bullet">🛡️</span>
                      <span><strong>Parameterized Cypher Queries:</strong> All FalkorDB interactions use structured parameter bindings to prevent Cypher injection vulnerabilities.</span>
                    </div>
                    <div className="rf-modal-feature-item">
                      <span className="rf-modal-feature-bullet">🛡️</span>
                      <span><strong>Human-in-the-Loop Approval Gates:</strong> Remediations rated with blast radius &gt; 0 require explicit engineer authorization before execution.</span>
                    </div>
                    <div className="rf-modal-feature-item">
                      <span className="rf-modal-feature-bullet">🛡️</span>
                      <span><strong>Audited Provenance Traces:</strong> Every agent conclusion references specific graph node IDs and Cypher queries displayed in the Inspector Drawer.</span>
                    </div>
                  </div>
                </>
              )}

              {activeModal === 'status' && (
                <>
                  <div className="rf-modal-feature-box">
                    <div className="rf-modal-feature-item">
                      {healthOk ? (
                        <CheckCircle2 size={18} color="#10b981" />
                      ) : (
                        <AlertCircle size={18} color="#ef4444" />
                      )}
                      <span>
                        <strong>FalkorDB Graph Engine:</strong>{' '}
                        {healthOk ? 'Connected & Healthy (Port 6379)' : 'Reconnecting...'}
                      </span>
                    </div>
                    <div className="rf-modal-feature-item">
                      <CheckCircle2 size={18} color="#10b981" />
                      <span><strong>FastAPI Backend Gateway:</strong> Active (Port 8000)</span>
                    </div>
                    <div className="rf-modal-feature-item">
                      <CheckCircle2 size={18} color="#10b981" />
                      <span><strong>SSE Event Bus:</strong> Resilient disk-backed logging active</span>
                    </div>
                  </div>
                  <p>
                    Live health endpoint: <a href="http://localhost:8000/health" target="_blank" rel="noopener noreferrer" style={{ color: '#FF642D' }}>http://localhost:8000/health</a>
                  </p>
                </>
              )}

              {activeModal === 'contact' && (
                <>
                  <p>
                    Have questions or feedback on Ripple? Connect with the core team:
                  </p>
                  <div className="rf-modal-feature-box">
                    <div className="rf-modal-feature-item">
                      <span className="rf-modal-feature-bullet">📦</span>
                      <span>
                        <strong>GitHub Repository:</strong>{' '}
                        <a
                          href="https://github.com/Vishallakshmikanthan/ripple"
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{ color: '#FF642D', textDecoration: 'underline' }}
                        >
                          github.com/Vishallakshmikanthan/ripple
                        </a>
                      </span>
                    </div>
                    <div className="rf-modal-feature-item">
                      <span className="rf-modal-feature-bullet">💬</span>
                      <span>
                        <strong>Issue Tracker:</strong> Submit bug reports or feature requests via GitHub Issues.
                      </span>
                    </div>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </footer>
  );
};
