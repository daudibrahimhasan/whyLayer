import { describe, it, expect, beforeEach } from 'vitest';
import { track, getEvents, clearEvents } from './telemetry';

describe('Telemetry', () => {
  beforeEach(() => {
    clearEvents();
  });

  it('should store an event properly', () => {
    track('test_event', { prop: 'value' });
    const events = getEvents();
    expect(events).toHaveLength(1);
    expect(events[0].event).toBe('test_event');
    expect(events[0].properties).toEqual({ prop: 'value' });
  });

  it('should clear events', () => {
    track('test_event_2');
    clearEvents();
    expect(getEvents()).toHaveLength(0);
  });
});
