'use client';

import { useEffect } from 'react';
import styles from './ThemeToggle.module.css';

type Theme = 'light' | 'dark';

const STORAGE_KEY = 'northernlingo-theme';

const applyTheme = (theme: Theme): void => {
  document.documentElement.setAttribute('data-theme', theme);
};

const getStoredTheme = (): Theme | null => {
  try {
    const storedTheme = window.localStorage.getItem(STORAGE_KEY);
    if (storedTheme === 'light' || storedTheme === 'dark') {
      return storedTheme;
    }
  } catch (error) {
    console.warn('Failed to read theme from localStorage', error);
  }
  return null;
};

const setStoredTheme = (theme: Theme): void => {
  try {
    window.localStorage.setItem(STORAGE_KEY, theme);
  } catch (error) {
    console.warn('Failed to persist theme in localStorage', error);
  }
};

const getInitialTheme = (): Theme => {
  const storedTheme = getStoredTheme();
  if (storedTheme) {
    return storedTheme;
  }

  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
};

export default function ThemeToggle() {
  useEffect(() => {
    const initialTheme = getInitialTheme();
    applyTheme(initialTheme);
    setStoredTheme(initialTheme);
  }, []);

  const handleToggleTheme = () => {
    const currentTheme =
      document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
    const nextTheme: Theme = currentTheme === 'light' ? 'dark' : 'light';
    applyTheme(nextTheme);
    setStoredTheme(nextTheme);
  };

  return (
    <button
      type="button"
      className={styles.toggleButton}
      aria-label="Toggle theme"
      onClick={handleToggleTheme}
    >
      Theme
    </button>
  );
}
