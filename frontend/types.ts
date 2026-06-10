/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

export type AppStep = 'idle' | 'interrogating' | 'researching' | 'verdict';

export interface Source {
  uri?: string;
  url?: string;
  title: string;
  snippet?: string;
}

export interface VerdictData {
  status: 'GO' | 'NO-GO' | 'CAUTION';
  summary: string;
  rationales: string[];
  risks: string[];
  community_sentiment?: string; // Updated from communitySentiment to match backend snake_case
  communitySentiment?: string; // Keep for backward compat if needed
  sources?: Source[];
  confidence?: number;
  success_probability?: string;
  key_advice?: string[];
  deal_breakers?: string[];
  receipt?: Array<{ claimed: string; reality: string }>;
  web_research?: {
    sources?: Source[];
    fact_bludgeons?: string[];
  };
  meta?: Record<string, any>;
}

export interface Question {
  id: string;
  text: string;
}

export interface Interaction {
  question: string;
  answer: string;
}

export interface DecisionSession {
  id: string;
  originalPrompt: string;
  topicCategory?: string;
  phase: 'initial' | 'followup'; // Phase 1: initial 3 questions, Phase 2: dynamic follow-ups
  initialQuestions: Question[]; // The 3 upfront questions
  initialQuestionIndex: number; // Current index in initial questions (0, 1, 2)
  history: Interaction[];
  currentQuestion?: Question;
  verdict?: VerdictData;
  contradictionConfidence?: number;
  currentInsight?: { text: string; label?: string; type?: string };
}
