'use client';

import { useState } from 'react';
import DirectoryDialog from '../community/DirectoryDialog';
import { RentalCandidateChoice, type RentalReview } from './RentalAssociationReview';
import { XingfuliProbe } from './XingfuliProbe';
import { rentalDataChanged } from '../../lib/rental-sources';

export default function RentalReviewDialog({ item, onClose, onChanged }: {
  item: RentalReview; onClose: () => void; onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function decide(action: 'bind' | 'skip' | 'reopen') {
    setBusy(true); setError('');
    try {
      const response = await fetch(`/api/map/rentals/association-tasks/${encodeURIComponent(item.community_id)}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action }),
      });
      const payload = await response.json();
      if (!response.ok || !payload.success) throw new Error(payload.detail || '保存失败，请重试');
      rentalDataChanged(); onChanged(); onClose();
    } catch (e) { setError(e instanceof Error ? e.message : '保存失败'); }
    finally { setBusy(false); }
  }
  return <DirectoryDialog title={item.community_name} onClose={onClose}>
    {error && <p role="alert" className="directory-warning">{error}</p>}
    <RentalCandidateChoice item={item} selected="" busy={busy} onSelect={() => {}} onDecide={action => void decide(action)} />
    {item.reason !== 'skipped' && <XingfuliProbe communityId={item.community_id} onChanged={() => { onChanged(); onClose(); }} />}
  </DirectoryDialog>;
}
