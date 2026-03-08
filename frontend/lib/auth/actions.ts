'use client';

import {
  getRedirectResult,
  GoogleAuthProvider,
  signInWithPopup,
  signInWithRedirect,
  signOut,
} from 'firebase/auth';
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
  return /iPhone|iPad|iPod/i.test(navigator.userAgent);
};

export const signInWithGoogle = async (): Promise<void> => {
  const auth = getRequiredAuth();
  if (shouldUseRedirectFlow()) {
    await signInWithRedirect(auth, googleProvider);
    return;
  }
  await signInWithPopup(auth, googleProvider);
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
