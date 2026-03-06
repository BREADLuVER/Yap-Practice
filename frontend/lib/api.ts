const LOCAL_API_ORIGIN = 'http://localhost:8000';

const normalizeOrigin = (origin: string): string => origin.trim().replace(/\/$/, '');

const isLocalHost = (hostname: string): boolean => hostname === 'localhost' || hostname === '127.0.0.1';

export const getApiBaseUrl = (): string => {
  const configuredOrigin = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();

  if (configuredOrigin) {
    const normalizedOrigin = normalizeOrigin(configuredOrigin);

    // Avoid mixed-content failures when the app is served over HTTPS.
    if (
      typeof window !== 'undefined' &&
      window.location.protocol === 'https:' &&
      normalizedOrigin.startsWith('http://')
    ) {
      const hostname = normalizedOrigin.slice('http://'.length).split('/')[0].split(':')[0];
      if (!isLocalHost(hostname)) {
        return normalizedOrigin.replace('http://', 'https://');
      }
    }

    return normalizedOrigin;
  }

  if (typeof window !== 'undefined' && isLocalHost(window.location.hostname)) {
    return LOCAL_API_ORIGIN;
  }

  return '';
};

export const getApiErrorMessage = (fallbackMessage: string): string => {
  if (typeof window !== 'undefined' && !process.env.NEXT_PUBLIC_API_BASE_URL && !isLocalHost(window.location.hostname)) {
    return 'API URL is not configured. Set NEXT_PUBLIC_API_BASE_URL in the frontend environment.';
  }

  return fallbackMessage;
};
