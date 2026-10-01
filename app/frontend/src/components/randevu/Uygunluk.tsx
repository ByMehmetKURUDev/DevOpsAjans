import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { CalendarOff, Loader2, Plus, Trash2, UserPlus } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { AralikDuzenleyici, Alan, Anahtar, DIS_DUGME, HaftalikDuzenleyici, KART, Rozet, SECIM, Yukleniyor } from '@/components/randevu/ortak';
import { hataMetni, type Istisna, type Kisi, type RandevuApi, type RandevuMod, type Sayfa } from '@/lib/randevu';
import { gunAdiYaz, type Aralik, type Haftalik } from '@/lib/randevuOrtak';

/** Faz 5R — ekip ve uygunluk: kişiler, haftalık saatler, tarih istisnaları, resmî tatil. */

function KisiKarti({ api, sayfa, kisi, tek, onDegisti }: { api: RandevuApi; sayfa: Sayfa; kisi: Kisi; tek: boolean; onDegisti: () => void }) {
  const { t } = useTranslation();
  const [ad, setAd] = useState(kisi.ad);
  const [haftalik, setHaftalik] = useState<Haftalik>(kisi.haftalik);
  const [acik, setAcik] = useState(tek);
  const [kaydediliyor, setKaydediliyor] = useState(false);
  const kirli = ad !== kisi.ad || JSON.stringify(haftalik) !== JSON.stringify(kisi.haftalik);

  const kaydet = async () => {
    setKaydediliyor(true);
    try {
      await api.kisiGuncelle(sayfa.id, kisi.id, { ad, haftalik });
      toast.success(t('randevu.kaydedildi'));
      onDegisti();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setKaydediliyor(false);
    }
  };

  return (
    <li className="rounded-xl border border-white/10 bg-black/20 p-3" data-kisi={kisi.eposta}>
      <div className="flex flex-wrap items-center gap-2">
        <Input value={ad} onChange={(e) => setAd(e.target.value)} maxLength={120} className="h-9 max-w-[16rem]" aria-label={t('randevu.uygunluk.kisiAdi')} />
        <span className="truncate text-xs text-muted-foreground" dir="ltr">
          {kisi.eposta}
        </span>
        {!kisi.aktif && <Rozet renk="border-amber-400/30 bg-amber-500/10 text-amber-200">{t('randevu.pasif')}</Rozet>}
        <div className="ms-auto flex items-center gap-1">
          <Button size="sm" variant="ghost" onClick={() => setAcik((x) => !x)} data-testid="randevu-kisi-saatler">
            {acik ? t('randevu.uygunluk.gizle') : t('randevu.uygunluk.saatler')}
          </Button>
          {!tek && (
            <>
              <Button
                size="sm"
                variant="ghost"
                onClick={async () => {
                  try {
                    await api.kisiGuncelle(sayfa.id, kisi.id, { aktif: !kisi.aktif });
                    onDegisti();
                  } catch (e) {
                    toast.error(hataMetni(t, e));
                  }
                }}
              >
                {kisi.aktif ? t('randevu.turler.pasifYap') : t('randevu.turler.aktifYap')}
              </Button>
              <Button
                size="icon"
                variant="ghost"
                className="h-8 w-8"
                aria-label={t('randevu.sil')}
                onClick={async () => {
                  if (!window.confirm(t('randevu.uygunluk.kisiSilOnay', { ad: kisi.ad }))) return;
                  try {
                    await api.kisiSil(sayfa.id, kisi.id);
                    toast.success(t('randevu.silindi'));
                    onDegisti();
                  } catch (e) {
                    toast.error(hataMetni(t, e));
                  }
                }}
              >
                <Trash2 className="h-4 w-4" aria-hidden="true" />
              </Button>
            </>
          )}
        </div>
      </div>
      {acik && (
        <div className="mt-3">
          <p className="mb-2 text-xs text-muted-foreground">{t('randevu.uygunluk.saatIpucu', { tz: sayfa.saat_dilimi })}</p>
          <HaftalikDuzenleyici haftalik={haftalik} onDegis={setHaftalik} testid="randevu-haftalik" />
        </div>
      )}
      {kirli && (
        <div className="mt-3 flex justify-end">
          <Button size="sm" onClick={() => void kaydet()} disabled={kaydediliyor} className="gap-1.5" data-testid="randevu-kisi-kaydet">
            {kaydediliyor && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
            {t('randevu.kaydet')}
          </Button>
        </div>
      )}
    </li>
  );
}

export default function Uygunluk({ api, sayfa, mod, onSayfa }: { api: RandevuApi; sayfa: Sayfa; mod: RandevuMod; onSayfa: (s: Sayfa) => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [kisiler, setKisiler] = useState<Kisi[] | null>(null);
  const [adaylar, setAdaylar] = useState<{ eposta: string; ad: string }[]>([]);
  const [istisnalar, setIstisnalar] = useState<Istisna[]>([]);
  const [yeniEposta, setYeniEposta] = useState('');
  const [yeniAd, setYeniAd] = useState('');
  const [tarih, setTarih] = useState('');
  const [istisnaKisi, setIstisnaKisi] = useState<string>('');
  const [kapali, setKapali] = useState(true);
  const [ozelSaatler, setOzelSaatler] = useState<Aralik[]>([['09:00', '13:00']]);
  const [aciklama, setAciklama] = useState('');

  const yukle = useCallback(async () => {
    try {
      const [k, i] = await Promise.all([api.kisiler(sayfa.id), api.istisnalar(sayfa.id)]);
      setKisiler(k.items);
      setAdaylar(k.adaylar);
      setIstisnalar(i.items);
    } catch (e) {
      toast.error(hataMetni(t, e));
      setKisiler([]);
    }
  }, [api, sayfa.id, t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  if (kisiler === null) return <Yukleniyor />;
  const eklenebilir = adaylar.filter((a) => !kisiler.some((k) => k.eposta === a.eposta));

  const kisiEkle = async () => {
    const eposta = yeniEposta.trim().toLowerCase();
    if (!eposta) return;
    try {
      await api.kisiEkle(sayfa.id, { eposta, ...(yeniAd.trim() ? { ad: yeniAd.trim() } : {}) });
      setYeniEposta('');
      setYeniAd('');
      toast.success(t('randevu.kaydedildi'));
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const istisnaEkle = async () => {
    if (!tarih) {
      toast.error(t('randevu.hata.tarih_gecersiz'));
      return;
    }
    try {
      await api.istisnaEkle(sayfa.id, {
        tarih,
        kisi_id: istisnaKisi ? Number(istisnaKisi) : null,
        araliklar: kapali ? [] : ozelSaatler,
        aciklama: aciklama.trim() || undefined,
      });
      setTarih('');
      setAciklama('');
      toast.success(t('randevu.kaydedildi'));
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const kisiAdi = (id: number | null) => (id === null ? t('randevu.uygunluk.butunEkip') : kisiler.find((k) => k.id === id)?.ad || '—');

  return (
    <div className="grid gap-4" data-testid="randevu-uygunluk">
      <section className={`${KART} p-4 sm:p-6`} aria-labelledby="randevu-ekip-baslik">
        <h3 id="randevu-ekip-baslik" className="mb-1 text-base font-semibold">
          {t('randevu.uygunluk.ekipBaslik')}
        </h3>
        <p className="mb-3 text-sm text-muted-foreground">{t('randevu.uygunluk.ekipAciklama')}</p>
        <ul className="space-y-3">
          {kisiler.map((k) => (
            <KisiKarti key={`${k.id}-${k.ad}-${JSON.stringify(k.haftalik)}-${k.aktif}`} api={api} sayfa={sayfa} kisi={k} tek={kisiler.length === 1} onDegisti={() => void yukle()} />
          ))}
        </ul>
        <div className="mt-4 rounded-xl border border-dashed border-white/15 p-3">
          <p className="mb-2 flex items-center gap-1.5 text-sm font-medium">
            <UserPlus className="h-4 w-4" aria-hidden="true" />
            {t('randevu.uygunluk.kisiEkle')}
          </p>
          {mod === 'musteri' && eklenebilir.length === 0 ? (
            <p className="text-xs text-muted-foreground">{t('randevu.uygunluk.adayYok')}</p>
          ) : (
            <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
              {mod === 'musteri' ? (
                <select className={SECIM} value={yeniEposta} onChange={(e) => setYeniEposta(e.target.value)} aria-label={t('randevu.uygunluk.eposta')}>
                  <option value="">{t('randevu.uygunluk.sec')}</option>
                  {eklenebilir.map((a) => (
                    <option key={a.eposta} value={a.eposta}>
                      {a.eposta}
                    </option>
                  ))}
                </select>
              ) : (
                <>
                  <Input value={yeniEposta} onChange={(e) => setYeniEposta(e.target.value)} type="email" list="randevu-adaylar" placeholder={t('randevu.uygunluk.eposta')} dir="ltr" />
                  <datalist id="randevu-adaylar">
                    {eklenebilir.map((a) => (
                      <option key={a.eposta} value={a.eposta} />
                    ))}
                  </datalist>
                </>
              )}
              <Input value={yeniAd} onChange={(e) => setYeniAd(e.target.value)} maxLength={120} placeholder={t('randevu.uygunluk.kisiAdi')} />
              <Button onClick={() => void kisiEkle()} disabled={!yeniEposta} className="gap-1.5">
                <Plus className="h-4 w-4" aria-hidden="true" />
                {t('randevu.ekle')}
              </Button>
            </div>
          )}
          <p className="mt-2 text-xs text-muted-foreground">{mod === 'musteri' ? t('randevu.uygunluk.adayIpucu') : t('randevu.uygunluk.adayIpucuYonetici')}</p>
        </div>
      </section>

      <section className={`${KART} p-4 sm:p-6`} aria-labelledby="randevu-istisna-baslik">
        <h3 id="randevu-istisna-baslik" className="mb-1 flex items-center gap-2 text-base font-semibold">
          <CalendarOff className="h-4 w-4 text-purple-300" aria-hidden="true" />
          {t('randevu.uygunluk.istisnaBaslik')}
        </h3>
        <p className="mb-3 text-sm text-muted-foreground">{t('randevu.uygunluk.istisnaAciklama')}</p>
        <div className="mb-4">
          <Anahtar
            acik={sayfa.tatilde_kapali}
            onDegis={async (v) => {
              try {
                onSayfa(await api.guncelle(sayfa.id, { tatilde_kapali: v }));
                toast.success(t('randevu.kaydedildi'));
              } catch (e) {
                toast.error(hataMetni(t, e));
              }
            }}
            etiket={t('randevu.uygunluk.tatilde')}
            testid="randevu-tatilde-kapali"
          />
          <p className="ms-6 mt-1 text-xs text-muted-foreground">{t('randevu.uygunluk.tatilIpucu')}</p>
        </div>
        <div className="grid gap-3 rounded-xl border border-white/10 p-3 md:grid-cols-2">
          <Alan etiket={t('randevu.uygunluk.tarih')}>
            <Input type="date" value={tarih} onChange={(e) => setTarih(e.target.value)} data-testid="randevu-istisna-tarih" />
          </Alan>
          <Alan etiket={t('randevu.uygunluk.kimIcin')}>
            <select className={SECIM} value={istisnaKisi} onChange={(e) => setIstisnaKisi(e.target.value)}>
              <option value="">{t('randevu.uygunluk.butunEkip')}</option>
              {kisiler.map((k) => (
                <option key={k.id} value={k.id}>
                  {k.ad}
                </option>
              ))}
            </select>
          </Alan>
          <div className="md:col-span-2">
            <div className="flex flex-wrap gap-4 text-sm">
              <label className="flex items-center gap-2">
                <input type="radio" name="istisna-tur" className="accent-purple-500" checked={kapali} onChange={() => setKapali(true)} />
                {t('randevu.uygunluk.kapaliGun')}
              </label>
              <label className="flex items-center gap-2">
                <input type="radio" name="istisna-tur" className="accent-purple-500" checked={!kapali} onChange={() => setKapali(false)} />
                {t('randevu.uygunluk.ozelSaat')}
              </label>
            </div>
            {!kapali && (
              <div className="mt-2">
                <AralikDuzenleyici araliklar={ozelSaatler} onDegis={setOzelSaatler} />
              </div>
            )}
          </div>
          <Alan etiket={t('randevu.uygunluk.not')} className="md:col-span-2">
            <Input value={aciklama} onChange={(e) => setAciklama(e.target.value)} maxLength={200} placeholder={t('randevu.uygunluk.notOrnek')} />
          </Alan>
          <div className="md:col-span-2 flex justify-end">
            <Button variant="outline" className={DIS_DUGME} onClick={() => void istisnaEkle()} data-testid="randevu-istisna-ekle">
              <Plus className="h-4 w-4" aria-hidden="true" />
              {t('randevu.uygunluk.istisnaEkle')}
            </Button>
          </div>
        </div>
        {istisnalar.length > 0 && (
          <ul className="mt-4 divide-y divide-white/5" data-testid="randevu-istisna-listesi">
            {istisnalar.map((i) => (
              <li key={i.id} className="flex flex-wrap items-center gap-2 py-2 text-sm">
                <span className="font-medium">{gunAdiYaz(i.tarih, dil, { weekday: 'short', day: 'numeric', month: 'long', year: 'numeric' })}</span>
                <Rozet>{kisiAdi(i.kisi_id)}</Rozet>
                <span className="text-muted-foreground">
                  {i.araliklar.length ? i.araliklar.map((a) => `${a[0]}–${a[1]}`).join(', ') : t('randevu.uygunluk.kapaliGun')}
                </span>
                {i.aciklama && <span className="text-xs text-muted-foreground">· {i.aciklama}</span>}
                <Button
                  size="icon"
                  variant="ghost"
                  className="ms-auto h-8 w-8"
                  aria-label={t('randevu.sil')}
                  onClick={async () => {
                    try {
                      await api.istisnaSil(sayfa.id, i.id);
                      await yukle();
                    } catch (e) {
                      toast.error(hataMetni(t, e));
                    }
                  }}
                >
                  <Trash2 className="h-4 w-4" aria-hidden="true" />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
