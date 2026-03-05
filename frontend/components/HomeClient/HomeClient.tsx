'use client';

import { useState } from 'react';
import dynamic from 'next/dynamic';
import axios from 'axios';
import ClipInput from '@/components/ClipInput/ClipInput';
import TranscriptDisplay from '@/components/TranscriptDisplay/TranscriptDisplay';
import { TranscriptData } from '@/types';
import styles from './HomeClient.module.css';

const VideoPlayer = dynamic(() => import('@/components/VideoPlayer/VideoPlayer'), { ssr: false });
type PlaybackRate = 0.5 | 0.75 | 1;
const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000').replace(/\/$/, '');

export default function HomeClient() {
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [transcript, setTranscript] = useState<TranscriptData | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [playbackRate, setPlaybackRate] = useState<PlaybackRate>(1);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleUrlSubmit = async (url: string) => {
    setIsLoading(true);
    setError(null);
    setVideoUrl(null);
    setTranscript(null);
    setCurrentTime(0);
    setIsPlaying(false);

    try {
      const response = await axios.post(`${API_BASE_URL}/api/process`, { url });
      setTranscript(response.data);
      setVideoUrl(url);
    } catch (err: unknown) {
      console.error(err);
      if (axios.isAxiosError(err)) {
        setError(err.response?.data?.detail || 'Failed to process video. Please try again.');
      } else {
        setError('Failed to process video. Please try again.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <main className={styles.page}>
      <h1 className={styles.pageTitle}>NorthernLingo</h1>

      <ClipInput onUrlSubmit={handleUrlSubmit} isLoading={isLoading} />

      {error && (
        <div className={styles.errorBanner} role="alert">
          <strong>Error: </strong>
          <span>{error}</span>
        </div>
      )}

      {videoUrl && transcript && (
        <section className={styles.playerSection}>
          <h2 className={styles.videoTitle}>{transcript.title}</h2>
          <VideoPlayer
            url={videoUrl}
            onProgress={setCurrentTime}
            playbackRate={playbackRate}
            isPlaying={isPlaying}
            onPlayStateChange={setIsPlaying}
          />
          <TranscriptDisplay
            words={transcript.words}
            currentTime={currentTime}
            playbackRate={playbackRate}
            onPlaybackRateChange={setPlaybackRate}
            isPlaying={isPlaying}
            onPlayPauseToggle={() => setIsPlaying((previous) => !previous)}
          />
        </section>
      )}
    </main>
  );
}
