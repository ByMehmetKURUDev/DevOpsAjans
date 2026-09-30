import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react';
import { Coins, Hourglass, Loader2, MinusCircle, PlusCircle, RefreshCw, Search, UserPlus } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { client } from '@/lib/sdkClient';
import {
  KrediHatasi,
  kalanGun,
  krediEkle,
  krediMusterileri,
  krediMusterisi,
  saatBicimle,
  saatHarca,
  sonKullanmaRengi,
  sureDolumlariniIsle,
  tarihBicimle,
  turRengi,
  type KrediMusteriAyrintisi,
  type KrediMusterisi,
  type YuklemeTuru,
} from '@/lib/kredi';

/**
 * Yönetici paneli › Krediler (Kullandıkça Öde'nin arka yüzü).
 *
 * Solda defterde hareketi olan müşteriler (bakiye + en yakın son kullanma),
 * sağda seçili müşterinin hareketleri, "Saat harca" ve "Kredi ekle".
 * Bakiye her zaman sunucudan geliyor. Yazan her işlem önce bir onay
 * penceresinden geçiyor: yanlış müşteriye ya da yanlış saatle yazılan
 * satır ancak ters bir düzeltmeyle geri alınabiliyor.
 */

const SECIM_SINIFI =
  'h-10 w-full rounded-md border border-white/10 bg-white/5 px-3 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-purple-500/40';
const YUKLEME_TURLERI: YuklemeTuru[] = ['hediye', 'iade', 'duzeltme', 'satin_alma'];
const EPOSTA_DESENI = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

interface Proje {
  id: number | string;
  title: string;
  client_email?: string | null;
}

interface Onay {
  mesaj: string;
  calistir: () => Promise<void>;
}

/** 0.25'in katı mı? */
function saatGecerli(deger: number, eksiOlabilir = false): boolean {
  if (!Number.isFinite(deger) || deger === 0) return false;
  if (deger < 0 && !eksiOlabilir) return false;
  return Math.abs(deger * 4 - Math.round(deger * 4)) < 1e-6;
}

export default function KrediDefteri() {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const saat = (n: number) => saatBicimle(n, dil);

  const [musteriler, setMusteriler] = useState<KrediMusterisi[]>([]);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [arama, setArama] = useState('');
  const [secili, setSecili] = useState<string | null>(null);
  const [ayrinti, setAyrinti] = useState<KrediMusteriAyrintisi | null>(null);
  const [ayrintiYukleniyor, setAyrintiYukleniyor] = useState(false);
  const [projeler, setProjeler] = useState<Proje[]>([]);
  const [onay, setOnay] = useState<Onay | null>(null);
  const [calisiyor, setCalisiyor] = useState(false);

  const [harcaSaat, setHarcaSaat] = useState('1');
  const [harcaAciklama, setHarcaAciklama] = useState('');
  const [harcaProje, setHarcaProje] = useState('');
  const [izinEksi, setIzinEksi] = useState(false);

  const [ekleSaat, setEkleSaat] = useState('1');
  const [ekleTur, setEkleTur] = useState<YuklemeTuru>('hediye');
  const [ekleAciklama, setEkleAciklama] = useState('');

  const listeyiYukle = useCallback(async () => {
    setYukleniyor(true);
    try {
      setMusteriler(await krediMusterileri());
    } catch {
      toast.error(t('kredi.hata.yukleme'));
    } finally {
      setYukleniyor(false);
    }
  }, [t]);

  const ayrintiyiYukle = useCallback(
    async (eposta: string) => {
      setAyrintiYukleniyor(true);
      try {
        setAyrinti(await krediMusterisi(eposta));
      } catch {
        toast.error(t('kredi.hata.yukleme'));
      } finally {
        setAyrintiYukleniyor(false);
      }
    },
    [t]
  );

  useEffect(() => {
    void listeyiYukle();
    client.entities.projects
      .query({ sort: '-created_at', limit: 200 })
      .then((yanit: { data?: { items?: Proje[] } }) => setProjeler(yanit?.data?.items ?? []))
      .catch(() => setProjeler([]));
  }, [listeyiYukle]);

  useEffect(() => {
    if (secili) void ayrintiyiYukle(secili);
    else setAyrinti(null);
  }, [secili, ayrintiyiYukle]);

  const aramaTemiz = arama.trim().toLowerCase();
  const suzulmus = useMemo(
    () => (aramaTemiz ? musteriler.filter((m) => m.eposta.includes(aramaTemiz)) : musteriler),
    [musteriler, aramaTemiz]
  );
  const yeniEposta =
    EPOSTA_DESENI.test(aramaTemiz) && !musteriler.some((m) => m.eposta === aramaTemiz) ? aramaTemiz : null;

  const musteriProjeleri = projeler.filter((p) => (p.client_email || '').toLowerCase() === secili);
  const digerProjeler = projeler.filter((p) => (p.client_email || '').toLowerCase() !== secili);

  const hataGoster = (hata: unknown) => {
    const kod = hata instanceof KrediHatasi ? hata.kod : 'genel';
    toast.error(t(`kredi.hata.${kod}`, { defaultValue: t('kredi.hata.genel') }));
  };

  const yenile = async (eposta?: string) => {
    await listeyiYukle();
    if (eposta) await ayrintiyiYukle(eposta);
  };

  const onayla = async () => {
    if (!onay) return;
    setCalisiyor(true);
    try {
      await onay.calistir();
      setOnay(null);
    } catch (hata) {
      hataGoster(hata);
    } finally {
      setCalisiyor(false);
    }
  };

  const harcaGonder = (olay: FormEvent) => {
    olay.preventDefault();
    if (!secili || !ayrinti) return;
    const miktar = Number(harcaSaat.replace(',', '.'));
    if (!saatGecerli(miktar)) {
      toast.error(t('kredi.yonetim.saatGecersiz'));
      return;
    }
    if (!harcaAciklama.trim()) {
      toast.error(t('kredi.yonetim.eksik'));
      return;
    }
    const yeni = ayrinti.bakiye - miktar;
    if (yeni < 0 && !izinEksi) {
      toast.error(t('kredi.hata.yetersiz_bakiye'));
      return;
    }
    const eposta = secili;
    setOnay({
      mesaj: t('kredi.yonetim.onayHarca', { eposta, saat: saat(miktar), yeni: saat(yeni) }),
      calistir: async () => {
        const sonuc = await saatHarca({
          eposta,
          saat: miktar,
          aciklama: harcaAciklama.trim(),
          proje_id: harcaProje ? Number(harcaProje) : null,
          izin_eksi: izinEksi,
        });
        toast.success(t('kredi.yonetim.harcandi', { bakiye: saat(sonuc.bakiye) }));
        setHarcaAciklama('');
        setIzinEksi(false);
        await yenile(eposta);
      },
    });
  };

  const ekleGonder = (olay: FormEvent) => {
    olay.preventDefault();
    if (!secili) return;
    const miktar = Number(ekleSaat.replace(',', '.'));
    if (!saatGecerli(miktar, ekleTur === 'duzeltme')) {
      toast.error(t('kredi.yonetim.saatGecersiz'));
      return;
    }
    if (!ekleAciklama.trim()) {
      toast.error(t('kredi.yonetim.eksik'));
      return;
    }
    const eposta = secili;
    const yeni = (ayrinti?.bakiye ?? 0) + miktar;
    setOnay({
      mesaj: t('kredi.yonetim.onayEkle', {
        eposta,
        saat: saat(miktar),
        tur: t(`kredi.tur.${ekleTur}`),
        yeni: saat(yeni),
      }),
      calistir: async () => {
        const sonuc = await krediEkle({ eposta, saat: miktar, tur: ekleTur, aciklama: ekleAciklama.trim() });
        toast.success(t('kredi.yonetim.eklendi', { bakiye: saat(sonuc.bakiye) }));
        setEkleAciklama('');
        setArama('');
        await yenile(eposta);
      },
    });
  };

  const dolumlariIsle = () => {
    setOnay({
      mesaj: t('kredi.yonetim.sureDolumOnay'),
      calistir: async () => {
        const sonuc = await sureDolumlariniIsle();
        toast.success(t('kredi.yonetim.sureDolumSonuc', { sayi: sonuc.yazilan, saat: saat(sonuc.toplam_saat) }));
        await yenile(secili ?? undefined);
      },
    });
  };

  return (
    <div className="space-y-6" data-testid="kredi-defteri">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="flex items-center gap-2 text-2xl font-bold">
            <Coins className="h-6 w-6 text-emerald-400" aria-hidden="true" />
            {t('kredi.baslik')}
          </h2>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{t('kredi.aciklama')}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={() => void yenile(secili ?? undefined)} className="!bg-transparent">
            <RefreshCw className={`mr-2 h-4 w-4 ${yukleniyor ? 'animate-spin' : ''}`} aria-hidden="true" />
            {t('kredi.yenile')}
          </Button>
          <Button variant="outline" onClick={dolumlariIsle} className="!bg-transparent" data-testid="sure-dolum">
            <Hourglass className="mr-2 h-4 w-4" aria-hidden="true" />
            {t('kredi.yonetim.sureDolum')}
          </Button>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
        {/* Müşteri listesi */}
        <section className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-4">
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-widest text-muted-foreground">
            {t('kredi.yonetim.musteriler')}
          </h3>
          <div className="relative mb-3">
            <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-muted-foreground" aria-hidden="true" />
            <Input
              value={arama}
              onChange={(o) => setArama(o.target.value)}
              placeholder={t('kredi.yonetim.ara')}
              aria-label={t('kredi.yonetim.ara')}
              className="pl-9"
              data-testid="kredi-ara"
            />
          </div>

          {yeniEposta && (
            <button
              type="button"
              onClick={() => setSecili(yeniEposta)}
              className="mb-3 flex w-full items-center gap-2 rounded-xl border border-dashed border-emerald-400/40 bg-emerald-500/5 p-3 text-left text-sm text-emerald-200 hover:bg-emerald-500/10"
              data-testid="kredi-yeni-musteri"
            >
              <UserPlus className="h-4 w-4 shrink-0" aria-hidden="true" />
              <span className="min-w-0 break-all">{t('kredi.yonetim.yeniMusteri', { eposta: yeniEposta })}</span>
            </button>
          )}

          {yukleniyor && musteriler.length === 0 ? (
            <div className="flex justify-center py-8 text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
            </div>
          ) : suzulmus.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">{t('kredi.yonetim.bos')}</p>
          ) : (
            <ul className="max-h-[32rem] space-y-2 overflow-y-auto pr-1">
              {suzulmus.map((m) => {
                const gun = kalanGun(m.en_yakin_son_kullanma);
                const aktif = m.eposta === secili;
                return (
                  <li key={m.eposta}>
                    <button
                      type="button"
                      onClick={() => setSecili(m.eposta)}
                      aria-pressed={aktif}
                      className={`w-full rounded-xl border p-3 text-left transition-colors ${
                        aktif
                          ? 'cam-secili border-purple-400/50 bg-purple-500/10'
                          : 'border-white/5 bg-white/[0.02] hover:border-white/15'
                      }`}
                    >
                      <div className="flex items-baseline justify-between gap-2">
                        <span className="min-w-0 truncate text-sm">{m.eposta}</span>
                        <span className={`shrink-0 font-mono text-sm font-semibold ${m.bakiye < 0 ? 'text-red-300' : ''}`}>
                          {t('kredi.saatKisa', { deger: saat(m.bakiye) })}
                        </span>
                      </div>
                      <div className="mt-1 flex flex-wrap items-center justify-between gap-2 text-[11px] text-muted-foreground">
                        <span className={sonKullanmaRengi(gun)}>
                          {m.en_yakin_son_kullanma
                            ? t('kredi.yonetim.enYakin', {
                                saat: saat(m.en_yakin_miktar ?? 0),
                                tarih: tarihBicimle(m.en_yakin_son_kullanma, dil),
                              })
                            : '—'}
                        </span>
                        {m.dolum_bekleyen > 0 && (
                          <span className="text-red-300">
                            {t('kredi.yonetim.dolumBekleyen', { deger: saat(m.dolum_bekleyen) })}
                          </span>
                        )}
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        {/* Seçili müşteri */}
        <section className="space-y-6">
          {!secili ? (
            <div className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-10 text-center text-sm text-muted-foreground">
              {t('kredi.yonetim.secimYok')}
            </div>
          ) : (
            <>
              <div className="cam-kart flex flex-wrap items-end justify-between gap-4 rounded-2xl border border-white/10 bg-white/[0.03] p-6">
                <div className="min-w-0">
                  <p className="break-all text-sm text-muted-foreground">{secili}</p>
                  <p
                    className={`mt-1 text-4xl font-bold ${ayrinti && ayrinti.bakiye < 0 ? 'text-red-300' : ''}`}
                    data-testid="kredi-bakiye"
                  >
                    {ayrinti ? t('kredi.saatKisa', { deger: saat(ayrinti.bakiye) }) : '…'}
                  </p>
                  {ayrinti && ayrinti.borc > 0 && (
                    <p className="mt-1 text-xs text-red-300">{t('kredi.yonetim.borc', { deger: saat(ayrinti.borc) })}</p>
                  )}
                </div>
                {ayrinti && ayrinti.yaklasan_son_kullanma.length > 0 && (
                  <ul className="space-y-1 text-right text-xs">
                    {ayrinti.yaklasan_son_kullanma.slice(0, 3).map((k) => (
                      <li key={k.tarih} className={sonKullanmaRengi(kalanGun(k.tarih))}>
                        {t('kredi.yonetim.enYakin', { saat: saat(k.miktar), tarih: tarihBicimle(k.tarih, dil) })}
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <div className="grid gap-6 md:grid-cols-2">
                <form
                  onSubmit={harcaGonder}
                  className="cam-kart space-y-3 rounded-2xl border border-white/10 bg-white/[0.03] p-5"
                  data-testid="kredi-harca-formu"
                >
                  <h4 className="flex items-center gap-2 font-semibold">
                    <MinusCircle className="h-4 w-4 text-amber-300" aria-hidden="true" />
                    {t('kredi.yonetim.harcaBaslik')}
                  </h4>
                  <label className="block text-xs text-muted-foreground">
                    {t('kredi.yonetim.saatEtiket')}
                    <Input
                      type="number"
                      step="0.25"
                      min="0.25"
                      value={harcaSaat}
                      onChange={(o) => setHarcaSaat(o.target.value)}
                      className="mt-1"
                      name="harca-saat"
                    />
                  </label>
                  <label className="block text-xs text-muted-foreground">
                    {t('kredi.yonetim.aciklamaEtiket')}
                    <Input
                      value={harcaAciklama}
                      onChange={(o) => setHarcaAciklama(o.target.value)}
                      maxLength={500}
                      className="mt-1"
                      name="harca-aciklama"
                    />
                  </label>
                  <label className="block text-xs text-muted-foreground">
                    {t('kredi.yonetim.projeEtiket')}
                    <select
                      value={harcaProje}
                      onChange={(o) => setHarcaProje(o.target.value)}
                      className={`${SECIM_SINIFI} mt-1`}
                    >
                      <option value="" className="bg-background">
                        {t('kredi.yonetim.projeYok')}
                      </option>
                      {musteriProjeleri.length > 0 && (
                        <optgroup label={t('kredi.yonetim.buMusterininProjeleri')} className="bg-background">
                          {musteriProjeleri.map((p) => (
                            <option key={p.id} value={String(p.id)} className="bg-background">
                              {p.title}
                            </option>
                          ))}
                        </optgroup>
                      )}
                      {digerProjeler.length > 0 && (
                        <optgroup label={t('kredi.yonetim.digerProjeler')} className="bg-background">
                          {digerProjeler.map((p) => (
                            <option key={p.id} value={String(p.id)} className="bg-background">
                              {p.title}
                            </option>
                          ))}
                        </optgroup>
                      )}
                    </select>
                  </label>
                  <label className="flex items-center gap-2 text-xs text-muted-foreground">
                    <input
                      type="checkbox"
                      checked={izinEksi}
                      onChange={(o) => setIzinEksi(o.target.checked)}
                      className="h-4 w-4 accent-purple-500"
                    />
                    {t('kredi.yonetim.izinEksi')}
                  </label>
                  <Button type="submit" className="w-full" disabled={!ayrinti || ayrintiYukleniyor}>
                    {t('kredi.yonetim.harcaDugme')}
                  </Button>
                </form>

                <form
                  onSubmit={ekleGonder}
                  className="cam-kart space-y-3 rounded-2xl border border-white/10 bg-white/[0.03] p-5"
                  data-testid="kredi-ekle-formu"
                >
                  <h4 className="flex items-center gap-2 font-semibold">
                    <PlusCircle className="h-4 w-4 text-emerald-300" aria-hidden="true" />
                    {t('kredi.yonetim.ekleBaslik')}
                  </h4>
                  <label className="block text-xs text-muted-foreground">
                    {t('kredi.yonetim.turEtiket')}
                    <select
                      value={ekleTur}
                      onChange={(o) => setEkleTur(o.target.value as YuklemeTuru)}
                      className={`${SECIM_SINIFI} mt-1`}
                      name="ekle-tur"
                    >
                      {YUKLEME_TURLERI.map((tur) => (
                        <option key={tur} value={tur} className="bg-background">
                          {t(`kredi.tur.${tur}`)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="block text-xs text-muted-foreground">
                    {t('kredi.yonetim.saatEtiket')}
                    <Input
                      type="number"
                      step="0.25"
                      min={ekleTur === 'duzeltme' ? undefined : '0.25'}
                      value={ekleSaat}
                      onChange={(o) => setEkleSaat(o.target.value)}
                      className="mt-1"
                      name="ekle-saat"
                    />
                  </label>
                  {ekleTur === 'duzeltme' && (
                    <p className="text-[11px] text-muted-foreground">{t('kredi.yonetim.duzeltmeIpucu')}</p>
                  )}
                  <label className="block text-xs text-muted-foreground">
                    {t('kredi.yonetim.aciklamaEtiket')}
                    <Input
                      value={ekleAciklama}
                      onChange={(o) => setEkleAciklama(o.target.value)}
                      maxLength={500}
                      className="mt-1"
                      name="ekle-aciklama"
                    />
                  </label>
                  <Button type="submit" variant="outline" className="w-full !bg-transparent">
                    {t('kredi.yonetim.ekleDugme')}
                  </Button>
                </form>
              </div>

              <div className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-5">
                <h4 className="mb-3 font-semibold">{t('kredi.yonetim.hareketler')}</h4>
                {ayrintiYukleniyor && !ayrinti ? (
                  <div className="flex justify-center py-6 text-muted-foreground">
                    <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
                  </div>
                ) : !ayrinti || ayrinti.hareketler.length === 0 ? (
                  <p className="py-4 text-sm text-muted-foreground">{t('kredi.yonetim.hareketYok')}</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm" data-testid="kredi-hareketler">
                      <thead className="text-xs text-muted-foreground">
                        <tr className="border-b border-white/10">
                          <th className="py-2 pr-4 font-medium">{t('kredi.sutun.tarih')}</th>
                          <th className="py-2 pr-4 font-medium">{t('kredi.sutun.tur')}</th>
                          <th className="py-2 pr-4 font-medium">{t('kredi.sutun.aciklama')}</th>
                          <th className="py-2 pr-4 text-right font-medium">{t('kredi.sutun.miktar')}</th>
                          <th className="py-2 pr-4 font-medium">{t('kredi.sutun.sonKullanma')}</th>
                          <th className="py-2 font-medium">{t('kredi.sutun.yazan')}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {ayrinti.hareketler.map((h) => (
                          <tr key={h.id} className="border-b border-white/5 align-top">
                            <td className="whitespace-nowrap py-2 pr-4 text-xs text-muted-foreground">
                              {tarihBicimle(h.created_at, dil)}
                            </td>
                            <td className="py-2 pr-4">
                              <span
                                className={`inline-block whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-medium ${turRengi(h.tur)}`}
                              >
                                {t(`kredi.tur.${h.tur}`, { defaultValue: h.tur })}
                              </span>
                            </td>
                            <td className="py-2 pr-4 text-xs">
                              {h.aciklama || '—'}
                              {h.proje_id ? (
                                <span className="text-muted-foreground">
                                  {' · '}
                                  {projeler.find((p) => String(p.id) === String(h.proje_id))?.title ?? `#${h.proje_id}`}
                                </span>
                              ) : null}
                            </td>
                            <td
                              className={`whitespace-nowrap py-2 pr-4 text-right font-mono ${h.miktar < 0 ? 'text-amber-300' : 'text-emerald-300'}`}
                            >
                              {h.miktar > 0 ? '+' : ''}
                              {saat(h.miktar)}
                            </td>
                            <td className="whitespace-nowrap py-2 pr-4 text-xs text-muted-foreground">
                              {h.son_kullanma ? tarihBicimle(h.son_kullanma, dil) : '—'}
                            </td>
                            <td className="py-2 text-xs text-muted-foreground">
                              {h.olusturan_eposta || t('kredi.yonetim.sistem')}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </>
          )}
        </section>
      </div>

      {onay && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="kredi-onay-baslik"
          onClick={() => !calisiyor && setOnay(null)}
        >
          <div
            className="cam-kart w-full max-w-md rounded-2xl border border-white/10 bg-background p-6 shadow-2xl"
            onClick={(o) => o.stopPropagation()}
            data-testid="kredi-onay"
          >
            <h3 id="kredi-onay-baslik" className="text-lg font-semibold">
              {t('kredi.yonetim.onayBaslik')}
            </h3>
            <p className="mt-3 break-words text-sm text-muted-foreground">{onay.mesaj}</p>
            <div className="mt-6 flex justify-end gap-2">
              <Button variant="outline" className="!bg-transparent" onClick={() => setOnay(null)} disabled={calisiyor}>
                {t('kredi.yonetim.vazgec')}
              </Button>
              <Button onClick={() => void onayla()} disabled={calisiyor} data-testid="kredi-onayla" autoFocus>
                {calisiyor && <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />}
                {t('kredi.yonetim.onayla')}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
