'use client';

import { useState, useEffect } from 'react';
import dynamic from 'next/dynamic';
import axios from 'axios';
import TranscriptDisplay from '@/components/TranscriptDisplay/TranscriptDisplay';
import { TranscriptData } from '@/types';
import { getApiBaseUrl, getApiErrorMessage } from '@/lib/api';
import { useAuthUser } from '@/lib/auth/useAuthUser';
import {
  PracticedAuthRequiredError,
  fetchPracticedVideoIds,
  setPracticedVideo,
} from '@/lib/practiced/api';
import styles from './PracticeClient.module.css';
import Link from 'next/link';

const VideoPlayer = dynamic(() => import('@/components/VideoPlayer/VideoPlayer'), { ssr: false });
type PlaybackRate = 0.5 | 0.75 | 1;
const API_BASE_URL = getApiBaseUrl();

interface PracticeClientProps {
  videoId: string;
}

export default function PracticeClient({ videoId }: PracticeClientProps) {
  const { user, isLoading: isAuthLoading } = useAuthUser();
  const [transcript, setTranscript] = useState<TranscriptData | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [playbackRate, setPlaybackRate] = useState<PlaybackRate>(1);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isPracticed, setIsPracticed] = useState(false);
  const [isPracticedUpdating, setIsPracticedUpdating] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [practicedError, setPracticedError] = useState<string | null>(null);

  useEffect(() => {
    const fetchVideo = async () => {
      try {
        const response = await axios.get(`${API_BASE_URL}/api/videos/${videoId}`);
        setTranscript(response.data);
      } catch (err: unknown) {
        console.error(err);
        if (axios.isAxiosError(err) && err.message === 'Network Error') {
          setError(getApiErrorMessage('Unable to reach the API server. Confirm backend URL and CORS settings.'));
        } else {
          setError('Failed to load video. Please try again.');
        }
      } finally {
        setIsLoading(false);
      }
    };

    fetchVideo();
  }, [videoId]);

  useEffect(() => {
    let isCancelled = false;

    const fetchPracticedState = async () => {
      if (isAuthLoading) {
        return;
      }

      if (!user) {
        setIsPracticed(false);
        setPracticedError(null);
        return;
      }

      try {
        const practicedIds = await fetchPracticedVideoIds([videoId]);
        if (!isCancelled) {
          setIsPracticed(practicedIds.has(videoId));
          setPracticedError(null);
        }
      } catch (err) {
        if (!isCancelled) {
          console.error(err);
          setPracticedError('Failed to load practiced-state.');
        }
      }
    };

    fetchPracticedState();

    return () => {
      isCancelled = true;
    };
  }, [isAuthLoading, user, videoId]);

  const handlePracticedToggle = async () => {
    if (!user || isPracticedUpdating) {
      return;
    }

    const nextPracticed = !isPracticed;
    setIsPracticed(nextPracticed);
    setIsPracticedUpdating(true);
    setPracticedError(null);

    try {
      await setPracticedVideo(videoId, nextPracticed);
    } catch (err) {
      setIsPracticed(!nextPracticed);
      if (err instanceof PracticedAuthRequiredError) {
        setPracticedError('Please log in to mark this clip as practiced.');
      } else {
        setPracticedError('Failed to update practiced-state. Please try again.');
      }
    } finally {
      setIsPracticedUpdating(false);
    }
  };

  if (isLoading) {
    return <div className={styles.loading}>Loading video...</div>;
  }

  if (error || !transcript) {
    return (
      <div className={styles.errorBanner} role="alert">
        <strong>Error: </strong>
        <span>{error || 'Video not found'}</span>
        <br />
        <Link href="/" className={styles.backLink}>Back to Library</Link>
      </div>
    );
  }

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <Link href="/" className={styles.backLink}>← Back to Library</Link>
        <h1 className={styles.videoTitle}>{transcript.title}</h1>
      </header>

      <section className={styles.playerSection}>
        <div className={styles.videoPane}>
          <VideoPlayer
            url={`https://www.youtube.com/watch?v=${transcript.video_id}`}
            onProgress={setCurrentTime}
            playbackRate={playbackRate}
            isPlaying={isPlaying}
            onPlayStateChange={setIsPlaying}
          />
        </div>
        <div className={styles.transcriptPane}>
          <TranscriptDisplay
            words={transcript.words}
            currentTime={currentTime}
            playbackRate={playbackRate}
            onPlaybackRateChange={setPlaybackRate}
            isPlaying={isPlaying}
            onPlayPauseToggle={() => setIsPlaying((previous) => !previous)}
            isPracticed={isPracticed}
            isPracticedUpdating={isPracticedUpdating}
            isPracticedDisabled={!user || isAuthLoading}
            onPracticedToggle={handlePracticedToggle}
            practicedHint={
              practicedError ??
              (!isAuthLoading && !user ? 'Log in to mark this clip as practiced.' : undefined)
            }
          />
        </div>
      </section>
    </main>
  );
}
