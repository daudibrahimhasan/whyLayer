/**
 * OfflineNotice — shown when the user has no internet connection.
 * Inline banner, non-blocking. App still works offline for cached data.
 *
 * EmptyState — shown when there's no content to display.
 * Reusable for any section that might be empty.
 */

import React, { useState, useEffect } from 'react';

// ─── Offline Notice ──────────────────────────────────────────────────────────

export const OfflineNotice: React.FC = () => {
  const [isOffline, setIsOffline] = useState(!navigator.onLine);

  useEffect(() => {
    const goOffline = () => setIsOffline(true);
    const goOnline = () => setIsOffline(false);

    window.addEventListener('offline', goOffline);
    window.addEventListener('online', goOnline);

    return () => {
      window.removeEventListener('offline', goOffline);
      window.removeEventListener('online', goOnline);
    };
  }, []);

  if (!isOffline) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        padding: '8px 16px',
        background: '#1a1000',
        borderBottom: '1px solid #f59e0b',
        color: '#f59e0b',
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: '0.75rem',
        fontWeight: 600,
        textAlign: 'center',
        textTransform: 'uppercase',
        letterSpacing: '0.1em',
        zIndex: 10000,
      }}
    >
      You are offline. Some features may not work until you reconnect.
    </div>
  );
};

// ─── Empty State ─────────────────────────────────────────────────────────────

interface EmptyStateProps {
  /** Main heading */
  title?: string;
  /** Descriptive subtext */
  description?: string;
  /** Optional icon (emoji or component) */
  icon?: React.ReactNode;
  /** Optional action button */
  action?: {
    label: string;
    onClick: () => void;
  };
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  title = 'Nothing here yet',
  description = 'Start a new analysis to see results.',
  icon = '📭',
  action,
}) => {
  return (
    <div
      role="status"
      aria-label={title}
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '64px 32px',
        textAlign: 'center',
        minHeight: '300px',
      }}
    >
      <div style={{ fontSize: '2.5rem', marginBottom: '16px', opacity: 0.6 }}>{icon}</div>
      <div
        style={{
          fontFamily: "'Bebas Neue', sans-serif",
          fontSize: '1.8rem',
          letterSpacing: '0.05em',
          color: '#ededed',
          marginBottom: '8px',
        }}
      >
        {title}
      </div>
      <p
        style={{
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: '0.8rem',
          color: '#737373',
          maxWidth: '400px',
          lineHeight: '1.6',
          margin: '0 0 24px',
        }}
      >
        {description}
      </p>
      {action && (
        <button
          onClick={action.onClick}
          aria-label={action.label}
          style={{
            background: 'transparent',
            border: '1px solid rgba(255,255,255,0.2)',
            color: '#fff',
            padding: '10px 20px',
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: '0.8rem',
            fontWeight: 600,
            textTransform: 'uppercase',
            letterSpacing: '0.1em',
            cursor: 'pointer',
          }}
        >
          {action.label}
        </button>
      )}
    </div>
  );
};
