'use client';

import { useEffect, useState } from 'react';
import { User, onAuthStateChanged } from 'firebase/auth';
import { finalizeRedirectSignIn } from '@/lib/auth/actions';
import { getFirebaseAuth } from '@/lib/firebase/client';

type AuthUserState = {
  user: User | null;
  isLoading: boolean;
};

export const useAuthUser = (): AuthUserState => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(() => getFirebaseAuth() !== null);

  useEffect(() => {
    const auth = getFirebaseAuth();
    if (!auth) {
      return;
    }

    let unsubscribe = () => {};
    let isCancelled = false;

    const initializeAuth = async () => {
      try {
        await finalizeRedirectSignIn();
      } catch (error) {
        console.error('Redirect sign-in failed', error);
      }

      if (isCancelled) {
        return;
      }

      unsubscribe = onAuthStateChanged(auth, (nextUser) => {
        setUser(nextUser);
        setIsLoading(false);
      });
    };

    initializeAuth().catch((error) => {
      console.error('Auth initialization failed', error);
      setIsLoading(false);
    });

    return () => {
      isCancelled = true;
      unsubscribe();
    };
  }, []);

  return { user, isLoading };
};
