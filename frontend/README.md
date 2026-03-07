## NorthernLingo Frontend

Next.js frontend for browsing and practicing with video clips.

## Local Setup

1. Copy env template and fill values:
   - `cp .env.example .env.local` (macOS/Linux) or `copy .env.example .env.local` (Windows)
2. Add Firebase Web App config values to `.env.local`:
   - `NEXT_PUBLIC_FIREBASE_API_KEY`
   - `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN`
   - `NEXT_PUBLIC_FIREBASE_PROJECT_ID`
   - `NEXT_PUBLIC_FIREBASE_APP_ID`
   - Optional: `NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET`, `NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID`, `NEXT_PUBLIC_FIREBASE_MEASUREMENT_ID`
3. Ensure backend API is running at `NEXT_PUBLIC_API_BASE_URL` (default `http://localhost:8000`).

## Firebase Auth Setup (Google Login)

1. Create or open your Firebase project.
2. Add a Web App in Firebase project settings.
3. In **Authentication -> Sign-in method**, enable **Google**.
4. In **Authentication -> Settings -> Authorized domains**, add:
   - `localhost`
5. Copy the Firebase config values into `.env.local`.

## Run Locally

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Pre-Push Checks

Run these before pushing:

```bash
npm run lint
npm run build
```
