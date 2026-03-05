'use client';

import React, { SyntheticEvent, useMemo, useRef } from 'react';
import ReactPlayer from 'react-player';
import styles from './VideoPlayer.module.css';

interface VideoPlayerProps {
  url: string;
  onProgress: (time: number) => void;
  playbackRate: number;
  isPlaying: boolean;
  onPlayStateChange: (playing: boolean) => void;
  onReady?: () => void;
}

const getNormalizedYoutubeUrl = (rawUrl: string): string => {
  const trimmedUrl = rawUrl.trim();
  if (!trimmedUrl) {
    return '';
  }

  const shortsMatch = trimmedUrl.match(/youtube\.com\/shorts\/([^?&/]+)/i);
  if (shortsMatch?.[1]) {
    return `https://www.youtube.com/watch?v=${shortsMatch[1]}`;
  }

  const shortLinkMatch = trimmedUrl.match(/youtu\.be\/([^?&/]+)/i);
  if (shortLinkMatch?.[1]) {
    return `https://www.youtube.com/watch?v=${shortLinkMatch[1]}`;
  }

  return trimmedUrl;
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const ReactPlayerAny = ReactPlayer as any;

const VideoPlayer: React.FC<VideoPlayerProps> = ({
  url,
  onProgress,
  playbackRate,
  isPlaying,
  onPlayStateChange,
  onReady,
}) => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const playerRef = useRef<any>(null);
  const playableUrl = useMemo(() => getNormalizedYoutubeUrl(url), [url]);

  const handleTimeUpdate = (event: SyntheticEvent<HTMLVideoElement>) => {
    onProgress(event.currentTarget.currentTime);
  };

  return (
    <div className={styles.playerShell}>
      <ReactPlayerAny
        key={playableUrl}
        ref={playerRef}
        src={playableUrl}
        width="100%"
        height="100%"
        controls
        playsInline
        playing={isPlaying}
        playbackRate={playbackRate}
        onReady={onReady}
        onPlay={() => onPlayStateChange(true)}
        onPause={() => onPlayStateChange(false)}
        onTimeUpdate={handleTimeUpdate}
      />
    </div>
  );
};

export default React.memo(VideoPlayer);
