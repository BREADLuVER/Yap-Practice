'use client';

import { GoogleAuthProvider, signInWithPopup, signOut } from 'firebase/auth';
import { getFirebaseAuth } from '@/lib/firebase/client';

const googleProvider = new GoogleAuthProvider();
googleProvider.setCustomParameters({ prompt: 'select_account' });

export const signInWithGoogle = async (): Promise<void> => {
  await signInWithPopup(getFirebaseAuth(), googleProvider);
};

export const signOutUser = async (): Promise<void> => {
  await signOut(getFirebaseAuth());
};

export const getCurrentUserIdToken = async (): Promise<string | null> => {
  const currentUser = getFirebaseAuth().currentUser;
  if (!currentUser) {
    return null;
  }

  return currentUser.getIdToken();
};
