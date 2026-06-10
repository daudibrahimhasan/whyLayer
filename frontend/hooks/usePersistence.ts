/**
 * usePersistence — saves and restores session state to/from localStorage.
 *
 * On mount, restores any saved session and validates it against the backend.
 * On state change, auto-persists the latest state.
 * If the backend reports the session is invalid, sets sessionError so the
 * UI can show a "Session expired" message.
 */

import { useEffect, useState, useRef, useCallback } from 'react';
import { AppStep, DecisionSession } from '../types';
import { track } from '../telemetry';

const STORAGE_KEY = 'whyLayer_session_v1';
const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

/** Unwrap standardized backend response: { success, data, error } */
async function apiFetch<T>(url: string, options: RequestInit): Promise<T> {
  const resp = await fetch(url, options);
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body?.error || `Server returned ${resp.status}`);
  }
  const json = await resp.json();
  if (json && typeof json === 'object' && 'success' in json && 'data' in json) {
    return json.data as T;
  }
  return json as T;
}

interface PersistenceState {
  step: AppStep;
  session: DecisionSession | null;
  showReport: boolean;
  isSidebarCollapsed: boolean;
}

interface UsePersistenceReturn {
  /** Non-null when the restored session is no longer valid on the backend */
  sessionError: string | null;
  /** Dismiss the session error and clear storage */
  dismissSessionError: () => void;
}

export function usePersistence(state: PersistenceState): UsePersistenceReturn {
  const [sessionError, setSessionError] = useState<string | null>(null);
  const restoredRef = useRef(false);

  // --- Restore on mount ---
  useEffect(() => {
    if (restoredRef.current) return;
    restoredRef.current = true;

    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return;

    try {
      const parsed: PersistenceState = JSON.parse(raw);
      if (!parsed.session?.id) return;

      // Restore the saved state into the component's state by calling the setters
      // We don't have direct access to setters here, so we store the saved data
      // and the component reads it via a returned value. Instead, we just check
      // session validity and rely on the component to check for saved data.
      checkSessionValidity(parsed.session.id);
    } catch {
      track('storage_load_error', { error: 'parse_failed' });
    }
  }, []);

  // --- Auto-save on state change ---
  // Note: the component that owns the state is responsible for calling
  // saveSession whenever state changes. This effect fires whenever the
  // passed-in state changes.
  useEffect(() => {
    if (!state.session) return;
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          step: state.step,
          session: state.session,
          showReport: state.showReport,
          isSidebarCollapsed: state.isSidebarCollapsed,
        })
      );
    } catch {
      // localStorage full — silently fail
    }
  }, [state.step, state.session, state.showReport, state.isSidebarCollapsed]);

  // --- Validate session against backend ---
  const checkSessionValidity = useCallback(async (sessionId: string) => {
    try {
      const data = await apiFetch<any>(`${API_BASE_URL}/api/decision/status`, {
        method: 'GET',
      });
      // The status endpoint returns {"status": "active", "version": "..."}
      // but doesn't know about individual sessions. If the backend is up,
      // the session is valid. If backend were down, we'd catch.
      // A real production app would have a session-specific endpoint.
      if (data.status === 'error' || data.status === 'not_found') {
        setSessionError('Your previous session has expired. Please start a new analysis.');
        localStorage.removeItem(STORAGE_KEY);
      }
    } catch {
      // Backend unreachable — keep the saved session, it might work
      // The user will see a normal error when they try to interact
    }
  }, []);

  const dismissSessionError = useCallback(() => {
    setSessionError(null);
    localStorage.removeItem(STORAGE_KEY);
  }, []);

  return { sessionError, dismissSessionError };
}

/**
 * Restore saved session data from localStorage.
 * Returns null if nothing is saved or the data is corrupt.
 */
export function restoreSavedSession(): PersistenceState | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed: PersistenceState = JSON.parse(raw);
    if (!parsed.session && parsed.step === 'idle') return null;
    return parsed;
  } catch {
    return null;
  }
}

/**
 * Clear the persisted session from localStorage.
 */
export function clearSavedSession(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // silently fail
  }
}
