import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Eye, Layers, Loader2, PackagePlus, RotateCcw, Sparkles, TriangleAlert, Undo2, Wand2, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { SUPPORTED_LANGUAGES } from '@/i18n';
import { modulIkonu } from '@/lib/modulIkonlari';
import {
  PaketHatasi,
  hazirAyarlariGeriAl,
  hazirAyarlariUygula,
  katalogGetir,
  musteriBilgisiGetir,
  onizle,
  paketiKaldir,
  paketiUygula,
  type Atlanan,
  type HazirOge,
  type Katalog,
  type MusteriBilgisi,
  type Onizleme,
  type PaketGirdisi,
  type Uygulama,
} from '@/lib/sektorPaketi';

/**
 * Faz 6R — Yönetici › Sistem › Modüller (müşteri seçiliyken): "Sektör paketi uygula" ve
 * "Hazır ayarları uygula". Akış: paket (ve alt seçenek) seç → önizleme (açılacak / zaten açık
 * modüller, plan etkisi, oluşturulacak başlangıç kayıtları, uyarılar, otomasyon önerileri) →
 * uygula (sunucuda TEK işlem) → geçmiş: "paketi kaldır" / "hazır ayarları geri al".
 *
 * Metinler `sektorPaketi` ek paketinde; paket/set adları `modulVitrini` ek paketinden
 * (bu bileşen ikisini birlikte yükleyerek açılıyor — ModulYonetimi). Modül adları `modul`dan.
 */

type Kip = 'paket' | 'hazir';

const KART = 'cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-4 sm:p-5';
const SECIM =
  'h-10 w-full rounded-md border border-white/10 bg-white/5 px-3 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-purple-500/40';
const ROZET = 'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wider';

function tarih(iso: string | null, dil: string): string {
  if (!iso) return '';
  try {
    return new Intl.DateTimeFormat(dil, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(iso));
  } catch {
    return iso;
  }
}

export default function SektorPaketiAlani({
  eposta,
  ilkPaket,
  onDegisti,
}: {
  eposta: string;
  /** Derin bağlantı (`?paket=`): açılışta bu paketle "Sektör paketi uygula" açık gelir. */
  ilkPaket?: string | null;
  onDegisti: () => void;
}) {
  const { t, i18n } = useTranslation();
  const [katalog, setKatalog] = useState<Katalog | null>(null);
  const [bilgi, setBilgi] = useState<MusteriBilgisi | null>(null);
  const [kip, setKip] = useState<Kip | null>(null);
  const [paket, setPaket] = useState<string | null>(null);
  const [setAnahtari, setSetAnahtari] = useState<string | null>(null);
  const [dil, setDil] = useState('tr');
  const [isletme, setIsletme] = useState('');
  const [adres, setAdres] = useState('');
  const [hazirDa, setHazirDa] = useState(true);
  const [bildirim, setBildirim] = useState(true);
  const [onizleme, setOnizleme] = useState<Onizleme | null>(null);
  const [calisiyor, setCalisiyor] = useState<string | null>(null);
  const [kaldirAcik, setKaldirAcik] = useState<number | null>(null);
  const [kaldirHazirDa, setKaldirHazirDa] = useState(true);
  const [kaldirBildirim, setKaldirBildirim] = useState(true);
  const [geriAlAcik, setGeriAlAcik] = useState<number | null>(null);

  const hataGoster = useCallback(
    (h: unknown) => {
      if (h instanceof PaketHatasi) {
        const modul = h.modul ? t(`modul.m.${h.modul}.ad`, { defaultValue: h.modul }) : '';
        toast.error(t(`sektorPaketi.hataKod.${h.kod}`, { modul, defaultValue: t('sektorPaketi.hata') }));
      } else {
        toast.error(t('sektorPaketi.hata'));
      }
    },
    [t]
  );

  const bilgiYukle = useCallback(async () => {
    try {
      const b = await musteriBilgisiGetir(eposta);
      setBilgi(b);
      return b;
    } catch (h) {
      hataGoster(h);
      return null;
    }
  }, [eposta, hataGoster]);

  // Müşteri değişince her şeyi sıfırla.
  useEffect(() => {
    setKip(null);
    setOnizleme(null);
    setKaldirAcik(null);
    setGeriAlAcik(null);
    let iptal = false;
    (async () => {
      try {
        const [k, b] = await Promise.all([katalogGetir(), musteriBilgisiGetir(eposta)]);
        if (iptal) return;
        setKatalog(k);
        setBilgi(b);
        setDil(b.varsayilan.dil || 'tr');
        setIsletme(b.varsayilan.isletme_adi || '');
        setAdres(b.varsayilan.adres || '');
        if (ilkPaket && k.paketler.some((p) => p.anahtar === ilkPaket)) {
          setKip('paket');
          setPaket(ilkPaket);
          setSetAnahtari(k.paketler.find((p) => p.anahtar === ilkPaket)?.setler[0] ?? null);
        }
      } catch (h) {
        if (!iptal) hataGoster(h);
      }
    })();
    return () => {
      iptal = true;
    };
  }, [eposta, ilkPaket, hataGoster]);

  const seciliPaket = useMemo(() => katalog?.paketler.find((p) => p.anahtar === paket) ?? null, [katalog, paket]);
  const setler = useMemo(() => {
    if (!katalog) return [];
    if (kip === 'paket') return katalog.setler.filter((s) => s.paket === paket);
    return katalog.setler;
  }, [katalog, kip, paket]);

  const ac = (yeni: Kip) => {
    setKip(yeni);
    setOnizleme(null);
    if (yeni === 'hazir') {
      setPaket(null);
      setSetAnahtari(katalog?.setler[0]?.anahtar ?? null);
    } else {
      setPaket(null);
      setSetAnahtari(null);
    }
  };

  const paketSec = (anahtar: string) => {
    setPaket(anahtar);
    setSetAnahtari(katalog?.paketler.find((p) => p.anahtar === anahtar)?.setler[0] ?? null);
    setOnizleme(null);
  };

  const girdi = (): PaketGirdisi => ({
    paket: kip === 'paket' ? paket : null,
    set: setAnahtari,
    dil,
    isletme_adi: isletme.trim(),
    adres: adres.trim(),
    hazir_ayarlar: kip === 'paket' ? hazirDa : true,
    bildirim,
  });

  const onizlemeAl = async () => {
    setCalisiyor('onizle');
    try {
      setOnizleme(await onizle(eposta, girdi()));
    } catch (h) {
      hataGoster(h);
    } finally {
      setCalisiyor(null);
    }
  };

  const uygula = async () => {
    setCalisiyor('uygula');
    try {
      if (kip === 'paket') {
        await paketiUygula(eposta, girdi());
        toast.success(t('sektorPaketi.uygulandi', { ad: t(`modulVitrini.p.${paket}.ad`) }));
      } else {
        const s = await hazirAyarlariUygula(eposta, girdi());
        toast.success(s.uygulama ? t('sektorPaketi.hazirUygulandi') : t('sektorPaketi.degisiklikYok'));
      }
      setKip(null);
      setOnizleme(null);
      await bilgiYukle();
      onDegisti();
    } catch (h) {
      hataGoster(h);
    } finally {
      setCalisiyor(null);
    }
  };

  const kaldir = async (u: Uygulama) => {
    setCalisiyor(`kaldir-${u.id}`);
    try {
      const s = await paketiKaldir(u.id, { hazir_ayarlar: kaldirHazirDa, bildirim: kaldirBildirim });
      toast.success(t('sektorPaketi.gecmis.kaldirildiMesaj', { sayi: s.kapatilan.length }));
      setKaldirAcik(null);
      await bilgiYukle();
      onDegisti();
    } catch (h) {
      hataGoster(h);
    } finally {
      setCalisiyor(null);
    }
  };

  const geriAl = async (u: Uygulama) => {
    setCalisiyor(`geri-${u.id}`);
    try {
      const s = await hazirAyarlariGeriAl(u.id);
      toast.success(
        t('sektorPaketi.gecmis.hazirGeriAlindiMesaj', { silinen: s.hazir.silinen.length, korunan: s.hazir.korunan.length })
      );
      setGeriAlAcik(null);
      await bilgiYukle();
      onDegisti();
    } catch (h) {
      hataGoster(h);
    } finally {
      setCalisiyor(null);
    }
  };

  // ------------------------------------------------------------------ biçimleyiciler
  const saatOzeti = (ham: string) => {
    // "0:09:00-12:30,13:30-18:00;1:…" → "Pzt–Cum 09:00–12:30, 13:30–18:00 · Cmt 09:00–13:00"
    const gunler = ham.split(';').filter(Boolean).map((p) => {
      const [g, ...geri] = p.split(':');
      return { g: Number(g), araliklar: geri.join(':').replace(/-/g, '–').replace(/,/g, ', ') };
    });
    const gruplar: { bas: number; bit: number; araliklar: string }[] = [];
    for (const x of gunler) {
      const son = gruplar[gruplar.length - 1];
      if (son && son.araliklar === x.araliklar && son.bit === x.g - 1) son.bit = x.g;
      else gruplar.push({ bas: x.g, bit: x.g, araliklar: x.araliklar });
    }
    return gruplar
      .map((g) => {
        const ad = (n: number) => t(`sektorPaketi.gun.${n}`);
        return `${g.bas === g.bit ? ad(g.bas) : `${ad(g.bas)}–${ad(g.bit)}`} ${g.araliklar}`;
      })
      .join(' · ');
  };

  const ogeMetni = (o: HazirOge) => {
    const tur = t(`sektorPaketi.oge.${o.tur}`, { defaultValue: o.tur });
    if (o.tur === 'oneri') return t(`sektorPaketi.oneri.${o.ad}`, { defaultValue: o.ad });
    if (o.tur === 'saatler') return `${tur}: ${saatOzeti(o.ad)}`;
    const ek: string[] = [];
    if (o.sure_dk) ek.push(t('sektorPaketi.ayrinti.sure', { sayi: o.sure_dk }));
    if (o.tampon_dk) ek.push(t('sektorPaketi.ayrinti.tampon', { sayi: o.tampon_dk }));
    if (o.kapasite && o.kapasite > 1) ek.push(t('sektorPaketi.ayrinti.kapasite', { sayi: o.kapasite }));
    if (o.tur === 'randevu_turu' && o.aktif === false) ek.push(t('sektorPaketi.ayrinti.pasif'));
    if (o.tur === 'sss' && o.sayi) ek.push(t('sektorPaketi.ayrinti.sss', { sayi: o.sayi }));
    if (o.madde_sayisi) ek.push(t('sektorPaketi.ayrinti.madde', { sayi: o.madde_sayisi }));
    if (o.hizmet_sayisi) ek.push(t('sektorPaketi.ayrinti.hizmet', { sayi: o.hizmet_sayisi }));
    if (o.tur === 'dizi_adimi' && o.bekle_gun !== undefined) ek.push(t('sektorPaketi.ayrinti.gun', { sayi: o.bekle_gun }));
    return `${tur}: ${o.ad}${ek.length ? ` · ${ek.join(' · ')}` : ''}`;
  };

  const atlananMetni = (a: Atlanan) =>
    `${t(`sektorPaketi.neden.${a.neden}`, { sayi: a.sayi ?? 0, sinir: a.sinir ?? 0, defaultValue: a.neden })}${
      a.ad ? ` (${a.ad})` : ''
    }`;

  const modulAdi = (k: string) => t(`modul.m.${k}.ad`, { defaultValue: k });

  if (!katalog || !bilgi) {
    return (
      <div className={`${KART} flex items-center gap-2 text-sm text-muted-foreground`}>
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
        {t('sektorPaketi.calisiyor')}
      </div>
    );
  }

  return (
    <section className={KART} data-testid="sektor-paketi-alani" aria-labelledby="sp-baslik">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 id="sp-baslik" className="flex items-center gap-2 font-semibold">
            <Layers className="h-4 w-4 text-purple-300" aria-hidden="true" />
            {t('sektorPaketi.baslik')}
          </h3>
          <p className="mt-1 max-w-2xl text-xs text-muted-foreground">{t('sektorPaketi.aciklama')}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            size="sm"
            onClick={() => ac('paket')}
            className="gap-1.5 border-0 bg-gradient-to-r from-purple-600 to-pink-600 text-white"
            data-testid="sektor-paketi-uygula"
            aria-pressed={kip === 'paket'}
          >
            <PackagePlus className="h-4 w-4" aria-hidden="true" />
            {t('sektorPaketi.paketUygula')}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => ac('hazir')}
            className="gap-1.5 !bg-transparent border-white/20"
            data-testid="hazir-ayar-uygula"
            aria-pressed={kip === 'hazir'}
          >
            <Wand2 className="h-4 w-4" aria-hidden="true" />
            {t('sektorPaketi.hazirUygula')}
          </Button>
        </div>
      </div>

      {kip ? (
        <div className="mt-4 space-y-4 rounded-xl border border-white/10 bg-black/20 p-3 sm:p-4" data-testid="sp-form" data-kip={kip}>
          {kip === 'paket' ? (
            <div>
              <p className="mb-2 text-xs uppercase tracking-widest text-muted-foreground">{t('sektorPaketi.paketSec')}</p>
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3" role="radiogroup" aria-label={t('sektorPaketi.paketSec')}>
                {katalog.paketler.map((p) => {
                  const Ikon = modulIkonu(p.ikon);
                  return (
                    <button
                      key={p.anahtar}
                      type="button"
                      role="radio"
                      aria-checked={paket === p.anahtar}
                      onClick={() => paketSec(p.anahtar)}
                      data-paket={p.anahtar}
                      className={`flex min-w-0 items-center gap-2 rounded-lg border px-3 py-2 text-start text-sm transition-colors ${
                        paket === p.anahtar ? 'border-purple-400/60 bg-purple-500/20 text-white' : 'border-white/10 hover:border-white/25'
                      }`}
                    >
                      <Ikon className="h-4 w-4 shrink-0 text-pink-300" aria-hidden="true" />
                      <span className="min-w-0 truncate">{t(`modulVitrini.p.${p.anahtar}.ad`)}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          ) : null}

          {(kip === 'hazir' || (seciliPaket && setler.length > 0)) ? (
            <div>
              <p className="mb-2 text-xs uppercase tracking-widest text-muted-foreground">{t('sektorPaketi.setSec')}</p>
              <div className="grid gap-2 sm:grid-cols-2" role="radiogroup" aria-label={t('sektorPaketi.setSec')}>
                {setler.map((s) => {
                  const Ikon = modulIkonu(s.ikon);
                  return (
                    <button
                      key={s.anahtar}
                      type="button"
                      role="radio"
                      aria-checked={setAnahtari === s.anahtar}
                      onClick={() => {
                        setSetAnahtari(s.anahtar);
                        setOnizleme(null);
                      }}
                      data-set={s.anahtar}
                      className={`flex min-w-0 gap-2 rounded-lg border px-3 py-2 text-start transition-colors ${
                        setAnahtari === s.anahtar ? 'border-purple-400/60 bg-purple-500/20' : 'border-white/10 hover:border-white/25'
                      }`}
                    >
                      <Ikon className="mt-0.5 h-4 w-4 shrink-0 text-purple-300" aria-hidden="true" />
                      <span className="min-w-0">
                        <span className="block text-sm font-medium">{t(`modulVitrini.s.${s.anahtar}.ad`)}</span>
                        <span className="block text-xs text-muted-foreground">{t(`modulVitrini.s.${s.anahtar}.ozet`)}</span>
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          ) : null}

          {setAnahtari && (kip === 'hazir' || seciliPaket) ? (
            <>
              <div className="grid gap-3 sm:grid-cols-3">
                <label className="block text-xs text-muted-foreground" htmlFor="sp-dil">
                  <span className="mb-1 block">{t('sektorPaketi.dil')}</span>
                  <select id="sp-dil" value={dil} onChange={(e) => { setDil(e.target.value); setOnizleme(null); }} className={SECIM} data-testid="sp-dil">
                    {SUPPORTED_LANGUAGES.map((l) => (
                      <option key={l.code} value={l.code}>
                        {l.full}
                      </option>
                    ))}
                  </select>
                  <span className="mt-1 block text-[11px]">{t('sektorPaketi.dilNotu')}</span>
                </label>
                <label className="block text-xs text-muted-foreground" htmlFor="sp-isletme">
                  <span className="mb-1 block">{t('sektorPaketi.isletmeAdi')}</span>
                  <Input
                    id="sp-isletme"
                    value={isletme}
                    maxLength={100}
                    onChange={(e) => { setIsletme(e.target.value); setOnizleme(null); }}
                    className="h-10 bg-white/5 border-white/10"
                    data-testid="sp-isletme"
                  />
                  <span className="mt-1 block text-[11px]">{t('sektorPaketi.isletmeAdiNotu')}</span>
                </label>
                <label className="block text-xs text-muted-foreground" htmlFor="sp-adres">
                  <span className="mb-1 block">{t('sektorPaketi.adres')}</span>
                  <Input
                    id="sp-adres"
                    value={adres}
                    maxLength={300}
                    onChange={(e) => { setAdres(e.target.value); setOnizleme(null); }}
                    className="h-10 bg-white/5 border-white/10"
                    data-testid="sp-adres"
                  />
                  <span className="mt-1 block text-[11px]">{t('sektorPaketi.adresNotu')}</span>
                </label>
              </div>
              <div className="flex flex-col gap-2 text-sm sm:flex-row sm:flex-wrap sm:gap-5">
                {kip === 'paket' ? (
                  <label className="flex items-center gap-2">
                    <input type="checkbox" checked={hazirDa} onChange={(e) => { setHazirDa(e.target.checked); setOnizleme(null); }} className="h-4 w-4 accent-purple-500" data-testid="sp-hazir-da" />
                    {t('sektorPaketi.hazirDa')}
                  </label>
                ) : null}
                {kip === 'paket' ? (
                  <label className="flex items-center gap-2">
                    <input type="checkbox" checked={bildirim} onChange={(e) => setBildirim(e.target.checked)} className="h-4 w-4 accent-purple-500" data-testid="sp-bildirim" />
                    {t('sektorPaketi.bildirim')}
                  </label>
                ) : null}
              </div>
              <div className="flex flex-wrap gap-2">
                <Button type="button" size="sm" onClick={() => void onizlemeAl()} disabled={calisiyor !== null} className="gap-1.5" data-testid="sp-onizle">
                  {calisiyor === 'onizle' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Eye className="h-4 w-4" aria-hidden="true" />}
                  {t('sektorPaketi.onizle')}
                </Button>
                <Button type="button" size="sm" variant="ghost" onClick={() => setKip(null)} className="gap-1.5">
                  <X className="h-4 w-4" aria-hidden="true" />
                  {t('sektorPaketi.vazgec')}
                </Button>
              </div>
            </>
          ) : null}

          {onizleme ? (
            <div className="space-y-4 border-t border-white/10 pt-4" data-testid="sp-onizleme" data-set={onizleme.set}>
              <h4 className="text-sm font-semibold">{t('sektorPaketi.onizleme.baslik')}</h4>
              {onizleme.moduller.length > 0 ? (
                <div>
                  <p className="mb-1 text-xs uppercase tracking-widest text-muted-foreground">{t('sektorPaketi.onizleme.moduller')}</p>
                  <p className="mb-2 text-sm" data-testid="sp-ozet">
                    {t('sektorPaketi.onizleme.ozet', { acilacak: onizleme.ozet.acilacak, acik: onizleme.ozet.zaten_acik })}
                  </p>
                  <ol className="space-y-1.5">
                    {onizleme.moduller.map((m) => {
                      const Ikon = modulIkonu(m.ikon);
                      return (
                        <li key={m.anahtar} className="flex flex-wrap items-center gap-2 text-sm" data-sp-modul={m.anahtar} data-durum={m.durum}>
                          <Ikon className="h-4 w-4 text-purple-300" aria-hidden="true" />
                          <span className="font-medium">{t(m.ad_anahtari)}</span>
                          <span
                            className={`${ROZET} ${
                              m.durum === 'acilacak' ? 'border-emerald-400/40 bg-emerald-500/10 text-emerald-200' : 'border-white/15 text-muted-foreground'
                            }`}
                          >
                            {t(`sektorPaketi.durum.${m.durum}`)}
                          </span>
                          {!m.paketten ? <span className={`${ROZET} border-sky-400/30 text-sky-200`}>{t('sektorPaketi.durum.bagimlilik')}</span> : null}
                          <span className={`${ROZET} border-white/15 text-muted-foreground`}>
                            {m.etki === 'ust_pakette'
                              ? t('sektorPaketi.etki.ust_pakette', { paket: m.en_dusuk_paket ?? '' })
                              : t(`sektorPaketi.etki.${m.etki}`)}
                          </span>
                          {m.kredi ? <span className={`${ROZET} border-amber-400/30 text-amber-200`}>{t('sektorPaketi.etki.kredi')}</span> : null}
                        </li>
                      );
                    })}
                  </ol>
                  <p className="mt-2 text-xs text-muted-foreground">{t('sektorPaketi.onizleme.fiyat')}</p>
                </div>
              ) : null}

              {onizleme.hazir.some((b) => b.modul !== 'otomasyon') ? (
              <div>
                <p className="mb-1 text-xs uppercase tracking-widest text-muted-foreground">{t('sektorPaketi.onizleme.hazir')}</p>
                {kip === 'paket' && !hazirDa ? null : (
                  <p className="mb-2 text-sm">
                    {onizleme.ozet.olusturulacak > 0
                      ? t('sektorPaketi.onizleme.olusturulacak', { sayi: onizleme.ozet.olusturulacak })
                      : t('sektorPaketi.onizleme.bos')}
                  </p>
                )}
                <div className="grid gap-3 lg:grid-cols-2">
                  {onizleme.hazir
                    .filter((b) => b.modul !== 'otomasyon')
                    .map((b) => (
                      <div key={b.modul} className="rounded-lg border border-white/10 bg-white/[0.02] p-3" data-sp-hazir={b.modul}>
                        <p className="mb-1 text-sm font-medium">{modulAdi(b.modul)}</p>
                        <ul className="space-y-0.5 text-xs">
                          {b.ogeler.map((o, i) => (
                            <li key={i} className="text-foreground/90" data-sp-oge={o.tur}>
                              <bdi>{ogeMetni(o)}</bdi>
                            </li>
                          ))}
                          {b.atlanan.map((a, i) => (
                            <li key={`a${i}`} className="text-muted-foreground" data-sp-atlanan={a.neden}>
                              {t('sektorPaketi.onizleme.atlandi')}: {atlananMetni(a)}
                              {a.oneri ? (
                                <span className="mt-0.5 block italic">
                                  “<bdi>{a.oneri}</bdi>”
                                </span>
                              ) : null}
                            </li>
                          ))}
                        </ul>
                      </div>
                    ))}
                </div>
              </div>
              ) : null}

              {onizleme.uyarilar.length > 0 ? (
                <div className="rounded-lg border border-amber-400/30 bg-amber-500/10 p-3" data-testid="sp-uyarilar">
                  <p className="mb-1 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-widest text-amber-200">
                    <TriangleAlert className="h-3.5 w-3.5" aria-hidden="true" />
                    {t('sektorPaketi.onizleme.uyarilar')}
                  </p>
                  <ul className="list-disc space-y-0.5 ps-5 text-xs text-amber-100">
                    {onizleme.uyarilar.map((u) => (
                      <li key={u} data-sp-uyari={u}>
                        {t(`sektorPaketi.uyari.${u}`)}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {onizleme.oneriler.length > 0 ? (
                <div>
                  <p className="mb-1 flex items-center gap-1.5 text-xs uppercase tracking-widest text-muted-foreground">
                    <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
                    {t('sektorPaketi.onizleme.oneriler')}
                  </p>
                  <ul className="list-disc space-y-0.5 ps-5 text-xs">
                    {onizleme.oneriler.map((k) => (
                      <li key={k}>{t(`sektorPaketi.oneri.${k}`, { defaultValue: k })}</li>
                    ))}
                  </ul>
                  <p className="mt-1 text-[11px] text-muted-foreground">{t('sektorPaketi.onizleme.onerilerNotu')}</p>
                </div>
              ) : null}

              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  onClick={() => void uygula()}
                  disabled={calisiyor !== null}
                  className="gap-1.5 border-0 bg-gradient-to-r from-purple-600 to-pink-600 text-white"
                  data-testid="sp-uygula"
                >
                  {calisiyor === 'uygula' ? <Loader2 className="h-4 w-4 animate-spin" /> : <PackagePlus className="h-4 w-4" aria-hidden="true" />}
                  {kip === 'paket' ? t('sektorPaketi.uygula') : t('sektorPaketi.hazirUygula')}
                </Button>
              </div>
            </div>
          ) : null}
        </div>
      ) : null}

      {/* ---------------- Geçmiş ---------------- */}
      <div className="mt-5" data-testid="sp-gecmis">
        <p className="mb-2 text-xs uppercase tracking-widest text-muted-foreground">{t('sektorPaketi.gecmis.baslik')}</p>
        {bilgi.gecmis.length === 0 ? (
          <p className="text-xs text-muted-foreground">{t('sektorPaketi.gecmis.bos')}</p>
        ) : (
          <ul className="space-y-2">
            {bilgi.gecmis.map((u) => {
              const kaldirildi = u.durum === 'kaldirildi';
              const korunan = u.geri_alma?.korunan ?? [];
              const hazirSonuc = u.geri_alma?.hazir;
              return (
                <li key={u.id} className="rounded-lg border border-white/10 bg-white/[0.02] p-3 text-sm" data-sp-uygulama={u.id} data-durum={u.durum} data-hazir-durum={u.hazir_durum}>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">
                      {u.tur === 'paket' ? t(`modulVitrini.p.${u.paket}.ad`, { defaultValue: u.paket ?? '' }) : t('sektorPaketi.gecmis.tur_hazir')}
                    </span>
                    {u.set ? <span className="text-xs text-muted-foreground">· {t(`modulVitrini.s.${u.set}.ad`, { defaultValue: u.set })}</span> : null}
                    <span className={`${ROZET} ${kaldirildi ? 'border-white/15 text-muted-foreground' : 'border-emerald-400/40 bg-emerald-500/10 text-emerald-200'}`}>
                      {kaldirildi ? t('sektorPaketi.gecmis.kaldirildi') : t('sektorPaketi.gecmis.uygulandi')}
                    </span>
                    {u.hazir_durum === 'geri_alindi' ? (
                      <span className={`${ROZET} border-white/15 text-muted-foreground`}>{t('sektorPaketi.gecmis.hazirGeriAlindi')}</span>
                    ) : null}
                    <span className="ms-auto text-xs text-muted-foreground">{tarih(u.olusturma, i18n.language)}</span>
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {t('sektorPaketi.gecmis.sayilar', { modul: u.acilan_moduller.length, kayit: u.hazir_kayitlar.length })}
                  </p>
                  {korunan.length > 0 ? (
                    <p className="mt-1 text-xs text-amber-200">
                      {t('sektorPaketi.gecmis.korunan')}:{' '}
                      {korunan.map((k) => `${modulAdi(k.anahtar)} (${t(`sektorPaketi.neden.${k.neden}`, { defaultValue: k.neden })})`).join(', ')}
                    </p>
                  ) : null}
                  {hazirSonuc && hazirSonuc.korunan.length > 0 ? (
                    <p className="mt-1 text-xs text-amber-200" data-testid="sp-korunan-kayitlar">
                      {t('sektorPaketi.gecmis.korunan')}:{' '}
                      {hazirSonuc.korunan.map((k) => `${k.etiket} (${t(`sektorPaketi.neden.${k.neden}`, { defaultValue: k.neden })})`).join(', ')}
                    </p>
                  ) : null}
                  <div className="mt-2 flex flex-wrap gap-2">
                    {u.tur === 'paket' && !kaldirildi ? (
                      <Button type="button" size="sm" variant="outline" className="gap-1.5 !bg-transparent border-white/20" onClick={() => { setKaldirAcik(u.id); setGeriAlAcik(null); }} data-testid="sp-kaldir">
                        <Undo2 className="h-3.5 w-3.5" aria-hidden="true" />
                        {t('sektorPaketi.gecmis.kaldir')}
                      </Button>
                    ) : null}
                    {u.hazir_durum === 'uygulandi' ? (
                      <Button type="button" size="sm" variant="ghost" className="gap-1.5" onClick={() => { setGeriAlAcik(u.id); setKaldirAcik(null); }} data-testid="sp-hazir-geri-al">
                        <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
                        {t('sektorPaketi.gecmis.hazirGeriAl')}
                      </Button>
                    ) : null}
                  </div>
                  {kaldirAcik === u.id ? (
                    <div className="mt-2 space-y-2 rounded-lg border border-white/10 bg-black/20 p-3 text-xs" data-testid="sp-kaldir-onay">
                      <p className="text-muted-foreground">{t('sektorPaketi.gecmis.kaldirAciklama')}</p>
                      {u.hazir_durum === 'uygulandi' ? (
                        <label className="flex items-center gap-2">
                          <input type="checkbox" checked={kaldirHazirDa} onChange={(e) => setKaldirHazirDa(e.target.checked)} className="h-4 w-4 accent-purple-500" />
                          {t('sektorPaketi.gecmis.hazirDaGeriAl')}
                        </label>
                      ) : null}
                      <label className="flex items-center gap-2">
                        <input type="checkbox" checked={kaldirBildirim} onChange={(e) => setKaldirBildirim(e.target.checked)} className="h-4 w-4 accent-purple-500" />
                        {t('sektorPaketi.bildirim')}
                      </label>
                      <div className="flex flex-wrap gap-2">
                        <Button type="button" size="sm" variant="destructive" onClick={() => void kaldir(u)} disabled={calisiyor !== null} data-testid="sp-kaldir-onayla">
                          {calisiyor === `kaldir-${u.id}` ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                          {t('sektorPaketi.gecmis.kaldirOnay')}
                        </Button>
                        <Button type="button" size="sm" variant="ghost" onClick={() => setKaldirAcik(null)}>
                          {t('sektorPaketi.vazgec')}
                        </Button>
                      </div>
                    </div>
                  ) : null}
                  {geriAlAcik === u.id ? (
                    <div className="mt-2 space-y-2 rounded-lg border border-white/10 bg-black/20 p-3 text-xs" data-testid="sp-geri-al-onay">
                      <p className="text-muted-foreground">{t('sektorPaketi.gecmis.hazirGeriAlAciklama')}</p>
                      <div className="flex flex-wrap gap-2">
                        <Button type="button" size="sm" variant="destructive" onClick={() => void geriAl(u)} disabled={calisiyor !== null} data-testid="sp-geri-al-onayla">
                          {calisiyor === `geri-${u.id}` ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                          {t('sektorPaketi.gecmis.hazirGeriAlOnay')}
                        </Button>
                        <Button type="button" size="sm" variant="ghost" onClick={() => setGeriAlAcik(null)}>
                          {t('sektorPaketi.vazgec')}
                        </Button>
                      </div>
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </section>
  );
}
