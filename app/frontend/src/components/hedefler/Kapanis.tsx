import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2, Lock } from 'lucide-react';

import { Button } from '@/components/ui/button';
import type { BolumProps } from '@/components/hedefler/Liste';
import { Alan, Bos, HataSatiri, KART, METIN_ALANI, Not, Rozet, SECIM, Yukleniyor } from '@/components/hedefler/ortak';
import { degerYaz, donemAdi, hataMetni, yuzde, zamanYaz, type Kapanis as KapanisVerisi } from '@/lib/okr';

/**
 * Faz 6O — dönem kapanışı: her KR'ye 0–1 puan (öneri: ilerleme, 0,1 adım), kapanış notu, açık KR'leri (ilerleme < 1)
 * seçili sonraki döneme KOPYA olarak taşıma (eski KR'ye bağlı — check-in geçmişi ayrıntıda görünür). Kapanmış dönemde
 * yalnız özet.
 */
export default function Kapanis({ api, meta, donem, surum, yenile }: BolumProps) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [v, setV] = useState<KapanisVerisi | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [puanlar, setPuanlar] = useState<Record<number, string>>({});
  const [tasinacak, setTasinacak] = useState<Record<number, boolean>>({});
  const [notu, setNotu] = useState('');
  const [tasi, setTasi] = useState(true);
  const [hedefDonem, setHedefDonem] = useState('');
  const [mesgul, setMesgul] = useState(false);
  const [sonuc, setSonuc] = useState<string | null>(null);

  useEffect(() => {
    let iptal = false;
    setHata(null);
    api
      .kapanis(donem.id)
      .then((r) => {
        if (iptal) return;
        setV(r);
        const p: Record<number, string> = {};
        const s: Record<number, boolean> = {};
        for (const h of r.hedefler) for (const k of h.krler) {
          p[k.id] = String(k.kapanis_puani ?? k.onerilen_puan ?? 0);
          s[k.id] = !!k.acik;
        }
        setPuanlar(p);
        setTasinacak(s);
        setHedefDonem(r.hedef_donemler[r.hedef_donemler.length - 1]?.id ? String(r.hedef_donemler[r.hedef_donemler.length - 1].id) : '');
      })
      .catch((e) => !iptal && setHata(hataMetni(t, e)));
    return () => {
      iptal = true;
    };
  }, [api, donem.id, surum, t]);

  const kapat = async () => {
    if (!v || !window.confirm(t('hedefler.kapanis.onay'))) return;
    setMesgul(true);
    setHata(null);
    try {
      const r = await api.kapat(donem.id, {
        puanlar: Object.fromEntries(Object.entries(puanlar).map(([k, x]) => [k, Number(String(x).replace(',', '.'))])),
        kapanis_notu: notu,
        tasi: tasi && !!hedefDonem,
        hedef_donem_id: tasi && hedefDonem ? Number(hedefDonem) : null,
        tasinacaklar: Object.entries(tasinacak).filter(([, x]) => x).map(([k]) => Number(k)),
      });
      setSonuc(t('hedefler.kapanis.tamam', { hedef: r.tasinan_hedef, kr: r.tasinan_kr }));
      yenile();
    } catch (e) {
      setHata(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  if (hata && !v) return <HataSatiri hata={hata} />;
  if (!v) return <Yukleniyor />;
  const kapali = v.donem.durum === 'kapandi';
  return (
    <div className="grid gap-4" data-testid="okr-kapanis">
      {sonuc && <Not testid="okr-kapanis-sonuc">{sonuc}</Not>}
      {kapali ? (
        <div className={`${KART} grid gap-1 p-4 text-sm`}>
          <p className="flex items-center gap-2 font-semibold">
            <Lock className="h-4 w-4" aria-hidden="true" />
            {t('hedefler.kapanis.kapandiBilgi', { zaman: zamanYaz(v.donem.kapandi_at, dil), kisi: v.donem.kapatan || '—' })}
          </p>
          {v.donem.kapanis_notu && <p className="whitespace-pre-line break-words text-white/85">{v.donem.kapanis_notu}</p>}
        </div>
      ) : (
        <Not>{t('hedefler.kapanis.aciklama')}</Not>
      )}
      {v.hedefler.length === 0 && <Bos>{t('hedefler.liste.bos')}</Bos>}
      {v.hedefler.map((h) => (
        <section key={h.id} className={`${KART} p-4`}>
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <h4 className="min-w-0 break-words font-semibold">{h.baslik}</h4>
            <span className="text-sm tabular-nums">{yuzde(h.ilerleme, dil)}</span>
          </div>
          <ul className="grid gap-2">
            {h.krler.map((k) => (
              <li key={k.id} className="grid gap-2 rounded-lg border border-white/5 p-2 sm:grid-cols-[1fr_auto_auto] sm:items-center" data-testid="okr-kapanis-kr">
                <span className="min-w-0 text-sm">
                  <span className="block break-words">{k.baslik}</span>
                  <span className="block text-xs text-muted-foreground">
                    {k.tur === 'kilometre'
                      ? t('hedefler.kr.kilometreSayisi', { tamam: k.kilometre_tamam, toplam: k.kilometre_toplam })
                      : `${degerYaz(k, k.mevcut, dil, t)} / ${degerYaz(k, k.hedef, dil, t)}`}{' '}
                    · {yuzde(k.ilerleme, dil)}
                  </span>
                </span>
                {kapali ? (
                  <Rozet>{t('hedefler.kapanis.puanKisa', { puan: k.kapanis_puani ?? '—' })}</Rozet>
                ) : (
                  <>
                    <label className="flex items-center gap-2 text-xs">
                      {t('hedefler.kapanis.puan')}
                      <input
                        className="h-9 w-20 rounded-md border border-white/10 bg-black/40 px-2 text-sm text-white"
                        type="number"
                        min={0}
                        max={1}
                        step={0.1}
                        value={puanlar[k.id] ?? ''}
                        onChange={(e) => setPuanlar({ ...puanlar, [k.id]: e.target.value })}
                        data-testid="okr-kapanis-puan"
                      />
                    </label>
                    {k.acik ? (
                      <label className="flex items-center gap-1.5 text-xs">
                        <input
                          type="checkbox"
                          className="h-4 w-4 accent-purple-500"
                          checked={!!tasinacak[k.id]}
                          disabled={!tasi}
                          onChange={(e) => setTasinacak({ ...tasinacak, [k.id]: e.target.checked })}
                        />
                        {t('hedefler.kapanis.tasi')}
                      </label>
                    ) : (
                      <span className="text-xs text-emerald-300">{t('hedefler.kapanis.bitti')}</span>
                    )}
                  </>
                )}
              </li>
            ))}
            {h.krler.length === 0 && <li className="text-xs text-muted-foreground">{t('hedefler.kr.yok')}</li>}
          </ul>
        </section>
      ))}
      {!kapali && !meta.okur && (
        <div className={`${KART} grid gap-3 p-4`}>
          <Alan etiket={t('hedefler.kapanis.not')}>
            <textarea className={METIN_ALANI} value={notu} maxLength={4000} onChange={(e) => setNotu(e.target.value)} data-testid="okr-kapanis-not" />
          </Alan>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" className="h-4 w-4 accent-purple-500" checked={tasi} onChange={(e) => setTasi(e.target.checked)} />
            {t('hedefler.kapanis.tasiHepsi')}
          </label>
          {tasi && (
            v.hedef_donemler.length > 0 ? (
              <Alan etiket={t('hedefler.kapanis.hedefDonem')}>
                <select className={SECIM} value={hedefDonem} onChange={(e) => setHedefDonem(e.target.value)} data-testid="okr-kapanis-hedef-donem">
                  {v.hedef_donemler.map((d) => (
                    <option key={d.id} value={d.id}>
                      {donemAdi(t, d, dil)}
                    </option>
                  ))}
                </select>
              </Alan>
            ) : (
              <p className="text-xs text-amber-200">{t('hedefler.kapanis.donemYok')}</p>
            )
          )}
          <HataSatiri hata={hata} />
          <div className="flex justify-end">
            <Button type="button" disabled={mesgul} onClick={() => void kapat()} className="gap-1.5 bg-gradient-to-r from-purple-600 to-pink-600 text-white" data-testid="okr-kapat">
              {mesgul ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Lock className="h-4 w-4" aria-hidden="true" />}
              {t('hedefler.kapanis.kapat')}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
