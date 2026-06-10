/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useEffect, useRef } from 'react';
import ReactDOM from 'react-dom/client';

import { INITIAL_PLACEHOLDERS } from './constants';
import { useSession } from './hooks/useSession';
import { useApi } from './hooks/useApi';
import { usePersistence, restoreSavedSession } from './hooks/usePersistence';
import { useNotification } from './hooks/useNotification';

import DottedGlowBackground from './components/DottedGlowBackground';
import ComputationOverlay from './components/ComputationOverlay';
import ErrorBoundary from './components/ErrorBoundary';
import { OfflineNotice, EmptyState } from './components/StatusStates';

import {
  ArrowUpIcon,
  PlusIcon,
  SparklesIcon,
  ThinkingIcon,
  HistoryIcon,
  PaperclipIcon,
  FocusIcon,
  UserIcon,
  SettingsIcon,
  MenuIcon,
  CloseIcon,
} from './components/Icons';

function App() {
  const {
    step, setStep,
    session, setSession,
    isLoading, setIsLoading,
    researchMessage, setResearchMessage,
    showReport, setShowReport,
    isSidebarOpen, setIsSidebarOpen,
    isSidebarCollapsed, setIsSidebarCollapsed,
    inputValue, setInputValue,
    contradictionConfidence,
    verdictSources,
    receiptItems,
  } = useSession();

  const { addNotification, NotificationBar } = useNotification();

  const { sessionError, dismissSessionError } = usePersistence({
    step,
    session,
    showReport,
    isSidebarCollapsed,
  });

  const api = useApi({
    getters: { step, session, inputValue, isLoading },
    setters: { setStep, setSession, setIsLoading, setResearchMessage, setInputValue },
    addNotification,
  });

  const inputRef = useRef<HTMLTextAreaElement>(null);
  const bottomInputRef = useRef<HTMLTextAreaElement>(null);

  // --- Restore saved session from localStorage on mount ---
  useEffect(() => {
    const saved = restoreSavedSession();
    if (saved && saved.session) {
      setStep(saved.step);
      setSession(saved.session);
      if (saved.showReport !== undefined) setShowReport(saved.showReport);
      if (saved.isSidebarCollapsed !== undefined)
        setIsSidebarCollapsed(saved.isSidebarCollapsed);
    }
    // Only run on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // --- Auto-focus inputs based on step ---
  useEffect(() => {
    if (step === 'idle') {
      inputRef.current?.focus();
    } else if (step === 'interrogating') {
      bottomInputRef.current?.focus();
    }
  }, [step]);

  // AGENT 3 UI NOTE: Add a useEffect with document-level keydown listener for Escape.
  // When isSidebarOpen === true and window.innerWidth <= 1024, call setIsSidebarOpen(false).
  // Optionally toggle .sidebar-escape-active on .app-shell when sidebar is open on mobile.
  const toggleSidebar = () => setIsSidebarOpen(!isSidebarOpen);
  const closeSidebarOnMobile = () => {
    if (window.innerWidth <= 1024) {
      setIsSidebarOpen(false);
    }
  };

  const handleNavAction = (action: () => void) => {
    action();
    closeSidebarOnMobile();
  };

  // --- Sidebar nav items configuration ---
  interface NavEntry {
    icon: React.ReactNode;
    label: string;
    title: string;
    comingSoon?: boolean;
    onClick?: () => void;
    active?: boolean;
  }

  const navItems: NavEntry[] = [
    {
      icon: <PlusIcon />,
      label: 'New Analysis',
      title: 'Start a new decision analysis',
      onClick: () => handleNavAction(api.reset),
      active: step === 'idle',
    },
    {
      icon: <ThinkingIcon />,
      label: 'Current Session',
      title: 'Coming soon — view current session summary',
      comingSoon: true,
      onClick: closeSidebarOnMobile,
    },
    {
      icon: <HistoryIcon />,
      label: 'Past Decisions',
      title: 'Coming soon — browse your decision history',
      comingSoon: true,
      onClick: closeSidebarOnMobile,
    },
    {
      icon: <PaperclipIcon />,
      label: 'Proof / Insights',
      title: 'Coming soon — explore proof and insights',
      comingSoon: true,
      onClick: closeSidebarOnMobile,
    },
  ];

  const footerNavItems: NavEntry[] = [
    {
      icon: <SettingsIcon />,
      label: 'Settings',
      title: 'Coming soon — configure preferences',
      comingSoon: true,
      onClick: closeSidebarOnMobile,
    },
  ];

  return (
    <div className={`app-shell ${isSidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
      <NotificationBar />

      {/* Session Expired Banner */}
      {sessionError && (
        <div
          role="alert"
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            zIndex: 10001,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 16,
            padding: '12px 24px',
            background: '#1a0505',
            borderBottom: '1px solid #ff2a2a',
            color: '#ff6b6b',
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: '0.8rem',
            fontWeight: 600,
          }}
        >
          <span>{sessionError}</span>
          <button
            onClick={() => {
              dismissSessionError();
              api.reset();
            }}
            style={{
              background: 'transparent',
              border: '1px solid rgba(255,255,255,0.2)',
              color: '#fff',
              padding: '6px 14px',
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: '0.75rem',
              fontWeight: 600,
              textTransform: 'uppercase',
              cursor: 'pointer',
            }}
          >
            Start New Session
          </button>
        </div>
      )}

      <div
        className={`sidebar-overlay ${isSidebarOpen ? 'visible' : ''}`}
        onClick={toggleSidebar}
      />

      <div className="floating-profile-icon" title="Profile">
        <UserIcon />
      </div>

      <aside
        className={`sidebar ${isSidebarOpen ? 'open' : ''} ${isSidebarCollapsed ? 'collapsed' : ''}`}
        onClick={() => {
          if (isSidebarCollapsed) {
            setIsSidebarCollapsed(false);
          }
        }}
      >
        <div className="sidebar-header-row">
          <div
            className="sidebar-logo"
            onClick={(e) => {
              e.stopPropagation();
              api.reset();
            }}
          >
            <img
              src="/2.png"
              alt="whyLayer Logo"
              style={{ width: 32, height: 32, objectFit: 'contain' }}
            />
            {!isSidebarCollapsed && <span>whyLayer</span>}
          </div>
          <button className="mobile-close-btn" onClick={toggleSidebar}>
            <CloseIcon />
          </button>
        </div>

        {!isSidebarCollapsed && <div className="nav-section-label">Sessions</div>}
        <nav className="sidebar-nav">
          {navItems.map((item) => (
            <div
              key={item.label}
              className={`nav-item ${item.active ? 'active' : ''}`}
              title={item.title}
              onClick={item.onClick}
            >
              {item.icon}
              {!isSidebarCollapsed && <span>{item.label}</span>}
            </div>
          ))}
        </nav>

        <div className="sidebar-footer">
          {footerNavItems.map((item) => (
            <div
              key={item.label}
              className="nav-item"
              title={item.title}
              onClick={item.onClick}
            >
              {item.icon}
              {!isSidebarCollapsed && <span>{item.label}</span>}
            </div>
          ))}

          <button
            className="collapse-toggle-btn"
            onClick={(e) => {
              e.stopPropagation();
              setIsSidebarCollapsed(!isSidebarCollapsed);
            }}
            title={isSidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            style={{ marginTop: '16px', alignSelf: 'center', width: '100%' }}
          >
            {isSidebarCollapsed ? '>>' : '<<'}
          </button>
        </div>
      </aside>

      <main className="main-content">
        <OfflineNotice />
        <button
          className="mobile-menu-btn"
          onClick={toggleSidebar}
          aria-label="Toggle Sidebar Menu"
          aria-expanded={isSidebarOpen}
        >
          <MenuIcon />
        </button>

        <DottedGlowBackground
          gap={30}
          radius={0.5}
          color="rgba(255,255,255,0.06)"
          speedScale={0.12}
        />

        {/* Research / Computation Overlay */}
        {step === 'researching' && (
          <>
            <ComputationOverlay />
            <div className="computation-label">
              <div className="clinical-cursor" />
              <div className="clinical-status-text">{researchMessage}</div>
            </div>
          </>
        )}

        {/* Home / Idle View */}
        {step === 'idle' && !session && (
          <div className="home-view">
            <h1 className="animate-hero">YOU DON&rsquo;T NEED ADVICE. YOU NEED THE TRUTH</h1>
            <div className="search-wrapper animate-search">
              <textarea
                ref={inputRef}
                placeholder="Describe your decision..."
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    api.handleStartDecision();
                  }
                }}
              />
              <div className="search-actions">
                <div className="action-buttons">
                  <button className="action-btn" type="button">
                    <FocusIcon /> Deep Scan
                  </button>
                  <button className="action-btn" type="button">
                    <PaperclipIcon /> Context
                  </button>
                </div>
                <button
                  className="submit-btn"
                  onClick={() => api.handleStartDecision()}
                  disabled={!inputValue.trim() || isLoading}
                  aria-label={isLoading ? 'Starting deep scan...' : 'Start Deep Scan'}
                  aria-busy={isLoading}
                >
                  {isLoading ? <ThinkingIcon className="spin-icon" /> : <ArrowUpIcon />}
                </button>
              </div>
            </div>

            <p className="hero-subtext animate-chips">You will be questioned. Not guided.</p>

            <div className="suggested-chips animate-chips">
              {INITIAL_PLACEHOLDERS.slice(0, 3).map((p, i) => (
                <button key={i} className="chip" onClick={() => api.handleStartDecision(p)}>
                  {p}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Error state — fallback for when session is null but step !== 'idle' */}
        {step !== 'idle' && !session && step !== 'researching' && (
          <EmptyState
            title="Session not found"
            description="Something went wrong and your session data was lost."
            icon="⚠️"
            action={{ label: 'Start New Analysis', onClick: api.reset }}
          />
        )}

        {/* Session View */}
        {session && (
          <div className="session-view">
            <div className="chat-msg">
              <div className="msg-header">Primary Inquiry</div>
              <div className="msg-query">{session.originalPrompt}</div>
            </div>

            {step !== 'verdict' && (
              <div className="chat-msg">
                <div className="msg-header">Contradiction Confidence</div>
                <div className="clinical-meter">
                  <div className="clinical-meter-bar">
                    <div
                      className="clinical-meter-fill"
                      style={{ width: `${Math.max(4, contradictionConfidence)}%` }}
                    />
                  </div>
                  <div className="clinical-meter-meta">
                    <span>Exposure rising</span>
                    <span>{contradictionConfidence}%</span>
                  </div>
                </div>
              </div>
            )}

            {step === 'interrogating' && session.currentInsight && (
              <div className="chat-msg insight-msg fadeIn">
                <div className="msg-header" style={{ color: 'var(--color-primary)' }}>
                  {session.currentInsight.label || 'WHAT I SEE SO FAR'}
                </div>
                <div
                  className="interrogation-card"
                  style={{
                    borderColor: 'var(--color-primary)',
                    background: 'rgba(255, 62, 62, 0.05)',
                  }}
                >
                  <div
                    className="question-text"
                    style={{
                      fontStyle: 'italic',
                      fontWeight: 600,
                      color: 'var(--color-primary)',
                    }}
                  >
                    &ldquo;{session.currentInsight.text}&rdquo;
                  </div>
                </div>
              </div>
            )}

            {step === 'interrogating' && session.currentQuestion && (
              <div className="chat-msg">
                <div className="msg-header">
                  {session.phase === 'initial'
                    ? `Foundational Analysis — Question ${session.initialQuestionIndex + 1} of 3`
                    : `Deep Dive — Follow-up ${session.history.length - 3 + 1}`}
                </div>
                <div className={`interrogation-card ${isLoading ? 'loading' : ''}`}>
                  <div className="question-progress">
                    {session.phase === 'initial' ? (
                      <>
                        {[0, 1, 2].map((i) => (
                          <div
                            key={i}
                            className={`progress-dot ${i < session.initialQuestionIndex ? 'completed' : i === session.initialQuestionIndex ? 'active' : ''}`}
                          />
                        ))}
                      </>
                    ) : (
                      <>
                        <div className="progress-dot completed" />
                        <div className="progress-dot completed" />
                        <div className="progress-dot completed" />
                        {session.history.slice(3).map((_, i) => (
                          <div key={i} className="progress-dot completed" />
                        ))}
                        <div className="progress-dot active" />
                      </>
                    )}
                  </div>
                  <div className="question-text">{session.currentQuestion.text}</div>
                  <div className="clinical-warning-subtext">
                    {session.phase === 'initial'
                      ? 'ANSWER CONCISELY.'
                      : 'TRUTH IS THE ONLY PATH TO CLARITY.'}
                  </div>
                </div>
              </div>
            )}

            {step === 'verdict' && session.verdict && (
              <>
                <div className="chat-msg">
                  <div className="msg-header">Final Synthesis</div>
                  <div className="primary-verdict locked">
                    <div
                      className={`verdict-badge ${session.verdict.status === 'GO' ? 'yes' : 'no'}`}
                    >
                      {session.verdict.status === 'GO' ? 'YES' : 'NO'}
                    </div>
                    <p className="verdict-summary">{session.verdict.summary}</p>

                    <div className="verdict-stats">
                      {session.verdict.confidence && (
                        <div className="stat-badge">
                          <span className="stat-label">Confidence</span>
                          <span className="stat-value">{session.verdict.confidence}%</span>
                        </div>
                      )}
                      {session.verdict.success_probability && (
                        <div className="stat-badge">
                          <span className="stat-label">Success Rate</span>
                          <span className="stat-value">
                            {session.verdict.success_probability}
                          </span>
                        </div>
                      )}
                      {session.verdict.meta?.session_tokens && (
                        <div className="stat-badge">
                          <span className="stat-label">Resources Used</span>
                          <span className="stat-value">
                            {session.verdict.meta.session_tokens}
                          </span>
                        </div>
                      )}
                    </div>

                    <button
                      className="show-report-btn"
                      onClick={() => setShowReport(!showReport)}
                    >
                      {showReport ? 'Hide Full Analysis' : 'View Research & Analysis'}
                    </button>
                  </div>
                </div>

                {receiptItems.length > 0 && (
                  <div className="chat-msg">
                    <div className="msg-header">Receipt</div>
                    <div className="receipt-grid">
                      {receiptItems.map((item, index) => (
                        <React.Fragment key={`${item.claimed}-${index}`}>
                          <div className="receipt-card">
                            <div className="receipt-label">What you claimed</div>
                            <div className="receipt-copy">&ldquo;{item.claimed}&rdquo;</div>
                          </div>
                          <div className="receipt-card reality">
                            <div className="receipt-label">The reality</div>
                            <div className="receipt-copy">{item.reality}</div>
                          </div>
                        </React.Fragment>
                      ))}
                    </div>
                  </div>
                )}

                {showReport && (
                  <div className="chat-msg fadeIn">
                    <div className="msg-header">Intelligence Report</div>
                    <div className="msg-content report-container">
                      {session.verdict.community_sentiment && (
                        <div className="insight-section">
                          <h3 className="section-title">Community Sentiment</h3>
                          <p className="insight-text">{session.verdict.community_sentiment}</p>
                        </div>
                      )}

                      {session.verdict.key_advice &&
                        session.verdict.key_advice.length > 0 && (
                          <div className="insight-section">
                            <h3 className="section-title">Key Advice</h3>
                            <div className="insight-list">
                              {session.verdict.key_advice.map((a: string, i: number) => (
                                <div key={i} className="advice-item">
                                  {a}
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                      <div className="insight-section">
                        <h3 className="section-title">Core Rationales</h3>
                        <div className="insight-list">
                          {session.verdict.rationales.map((r, i) => (
                            <div key={i} className="insight-item">
                              <span className="insight-icon">&bull;</span> {r}
                            </div>
                          ))}
                        </div>
                      </div>

                      <div className="insight-section">
                        <h3 className="section-title">Critical Risks</h3>
                        <div className="insight-list">
                          {session.verdict.risks.map((r, i) => (
                            <div key={i} className="insight-item risk">
                              <span className="insight-icon">&bull;</span> {r}
                            </div>
                          ))}
                        </div>
                      </div>

                      {session.verdict.deal_breakers &&
                        session.verdict.deal_breakers.length > 0 && (
                          <div className="insight-section">
                            <h3 className="section-title">Deal Breakers</h3>
                            <div className="insight-list">
                              {session.verdict.deal_breakers.map(
                                (d: string, i: number) => (
                                  <div key={i} className="insight-item dealbreaker">
                                    &bull; {d}
                                  </div>
                                )
                              )}
                            </div>
                          </div>
                        )}

                      {session.verdict.web_research?.fact_bludgeons &&
                        session.verdict.web_research.fact_bludgeons.length > 0 && (
                          <div className="insight-section">
                            <h3 className="section-title">Case File Facts</h3>
                            <div className="insight-list">
                              {session.verdict.web_research.fact_bludgeons.map(
                                (fact: string, i: number) => (
                                  <div key={i} className="advice-item neutral">
                                    {fact}
                                  </div>
                                )
                              )}
                            </div>
                          </div>
                        )}

                      {verdictSources.length > 0 && (
                        <div className="insight-section">
                          <h3 className="section-title">Evidence</h3>
                          <div className="insight-list">
                            {verdictSources.slice(0, 5).map((source: any, i: number) => (
                              <a
                                key={`${source.url || source.uri || source.title}-${i}`}
                                className="source-link"
                                href={source.url || source.uri || '#'}
                                target="_blank"
                                rel="noreferrer"
                              >
                                <span>{source.title}</span>
                                {source.snippet && <small>{source.snippet}</small>}
                              </a>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </>
            )}

            {step !== 'verdict' && (
              <div className="bottom-search-bar">
                <div className={`search-wrapper ${session ? 'active' : ''}`}>
                  <textarea
                    ref={bottomInputRef}
                    placeholder={
                      step === 'interrogating'
                        ? 'Add details...'
                        : 'Refine your query...'
                    }
                    value={inputValue}
                    onChange={(e) => setInputValue(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        if (step === 'interrogating') {
                          api.handleAnswerSubmit();
                        } else {
                          api.handleStartDecision();
                        }
                      }
                    }}
                  />
                  <div className="search-actions">
                    <div className="action-buttons">
                      <button
                        className="action-btn"
                        onClick={api.reset}
                        aria-label="Reset Analysis"
                      >
                        Reset
                      </button>
                      <button className="action-btn" aria-label="Deep Focus Mode">
                        <SparklesIcon /> Deep Focus
                      </button>
                    </div>
                    <button
                      className="submit-btn"
                      onClick={
                        step === 'interrogating'
                          ? api.handleAnswerSubmit
                          : () => api.handleStartDecision()
                      }
                      disabled={!inputValue.trim() || isLoading}
                      aria-label={isLoading ? 'Loading...' : 'Submit decision input'}
                      aria-busy={isLoading}
                    >
                      {isLoading ? (
                        <ThinkingIcon className="spin-icon" />
                      ) : (
                        <ArrowUpIcon />
                      )}
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}

const rootElement = document.getElementById('root');
if (rootElement) {
  const root = ReactDOM.createRoot(rootElement);
  root.render(
    <React.StrictMode>
      <ErrorBoundary>
        <App />
      </ErrorBoundary>
    </React.StrictMode>
  );
}
