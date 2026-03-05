export interface Word {
  word: string;
  start: number;
  end: number;
}

export interface TranscriptData {
  video_id: string;
  title: string;
  words: Word[];
  full_text: string;
}
