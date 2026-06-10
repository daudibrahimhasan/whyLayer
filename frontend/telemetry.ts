/**
 * telemetry.ts — Local-only event tracking for whyLayer.
 *
 * PRIVACY: All data stays in localStorage. No external calls. No PII.
 * This is free because it's 100% client-side with zero dependencies.
 *
 * Usage:
 *   import { track, getEvents, clearEvents } from './telemetry';
 *   track('session_started', { query_length: 42 });
 */

interface TelemetryEvent {
  event: string;
  properties?: Record<string, string | number | boolean>;
  timestamp: string;
}

const STORAGE_KEY = 'whyLayer_telemetry';
const MAX_EVENTS = 500; // Ring buffer to prevent storage bloat

/**
 * Track an event locally. Never leaves the device.
 */
export function track(event: string, properties?: Record<string, string | number | boolean>): void {
  try {
    const entry: TelemetryEvent = {
      event,
      properties,
      timestamp: new Date().toISOString(),
    };

    const existing = getEvents();
    existing.push(entry);

    // Keep only the most recent MAX_EVENTS
    const trimmed = existing.slice(-MAX_EVENTS);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed));
  } catch {
    // localStorage full or unavailable — silently fail, never crash
  }
}

/**
 * Retrieve all locally stored telemetry events.
 */
export function getEvents(): TelemetryEvent[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

/**
 * Clear all locally stored telemetry events.
 */
export function clearEvents(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // silently fail
  }
}

/**
 * Get a simple summary of event counts (for dev dashboard / debugging).
 */
export function getEventSummary(): Record<string, number> {
  const events = getEvents();
  const counts: Record<string, number> = {};
  for (const e of events) {
    counts[e.event] = (counts[e.event] || 0) + 1;
  }
  return counts;
}
