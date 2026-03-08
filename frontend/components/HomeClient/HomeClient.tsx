'use client';

import { useState, useEffect, useMemo } from 'react';
import axios from 'axios';
import Link from 'next/link';
import Image from 'next/image';
import { VideoSummary } from '@/types';
import { getApiBaseUrl, getApiErrorMessage } from '@/lib/api';
import { useAuthUser } from '@/lib/auth/useAuthUser';
import {
  PracticedAuthRequiredError,
  fetchPracticedVideoIds,
  setPracticedVideo,
} from '@/lib/practiced/api';
import styles from './HomeClient.module.css';

const API_BASE_URL = getApiBaseUrl();
const getYouTubeThumbnailUrl = (videoId: string) => `https://i.ytimg.com/vi/${videoId}/hqdefault.jpg`;
type PracticedFilter = 'all' | 'practiced' | 'unpracticed';
const INITIAL_VISIBLE_VIDEOS = 48;
const LOAD_MORE_STEP = 48;

const getNormalizedThumbnailUrl = (video: VideoSummary) => {
  if (!video.thumbnailUrl) {
    return getYouTubeThumbnailUrl(video.video_id);
  }

  try {
    const parsedUrl = new URL(video.thumbnailUrl);
    if (parsedUrl.hostname.includes('ytimg.com')) {
      return getYouTubeThumbnailUrl(video.video_id);
    }
    return video.thumbnailUrl;
  } catch {
    return getYouTubeThumbnailUrl(video.video_id);
  }
};

export default function HomeClient() {
  const { user, isLoading: isAuthLoading } = useAuthUser();
  const [videos, setVideos] = useState<VideoSummary[]>([]);
  const [practicedVideoIds, setPracticedVideoIds] = useState<Set<string>>(new Set());
  const [updatingVideoIds, setUpdatingVideoIds] = useState<Set<string>>(new Set());
  const [fallbackThumbnailVideoIds, setFallbackThumbnailVideoIds] = useState<Set<string>>(new Set());
  const [activeFilter, setActiveFilter] = useState<PracticedFilter>('all');
  const [visibleCount, setVisibleCount] = useState(INITIAL_VISIBLE_VIDEOS);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchVideos = async () => {
      try {
        const response = await axios.get(`${API_BASE_URL}/api/videos`);
        setVideos(response.data);
      } catch (err: unknown) {
        console.error(err);
        if (axios.isAxiosError(err) && err.message === 'Network Error') {
          setError(getApiErrorMessage('Unable to reach the API server. Confirm backend URL and CORS settings.'));
        } else {
          setError('Failed to load videos. Please try again later.');
        }
      } finally {
        setIsLoading(false);
      }
    };

    fetchVideos();
  }, []);

  useEffect(() => {
    let isCancelled = false;

    const fetchPracticed = async () => {
      if (isAuthLoading) {
        return;
      }

      if (!user || videos.length === 0) {
        setPracticedVideoIds(new Set());
        return;
      }

      try {
        const practiced = await fetchPracticedVideoIds(videos.map((video) => video.video_id));
        if (!isCancelled) {
          setPracticedVideoIds(practiced);
        }
      } catch (err) {
        if (!isCancelled) {
          console.error(err);
          setError('Failed to load practiced-state. Please try refreshing.');
        }
      }
    };

    fetchPracticed();

    return () => {
      isCancelled = true;
    };
  }, [isAuthLoading, user, videos]);

  const filteredVideos = useMemo(() => {
    if (activeFilter === 'all') {
      return videos;
    }

    return videos.filter((video) => {
      const isPracticed = practicedVideoIds.has(video.video_id);
      if (activeFilter === 'practiced') {
        return isPracticed;
      }
      return !isPracticed;
    });
  }, [activeFilter, practicedVideoIds, videos]);

  const visibleVideos = useMemo(
    () => filteredVideos.slice(0, visibleCount),
    [filteredVideos, visibleCount],
  );

  const canLoadMore = visibleCount < filteredVideos.length;

  const handleFilterChange = (nextFilter: PracticedFilter) => {
    setActiveFilter(nextFilter);
    setVisibleCount(INITIAL_VISIBLE_VIDEOS);
  };

  const handleLoadMore = () => {
    setVisibleCount((previous) => previous + LOAD_MORE_STEP);
  };

  const handlePracticedToggle = async (videoId: string) => {
    if (!user || updatingVideoIds.has(videoId)) {
      return;
    }

    const nextPracticed = !practicedVideoIds.has(videoId);

    setUpdatingVideoIds((previous) => new Set([...previous, videoId]));
    setPracticedVideoIds((previous) => {
      const next = new Set(previous);
      if (nextPracticed) {
        next.add(videoId);
      } else {
        next.delete(videoId);
      }
      return next;
    });

    try {
      await setPracticedVideo(videoId, nextPracticed);
    } catch (err) {
      setPracticedVideoIds((previous) => {
        const next = new Set(previous);
        if (nextPracticed) {
          next.delete(videoId);
        } else {
          next.add(videoId);
        }
        return next;
      });

      if (err instanceof PracticedAuthRequiredError) {
        setError('Please log in to mark clips as practiced.');
      } else {
        setError('Failed to update practiced-state. Please try again.');
      }
    } finally {
      setUpdatingVideoIds((previous) => {
        const next = new Set(previous);
        next.delete(videoId);
        return next;
      });
    }
  };

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.pageTitle}>NorthernLingo</h1>
        <p className={styles.subtitle}>Select a clip to start practicing</p>
        <div className={styles.filterRow} role="group" aria-label="Practice filters">
          <button
            type="button"
            className={`${styles.filterButton} ${activeFilter === 'all' ? styles.filterButtonActive : ''}`}
            aria-pressed={activeFilter === 'all'}
            onClick={() => handleFilterChange('all')}
          >
            All
          </button>
          <button
            type="button"
            className={`${styles.filterButton} ${activeFilter === 'practiced' ? styles.filterButtonActive : ''}`}
            aria-pressed={activeFilter === 'practiced'}
            onClick={() => handleFilterChange('practiced')}
          >
            Practiced
          </button>
          <button
            type="button"
            className={`${styles.filterButton} ${activeFilter === 'unpracticed' ? styles.filterButtonActive : ''}`}
            aria-pressed={activeFilter === 'unpracticed'}
            onClick={() => handleFilterChange('unpracticed')}
          >
            Unpracticed
          </button>
        </div>
        {!isAuthLoading && !user && (
          <p className={styles.authPrompt}>Log in with Google to save practiced clips.</p>
        )}
      </header>

      {error && (
        <div className={styles.errorBanner} role="alert">
          <strong>Error: </strong>
          <span>{error}</span>
        </div>
      )}

      {isLoading ? (
        <div className={styles.loading}>Loading library...</div>
      ) : (
        <div className={styles.videoGrid}>
          {visibleVideos.map((video) => (
            <article key={video.video_id} className={styles.videoCard}>
              <div className={styles.thumbnailWrapper}>
                <button
                  type="button"
                  className={`${styles.practicedToggle} ${practicedVideoIds.has(video.video_id) ? styles.practicedToggleActive : ''}`}
                  aria-pressed={practicedVideoIds.has(video.video_id)}
                  aria-label={
                    practicedVideoIds.has(video.video_id)
                      ? 'Marked as practiced. Click to unmark.'
                      : 'Mark clip as practiced.'
                  }
                  onClick={() => handlePracticedToggle(video.video_id)}
                  disabled={!user || isAuthLoading || updatingVideoIds.has(video.video_id)}
                >
                  {updatingVideoIds.has(video.video_id) ? '...' : '✓'}
                </button>
                <Link
                  href={`/practice/${video.video_id}`}
                  className={styles.thumbnailLink}
                  aria-label={`Open practice clip: ${video.title}`}
                >
                  <Image
                    src={
                      fallbackThumbnailVideoIds.has(video.video_id)
                        ? `https://img.youtube.com/vi/${video.video_id}/mqdefault.jpg`
                        : getNormalizedThumbnailUrl(video)
                    }
                    alt={video.title}
                    fill
                    sizes="(max-width: 768px) 100vw, (max-width: 1200px) 50vw, 33vw"
                    className={styles.thumbnail}
                    onError={() => {
                      setFallbackThumbnailVideoIds((previous) => {
                        if (previous.has(video.video_id)) {
                          return previous;
                        }

                        return new Set([...previous, video.video_id]);
                      });
                    }}
                  />
                </Link>
                <span className={styles.duration}>
                  {Math.floor(video.duration / 60)}:{String(video.duration % 60).padStart(2, '0')}
                </span>
              </div>
              <Link
                href={`/practice/${video.video_id}`}
                className={styles.cardContent}
                aria-label={`Practice ${video.title}`}
              >
                <h3 className={styles.cardTitle}>{video.title}</h3>
              </Link>
            </article>
          ))}
          
          {filteredVideos.length === 0 && !error && (
            <div className={styles.emptyState}>
              {videos.length === 0
                ? 'No videos found. Run the ingestion script to add some!'
                : 'No clips match the selected filter yet.'}
            </div>
          )}
        </div>
      )}
      {!isLoading && !error && canLoadMore && (
        <div className={styles.filterRow}>
          <button
            type="button"
            className={styles.filterButton}
            onClick={handleLoadMore}
            aria-label="Load more clips"
          >
            Load more ({Math.min(LOAD_MORE_STEP, filteredVideos.length - visibleCount)})
          </button>
        </div>
      )}
    </main>
  );
}
