/**
 * ErrorBoundary — catches unhandled React errors and shows a fallback UI.
 * Prevents the entire app from crashing on component-level failures.
 */

import React from 'react';
import { track } from '../telemetry';

interface ErrorBoundaryProps {
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, _errorInfo: React.ErrorInfo) {
    track('uncaught_error', { message: error.message, name: error.name });
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div className="error-page" role="alert" aria-live="assertive">
          <div className="error-page-inner">
            <div className="error-page-heading">
              SOMETHING BROKE
            </div>
            <p className="error-page-subtext">
              {this.state.error?.message || 'An unexpected error occurred.'}
            </p>
            <button
              className="error-page-btn"
              onClick={this.handleReset}
              aria-label="Try again"
            >
              Try Again
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
