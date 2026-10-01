import { Fragment } from 'react';

/**
 * Düz metni çizer, içindeki http/https adreslerini bağlantıya çevirir.
 *
 * GÜVENLİK: HTML hiçbir zaman çizilmiyor (`dangerouslySetInnerHTML` yok);
 * metin React metin düğümü olarak kaçışlanıyor — `<script>` ekranda yazı
 * olarak görünür. Bağlantı yalnız `http://` ya da `https://` ile başlayan
 * parçadan kuruluyor (javascript:, data: vb. asla) ve
 * `rel="noopener noreferrer nofollow"` + yeni sekme.
 */
const ADRES = /\bhttps?:\/\/[^\s<>"'`]+/gi;
// Cümle sonundaki noktalama bağlantıya dahil olmasın: "bakın: https://x.com/a."
const SON_NOKTALAMA = /[.,;:!?)\]}»"'’”]+$/;

export function parcala(metin: string): { tur: 'metin' | 'baglanti'; deger: string }[] {
  const parcalar: { tur: 'metin' | 'baglanti'; deger: string }[] = [];
  let son = 0;
  for (const eslesme of metin.matchAll(ADRES)) {
    const bas = eslesme.index ?? 0;
    let adres = eslesme[0];
    const fazla = adres.match(SON_NOKTALAMA)?.[0] ?? '';
    // Kapanan parantez adresin kendi parçasıysa (wiki/Foo_(bar)) bırak.
    if (fazla && !(fazla === ')' && adres.includes('('))) adres = adres.slice(0, adres.length - fazla.length);
    if (bas > son) parcalar.push({ tur: 'metin', deger: metin.slice(son, bas) });
    let gecerli = false;
    try {
      const u = new URL(adres);
      gecerli = u.protocol === 'http:' || u.protocol === 'https:';
    } catch {
      gecerli = false;
    }
    parcalar.push({ tur: gecerli ? 'baglanti' : 'metin', deger: adres });
    son = bas + adres.length;
  }
  if (son < metin.length) parcalar.push({ tur: 'metin', deger: metin.slice(son) });
  return parcalar;
}

export default function BaglantiliMetin({ metin, className }: { metin: string; className?: string }) {
  return (
    <span className={className}>
      {parcala(metin).map((p, i) =>
        p.tur === 'baglanti' ? (
          <a
            key={i}
            href={p.deger}
            target="_blank"
            rel="noopener noreferrer nofollow"
            className="underline decoration-dotted underline-offset-2 break-all hover:opacity-80"
            data-mesaj-baglanti
          >
            {p.deger}
          </a>
        ) : (
          <Fragment key={i}>{p.deger}</Fragment>
        )
      )}
    </span>
  );
}
