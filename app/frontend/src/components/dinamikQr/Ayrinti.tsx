import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ArrowLeft,
  Ban,
  Copy,
  Download,
  Link as LinkIcon,
  Loader2,
  Pause,
  Pencil,
  Play,
  ShieldCheck,
  Table2,
  Trash2,
  BarChart3,
} from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { hataMetni, type Analiz, type Dagilim, type QrApi, type QrKaydi, type QrMod } from '@/lib/dinamikQr';

import { DurumRozeti, KART, TurRozeti, kopyala, sayiYaz, tarihYaz } from './ortak';

/**
 * Faz 4Q — bir QR / kısa linkin ayrıntısı: görsel + indirme, adresler,
 * durum işlemleri ve tarama analitiği (son 30 gün günlük seri, ülke / cihaz /
 * işletim sistemi / yönlendiren dağılımı). Bot ve bağlantı önizlemeleri
 * sayılara katılmıyor (sunucu ayırıyor).
 *
 * Grafik tek seri (tarama) — tek renk, açıklama kutusu yok (başlık adlandırıyor),
 * çubuk başına üzerine gelince/odaklanınca ipucu ve "Tablo" görünümü.
 */

export default function Ayrinti({
  api,
  mod,
  id,
  onGeri,
  onDuzenle,
  onSilindi,
}: {
  api: QrApi;
  mod: QrMod;
  id: number;
  onGeri: () => void;
  onDuzenle: (k: QrKaydi) => void;
  onSilindi: () => void;
}) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [kayit, setKayit] = useState<QrKaydi | null>(null);
  const [analiz, setAnaliz] = useState<Analiz | null>(null);
  const [gorsel, setGorsel] = useState<string | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [mesgul, setMesgul] = useState<string | null>(null);

  useEffect(() => {
    let iptal = false;
    let adres: string | null = null;
    setHata(null);
    (async () => {
      try {
        const k = await api.getir(id);
        if (iptal) return;
        setKayit(k);
        const [a, blob] = await Promise.all([
          api.analiz(id, 30),
          k.kisa_link ? Promise.resolve(null) : api.gorselBlob(id, 'svg'),
        ]);
        if (iptal) return;
        setAnaliz(a);
        if (blob) {
          adres = URL.createObjectURL(blob);
          setGorsel(adres);
        }
      } catch (e) {
        if (!iptal) setHata(hataMetni(t, e));
      }
    })();
    return () => {
      iptal = true;
      if (adres) URL.revokeObjectURL(adres);
    };
  }, [api, id, t]);

  const islem = async (ad: string, is: () => Promise<QrKaydi | void>) => {
    setMesgul(ad);
    try {
      const sonuc = await is();
      if (sonuc) setKayit(sonuc);
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(null);
    }
  };

  if (hata) {
    return (
      <div className={`${KART} p-6`}>
        <Button variant="ghost" size="sm" onClick={onGeri} className="mb-3 gap-1 px-2">
          <ArrowLeft className="h-4 w-4 rtl:rotate-180" aria-hidden="true" />
          {t('dinamikQr.ayrinti.geri')}
        </Button>
        <p className="text-sm text-red-300" role="alert">
          {hata}
        </p>
      </div>
    );
  }
  if (!kayit) {
    return (
      <div className="flex items-center justify-center py-20 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
      </div>
    );
  }

  const kopyalaMetin = (metin: string) => kopyala(metin, t('dinamikQr.liste.kopyalandi'), t('dinamikQr.liste.kopyalanamadi'));

  return (
    <div className="space-y-6" data-testid="qr-ayrinti" data-qr-id={kayit.id}>
      <div className={`${KART} p-4 sm:p-6`}>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2">
            <Button variant="ghost" size="sm" onClick={onGeri} className="gap-1 px-2" data-testid="qr-ayrinti-geri">
              <ArrowLeft className="h-4 w-4 rtl:rotate-180" aria-hidden="true" />
              {t('dinamikQr.ayrinti.geri')}
            </Button>
            <h3 className="truncate text-lg font-semibold">{kayit.ad}</h3>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <TurRozeti tur={kayit.tur} kisa={kayit.kisa_link} />
            <DurumRozeti durum={kayit.durum} statik={kayit.statik} />
          </div>
        </div>

        {kayit.engelli && (
          <p className="mb-4 rounded-lg border border-red-400/30 bg-red-500/10 p-3 text-sm text-red-100" role="status">
            {t('dinamikQr.ayrinti.engelliBilgi')}
          </p>
        )}

        <div className="grid gap-6 md:grid-cols-[220px_minmax(0,1fr)]">
          <div className="space-y-3">
            {kayit.kisa_link ? (
              <div className="flex aspect-square w-full max-w-[220px] items-center justify-center rounded-xl border border-white/10 bg-white/[0.02]">
                <LinkIcon className="h-12 w-12 text-purple-300" aria-hidden="true" />
              </div>
            ) : (
              <div className="flex aspect-square w-full max-w-[220px] items-center justify-center overflow-hidden rounded-xl border border-white/10 bg-white/[0.02] p-2">
                {gorsel ? (
                  <img src={gorsel} alt={t('dinamikQr.sihirbaz.onizlemeAlt', { ad: kayit.ad })} className="h-full w-full object-contain" data-testid="qr-ayrinti-img" />
                ) : (
                  <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" aria-hidden="true" />
                )}
              </div>
            )}
            {!kayit.kisa_link && (
              <div className="flex flex-wrap gap-2">
                {(['png', 'svg'] as const).map((b) => (
                  <Button
                    key={b}
                    variant="outline"
                    size="sm"
                    className="gap-1.5 !bg-transparent border-white/20"
                    disabled={mesgul === b}
                    onClick={() => islem(b, () => api.gorselIndir(kayit.id, b, kayit.kod))}
                    data-testid={`qr-indir-${b}`}
                  >
                    {mesgul === b ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Download className="h-4 w-4" aria-hidden="true" />}
                    {b.toUpperCase()}
                  </Button>
                ))}
              </div>
            )}
          </div>

          <div className="min-w-0 space-y-3 text-sm">
            {kayit.kisa_adres && (
              <AdresSatiri etiket={t('dinamikQr.ayrinti.kisaAdres')} adres={kayit.kisa_adres} onKopyala={kopyalaMetin} testId="qr-kisa-adres" />
            )}
            {kayit.qr_adresi && kayit.qr_adresi !== kayit.kisa_adres && (
              <AdresSatiri etiket={t('dinamikQr.ayrinti.qrAdresi')} adres={kayit.qr_adresi} onKopyala={kopyalaMetin} />
            )}
            <div>
              <p className="text-xs text-muted-foreground">{t(kayit.statik ? 'dinamikQr.ayrinti.icerik' : 'dinamikQr.ayrinti.hedef')}</p>
              <p className="break-all" dir="auto">
                {kayit.hedef_ozet || '—'}
              </p>
            </div>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs sm:grid-cols-3">
              <div>
                <dt className="text-muted-foreground">{t('dinamikQr.ayrinti.olusturma')}</dt>
                <dd>{tarihYaz(kayit.created_at, dil)}</dd>
              </div>
              {!kayit.statik && (
                <>
                  <div>
                    <dt className="text-muted-foreground">{t('dinamikQr.ayarlar.bitis')}</dt>
                    <dd>{kayit.bitis ? tarihYaz(kayit.bitis, dil) : t('dinamikQr.ayarlar.sinirsiz')}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">{t('dinamikQr.ayarlar.taramaLimiti')}</dt>
                    <dd>
                      {kayit.tarama_limiti
                        ? `${sayiYaz(kayit.tarama_sayisi, dil)} / ${sayiYaz(kayit.tarama_limiti, dil)}`
                        : t('dinamikQr.ayarlar.sinirsiz')}
                    </dd>
                  </div>
                </>
              )}
              {mod === 'yonetici' && (
                <div className="col-span-2 sm:col-span-3">
                  <dt className="text-muted-foreground">{t('dinamikQr.liste.sahip')}</dt>
                  <dd className="break-all">{kayit.hesap_email || t('dinamikQr.liste.ajans')}</dd>
                </div>
              )}
            </dl>
            <div className="flex flex-wrap gap-2 pt-2">
              <Button size="sm" variant="outline" className="gap-1.5 !bg-transparent border-white/20" onClick={() => onDuzenle(kayit)} data-testid="qr-duzenle">
                <Pencil className="h-4 w-4" aria-hidden="true" />
                {t('dinamikQr.ayrinti.duzenle')}
              </Button>
              {!kayit.statik && (
                <Button
                  size="sm"
                  variant="outline"
                  className="gap-1.5 !bg-transparent border-white/20"
                  disabled={mesgul === 'aktif'}
                  onClick={() => islem('aktif', () => api.guncelle(kayit.id, { aktif: !kayit.aktif }))}
                  data-testid="qr-aktif-degistir"
                >
                  {kayit.aktif ? <Pause className="h-4 w-4" aria-hidden="true" /> : <Play className="h-4 w-4" aria-hidden="true" />}
                  {kayit.aktif ? t('dinamikQr.ayrinti.durdur') : t('dinamikQr.ayrinti.etkinlestir')}
                </Button>
              )}
              {mod === 'yonetici' && (
                <Button
                  size="sm"
                  variant="outline"
                  className={`gap-1.5 !bg-transparent ${kayit.engelli ? 'border-white/20' : 'border-red-400/40 text-red-200'}`}
                  disabled={mesgul === 'engel'}
                  onClick={() => islem('engel', () => api.engelle(kayit.id, !kayit.engelli))}
                  data-testid="qr-engelle"
                >
                  {kayit.engelli ? <ShieldCheck className="h-4 w-4" aria-hidden="true" /> : <Ban className="h-4 w-4" aria-hidden="true" />}
                  {kayit.engelli ? t('dinamikQr.ayrinti.engeliKaldir') : t('dinamikQr.ayrinti.engelle')}
                </Button>
              )}
              <Button
                size="sm"
                variant="ghost"
                className="gap-1.5 text-red-300"
                disabled={mesgul === 'sil'}
                onClick={() => {
                  if (!window.confirm(t('dinamikQr.ayrinti.silOnay', { ad: kayit.ad }))) return;
                  void islem('sil', async () => {
                    await api.sil(kayit.id);
                    toast.success(t('dinamikQr.ayrinti.silindi'));
                    onSilindi();
                  });
                }}
                data-testid="qr-sil"
              >
                <Trash2 className="h-4 w-4" aria-hidden="true" />
                {t('dinamikQr.ayrinti.sil')}
              </Button>
            </div>
          </div>
        </div>
      </div>

      <AnalizBolumu analiz={analiz} kayit={kayit} />
    </div>
  );
}

function AdresSatiri({
  etiket,
  adres,
  onKopyala,
  testId,
}: {
  etiket: string;
  adres: string;
  onKopyala: (m: string) => void;
  testId?: string;
}) {
  const { t } = useTranslation();
  return (
    <div>
      <p className="text-xs text-muted-foreground">{etiket}</p>
      <div className="flex items-center gap-2">
        <a href={adres} target="_blank" rel="noopener noreferrer" className="min-w-0 truncate font-mono text-purple-200 hover:underline" dir="ltr" data-testid={testId}>
          {adres.replace(/^https?:\/\//, '')}
        </a>
        <Button size="icon" variant="ghost" className="h-8 w-8 flex-none" onClick={() => onKopyala(adres)} aria-label={t('dinamikQr.liste.kopyala')}>
          <Copy className="h-4 w-4" aria-hidden="true" />
        </Button>
      </div>
    </div>
  );
}

function AnalizBolumu({ analiz, kayit }: { analiz: Analiz | null; kayit: QrKaydi }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [tablo, setTablo] = useState(false);
  const [secili, setSecili] = useState<number | null>(null);

  const ulkeAdi = useMemo(() => {
    try {
      const d = new Intl.DisplayNames([dil], { type: 'region' });
      return (k: string) => d.of(k) || k;
    } catch {
      return (k: string) => k;
    }
  }, [dil]);

  if (kayit.statik) {
    return (
      <div className={`${KART} p-4 text-sm text-muted-foreground sm:p-6`} data-testid="qr-analiz">
        {t('dinamikQr.analiz.statikBilgi')}
      </div>
    );
  }
  if (!analiz) {
    return (
      <div className="flex items-center justify-center py-10 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
      </div>
    );
  }
  const enCok = Math.max(1, ...analiz.gunluk.map((g) => g.tarama));
  const gunYaz = (g: string) => {
    try {
      return new Intl.DateTimeFormat(dil, { day: 'numeric', month: 'short' }).format(new Date(`${g}T12:00:00Z`));
    } catch {
      return g;
    }
  };
  const odak = secili !== null ? analiz.gunluk[secili] : null;

  return (
    <div className={`${KART} space-y-6 p-4 sm:p-6`} data-testid="qr-analiz">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h4 className="text-base font-semibold">{t('dinamikQr.analiz.baslik')}</h4>
        <p className="text-xs text-muted-foreground">{t('dinamikQr.analiz.botBilgi', { sayi: sayiYaz(analiz.bot, dil) })}</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        {[
          { ad: 'toplam', deger: analiz.toplam },
          { ad: 'tekil', deger: analiz.tekil },
          { ad: 'donem', deger: analiz.donem.tarama },
        ].map((x) => (
          <div key={x.ad} className="rounded-xl border border-white/10 bg-black/20 p-4" data-qr-istatistik={x.ad}>
            <p className="text-xs text-muted-foreground">{t(`dinamikQr.analiz.${x.ad}`, { gun: analiz.donem.gun })}</p>
            <p className="mt-1 text-2xl font-semibold tabular-nums">{sayiYaz(x.deger, dil)}</p>
          </div>
        ))}
      </div>

      <section aria-labelledby="qr-gunluk-baslik">
        <div className="mb-2 flex items-center justify-between gap-2">
          <h5 id="qr-gunluk-baslik" className="text-sm font-medium">
            {t('dinamikQr.analiz.gunluk', { gun: analiz.donem.gun })}
          </h5>
          <Button size="sm" variant="ghost" className="h-8 gap-1.5 text-xs" onClick={() => setTablo((x) => !x)} aria-pressed={tablo}>
            {tablo ? <BarChart3 className="h-3.5 w-3.5" aria-hidden="true" /> : <Table2 className="h-3.5 w-3.5" aria-hidden="true" />}
            {tablo ? t('dinamikQr.analiz.grafik') : t('dinamikQr.analiz.tablo')}
          </Button>
        </div>
        {tablo ? (
          <div className="max-h-72 overflow-auto rounded-lg border border-white/10">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-black/60 text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 text-start font-medium">{t('dinamikQr.analiz.tarih')}</th>
                  <th className="px-3 py-2 text-end font-medium">{t('dinamikQr.analiz.tarama')}</th>
                  <th className="px-3 py-2 text-end font-medium">{t('dinamikQr.analiz.tekilSutun')}</th>
                </tr>
              </thead>
              <tbody>
                {[...analiz.gunluk].reverse().map((g) => (
                  <tr key={g.gun} className="border-t border-white/5">
                    <td className="px-3 py-1.5">{gunYaz(g.gun)}</td>
                    <td className="px-3 py-1.5 text-end tabular-nums">{sayiYaz(g.tarama, dil)}</td>
                    <td className="px-3 py-1.5 text-end tabular-nums">{sayiYaz(g.tekil, dil)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div>
            <p className="mb-1 h-4 text-xs text-muted-foreground" aria-live="polite">
              {odak
                ? t('dinamikQr.analiz.ipucu', { tarih: gunYaz(odak.gun), tarama: sayiYaz(odak.tarama, dil), tekil: sayiYaz(odak.tekil, dil) })
                : ''}
            </p>
            <div className="relative" dir="ltr">
              <span className="absolute -top-0.5 start-0 text-[10px] text-muted-foreground">{sayiYaz(enCok, dil)}</span>
              <div
                className="flex h-36 items-end gap-[2px] border-b border-white/15 pt-4"
                role="img"
                aria-label={t('dinamikQr.analiz.grafikEtiket', { gun: analiz.donem.gun, sayi: analiz.donem.tarama })}
                onMouseLeave={() => setSecili(null)}
                data-testid="qr-gunluk-grafik"
              >
                {analiz.gunluk.map((g, i) => (
                  <div
                    key={g.gun}
                    className="group flex h-full flex-1 items-end"
                    onMouseEnter={() => setSecili(i)}
                    onFocus={() => setSecili(i)}
                    onBlur={() => setSecili(null)}
                    tabIndex={0}
                    aria-label={t('dinamikQr.analiz.ipucu', { tarih: gunYaz(g.gun), tarama: g.tarama, tekil: g.tekil })}
                  >
                    <div
                      className={`w-full rounded-t-[4px] transition-colors ${secili === i ? 'bg-purple-300' : 'bg-purple-400/80'}`}
                      style={{ height: g.tarama ? `${Math.max(3, (g.tarama / enCok) * 100)}%` : 0 }}
                    />
                  </div>
                ))}
              </div>
              <div className="mt-1 flex justify-between text-[10px] text-muted-foreground">
                <span>{gunYaz(analiz.gunluk[0]?.gun ?? '')}</span>
                <span>{gunYaz(analiz.gunluk[analiz.gunluk.length - 1]?.gun ?? '')}</span>
              </div>
            </div>
          </div>
        )}
      </section>

      <div className="grid gap-6 md:grid-cols-2">
        <DagilimListesi baslik={t('dinamikQr.analiz.ulkeler')} satirlar={analiz.ulkeler} etiket={(k) => (k ? ulkeAdi(k) : t('dinamikQr.analiz.bilinmeyen'))} test="ulke" />
        <DagilimListesi baslik={t('dinamikQr.analiz.cihazlar')} satirlar={analiz.cihazlar} etiket={(k) => t(`dinamikQr.cihaz.${k || 'bilinmiyor'}`)} test="cihaz" />
        <DagilimListesi baslik={t('dinamikQr.analiz.isletim')} satirlar={analiz.isletim} etiket={(k) => t(`dinamikQr.isletim.${k || 'diger'}`)} test="isletim" />
        <DagilimListesi baslik={t('dinamikQr.analiz.refererlar')} satirlar={analiz.refererlar} etiket={(k) => k || t('dinamikQr.analiz.dogrudan')} test="referer" />
      </div>
    </div>
  );
}

function DagilimListesi({
  baslik,
  satirlar,
  etiket,
  test,
}: {
  baslik: string;
  satirlar: Dagilim[];
  etiket: (k: string | null) => string;
  test: string;
}) {
  const { t, i18n } = useTranslation();
  const toplam = satirlar.reduce((s, x) => s + x.sayi, 0);
  return (
    <section data-qr-dagilim={test}>
      <h5 className="mb-2 text-sm font-medium">{baslik}</h5>
      {satirlar.length === 0 ? (
        <p className="text-xs text-muted-foreground">{t('dinamikQr.analiz.veriYok')}</p>
      ) : (
        <ul className="space-y-1.5">
          {satirlar.map((s) => {
            const oran = toplam ? s.sayi / toplam : 0;
            return (
              <li key={s.anahtar ?? '_'} className="text-xs">
                <div className="mb-0.5 flex justify-between gap-2">
                  <span className="truncate">{etiket(s.anahtar)}</span>
                  <span className="tabular-nums text-muted-foreground">
                    {sayiYaz(s.sayi, i18n.language || 'tr')} · {Math.round(oran * 100)}%
                  </span>
                </div>
                <div className="h-1.5 rounded-full bg-white/[0.06]">
                  <div className="h-1.5 rounded-full bg-purple-400/80" style={{ width: `${Math.max(2, oran * 100)}%` }} />
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
