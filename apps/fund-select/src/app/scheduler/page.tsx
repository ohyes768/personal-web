import { redirect } from 'next/navigation';

/** Keep existing bookmarks: management now opens over the fund list. */
export default function SchedulerPage() {
  redirect('/bond?scheduler=1');
}
