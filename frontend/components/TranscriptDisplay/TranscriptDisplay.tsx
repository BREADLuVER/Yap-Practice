import React, { useEffect, useMemo, useRef, useState } from 'react';
import styles from './TranscriptDisplay.module.css';

interface Word {
  word: string;
  start: number;
  end: number;
}

interface TranscriptDisplayProps {
  words: Word[];
  currentTime: number;
  playbackRate: 0.5 | 0.75 | 1;
  onPlaybackRateChange: (rate: 0.5 | 0.75 | 1) => void;
  isPlaying: boolean;
  onPlayPauseToggle: () => void;
  isPracticed: boolean;
  isPracticedUpdating: boolean;
  isPracticedDisabled: boolean;
  onPracticedToggle: () => void;
  practicedHint?: string;
}

interface TranscriptLine {
  id: string;
  start: number;
  end: number;
  words: Word[];
}

const PAUSE_BREAK_SECONDS = 0.5;
const MAX_WORDS_PER_LINE = 10;
const MIN_WORDS_PER_LINE = 3;
const MAX_LINE_CHARS = 52;
const MAX_LINE_DURATION_SECONDS = 4.2;
const SPEED_OPTIONS: Array<0.5 | 0.75 | 1> = [0.5, 0.75, 1];

const endsSentence = (word: string): boolean => /[.!?]["']?$/.test(word.trim());
const isSoftPunctuation = (word: string): boolean => /[,;:]["']?$/.test(word.trim());

const estimateLineChars = (lineWords: Word[]): number =>
  lineWords.reduce((acc, lineWord) => acc + lineWord.word.trim().length + 1, 0);

const toTranscriptLines = (words: Word[]): TranscriptLine[] => {
  if (!words.length) {
    return [];
  }

  const lines: TranscriptLine[] = [];
  let buffer: Word[] = [];

  const flushBuffer = () => {
    if (!buffer.length) {
      return;
    }

    lines.push({
      id: `${lines.length}-${buffer[0].start}`,
      start: buffer[0].start,
      end: buffer[buffer.length - 1].end,
      words: buffer,
    });

    buffer = [];
  };

  words.forEach((word, index) => {
    const previousWord = index > 0 ? words[index - 1] : null;
    const pauseGap = previousWord ? word.start - previousWord.end : 0;
    const shouldBreakBeforeWord =
      buffer.length >= MIN_WORDS_PER_LINE && pauseGap > PAUSE_BREAK_SECONDS;

    if (shouldBreakBeforeWord) {
      flushBuffer();
    }

    buffer.push(word);

    const isLastWord = index === words.length - 1;
    const reachedLineLength = buffer.length >= MAX_WORDS_PER_LINE;
    const reachedLineCharLimit = estimateLineChars(buffer) >= MAX_LINE_CHARS;
    const lineDuration = buffer[buffer.length - 1].end - buffer[0].start;
    const reachedLineDuration = lineDuration >= MAX_LINE_DURATION_SECONDS;
    const isSentenceEnd = endsSentence(word.word);
    const isSoftBreakPoint = isSoftPunctuation(word.word);
    const canBreakNaturally = buffer.length >= MIN_WORDS_PER_LINE;

    if (
      isLastWord ||
      reachedLineLength ||
      (canBreakNaturally && isSentenceEnd) ||
      (canBreakNaturally && reachedLineCharLimit && isSoftBreakPoint) ||
      (canBreakNaturally && reachedLineDuration && isSoftBreakPoint)
    ) {
      flushBuffer();
    }
  });

  const mergedLines: TranscriptLine[] = [];
  lines.forEach((line) => {
    const previousLine = mergedLines[mergedLines.length - 1];
    const currentChars = estimateLineChars(line.words);
    const isTinyLine = line.words.length <= 2 || currentChars <= 14;

    if (!previousLine || !isTinyLine) {
      mergedLines.push(line);
      return;
    }

    previousLine.words = [...previousLine.words, ...line.words];
    previousLine.end = line.end;
  });

  return mergedLines.map((line, lineIndex) => ({
    ...line,
    id: `${lineIndex}-${line.start}`,
  }));
};

const TranscriptDisplay: React.FC<TranscriptDisplayProps> = ({
  words,
  currentTime,
  playbackRate,
  onPlaybackRateChange,
  isPlaying,
  onPlayPauseToggle,
  isPracticed,
  isPracticedUpdating,
  isPracticedDisabled,
  onPracticedToggle,
  practicedHint,
}) => {
  const activeLineRef = useRef<HTMLParagraphElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const transcriptLines = useMemo(() => toTranscriptLines(words), [words]);
  const [isCompactMobile, setIsCompactMobile] = useState(() =>
    typeof window !== 'undefined' ? window.matchMedia('(max-width: 767px)').matches : false,
  );

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }

    const media = window.matchMedia('(max-width: 767px)');
    const handleMediaChange = (event: MediaQueryListEvent) => {
      setIsCompactMobile(event.matches);
    };

    media.addEventListener('change', handleMediaChange);
    return () => {
      media.removeEventListener('change', handleMediaChange);
    };
  }, []);

  const activeLineIndex = useMemo(
    () =>
      transcriptLines.findIndex(
        (line) => currentTime >= line.start && currentTime <= line.end,
      ),
    [currentTime, transcriptLines],
  );

  useEffect(() => {
    if (isCompactMobile) {
      return;
    }

    if (!activeLineRef.current || !containerRef.current) {
      return;
    }

    activeLineRef.current.scrollIntoView({
      behavior: 'smooth',
      block: 'center',
    });
  }, [activeLineIndex, isCompactMobile]);

  const renderedLines = useMemo(() => {
    if (!isCompactMobile) {
      return transcriptLines.map((line, index) => ({ line, index }));
    }

    if (transcriptLines.length === 0) {
      return [];
    }

    if (activeLineIndex < 0) {
      return transcriptLines.slice(0, 3).map((line, index) => ({ line, index }));
    }

    const startIndex = Math.max(0, activeLineIndex - 1);
    const endIndex = Math.min(transcriptLines.length - 1, activeLineIndex + 1);
    const visible: Array<{ line: TranscriptLine; index: number }> = [];

    for (let index = startIndex; index <= endIndex; index += 1) {
      visible.push({ line: transcriptLines[index], index });
    }
    return visible;
  }, [activeLineIndex, isCompactMobile, transcriptLines]);

  return (
    <div
      ref={containerRef}
      className={styles.captionPanel}
      role="region"
      aria-label="Timed transcript"
    >
      <div className={styles.controlDock}>
        <div className={styles.controlDockLeft}>
        <button
          type="button"
          className={styles.playPauseButton}
          onClick={onPlayPauseToggle}
          aria-label={isPlaying ? 'Pause video' : 'Play video'}
        >
          {isPlaying ? 'Pause' : 'Play'}
        </button>
        </div>
        <div className={styles.controlDockRight}>
          <div className={styles.speedControl} aria-label="Playback speed control">
            {SPEED_OPTIONS.map((speed) => {
              const isActiveSpeed = playbackRate === speed;
              const speedButtonClassName = [
                styles.speedButton,
                isActiveSpeed ? styles.speedButtonActive : '',
              ]
                .filter(Boolean)
                .join(' ');

              return (
                <button
                  key={speed}
                  type="button"
                  className={speedButtonClassName}
                  aria-pressed={isActiveSpeed}
                  onClick={() => onPlaybackRateChange(speed)}
                >
                  {speed}x
                </button>
              );
            })}
          </div>
        </div>
      </div>
      <div className={styles.captionTrack}>
        {renderedLines.map(({ line, index: lineIndex }) => {
          const isActiveLine = lineIndex === activeLineIndex;
          const hasActiveLine = activeLineIndex >= 0;
          const lineDistance = hasActiveLine
            ? Math.abs(lineIndex - activeLineIndex)
            : 99;

          const lineClassNames = [
            styles.captionLine,
            isActiveLine ? styles.lineActive : '',
            !isActiveLine && lineDistance === 1 ? styles.lineNear : '',
            !isActiveLine && lineDistance === 2 ? styles.lineFar : '',
            !isActiveLine && lineDistance >= 3 ? styles.lineDistant : '',
          ]
            .filter(Boolean)
            .join(' ');

          return (
            <p
              key={line.id}
              ref={isActiveLine ? activeLineRef : null}
              className={lineClassNames}
            >
              {line.words.map((word, wordIndex) => {
                const isCurrentWord =
                  isActiveLine &&
                  currentTime >= word.start &&
                  currentTime <= word.end;

                const wordClassNames = [
                  styles.captionWord,
                  isCurrentWord ? styles.wordCurrent : '',
                ]
                  .filter(Boolean)
                  .join(' ');

                return (
                  <span
                    key={`${line.id}-${word.start}-${wordIndex}`}
                    className={wordClassNames}
                  >
                    {word.word}
                  </span>
                );
              })}
            </p>
          );
        })}
      </div>
      <div className={styles.practicedDock}>
        {practicedHint ? <p className={styles.practicedHint}>{practicedHint}</p> : null}
        <button
          type="button"
          className={`${styles.practicedButton} ${isPracticed ? styles.practicedButtonActive : ''}`}
          aria-pressed={isPracticed}
          aria-label={
            isPracticed
              ? 'Marked as practiced. Click to unmark.'
              : 'Mark this clip as practiced.'
          }
          onClick={onPracticedToggle}
          disabled={isPracticedDisabled || isPracticedUpdating}
        >
          {isPracticedUpdating ? '...' : '✓'}
        </button>
      </div>
    </div>
  );
};

export default TranscriptDisplay;
