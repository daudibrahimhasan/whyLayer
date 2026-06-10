/**
 * useSession — manages all UI and session state for the decision app.
 *
 * Returns state values and setter functions so that other hooks and
 * the component can compose them without passing props through layers.
 */

import { useState } from 'react';
import { AppStep, DecisionSession } from '../types';

export interface SessionState {
  step: AppStep;
  setStep: React.Dispatch<React.SetStateAction<AppStep>>;
  session: DecisionSession | null;
  setSession: React.Dispatch<React.SetStateAction<DecisionSession | null>>;
  isLoading: boolean;
  setIsLoading: React.Dispatch<React.SetStateAction<boolean>>;
  researchMessage: string;
  setResearchMessage: React.Dispatch<React.SetStateAction<string>>;
  showReport: boolean;
  setShowReport: React.Dispatch<React.SetStateAction<boolean>>;
  isSidebarOpen: boolean;
  setIsSidebarOpen: React.Dispatch<React.SetStateAction<boolean>>;
  isSidebarCollapsed: boolean;
  setIsSidebarCollapsed: React.Dispatch<React.SetStateAction<boolean>>;
  inputValue: string;
  setInputValue: React.Dispatch<React.SetStateAction<string>>;
  /** Derived: contradiction confidence from current session */
  contradictionConfidence: number;
  /** Derived: flattened list of verdict sources */
  verdictSources: any[];
  /** Derived: receipt items from verdict */
  receiptItems: Array<{ claimed: string; reality: string }>;
}

export function useSession(): SessionState {
  const [step, setStep] = useState<AppStep>('idle');
  const [session, setSession] = useState<DecisionSession | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [researchMessage, setResearchMessage] = useState(
    'Initializing research architecture...'
  );
  const [showReport, setShowReport] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [inputValue, setInputValue] = useState('');

  const contradictionConfidence = session?.contradictionConfidence ?? 0;
  const verdictSources =
    session?.verdict?.web_research?.sources ?? session?.verdict?.sources ?? [];
  const receiptItems = session?.verdict?.receipt ?? [];

  return {
    step,
    setStep,
    session,
    setSession,
    isLoading,
    setIsLoading,
    researchMessage,
    setResearchMessage,
    showReport,
    setShowReport,
    isSidebarOpen,
    setIsSidebarOpen,
    isSidebarCollapsed,
    setIsSidebarCollapsed,
    inputValue,
    setInputValue,
    contradictionConfidence,
    verdictSources,
    receiptItems,
  };
}
