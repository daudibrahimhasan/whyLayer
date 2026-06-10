/**
 * LoadingSpinner — a minimal animated loading indicator.
 * Used for inline loading states during API calls and transitions.
 */

import React from 'react';

interface LoadingSpinnerProps {
  /** Message shown below the spinner */
  message?: string;
  /** Size variant */
  size?: 'small' | 'medium' | 'large';
}

const sizes = {
  small: { spinner: 16, fontSize: '0.7rem' },
  medium: { spinner: 28, fontSize: '0.8rem' },
  large: { spinner: 44, fontSize: '0.9rem' },
};

const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({ message, size = 'medium' }) => {
  const { spinner, fontSize } = sizes[size];

  return (
    <div
      role="status"
      aria-live="polite"
      aria-label={message || 'Loading'}
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: '12px',
      }}
    >
      <div
        style={{
          width: spinner,
          height: spinner,
          border: '2px solid rgba(255,255,255,0.1)',
          borderTopColor: '#fff',
          borderRadius: '50%',
          animation: 'wl-spin 0.7s linear infinite',
        }}
      />
      {message && (
        <span
          style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize,
            color: '#737373',
            textTransform: 'uppercase',
            letterSpacing: '0.1em',
          }}
        >
          {message}
        </span>
      )}
      <style>{`
        @keyframes wl-spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
};

export default LoadingSpinner;
