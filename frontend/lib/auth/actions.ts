'use client';

import {
  getRedirectResult,
  GoogleAuthProvider,
  signInWithPopup,
  signInWithRedirect,
  signOut,
} from 'firebase/auth';
import { FirebaseError } from 'firebase/app';
import { getFirebaseAuth, getFirebaseInitError } from '@/lib/firebase/client';

const googleProvider = new GoogleAuthProvider();
googleProvider.setCustomParameters({ prompt: 'select_account' });

const getRequiredAuth = () => {
  const auth = getFirebaseAuth();
  if (auth) {
    return auth;
  }

  const initError = getFirebaseInitError();
  if (initError) {
    throw initError;
  }

  throw new Error('Firebase Auth is unavailable.');
};

const shouldUseRedirectFlow = (): boolean => {
  if (typeof navigator === 'undefined') {
    return false;
  }

  const userAgent = navigator.userAgent;
  const isClassicIos = /iPhone|iPad|iPod/i.test(userAgent);
  // iPadOS can identify itself as Macintosh while still requiring iOS-safe auth flow.
  const isTouchMac = /Macintosh/i.test(userAgent) && navigator.maxTouchPoints > 1;

  return isClassicIos || isTouchMac;
};

const shouldFallbackToRedirect = (error: unknown): boolean => {
  if (!(error instanceof FirebaseError)) {
    return false;
  }

  return (
    error.code === 'auth/popup-blocked' ||
    error.code === 'auth/cancelled-popup-request' ||
    error.code === 'auth/operation-not-supported-in-this-environment'
  );
};

export const signInWithGoogle = async (): Promise<void> => {
  const auth = getRequiredAuth();
  if (shouldUseRedirectFlow()) {
    await signInWithRedirect(auth, googleProvider);
    return;
  }

  try {
    await signInWithPopup(auth, googleProvider);
  } catch (error) {
    if (!shouldFallbackToRedirect(error)) {
      throw error;
    }

    await signInWithRedirect(auth, googleProvider);
  }
};

export const signOutUser = async (): Promise<void> => {
  await signOut(getRequiredAuth());
};

export const finalizeRedirectSignIn = async (): Promise<void> => {
  await getRedirectResult(getRequiredAuth());
};

export const getCurrentUserIdToken = async (): Promise<string | null> => {
  const auth = getFirebaseAuth();
  if (!auth) {
    return null;
  }

  const currentUser = auth.currentUser;
  if (!currentUser) {
    return null;
  }

  return currentUser.getIdToken();
};
