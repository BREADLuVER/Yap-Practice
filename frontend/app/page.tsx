import HomeClient from '@/components/HomeClient/HomeClient';
import { VideoSummary } from '@/types';
import { getServerApiBaseUrl } from '@/lib/api';

const PAGE_REVALIDATE_SECONDS = 300;

const getInitialVideos = async (): Promise<{
  videos: VideoSummary[];
  error: string | null;
}> => {
  const apiBaseUrl = getServerApiBaseUrl();
  if (!apiBaseUrl) {
    return { videos: [], error: null };
  }

  try {
    const response = await fetch(`${apiBaseUrl}/api/videos`, {
      next: { revalidate: PAGE_REVALIDATE_SECONDS },
    });
    if (!response.ok) {
      return { videos: [], error: 'Failed to load videos. Please try again later.' };
    }

    const videos = (await response.json()) as VideoSummary[];
    return { videos, error: null };
  } catch {
    return { videos: [], error: null };
  }
};

export default async function Home() {
  const { videos, error } = await getInitialVideos();
  return <HomeClient initialVideos={videos} initialError={error} />;
}
