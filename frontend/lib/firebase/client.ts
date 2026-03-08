import { FirebaseApp, getApp, getApps, initializeApp } from 'firebase/app';
import {
  Auth,
  browserLocalPersistence,
  browserSessionPersistence,
  getAuth,
  indexedDBLocalPersistence,
  initializeAuth,
} from 'firebase/auth';

type FirebaseConfig = {
  apiKey: string;
  authDomain: string;
  projectId: string;
  appId: string;
  storageBucket?: string;
  messagingSenderId?: string;
  measurementId?: string;
};

let appInstance: FirebaseApp | null = null;
let authInstance: Auth | null = null;
let initError: Error | null = null;

const getFirebaseConfig = (): FirebaseConfig => {
  const config: FirebaseConfig = {
    apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY ?? '',
    authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN ?? '',
    projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID ?? '',
    appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID ?? '',
    storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET,
    messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
    measurementId: process.env.NEXT_PUBLIC_FIREBASE_MEASUREMENT_ID,
  };

  const missingKeys = Object.entries({
    NEXT_PUBLIC_FIREBASE_API_KEY: config.apiKey,
    NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN: config.authDomain,
    NEXT_PUBLIC_FIREBASE_PROJECT_ID: config.projectId,
    NEXT_PUBLIC_FIREBASE_APP_ID: config.appId,
  })
    .filter(([, value]) => !value)
    .map(([key]) => key);

  if (missingKeys.length > 0) {
    throw new Error(`Firebase config is incomplete. Missing env vars: ${missingKeys.join(', ')}`);
  }

  return config;
};

const getFirebaseApp = (): FirebaseApp | null => {
  if (appInstance) {
    return appInstance;
  }
  if (initError) {
    return null;
  }

  try {
    appInstance = getApps().length > 0 ? getApp() : initializeApp(getFirebaseConfig());
    return appInstance;
  } catch (error) {
    initError = error instanceof Error ? error : new Error('Failed to initialize Firebase app.');
    console.error(initError);
    return null;
  }
};

export const getFirebaseAuth = (): Auth | null => {
  if (authInstance) {
    return authInstance;
  }

  const app = getFirebaseApp();
  if (!app) {
    return null;
  }

  try {
    authInstance = initializeAuth(app, {
      persistence: [indexedDBLocalPersistence, browserLocalPersistence, browserSessionPersistence],
    });
  } catch (error) {
    // If auth was already initialized elsewhere (or environment limits persistence),
    // fall back to the default singleton to avoid breaking login flows.
    authInstance = getAuth(app);
    if (process.env.NODE_ENV !== 'production') {
      console.warn('Falling back to getAuth()', error);
    }
  }

  return authInstance;
};

export const getFirebaseInitError = (): Error | null => initError;
