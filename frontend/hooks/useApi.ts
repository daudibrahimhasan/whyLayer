/**
 * useApi — all API interaction logic extracted from the monolith.
 *
 * Accepts the session state bag and setter functions from useSession,
 * plus a notification callback, and returns stable action handlers
 * with proper race-condition guards, error handling, and retry support.
 */

import { useCallback, useRef } from 'react';
import { AppStep, DecisionSession, Interaction } from '../types';
import { generateId } from '../utils';
import { track } from '../telemetry';
import { NotificationMessage } from './useNotification';
import { clearSavedSession } from './usePersistence';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

/** Unwrap standardized backend response: { success, data, error } */
async function apiFetch<T>(url: string, options: RequestInit): Promise<T> {
  const resp = await fetch(url, options);
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body?.error || `Server returned ${resp.status}`);
  }
  const json = await resp.json();
  // The backend wraps all responses in { success, data, error }
  if (json && typeof json === 'object' && 'success' in json && 'data' in json) {
    return json.data as T;
  }
  return json as T;
}

interface SessionSetters {
  setStep: React.Dispatch<React.SetStateAction<AppStep>>;
  setSession: React.Dispatch<React.SetStateAction<DecisionSession | null>>;
  setIsLoading: React.Dispatch<React.SetStateAction<boolean>>;
  setResearchMessage: React.Dispatch<React.SetStateAction<string>>;
  setInputValue: React.Dispatch<React.SetStateAction<string>>;
}

interface SessionGetters {
  step: AppStep;
  session: DecisionSession | null;
  inputValue: string;
  isLoading: boolean;
}

interface UseApiProps {
  getters: SessionGetters;
  setters: SessionSetters;
  addNotification: (msg: Omit<NotificationMessage, 'id'>) => void;
}

export interface ApiActions {
  handleStartDecision: (queryParam?: string) => Promise<void>;
  handleAnswerSubmit: () => Promise<void>;
  performResearch: (finalHistory: Interaction[], queryOverride?: string) => Promise<void>;
  reset: () => void;
}

export function useApi({ getters, setters, addNotification }: UseApiProps): ApiActions {
  // Track component mount state to prevent setState on unmounted component
  const mountedRef = useRef(true);

  const { step, session, inputValue, isLoading } = getters;
  const { setStep, setSession, setIsLoading, setResearchMessage, setInputValue } = setters;

  const performResearch = useCallback(
    async (finalHistory: Interaction[], queryOverride?: string) => {
      setStep('researching');
      setResearchMessage('[Analyzing behavior...]');

      try {
        const verdictData = await apiFetch<any>(`${API_BASE_URL}/api/decision/analyze`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            query: queryOverride || session?.originalPrompt,
            history: finalHistory,
            session_id: session?.id,
          }),
        });
        track('verdict_received', { confidence: verdictData.confidence ?? 0 });

        setSession((prev) =>
          prev
            ? {
                ...prev,
                verdict: verdictData,
                contradictionConfidence:
                  verdictData.confidence ?? prev.contradictionConfidence ?? 0,
              }
            : null
        );
        setStep('verdict');
      } catch (e) {
        track('research_failed', { error: String(e) });
        addNotification({
          type: 'error',
          message: 'Research analysis failed. Please try again.',
          action: {
            label: 'Retry',
            onClick: () => performResearch(finalHistory, queryOverride),
          },
        });
        setStep('idle');
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [session?.originalPrompt, session?.id]
  );

  const handleStartDecision = useCallback(
    async (queryParam?: string) => {
      const query = queryParam || inputValue;
      if (!query.trim() || isLoading) return;

      setInputValue('');
      setIsLoading(true);

      try {
        track('decision_started', {
          is_empty_query: !query.trim(),
          query_length: query.length,
        });

        const data = await apiFetch<any>(`${API_BASE_URL}/api/decision/start`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query }),
        });

        // CASE 1: Immediate Verdict (Lightweight)
        if (data.status === 'decision_complete' && data.verdict) {
          track('lightweight_verdict_received', {});
          setSession({
            id: data.session_id || generateId(),
            originalPrompt: query,
            topicCategory: data.topic_category,
            phase: 'initial',
            initialQuestions: [],
            initialQuestionIndex: 0,
            history: [],
            currentQuestion: undefined,
            verdict: data.verdict,
            contradictionConfidence: 100,
          });
          setStep('verdict');
          return;
        }

        // CASE 2: Interrogation (Standard)
        if (data.questions && data.questions.length > 0) {
          const initialQs = data.questions.map((q: any, i: number) => ({
            id: `initial_${i}`,
            text: q.text,
          }));

          setSession({
            id: data.session_id || generateId(),
            originalPrompt: query,
            topicCategory: data.topic_category,
            phase: 'initial',
            initialQuestions: initialQs,
            initialQuestionIndex: 0,
            history: [],
            currentQuestion: initialQs[0],
            contradictionConfidence: 0,
          });
          setStep('interrogating');
        }
      } catch (e) {
        track('start_decision_failed', { error: String(e) });
        addNotification({
          type: 'error',
          message: 'Failed to start session. Please ensure the backend is running on port 8000.',
          action: {
            label: 'Dismiss',
            onClick: () => {},
          },
        });
      } finally {
        setIsLoading(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [inputValue, isLoading]
  );

  const handleAnswerSubmit = useCallback(async () => {
    if (!session || !session.currentQuestion || !inputValue.trim() || isLoading) return;

    const answer = inputValue;
    track('answer_submitted', { answer_length: answer.length, phase: session.phase });

    const newHistory: Interaction[] = [
      ...session.history,
      { question: session.currentQuestion.text, answer },
    ];

    setInputValue('');
    setIsLoading(true);

    try {
      // Phase 1: Initial questions
      if (session.phase === 'initial') {
        const nextIndex = session.initialQuestionIndex + 1;

        if (nextIndex < session.initialQuestions.length) {
          // More initial questions to ask
          setSession({
            ...session,
            history: newHistory,
            initialQuestionIndex: nextIndex,
            currentQuestion: session.initialQuestions[nextIndex],
            contradictionConfidence: session.contradictionConfidence ?? 0,
          });
          return; // finally block will set isLoading(false)
        }

        // All initial questions answered — switch to follow-up phase
        setSession({
          ...session,
          phase: 'followup',
          history: newHistory,
          currentQuestion: undefined,
          contradictionConfidence: session.contradictionConfidence ?? 0,
        });

        // Fetch first dynamic follow-up question
        const data = await apiFetch<any>(`${API_BASE_URL}/api/decision/next`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            query: session.originalPrompt,
            history: newHistory,
            session_id: session.id,
            topic_category: session.topicCategory,
          }),
        });

        if (data.status === 'in_progress' && data.question) {
          setSession((prev) =>
            prev
              ? {
                  ...prev,
                  history: newHistory,
                  currentQuestion: {
                    id: generateId(),
                    text: data.question.text,
                  },
                  contradictionConfidence:
                    data.exposure_confidence ?? prev.contradictionConfidence ?? 0,
                  currentInsight: data.insight,
                }
              : null
          );
        } else {
          // Verdict ready after initial questions
          performResearch(newHistory);
        }
        return;
      }

      // Phase 2: Dynamic follow-up questions
      setSession({
        ...session,
        history: newHistory,
        currentQuestion: undefined,
        contradictionConfidence: session.contradictionConfidence ?? 0,
      });

      const data = await apiFetch<any>(`${API_BASE_URL}/api/decision/next`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: session.originalPrompt,
          history: newHistory,
          session_id: session.id,
          topic_category: session.topicCategory,
        }),
      });

      if (data.status === 'in_progress' && data.question) {
        setSession((prev) =>
          prev
            ? {
                ...prev,
                history: newHistory,
                currentQuestion: { id: generateId(), text: data.question.text },
                contradictionConfidence:
                  data.exposure_confidence ?? prev.contradictionConfidence ?? 0,
                currentInsight: data.insight,
              }
            : null
        );
      } else {
        // Ready for verdict
        performResearch(newHistory);
      }
    } catch (e) {
      track('answer_submit_failed', { error: String(e) });
      addNotification({
        type: 'error',
        message: 'Failed to communicate with the backend. Please check your connection.',
        action: {
          label: 'Retry',
          onClick: handleAnswerSubmit,
        },
      });
    } finally {
      setIsLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session, inputValue, isLoading]);

  const reset = useCallback(() => {
    setStep('idle');
    setSession(null);
    setInputValue('');
    clearSavedSession();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return {
    handleStartDecision,
    handleAnswerSubmit,
    performResearch,
    reset,
  };
}
