import { Suspense, useEffect, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, CheckCircle2, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import AydinlatmaSatiri from '@/components/AydinlatmaSatiri';
import { Button } from '@/components/ui/button';
import { ekliLazy } from '@/i18n/ekliLazy';
import { getAPIBaseURL } from '@/lib/config';
import { client } from '@/lib/sdkClient';
import { VITRIN } from '@/lib/modulVitrini';
import { modulYolu } from '../../prerender/moduller-veri.js';
import { DEFAULT_LANGUAGE, LANGUAGE_CODES, localizedPath } from '../../prerender/site.js';

// Faz 2B — "Topluluktan" (planlanan müşteri önerileri). Yalnız yönetici
// ayarı açıksa ve liste boş değilse, istemcide yükleniyor; prerender ve
// kapalı durumda sayfaya hiçbir kod/metin eklenmiyor.
const TopluluktanBolumu = ekliLazy('duyurular', () => import('@/components/TopluluktanBolumu'));
type ToplulukOnerisi = { baslik: string; oy_sayisi: number };

/**
 * Yol haritası + bekleme listesi (Faz 0, 30 Eylül 2026).
 *
 * Modüler portalın herkese açık özeti: hangi modül hangi aşamada. Tarih
 * verilmiyor — söz verilemeyecek bir takvim yazmamak için yalnız durum var.
 *
 * Bekleme listesi ayrı tablo açmıyor: `inquiries` zaten girişsiz kayıt
 * alıyor (entity_guard → HERKESE_ACIK_OLUSTURMA). Kaynak `bekleme_listesi`,
 * seçilen modüller mesajda; admin panelindeki Talepler'de görünür.
 *
 * Aşamaların durumu burada, `FAZLAR` içinde güncellenir.
 */

type Durum = 'yayinda' | 'gelistiriliyor' | 'planlandi';

const FAZLAR: { no: number; durum: Durum }[] = [
  { no: 0, durum: 'yayinda' },
  { no: 1, durum: 'yayinda' },
  { no: 2, durum: 'yayinda' },
  { no: 3, durum: 'gelistiriliyor' },
  { no: 4, durum: 'planlandi' },
  { no: 5, durum: 'planlandi' },
  { no: 6, durum: 'planlandi' },
];

/**
 * Faz 4V: aşamanın yayındaki modülleri → modül vitrinindeki tanıtım sayfası.
 * Yalnız vitrinde (satışta) olan anahtarlar çiziliyor; adlar modül ek paketinden.
 */
const FAZ_MODULLERI: Record<number, string[]> = {
  2: ['uptime', 'yenileme', 'aylik_rapor', 'dosyalar'],
  4: ['dijital_kartvizit', 'dinamik_qr', 'qr_menu', 'whatsapp_katalog', 'google_yorum_sayfasi', 'api_erisimi'],
  5: ['ai_asistan', 'otomasyon', 'eposta_pazarlama', 'icerik_studyosu', 'uzman_asistanlar'],
  6: ['saha_servisi', 'etkinlik_bilet', 'randevu'],
};

const DURUM_STILI: Record<Durum, string> = {
  yayinda: 'border-emerald-400/50 bg-emerald-500/10 text-emerald-300',
  gelistiriliyor: 'border-sky-400/50 bg-sky-500/10 text-sky-300',
  planlandi: 'border-white/15 bg-white/[0.04] text-muted-foreground',
};

const TONLAR = ['', 'cam-gok', 'cam-mor', 'cam-pembe'];

export default function YolHaritasi() {
  const { t, i18n } = useTranslation();
  const dil = LANGUAGE_CODES.includes(i18n.language) ? i18n.language : DEFAULT_LANGUAGE;
  const [ad, setAd] = useState('');
  const [eposta, setEposta] = useState('');
  const [secili, setSecili] = useState<number[]>([]);
  const [gonderiliyor, setGonderiliyor] = useState(false);
  const [bitti, setBitti] = useState(false);
  const [topluluk, setTopluluk] = useState<ToplulukOnerisi[]>([]);

  useEffect(() => {
    let iptal = false;
    fetch(`${getAPIBaseURL()}/api/v1/topluluk-onerileri`)
      .then((y) => (y.ok ? y.json() : null))
      .then((g: { acik?: boolean; oneriler?: ToplulukOnerisi[] } | null) => {
        if (!iptal && g?.acik && Array.isArray(g.oneriler)) setTopluluk(g.oneriler);
      })
      .catch(() => {});
    return () => {
      iptal = true;
    };
  }, []);

  const baslik = (no: number) => t(`yolHaritasi.f${no}Baslik`);
  const secimDegistir = (no: number) =>
    setSecili((s) => (s.includes(no) ? s.filter((x) => x !== no) : [...s, no].sort()));

  const gonder = async (olay: FormEvent) => {
    olay.preventDefault();
    if (gonderiliyor || bitti) return;
    if (!eposta.trim()) {
      toast.error(t('yolHaritasi.epostaGerekli'));
      return;
    }
    setGonderiliyor(true);
    try {
      const moduller = secili.length ? secili.map(baslik).join(', ') : t('yolHaritasi.hepsi');
      await client.entities.inquiries.create({
        data: {
          name: ad.trim() || eposta.trim(),
          email: eposta.trim(),
          subject: `${t('yolHaritasi.talepKonusu')}: ${moduller}`,
          message: moduller,
          status: 'new',
          source: 'bekleme_listesi',
        },
      });
      setBitti(true);
      toast.success(t('yolHaritasi.alindi'));
    } catch (hata) {
      const h = hata as { message?: string };
      toast.error(h?.message || t('yolHaritasi.hata'));
    } finally {
      setGonderiliyor(false);
    }
  };

  return (
    <div className="pt-32 pb-24">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="max-w-3xl mb-14">
          <p className="text-xs uppercase tracking-[0.3em] text-purple-300 mb-4">{t('yolHaritasi.etiket')}</p>
          <h1 className="text-4xl sm:text-5xl font-bold leading-tight mb-5">
            {t('yolHaritasi.baslik1')} <span className="gradient-text">{t('yolHaritasi.baslikVurgu')}</span>
          </h1>
          <p className="text-lg text-muted-foreground">{t('yolHaritasi.giris')}</p>
          <Link
            to={localizedPath(dil, 'moduller')}
            className="mt-5 inline-flex items-center gap-2 text-sm font-semibold text-purple-300 underline-offset-4 hover:underline"
            data-yol-moduller
          >
            {t('modulBaglanti.yolIncele')}
            <ArrowRight className="h-4 w-4 rtl:rotate-180" aria-hidden="true" />
          </Link>
        </div>

        <ol className="cam-dongu grid gap-5 md:grid-cols-2">
          {FAZLAR.map((f, i) => (
            <li
              key={f.no}
              data-faz={f.no}
              data-durum={f.durum}
              className={`cam-kart ${TONLAR[i % TONLAR.length]} rounded-2xl border border-white/10 bg-white/[0.03] p-6 ${
                i === 0 ? 'md:col-span-2' : ''
              }`}
            >
              <div className="flex items-center justify-between gap-3">
                <span className="font-mono text-xs text-muted-foreground">
                  {t('yolHaritasi.asama')} {f.no}
                </span>
                <span className={`rounded-full border px-2.5 py-0.5 text-[11px] font-semibold ${DURUM_STILI[f.durum]}`}>
                  {t(`yolHaritasi.durum_${f.durum}`)}
                </span>
              </div>
              <h2 className="mt-3 text-lg font-semibold">{baslik(f.no)}</h2>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{t(`yolHaritasi.f${f.no}Aciklama`)}</p>
              {(() => {
                const moduller = (FAZ_MODULLERI[f.no] ?? [])
                  .map((k) => VITRIN.moduller.find((m) => m.anahtar === k))
                  .filter(Boolean);
                return moduller.length > 0 ? (
                  <ul className="mt-4 flex flex-wrap gap-2" aria-label={t('modulBaglanti.yolFazModulleri')}>
                    {moduller.map((m) => (
                      <li key={m.anahtar} className="min-w-0">
                        <Link
                          to={modulYolu(dil, m.slug)}
                          className="inline-flex max-w-full rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-xs text-foreground/90 transition-colors hover:border-purple-500/40"
                          data-yol-modul={m.anahtar}
                        >
                          <span className="truncate">{t(`modul.m.${m.anahtar}.ad`)}</span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                ) : null;
              })()}
            </li>
          ))}
        </ol>

        {topluluk.length > 0 && (
          <Suspense fallback={null}>
            <TopluluktanBolumu oneriler={topluluk} />
          </Suspense>
        )}

        <section
          id="bekleme-listesi"
          className="cam-kart cam-gok mt-16 rounded-3xl border border-white/10 bg-white/[0.03] p-6 md:p-10"
          aria-labelledby="bekleme-baslik"
        >
          {bitti ? (
            <div className="py-6 text-center">
              <CheckCircle2 className="mx-auto mb-3 h-10 w-10 text-emerald-400" aria-hidden="true" />
              <p className="text-lg font-semibold">{t('yolHaritasi.tesekkur')}</p>
              <p className="mt-2 text-sm text-muted-foreground">{t('yolHaritasi.tesekkurAciklama')}</p>
            </div>
          ) : (
            <form onSubmit={gonder} className="grid gap-8 lg:grid-cols-2">
              <div>
                <h2 id="bekleme-baslik" className="text-2xl md:text-3xl font-bold">
                  {t('yolHaritasi.bekleme')}
                </h2>
                <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
                  {t('yolHaritasi.beklemeAciklama')}
                </p>
                <div className="mt-6 space-y-3">
                  <input
                    id="bekleme-ad"
                    value={ad}
                    onChange={(o) => setAd(o.target.value)}
                    placeholder={t('yolHaritasi.ad')}
                    autoComplete="name"
                    className="w-full rounded-lg border border-white/10 bg-black/40 px-3 py-2.5 text-sm text-white placeholder:text-muted-foreground focus:border-primary focus:outline-none"
                  />
                  <input
                    id="bekleme-eposta"
                    required
                    type="email"
                    value={eposta}
                    onChange={(o) => setEposta(o.target.value)}
                    placeholder={t('yolHaritasi.eposta')}
                    autoComplete="email"
                    className="w-full rounded-lg border border-white/10 bg-black/40 px-3 py-2.5 text-sm text-white placeholder:text-muted-foreground focus:border-primary focus:outline-none"
                  />
                </div>
              </div>
              <div>
                <fieldset>
                  <legend className="mb-3 text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                    {t('yolHaritasi.ilgi')}
                  </legend>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {FAZLAR.filter((f) => f.durum !== 'yayinda').map((f) => (
                      <label
                        key={f.no}
                        className="flex cursor-pointer items-start gap-2 rounded-lg border border-white/10 px-3 py-2 text-sm hover:bg-white/5"
                      >
                        <input
                          type="checkbox"
                          checked={secili.includes(f.no)}
                          onChange={() => secimDegistir(f.no)}
                          className="mt-0.5 h-4 w-4 accent-emerald-500"
                        />
                        <span>{baslik(f.no)}</span>
                      </label>
                    ))}
                  </div>
                </fieldset>
                <Button type="submit" disabled={gonderiliyor} className="mt-6 h-11 w-full gap-2">
                  {gonderiliyor ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : null}
                  {t('yolHaritasi.gonder')}
                </Button>
                <AydinlatmaSatiri
                  metin={t('yolHaritasi.gizlilik')}
                  className="mt-3 text-center text-[11px] leading-relaxed text-muted-foreground"
                />
              </div>
            </form>
          )}
        </section>
      </div>
    </div>
  );
}
