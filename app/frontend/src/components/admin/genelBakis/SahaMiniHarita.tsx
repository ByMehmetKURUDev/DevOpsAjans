import { useMemo, useState } from 'react';

import OsmHarita, { type HaritaIsareti } from '@/components/harita/OsmHarita';
import type { SahaNoktasi } from '@/lib/yonetimOzeti';

/**
 * Faz 11F — Genel bakış › Saha kartındaki küçük harita: bugünkü etkin iş emirleri, adresin işaretlenmiş
 * yerinde (teknisyen konumu yok). Ayrı parça: yalnız işaretli adres varsa yüklenir. Sayfa içinde durduğu
 * için dokunmatikte tek parmak sayfayı kaydırır, harita iki parmakla; düğmeler kapalı (karta sığsın).
 */
export default function SahaMiniHarita({
  noktalar,
  renkler,
  acilRengi,
  etiket,
}: {
  noktalar: SahaNoktasi[];
  renkler: Record<string, string>;
  acilRengi: string;
  etiket: string;
}) {
  const [secili, setSecili] = useState<number | null>(null);
  const isaretler = useMemo<HaritaIsareti[]>(
    () =>
      noktalar.map((n) => ({
        id: n.id,
        enlem: n.enlem,
        boylam: n.boylam,
        renk: n.acil ? acilRengi : renkler[n.durum] || '#38d1ff',
        etiket: `${n.no} · ${n.baslik}`,
        nabiz: n.acil || n.durum === 'iste',
      })),
    [noktalar, renkler, acilRengi],
  );
  return (
    <OsmHarita
      isaretler={isaretler}
      secili={secili}
      onSec={(id) => setSecili((s) => (s === Number(id) ? null : Number(id)))}
      sigdirAnahtari={noktalar.map((n) => n.id).join(',')}
      enFazlaYakinlik={14}
      jest="sayfa"
      kontroller={false}
      className="gb-saha-harita"
      etiket={etiket}
      testid="gb-saha-harita"
    />
  );
}
