import React, { useState } from 'react';
import styles from './ClipInput.module.css';

interface ClipInputProps {
  onUrlSubmit: (url: string) => void;
  isLoading: boolean;
}

const ClipInput: React.FC<ClipInputProps> = ({ onUrlSubmit, isLoading }) => {
  const [url, setUrl] = useState('');

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!url.trim()) {
      return;
    }

    onUrlSubmit(url);
  };

  return (
    <form onSubmit={handleSubmit} className={styles.form}>
      <input
        type="text"
        value={url}
        onChange={(event) => setUrl(event.target.value)}
        placeholder="Paste YouTube URL here..."
        className={styles.inputField}
        disabled={isLoading}
        aria-label="YouTube URL input"
      />
      <button
        type="submit"
        disabled={isLoading || !url.trim()}
        className={styles.submitButton}
      >
        {isLoading ? 'Processing...' : 'Load'}
      </button>
    </form>
  );
};

export default ClipInput;
