import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { CheckCircle2, Download, Loader2, MailPlus, RotateCcw, Search, UserPlus, XCircle } from 'lucide-react';
import { toast } from 'sonner';

import { Alan, DIS_DUGME, KART, Rozet, SECIM, Yukleniyor } from '@/components/randevu/ortak';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { blobIndir, hataMetni, type BeklemeKaydi, type BiletTuru, type Etkinlik, type EtkinlikApi, type Katilimci } from '@/lib/etkinlik';
import { paraYaz, tarihYaz } from '@/lib/etkinlikOrtak';

/**
 * Faz 6E — katılımcılar: süzgeç (durum, tür, giriş, arama), CSV, elle ekle (kapıda kayıt),
 * iptal / iade işaretle, elle giriş / geri al, ödemesi bekleyen kaydı "ödendi" (havale) işaretle;
 * bekleme listesi (davet et, çıkar).
 */

const DURUM_RENGI: Record<Katilimci['durum'], string> = {
  gecerli: 'border-emerald-400/40 bg-emerald-500/15 text-emerald-200',
  odeme_bekliyor: 'border-amber-400/40 bg-amber-500/15 text-amber-200',
  iptal: 'border-red-400/40 bg-red-500/15 text-red-200',
};

export default function Katilimcilar({ api, etkinlik }: { api: EtkinlikApi; etkinlik: Etkinlik }) {
  const { t, i18n } = useTranslation();
  const tz = etkinlik.saat_dilimi;
  const [kayitlar, setKayitlar] = useState<Katilimci[] | null>(null);
  const [toplam, setToplam] = useState(0);
  const [turler, setTurler] = useState<BiletTuru[]>([]);
  const [bekleme, setBekleme] = useState<BeklemeKaydi[]>([]);
  const [suzgec, setSuzgec] = useState({ durum: 'gecerli', tur_id: '', giris: '', ara: '' });
  const [ekle, setEkle] = useState<{ ad: string; eposta: string; tur_id: string; adet: string; bildir: boolean } | null>(null);
  const [mesgul, setMesgul] = useState(false);
  const [acik, setAcik] = useState<number | null>(null);

  const yukle = useCallback(async () => {
    try {
      const [k, tl, b] = await Promise.all([api.katilimcilar(etkinlik.id, suzgec), api.turler(etkinlik.id), api.bekleme(etkinlik.id)]);
      setKayitlar(k.items);
      setToplam(k.toplam);
      setTurler(tl.items);
      setBekleme(b.items);
    } catch (e) {
      toast.error(hataMetni(t, e));
      setKayitlar([]);
    }
  }, [api, etkinlik.id, suzgec, t]);
  useEffect(() => {
    void yukle();
  }, [yukle]);

  const islem = async (f: () => Promise<unknown>, basari: string) => {
    setMesgul(true);
    try {
      await f();
      toast.success(basari);
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  const csv = async () => {
    try {
      blobIndir(await api.csvBlob(etkinlik.id), `katilimcilar-${etkinlik.slug}.csv`);
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const ekleGonder = async () => {
    if (!ekle) return;
    await islem(
      () => api.katilimciEkle(etkinlik.id, { ad: ekle.ad, eposta: ekle.eposta, tur_id: Number(ekle.tur_id), adet: Number(ekle.adet || 1), bildir: ekle.bildir }),
      t('etkinlik.katilimci.eklendi')
    );
    setEkle(null);
  };

  return (
    <div className="space-y-4" data-testid="etkinlik-katilimcilar">
      <div className={`${KART} p-4 sm:p-6`}>
        <div className="mb-3 flex flex-wrap items-end gap-2">
          <label className="relative min-w-[12rem] flex-1">
            <Search className="pointer-events-none absolute start-2 top-2.5 h-4 w-4 text-muted-foreground" aria-hidden="true" />
            <Input className="ps-8" value={suzgec.ara} onChange={(e) => setSuzgec({ ...suzgec, ara: e.target.value })} placeholder={t('etkinlik.katilimci.ara')} data-testid="etkinlik-katilimci-ara" />
          </label>
          <select className={`${SECIM} w-auto`} value={suzgec.durum} onChange={(e) => setSuzgec({ ...suzgec, durum: e.target.value })} aria-label={t('etkinlik.katilimci.durum')}>
            {['gecerli', 'odeme_bekliyor', 'iptal', 'tum'].map((d) => (
              <option key={d} value={d}>
                {t(`etkinlik.biletDurumu.${d}`)}
              </option>
            ))}
          </select>
          <select className={`${SECIM} w-auto`} value={suzgec.tur_id} onChange={(e) => setSuzgec({ ...suzgec, tur_id: e.target.value })} aria-label={t('etkinlik.katilimci.tur')}>
            <option value="">{t('etkinlik.katilimci.tumTurler')}</option>
            {turler.map((x) => (
              <option key={x.id} value={x.id}>
                {x.ad}
              </option>
            ))}
          </select>
          <select className={`${SECIM} w-auto`} value={suzgec.giris} onChange={(e) => setSuzgec({ ...suzgec, giris: e.target.value })} aria-label={t('etkinlik.katilimci.giris')}>
            <option value="">{t('etkinlik.katilimci.girisHepsi')}</option>
            <option value="evet">{t('etkinlik.katilimci.girdi')}</option>
            <option value="hayir">{t('etkinlik.katilimci.girmedi')}</option>
          </select>
          <Button variant="outline" className={DIS_DUGME} onClick={() => void csv()} data-testid="etkinlik-csv">
            <Download className="h-4 w-4" aria-hidden="true" />
            CSV
          </Button>
          <Button className="gap-1.5" onClick={() => setEkle({ ad: '', eposta: '', tur_id: String(turler[0]?.id ?? ''), adet: '1', bildir: true })} data-testid="etkinlik-katilimci-ekle">
            <UserPlus className="h-4 w-4" aria-hidden="true" />
            {t('etkinlik.katilimci.ekle')}
          </Button>
        </div>
        {ekle && (
          <div className="mb-4 grid gap-2 rounded-xl border border-purple-400/30 bg-purple-500/5 p-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,10rem)_5rem_auto] sm:items-end">
            <Alan etiket={t('etkinlik.katilimci.ad')}>
              <Input value={ekle.ad} onChange={(e) => setEkle({ ...ekle, ad: e.target.value })} maxLength={120} />
            </Alan>
            <Alan etiket={t('etkinlik.katilimci.eposta')}>
              <Input type="email" dir="ltr" value={ekle.eposta} onChange={(e) => setEkle({ ...ekle, eposta: e.target.value })} />
            </Alan>
            <Alan etiket={t('etkinlik.katilimci.tur')}>
              <select className={SECIM} value={ekle.tur_id} onChange={(e) => setEkle({ ...ekle, tur_id: e.target.value })}>
                {turler.map((x) => (
                  <option key={x.id} value={x.id}>
                    {x.ad}
                  </option>
                ))}
              </select>
            </Alan>
            <Alan etiket={t('etkinlik.katilimci.adet')}>
              <Input type="number" min={1} max={20} value={ekle.adet} onChange={(e) => setEkle({ ...ekle, adet: e.target.value })} />
            </Alan>
            <Button onClick={() => void ekleGonder()} disabled={mesgul || !ekle.ad || !ekle.eposta}>
              {mesgul ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : t('etkinlik.ekle')}
            </Button>
            <label className="flex items-center gap-2 text-xs text-muted-foreground sm:col-span-5">
              <input type="checkbox" className="h-4 w-4 accent-purple-500" checked={ekle.bildir} onChange={(e) => setEkle({ ...ekle, bildir: e.target.checked })} />
              {t('etkinlik.katilimci.biletGonder')}
            </label>
          </div>
        )}
        <p className="mb-2 text-xs text-muted-foreground">{t('etkinlik.katilimci.toplam', { sayi: toplam })}</p>
        {kayitlar === null ? (
          <Yukleniyor />
        ) : kayitlar.length === 0 ? (
          <p className="py-10 text-center text-sm text-muted-foreground">{t('etkinlik.katilimci.bos')}</p>
        ) : (
          <ul className="divide-y divide-white/5" data-testid="etkinlik-katilimci-listesi">
            {kayitlar.map((k) => (
              <li key={k.id} className="py-2" data-kod={k.kod}>
                <div className="flex flex-wrap items-center gap-2">
                  <button type="button" className="min-w-0 flex-1 text-start" onClick={() => setAcik(acik === k.id ? null : k.id)}>
                    <span className="block truncate font-medium">{k.katilimci_ad || k.siparis.ad || '—'}</span>
                    <span className="block truncate text-xs text-muted-foreground" dir="auto">
                      {k.siparis.eposta || t('etkinlik.katilimci.anonim')} · {k.tur_adi} · <span className="font-mono">{k.kod}</span>
                    </span>
                  </button>
                  <Rozet renk={DURUM_RENGI[k.durum]}>{t(`etkinlik.biletDurumu.${k.durum}`)}</Rozet>
                  {k.giris_at && (
                    <Rozet renk="border-sky-400/40 bg-sky-500/15 text-sky-200" testid="etkinlik-girdi-rozeti">
                      <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
                      {tarihYaz(k.giris_at, tz, i18n.language, { timeStyle: 'short' })}
                    </Rozet>
                  )}
                  {k.iade !== 'yok' && <Rozet>{t(`etkinlik.iade.${k.iade}`)}</Rozet>}
                  {k.durum === 'gecerli' && !k.giris_at && (
                    <Button size="sm" variant="ghost" onClick={() => void islem(() => api.biletGiris(etkinlik.id, k.id), t('etkinlik.katilimci.girisYapildi'))}>
                      <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
                      {t('etkinlik.katilimci.girisYap')}
                    </Button>
                  )}
                </div>
                {acik === k.id && (
                  <div className="mt-2 grid gap-2 rounded-lg border border-white/10 bg-black/20 p-3 text-xs sm:grid-cols-2">
                    <span>
                      {t('etkinlik.katilimci.siparis')}: <span className="font-mono">{k.siparis.kod}</span> · {t(`etkinlik.siparisDurumu.${k.siparis.durum}`, { defaultValue: k.siparis.durum })}
                    </span>
                    <span>
                      {t('etkinlik.katilimci.tutar')}: {k.siparis.toplam ? paraYaz(k.siparis.toplam, k.siparis.para_birimi, i18n.language) : t('etkinlik.bilet.ucretsiz')}
                    </span>
                    {k.siparis.telefon && <span dir="ltr">{k.siparis.telefon}</span>}
                    <span>{k.siparis.pazarlama_izni ? t('etkinlik.katilimci.pazarlamaVar') : t('etkinlik.katilimci.pazarlamaYok')}</span>
                    {k.siparis.yanitlar.map((y) => (
                      <span key={y.id} className="sm:col-span-2">
                        <span className="text-muted-foreground">{y.soru}:</span> {y.yanit === true ? '✓' : String(y.yanit)}
                      </span>
                    ))}
                    <div className="flex flex-wrap gap-2 sm:col-span-2">
                      {k.giris_at && (
                        <Button size="sm" variant="outline" className={DIS_DUGME} onClick={() => void islem(() => api.biletGirisGeri(etkinlik.id, k.id), t('etkinlik.ayar.kaydedildi'))}>
                          <RotateCcw className="h-4 w-4" aria-hidden="true" />
                          {t('etkinlik.katilimci.girisGeriAl')}
                        </Button>
                      )}
                      {k.durum !== 'iptal' && (
                        <Button
                          size="sm"
                          variant="outline"
                          className={`${DIS_DUGME} text-red-200`}
                          onClick={() => {
                            if (!window.confirm(t('etkinlik.katilimci.iptalOnay'))) return;
                            void islem(() => api.biletIptal(etkinlik.id, k.id, { iade: k.fiyat > 0, bildir: true }), t('etkinlik.katilimci.iptalEdildi'));
                          }}
                        >
                          <XCircle className="h-4 w-4" aria-hidden="true" />
                          {t('etkinlik.katilimci.iptal')}
                        </Button>
                      )}
                      {(k.siparis.durum === 'odeme_bekliyor' || k.siparis.durum === 'suresi_doldu') && (
                        <Button size="sm" variant="outline" className={DIS_DUGME} onClick={() => void islem(() => api.siparisOdendi(etkinlik.id, k.siparis.id), t('etkinlik.katilimci.odendiYapildi'))}>
                          {t('etkinlik.katilimci.odendi')}
                        </Button>
                      )}
                      {k.iade === 'bekliyor' && (
                        <Button size="sm" variant="outline" className={DIS_DUGME} onClick={() => void islem(() => api.biletIade(etkinlik.id, k.id, 'yapildi'), t('etkinlik.ayar.kaydedildi'))}>
                          {t('etkinlik.katilimci.iadeYapildi')}
                        </Button>
                      )}
                    </div>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className={`${KART} p-4 sm:p-6`} data-testid="etkinlik-bekleme">
        <h3 className="mb-1 text-base font-semibold">{t('etkinlik.bekleme.baslik')}</h3>
        <p className="mb-3 text-sm text-muted-foreground">{t('etkinlik.bekleme.aciklama')}</p>
        {bekleme.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('etkinlik.bekleme.bos')}</p>
        ) : (
          <ul className="divide-y divide-white/5">
            {bekleme.map((w, i) => (
              <li key={w.id} className="flex flex-wrap items-center gap-2 py-2 text-sm" data-bekleme={w.durum}>
                <span className="w-6 text-muted-foreground">{i + 1}.</span>
                <span className="min-w-0 flex-1 truncate">
                  {w.ad || '—'} <span className="text-xs text-muted-foreground">{w.eposta}</span>
                </span>
                <Rozet>{t('etkinlik.bekleme.adet', { sayi: w.adet })}</Rozet>
                <Rozet>{t(`etkinlik.bekleme.durum.${w.durum}`)}</Rozet>
                {(w.durum === 'bekliyor' || w.durum === 'suresi_doldu') && (
                  <Button size="sm" variant="ghost" onClick={() => void islem(() => api.beklemeDavet(etkinlik.id, w.id), t('etkinlik.bekleme.davetEdildi'))}>
                    <MailPlus className="h-4 w-4" aria-hidden="true" />
                    {t('etkinlik.bekleme.davetEt')}
                  </Button>
                )}
                {w.durum !== 'kullanildi' && w.durum !== 'iptal' && (
                  <Button size="sm" variant="ghost" onClick={() => void islem(() => api.beklemeSil(etkinlik.id, w.id), t('etkinlik.ayar.kaydedildi'))}>
                    {t('etkinlik.bekleme.cikar')}
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
