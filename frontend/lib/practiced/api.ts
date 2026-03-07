'use client';

import axios from 'axios';
import { getApiBaseUrl } from '@/lib/api';
import { getCurrentUserIdToken } from '@/lib/auth/actions';

const API_BASE_URL = getApiBaseUrl();

type PracticedResponse = {
  practiced: string[];
};

export class PracticedAuthRequiredError extends Error {
  constructor() {
    super('You must be logged in to update practiced clips.');
    this.name = 'PracticedAuthRequiredError';
  }
}

const getAuthorizationHeader = async (): Promise<string | null> => {
  const token = await getCurrentUserIdToken();
  if (!token) {
    return null;
  }

  return `Bearer ${token}`;
};

export const fetchPracticedVideoIds = async (videoIds: string[]): Promise<Set<string>> => {
  const authorization = await getAuthorizationHeader();
  if (!authorization) {
    return new Set<string>();
  }

  const normalizedVideoIds = Array.from(
    new Set(videoIds.map((videoId) => videoId.trim()).filter(Boolean)),
  );

  const query = normalizedVideoIds.length
    ? `?videoIds=${encodeURIComponent(normalizedVideoIds.join(','))}`
    : '';
  const response = await axios.get<PracticedResponse>(
    `${API_BASE_URL}/api/users/me/practiced${query}`,
    {
      headers: {
        Authorization: authorization,
      },
    },
  );

  return new Set(response.data.practiced ?? []);
};

export const setPracticedVideo = async (
  videoId: string,
  practiced: boolean,
): Promise<void> => {
  const normalizedVideoId = videoId.trim();
  if (!normalizedVideoId) {
    return;
  }

  const authorization = await getAuthorizationHeader();
  if (!authorization) {
    throw new PracticedAuthRequiredError();
  }

  await axios.put(
    `${API_BASE_URL}/api/users/me/practiced/${encodeURIComponent(normalizedVideoId)}`,
    { practiced },
    {
      headers: {
        Authorization: authorization,
      },
    },
  );
};
