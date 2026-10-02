import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { KART, Yukleniyor, sayiYaz } from '@/components/aiAsistan/ortak';
import { hataMetni, type Asistan, type AsistanApi, type Kullanim as KullanimVerisi } from '@/lib/aiAsistan';

/**
 * Faz 5A — kullanım ve maliyet: bu ay yanıtlanan mesaj, yapay zekâya giden mesaj, aya dahil
 * hak ve kalan, düşülen kredi (blok başına), insana devir, bugünkü mesaj / günlük sınır,
 * jeton sayıları ve son 30 günün mesaj grafiği.
 */

export default function Kullanim({ api, asistan }: { api: AsistanApi; asistan: Asistan }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [veri, setVeri] = useState<KullanimVerisi | null>(null);

  useEffect(() => {
    let iptal = false;
    api
      .kullanim(asistan.id, 30)
      .then((v) => {
        if (!iptal) setVeri(v);
      })
      .catch((e) => toast.error(hataMetni(t, e)));
    return () => {
      iptal = true;
    };
  }, [api, asistan.id, t]);

  if (!veri) return <Yukleniyor />;
  const dahil = veri.sinirlar.aylik_mesaj;
  const kalan = Math.max(0, dahil - veri.ay.ai_mesaj);
  const enCok = Math.max(1, ...veri.gunluk.map((g) => g.mesaj));
  const kartlar: { anahtar: string; deger: string; alt?: string }[] = [
    { anahtar: 'ayMesaj', deger: sayiYaz(veri.ay.mesaj, dil), alt: t('aiAsistan.kullanim.aiMesaj', { sayi: veri.ay.ai_mesaj }) },
    ...(veri.ajans
      ? []
      : [
          { anahtar: 'dahil', deger: `${sayiYaz(kalan, dil)} / ${sayiYaz(dahil, dil)}`, alt: t('aiAsistan.kullanim.dahilAlt') },
          {
            anahtar: 'kredi',
            deger: sayiYaz(veri.ay.kredi, dil, 2),
            alt: veri.blok_kredi > 0 ? t('aiAsistan.kullanim.blok', { mesaj: veri.blok_mesaj, kredi: veri.blok_kredi }) : t('aiAsistan.kullanim.krediYok'),
          },
        ]),
    { anahtar: 'devir', deger: sayiYaz(veri.ay.devir, dil) },
    { anahtar: 'bugun', deger: `${sayiYaz(veri.bugun.mesaj, dil)} / ${sayiYaz(veri.sinirlar.gunluk_mesaj, dil)}` },
    { anahtar: 'jeton', deger: sayiYaz(veri.ay.token_giris + veri.ay.token_cikis, dil), alt: t('aiAsistan.kullanim.jetonAlt', { giris: veri.ay.token_giris, cikis: veri.ay.token_cikis }) },
  ];
  if (veri.kredi_bakiyesi !== null) kartlar.push({ anahtar: 'bakiye', deger: sayiYaz(veri.kredi_bakiyesi, dil, 2) });

  return (
    <div className="space-y-5" data-testid="ai-kullanim">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {kartlar.map((k) => (
          <div key={k.anahtar} className={`${KART} p-4`} data-kart={k.anahtar}>
            <p className="text-xs text-muted-foreground">{t(`aiAsistan.kullanim.${k.anahtar}`)}</p>
            <p className="mt-1 text-xl font-semibold" dir="ltr">
              {k.deger}
            </p>
            {k.alt && <p className="mt-0.5 text-[11px] text-muted-foreground">{k.alt}</p>}
          </div>
        ))}
      </div>
      <div className={`${KART} p-4`}>
        <p className="mb-3 text-sm font-medium">{t('aiAsistan.kullanim.grafik')}</p>
        {veri.gunluk.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('aiAsistan.kullanim.bos')}</p>
        ) : (
          <div className="flex h-32 items-end gap-1" dir="ltr" role="img" aria-label={t('aiAsistan.kullanim.grafik')}>
            {veri.gunluk.map((g) => (
              <div key={g.gun} className="flex-1 rounded-t bg-purple-400/60" style={{ height: `${Math.max(4, (g.mesaj / enCok) * 100)}%` }} title={`${g.gun}: ${g.mesaj}`} />
            ))}
          </div>
        )}
      </div>
      <p className="text-xs text-muted-foreground">{t(veri.ajans ? 'aiAsistan.kullanim.notAjans' : 'aiAsistan.kullanim.not')}</p>
    </div>
  );
}
