import { test, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import ErrorBoundary from './ErrorBoundary';

const Bomb = () => {
  throw new Error('Kaboom');
};

test('ErrorBoundary catches errors and displays fallback UI', () => {
  // Prevent React from logging the error to console during this test
  const spy = vi.spyOn(console, 'error').mockImplementation(() => {});

  render(
    <ErrorBoundary>
      <Bomb />
    </ErrorBoundary>
  );

  expect(screen.getByText('SOMETHING BROKE')).toBeInTheDocument();
  expect(screen.getByText('Kaboom')).toBeInTheDocument();

  spy.mockRestore();
});
