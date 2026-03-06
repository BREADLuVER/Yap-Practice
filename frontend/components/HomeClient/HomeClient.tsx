'use client';

import { useState, useEffect } from 'react';
import axios from 'axios';
import Link from 'next/link';
import { VideoSummary } from '@/types';
import { getApiBaseUrl, getApiErrorMessage } from '@/lib/api';
import styles from './HomeClient.module.css';

const API_BASE_URL = getApiBaseUrl();

export default function HomeClient() {
  const [videos, setVideos] = useState<VideoSummary[]>([]);
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

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.pageTitle}>NorthernLingo</h1>
        <p className={styles.subtitle}>Select a clip to start practicing</p>
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
          {videos.map((video) => (
            <Link key={video.video_id} href={`/practice/${video.video_id}`} className={styles.videoCard}>
              <div className={styles.thumbnailWrapper}>
                <img 
                  src={video.thumbnailUrl || `https://img.youtube.com/vi/${video.video_id}/mqdefault.jpg`} 
                  alt={video.title} 
                  className={styles.thumbnail}
                />
                <span className={styles.duration}>
                  {Math.floor(video.duration / 60)}:{String(video.duration % 60).padStart(2, '0')}
                </span>
              </div>
              <div className={styles.cardContent}>
                <h3 className={styles.cardTitle}>{video.title}</h3>
              </div>
            </Link>
          ))}
          
          {videos.length === 0 && !error && (
            <div className={styles.emptyState}>
              No videos found. Run the ingestion script to add some!
            </div>
          )}
        </div>
      )}
    </main>
  );
}
