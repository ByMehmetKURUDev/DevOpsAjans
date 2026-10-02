import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ExternalLink, Info } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { DURUM_RENGI, KART, Rozet, Yukleniyor, sayiYaz } from '@/components/epostaPazarlama/ortak';
import { hataMetni, tarihYaz, type Meta, type Ozet as OzetVeri, type PazarlamaApi } from '@/lib/epostaPazarlama';

/** Faz 5M — özet: kişiler (izin dağılımı), son 30 gün gönderim sağlığı, kota, İYS bilgisi, son kampanyalar. */
export default function Ozet({ api, meta, gecis }: { api: PazarlamaApi; meta: Meta; gecis: (s: string) => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [veri, setVeri] = useState<OzetVeri | null>(null);
  const [hata, setHata] = useState<string | null>(null);

  useEffect(() => {
    let iptal = false;
    api
      .ozet()
      .then((v) => !iptal && setVeri(v))
      .catch((e) => !iptal && setHata(hataMetni(t, e)));
    return () => {
      iptal = true;
    };
  }, [api, t]);

  if (hata) return <p className="text-sm text-rose-300">{hata}</p>;
  if (!veri) return <Yukleniyor />;
  const izin = veri.kisiler.izin;
  const g = veri.son_30_gun;
  const sikayetOrani = g.gonderilen ? g.sikayet / g.gonderilen : 0;
  const kartlar = [
    { anahtar: 'kisi', deger: veri.kisiler.toplam, alt: t('epostaPazarlama.ozet.izinli', { sayi: sayiYaz(izin.izinli || 0, dil) }) },
    { anahtar: 'kurumsal', deger: veri.kisiler.tur.kurumsal || 0, alt: t('epostaPazarlama.ozet.bireysel', { sayi: sayiYaz(veri.kisiler.tur.bireysel || 0, dil) }) },
    { anahtar: 'gonderilen', deger: g.gonderilen, alt: t('epostaPazarlama.ozet.son30') },
    { anahtar: 'bastirilan', deger: veri.kisiler.bastirilan, alt: t('epostaPazarlama.ozet.bastirmaAlt') },
  ];

  return (
    <div className="space-y-5" data-testid="ep-ozet">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {kartlar.map((k) => (
          <div key={k.anahtar} className={`${KART} p-4`}>
            <p className="text-xs text-muted-foreground">{t(`epostaPazarlama.ozet.kart.${k.anahtar}`)}</p>
            <p className="mt-1 text-2xl font-bold" data-testid={`ep-ozet-${k.anahtar}`}>
              {sayiYaz(k.deger, dil)}
            </p>
            <p className="mt-1 text-xs text-muted-foreground">{k.alt}</p>
          </div>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className={`${KART} p-5`}>
          <h3 className="font-semibold">{t('epostaPazarlama.ozet.saglik')}</h3>
          <ul className="mt-3 space-y-2 text-sm">
            <li className="flex justify-between gap-3">
              <span className="text-muted-foreground">{t('epostaPazarlama.ozet.kota')}</span>
              <span>
                {sayiYaz(meta.sinirlar.kullanilan, dil)} / {sayiYaz(meta.sinirlar.aylik, dil)}
              </span>
            </li>
            <li className="flex justify-between gap-3">
              <span className="text-muted-foreground">{t('epostaPazarlama.ozet.kisiSiniri')}</span>
              <span>
                {sayiYaz(meta.sinirlar.kisi_sayisi, dil)} / {sayiYaz(meta.sinirlar.kisi, dil)}
              </span>
            </li>
            <li className="flex justify-between gap-3">
              <span className="text-muted-foreground">{t('epostaPazarlama.ozet.sikayet')}</span>
              <span className={sikayetOrani > 0.003 ? 'text-rose-300' : ''}>
                {sayiYaz(g.sikayet, dil)} · {sayiYaz(g.geri_donen, dil)} {t('epostaPazarlama.ozet.geriDonen')}
              </span>
            </li>
          </ul>
          <p className="mt-3 text-xs text-muted-foreground">{t('epostaPazarlama.ozet.esikNotu')}</p>
        </div>

        <div className={`${KART} p-5`} data-testid="ep-iys-bilgi">
          <h3 className="flex items-center gap-2 font-semibold">
            <Info className="h-4 w-4 text-sky-300" aria-hidden="true" />
            {t('epostaPazarlama.iys.baslik')}
          </h3>
          <p className="mt-2 text-sm text-muted-foreground">{t('epostaPazarlama.iys.metin')}</p>
          <ul className="mt-2 list-disc space-y-1 ps-5 text-sm text-muted-foreground">
            <li>{t('epostaPazarlama.iys.madde1')}</li>
            <li>{t('epostaPazarlama.iys.madde2')}</li>
            <li>{t('epostaPazarlama.iys.madde3')}</li>
          </ul>
          <a className="mt-3 inline-flex items-center gap-1 text-sm text-purple-200 hover:underline" href="https://iys.org.tr" target="_blank" rel="noopener noreferrer">
            iys.org.tr <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
          </a>
        </div>
      </div>

      <div className={`${KART} p-5`}>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h3 className="font-semibold">{t('epostaPazarlama.ozet.sonKampanyalar')}</h3>
          <Button size="sm" variant="outline" className="!bg-transparent border-white/20" onClick={() => gecis('kampanyalar')}>
            {t('epostaPazarlama.alt.kampanyalar')}
          </Button>
        </div>
        {veri.son_kampanyalar.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('epostaPazarlama.kampanya.bos')}</p>
        ) : (
          <ul className="divide-y divide-white/5">
            {veri.son_kampanyalar.map((k) => (
              <li key={k.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
                <span className="min-w-0 truncate">{k.ad}</span>
                <span className="flex items-center gap-2 text-xs text-muted-foreground">
                  {tarihYaz(k.bitis_at || k.baslangic_at || k.zamanlanan_at, dil)}
                  <Rozet renk={DURUM_RENGI[k.durum]}>{t(`epostaPazarlama.durum.${k.durum}`)}</Rozet>
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
