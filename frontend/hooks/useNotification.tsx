/**
 * useNotification — lightweight toast notification system.
 *
 * Provides an add/remove API and a <NotificationBar /> component
 * to render active notifications as overlays.
 *
 * Usage:
 *   const { addNotification, NotificationBar } = useNotification();
 *   addNotification({ type: 'error', message: 'Something failed', action: { label: 'Retry', onClick: retryFn } });
 *   // In JSX: <NotificationBar />
 */

import React, { useState, useCallback } from 'react';

export interface NotificationMessage {
  id?: string;
  type: 'error' | 'info' | 'success';
  message: string;
  action?: {
    label: string;
    onClick: () => void;
  };
}

let nextId = 0;

export function useNotification() {
  const [notifications, setNotifications] = useState<NotificationMessage[]>([]);

  const addNotification = useCallback((msg: Omit<NotificationMessage, 'id'>) => {
    const id = `notif_${++nextId}`;
    setNotifications((prev) => [...prev, { ...msg, id }]);

    // Auto-dismiss info/success notifications after 6 seconds
    if (msg.type !== 'error') {
      setTimeout(() => {
        setNotifications((prev) => prev.filter((n) => n.id !== id));
      }, 6000);
    }
  }, []);

  const removeNotification = useCallback((id: string) => {
    setNotifications((prev) => prev.filter((n) => n.id !== id));
  }, []);

  const clearAll = useCallback(() => {
    setNotifications([]);
  }, []);

  const NotificationBar: React.FC = () => {
    if (notifications.length === 0) return null;

    return (
      <div
        style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          zIndex: 10000,
          display: 'flex',
          flexDirection: 'column',
          gap: 4,
          padding: '8px 16px',
          pointerEvents: 'none',
        }}
      >
        {notifications.map((n) => (
          <div
            key={n.id}
            role="alert"
            aria-live="assertive"
            style={{
              pointerEvents: 'auto',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 12,
              padding: '12px 16px',
              background: n.type === 'error' ? '#1a0505' : n.type === 'success' ? '#051a05' : '#0a0a1a',
              border: `1px solid ${
                n.type === 'error' ? '#ff2a2a' : n.type === 'success' ? '#00e676' : '#00a3ff'
              }`,
              color: '#ededed',
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: '0.8rem',
              lineHeight: 1.5,
              animation: 'slideDown 0.25s ease-out',
            }}
          >
            <span style={{ flex: 1 }}>{n.message}</span>
            <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
              {n.action && (
                <button
                  onClick={n.action.onClick}
                  style={{
                    background: 'transparent',
                    border: '1px solid rgba(255,255,255,0.2)',
                    color: '#fff',
                    padding: '6px 12px',
                    fontFamily: "'JetBrains Mono', monospace",
                    fontSize: '0.75rem',
                    fontWeight: 600,
                    textTransform: 'uppercase',
                    cursor: 'pointer',
                  }}
                >
                  {n.action.label}
                </button>
              )}
              <button
                onClick={() => removeNotification(n.id!)}
                aria-label="Dismiss"
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: '#737373',
                  cursor: 'pointer',
                  fontSize: '1.1rem',
                  lineHeight: 1,
                  padding: '0 4px',
                }}
              >
                &times;
              </button>
            </div>
          </div>
        ))}
        <style>{`
          @keyframes slideDown {
            from { opacity: 0; transform: translateY(-20px); }
            to { opacity: 1; transform: translateY(0); }
          }
        `}</style>
      </div>
    );
  };

  return { notifications, addNotification, removeNotification, clearAll, NotificationBar };
}
