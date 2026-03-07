'use client';

import { useMemo, useState } from 'react';
import { FirebaseError } from 'firebase/app';
import { signInWithGoogle, signOutUser } from '@/lib/auth/actions';
import { useAuthUser } from '@/lib/auth/useAuthUser';
import styles from './AuthControl.module.css';

const getFriendlyAuthError = (error: unknown): string => {
  if (error instanceof FirebaseError) {
    if (error.code === 'auth/popup-closed-by-user') {
      return 'Login popup was closed before sign in completed.';
    }

    if (error.code === 'auth/unauthorized-domain') {
      return 'This domain is not authorized in Firebase Auth settings.';
    }

    return `Authentication failed (${error.code}).`;
  }

  return 'Authentication failed. Please try again.';
};

export default function AuthControl() {
  const { user, isLoading } = useAuthUser();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const userLabel = useMemo(() => {
    if (!user) {
      return '';
    }

    return user.displayName ?? user.email ?? 'Signed in';
  }, [user]);

  const handleSignIn = async () => {
    setIsSubmitting(true);
    setErrorMessage(null);

    try {
      await signInWithGoogle();
    } catch (error) {
      setErrorMessage(getFriendlyAuthError(error));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSignOut = async () => {
    setIsSubmitting(true);
    setErrorMessage(null);

    try {
      await signOutUser();
    } catch (error) {
      setErrorMessage(getFriendlyAuthError(error));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className={styles.container}>
      {isLoading ? (
        <span className={styles.statusText} aria-live="polite">
          Checking login...
        </span>
      ) : user ? (
        <div className={styles.authRow}>
          <span className={styles.userLabel} title={userLabel}>
            {userLabel}
          </span>
          <button
            type="button"
            className={styles.actionButton}
            onClick={handleSignOut}
            disabled={isSubmitting}
            aria-label="Log out"
          >
            {isSubmitting ? 'Logging out...' : 'Log out'}
          </button>
        </div>
      ) : (
        <button
          type="button"
          className={styles.actionButton}
          onClick={handleSignIn}
          disabled={isSubmitting}
          aria-label="Log in with Google"
        >
          {isSubmitting ? 'Opening login...' : 'Log in'}
        </button>
      )}

      {errorMessage && (
        <p className={styles.errorText} role="alert">
          {errorMessage}
        </p>
      )}
    </div>
  );
}
