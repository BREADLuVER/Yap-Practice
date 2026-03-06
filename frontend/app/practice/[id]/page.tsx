import PracticeClient from '@/components/PracticeClient/PracticeClient';

export default async function PracticePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <PracticeClient videoId={id} />;
}
