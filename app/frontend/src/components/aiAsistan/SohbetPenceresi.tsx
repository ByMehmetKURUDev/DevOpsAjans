import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode } from 'react';
import type { TFunction } from 'i18next';
import { Bot, CheckCircle2, Loader2, Send, UserRound, X } from 'lucide-react';

import GuvenliMarkdown from '@/components/asistanlar/GuvenliMarkdown';
import {
  AcikHata,
  acikIstek,
  depoOku,
  depoYaz,
  oturumTaze,
  ustYaziRengi,
  type AcikYapilandirma,
  type AsistanDili,
  type EkranMesaji,
  type MesajYaniti,
} from '@/lib/asistanOrtak';

/**
 * Faz 5A — AI asistan sohbet penceresi. Herkese açık sayfa (`/asistan/<anahtar>`,
 * gömülü çerçeve `?gomulu=1`) ve panel önizlemesi aynı bileşeni kullanıyor.
 *
 * GÜVENLİK: yanıtlar `GuvenliMarkdown` ile çiziliyor (HTML yok); kaynak bağlantıları
 * yalnız http(s), yeni sekmede `noopener noreferrer nofollow`. Bal küpü alanı
 * (`web_adresi`) görünmez; botlar doldurursa sunucu "başarılı" deyip hiçbir şey yapmıyor.
 * Kişisel veri: yazma alanının altında aydınlatma satırı + gizlilik bağlantısı; insana
 * devir formunda ayrıca. Sohbet aynı sekmede sürsün diye mesajlar sessionStorage'da.
 */

export interface SohbetPenceresiProps {
  t: TFunction;
  dil: AsistanDili;
  yap: AcikYapilandirma;
  gomulu?: boolean;
  /** Gömüldüğü sitenin kökeni (postMessage / ancestorOrigins / referrer). */
  kaynak?: string | null;
  onizleme?: boolean;
  ekBasliklar?: () => Record<string, string>;
  onKapat?: () => void;
  /** İçeriğin doğal yüksekliği (gömülü pencere üst sayfaya bildiriyor). */
  onYukseklik?: (px: number) => void;
  /** sessionStorage anahtarı; null → saklanmaz (önizleme). */
  depoAnahtari?: string | null;
  className?: string;
}

interface Depo {
  oturum: string;
  mesajlar: EkranMesaji[];
  devirTamam?: boolean;
}

const GIRDI = 'w-full rounded-xl border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-zinc-500 focus:outline-none';

export default function SohbetPenceresi({
  t,
  dil,
  yap,
  gomulu = false,
  kaynak = null,
  onizleme = false,
  ekBasliklar,
  onKapat,
  onYukseklik,
  depoAnahtari = null,
  className = '',
}: SohbetPenceresiProps) {
  const ilk = useMemo(() => (depoAnahtari ? depoOku<Depo>(depoAnahtari) : null), [depoAnahtari]);
  const [oturum] = useState(() => (ilk && oturumTaze(ilk.oturum) ? ilk.oturum : yap.oturum));
  const [mesajlar, setMesajlar] = useState<EkranMesaji[]>(() => (ilk && oturumTaze(ilk.oturum) ? ilk.mesajlar : []));
  const [girdi, setGirdi] = useState('');
  const [gonderiliyor, setGonderiliyor] = useState(false);
  const [devirAcik, setDevirAcik] = useState(false);
  const [devirTamam, setDevirTamam] = useState(Boolean(ilk?.devirTamam));
  const [devirMesaj, setDevirMesaj] = useState<string | null>(null);
  const [ad, setAd] = useState('');
  const [eposta, setEposta] = useState('');
  const [telefon, setTelefon] = useState('');
  const [not, setNot] = useState('');
  const [balKupu, setBalKupu] = useState('');
  const [formHatasi, setFormHatasi] = useState<string | null>(null);
  const listeRef = useRef<HTMLDivElement>(null);
  const icerikRef = useRef<HTMLDivElement>(null);
  const ustRef = useRef<HTMLDivElement>(null);
  const altRef = useRef<HTMLDivElement>(null);
  const girdiRef = useRef<HTMLTextAreaElement>(null);

  const renk = /^#[0-9a-f]{6}$/i.test(yap.renk) ? yap.renk : '#7c3aed';
  const yazi = ustYaziRengi(renk);
  const yon = dil === 'ar' ? 'rtl' : 'ltr';
  const karsilama = yap.karsilama || yap.varsayilan_karsilama || t('asistanSayfa.karsilama');
  const aydinlatma = yap.aydinlatma.metin || t('asistanSayfa.aydinlatma', { ad: yap.ad });

  useEffect(() => {
    if (depoAnahtari) depoYaz(depoAnahtari, { oturum, mesajlar: mesajlar.slice(-60), devirTamam } satisfies Depo);
  }, [depoAnahtari, oturum, mesajlar, devirTamam]);

  // Yeni mesajda en alta kaydır.
  useLayoutEffect(() => {
    const l = listeRef.current;
    if (l) l.scrollTop = l.scrollHeight;
  }, [mesajlar, gonderiliyor, devirAcik, devirTamam]);

  // Doğal yükseklik: üst + mesajlar + alt (gömülü pencere bununla büyür, sınırda kaydırır).
  useEffect(() => {
    if (!onYukseklik || typeof ResizeObserver === 'undefined') return;
    const bildir = () => {
      const u = ustRef.current?.offsetHeight || 0;
      const i = icerikRef.current?.scrollHeight || 0;
      const a = altRef.current?.offsetHeight || 0;
      onYukseklik(Math.ceil(u + i + a + 24));
    };
    const g = new ResizeObserver(bildir);
    for (const el of [ustRef.current, icerikRef.current, altRef.current]) if (el) g.observe(el);
    bildir();
    return () => g.disconnect();
  }, [onYukseklik]);

  const basliklar = useCallback(() => (ekBasliklar ? ekBasliklar() : {}), [ekBasliklar]);
  const ortak = useMemo(
    () => ({ oturum, dil, gomulu, kaynak: kaynak || undefined, onizleme, web_adresi: balKupu || undefined }),
    [oturum, dil, gomulu, kaynak, onizleme, balKupu]
  );

  const gonder = async (ham: string) => {
    const soru = ham.trim();
    if (!soru || gonderiliyor) return;
    if (soru.length > yap.mesaj_siniri) return;
    setMesajlar((m) => [...m, { rol: 'kullanici', metin: soru }]);
    setGirdi('');
    setGonderiliyor(true);
    try {
      const r = await acikIstek<MesajYaniti>(
        `/api/v1/asistan/${encodeURIComponent(yap.anahtar)}/mesaj`,
        { method: 'POST', body: JSON.stringify({ ...ortak, mesaj: soru }) },
        basliklar()
      );
      setMesajlar((m) => [...m, { rol: 'asistan', metin: r.yanit, kaynaklar: r.kaynaklar, devir: r.devir_onerisi }]);
      if (r.mod === 'butce' && !devirTamam) setDevirAcik(true);
    } catch (e) {
      const kod = e instanceof AcikHata ? e.kod : 'genel';
      setMesajlar((m) => [...m, { rol: 'asistan', metin: t(`asistanSayfa.hata.${kod}`, { defaultValue: t('asistanSayfa.hata.genel') }), hata: true }]);
    } finally {
      setGonderiliyor(false);
      window.setTimeout(() => girdiRef.current?.focus(), 0);
    }
  };

  const devret = async (olay: FormEvent) => {
    olay.preventDefault();
    if (gonderiliyor) return;
    setFormHatasi(null);
    if (!ad.trim()) return setFormHatasi(t('asistanSayfa.hata.ad_gerekli'));
    if (!eposta.trim() && !telefon.trim()) return setFormHatasi(t('asistanSayfa.hata.iletisim_gerekli'));
    setGonderiliyor(true);
    try {
      const r = await acikIstek<{ ok: boolean; mesai?: boolean | null }>(
        `/api/v1/asistan/${encodeURIComponent(yap.anahtar)}/devret`,
        { method: 'POST', body: JSON.stringify({ ...ortak, ad, eposta, telefon, not }) },
        basliklar()
      );
      setDevirTamam(true);
      setDevirAcik(false);
      const mesaiDisi = r.mesai === false || (r.mesai === undefined && yap.mesai.aktif && yap.mesai.ici === false);
      setDevirMesaj(mesaiDisi ? t('asistanSayfa.devir.tamamMesaiDisi') : t('asistanSayfa.devir.tamam'));
    } catch (e) {
      const kod = e instanceof AcikHata ? e.kod : 'genel';
      setFormHatasi(t(`asistanSayfa.hata.${kod}`, { defaultValue: t('asistanSayfa.hata.genel') }));
    } finally {
      setGonderiliyor(false);
    }
  };

  const tus = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      void gonder(girdi);
    }
  };

  const avatar = yap.avatar ? (
    <img src={yap.avatar} alt="" className="h-9 w-9 shrink-0 rounded-full border border-white/40 object-cover" />
  ) : (
    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white/20" aria-hidden="true">
      <Bot className="h-5 w-5" />
    </span>
  );
  const kullaniciSayisi = mesajlar.filter((m) => m.rol === 'kullanici').length;
  const durumMetni = yap.mesai.aktif ? (yap.mesai.ici ? t('asistanSayfa.mesaiIci') : t('asistanSayfa.mesaiDisi')) : t('asistanSayfa.altBaslik');

  return (
    <div
      className={`flex h-full min-h-0 flex-col overflow-hidden bg-white text-zinc-900 ${className}`}
      dir={yon}
      lang={dil}
      data-testid="asistan-pencere"
      data-onizleme={onizleme ? '1' : '0'}
      style={{ fontFamily: 'inherit' }}
    >
      <div ref={ustRef} className="flex items-center gap-3 px-4 py-3" style={{ background: renk, color: yazi }}>
        {avatar}
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold" data-testid="asistan-ad">
            {yap.ad}
          </p>
          <p className="truncate text-xs opacity-85">{durumMetni}</p>
        </div>
        {!devirTamam && (
          <button
            type="button"
            onClick={() => setDevirAcik((x) => !x)}
            className="flex shrink-0 items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium"
            style={{ borderColor: yazi === '#ffffff' ? 'rgba(255,255,255,.55)' : 'rgba(17,24,39,.35)' }}
            data-testid="asistan-insan"
          >
            <UserRound className="h-3.5 w-3.5" aria-hidden="true" />
            <span className="hidden min-[360px]:inline">{t('asistanSayfa.insanla')}</span>
          </button>
        )}
        {onKapat && (
          <button type="button" onClick={onKapat} className="shrink-0 rounded-full p-1.5 hover:bg-black/10" aria-label={t('asistanSayfa.kapat')} data-testid="asistan-kapat">
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        )}
      </div>

      <div ref={listeRef} className="min-h-0 flex-1 overflow-y-auto bg-zinc-50 px-3 py-4" role="log" aria-live="polite" aria-label={t('asistanSayfa.mesajlar')}>
        <div ref={icerikRef} className="flex flex-col gap-3" data-testid="asistan-mesajlar">
          <Balon rol="asistan" renk={renk} yazi={yazi}>
            <p className="whitespace-pre-line">{karsilama}</p>
          </Balon>
          {kullaniciSayisi === 0 && yap.onerilen_sorular.length > 0 && (
            <div className="flex flex-wrap gap-2" data-testid="asistan-oneriler">
              {yap.onerilen_sorular.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => void gonder(s)}
                  className="rounded-full border bg-white px-3 py-1.5 text-start text-xs font-medium text-zinc-700 hover:bg-zinc-100"
                  style={{ borderColor: `${renk}66` }}
                >
                  {s}
                </button>
              ))}
            </div>
          )}
          {mesajlar.map((m, i) => (
            <Balon key={i} rol={m.rol} renk={renk} yazi={yazi} hata={m.hata}>
              {m.rol === 'kullanici' ? (
                <p className="whitespace-pre-wrap break-words">{m.metin}</p>
              ) : (
                <GuvenliMarkdown
                  metin={m.metin}
                  className="text-sm [&_blockquote]:border-zinc-300 [&_blockquote]:text-zinc-600 [&_code]:bg-zinc-100 [&_hr]:border-zinc-200 [&_li]:text-zinc-800 [&_p]:text-zinc-800 [&_pre]:border-zinc-200 [&_pre]:bg-zinc-100 [&_strong]:text-zinc-900"
                />
              )}
              {m.kaynaklar && m.kaynaklar.length > 0 && (
                <ol className="mt-2 space-y-0.5 border-t border-zinc-200 pt-2 text-[11px] text-zinc-500" data-testid="asistan-kaynaklar">
                  {m.kaynaklar.map((k) => (
                    <li key={`${k.no}-${k.kaynak_id}`} className="truncate">
                      <span className="font-semibold">[{k.no}]</span>{' '}
                      {k.adres && /^https?:\/\//i.test(k.adres) ? (
                        <a href={k.adres} target="_blank" rel="noopener noreferrer nofollow" className="underline decoration-dotted underline-offset-2">
                          {k.baslik || k.adres}
                        </a>
                      ) : (
                        <span>{k.baslik || t('asistanSayfa.kaynak')}</span>
                      )}
                    </li>
                  ))}
                </ol>
              )}
              {m.devir && !devirTamam && !devirAcik && (
                <button
                  type="button"
                  onClick={() => setDevirAcik(true)}
                  className="mt-2 inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-semibold"
                  style={{ background: renk, color: yazi }}
                  data-testid="asistan-devir-oneri"
                >
                  <UserRound className="h-3.5 w-3.5" aria-hidden="true" />
                  {t('asistanSayfa.insanla')}
                </button>
              )}
            </Balon>
          ))}
          {gonderiliyor && !devirAcik && (
            <div className="flex items-center gap-2 text-xs text-zinc-500" data-testid="asistan-yaziyor">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              {t('asistanSayfa.yaziyor')}
            </div>
          )}
          {devirTamam && (
            <div className="flex items-start gap-2 rounded-2xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900" data-testid="asistan-devir-tamam" role="status">
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              <p>{devirMesaj || t('asistanSayfa.devir.tamam')}</p>
            </div>
          )}
        </div>
      </div>

      <div ref={altRef} className="border-t border-zinc-200 bg-white px-3 pb-2 pt-2">
        {/* Bal küpü: görünmez, ekran okuyucudan da gizli. Mantıksal yön (-start): RTL'de sola
            itilen öğe yatay kaydırma alanını büyütüyordu (ar, 375 px). */}
        <input
          type="text"
          name="web_adresi"
          tabIndex={-1}
          autoComplete="off"
          value={balKupu}
          onChange={(e) => setBalKupu(e.target.value)}
          aria-hidden="true"
          className="pointer-events-none absolute -start-[9999px] top-0 h-px w-px opacity-0"
        />
        {devirAcik ? (
          <form onSubmit={devret} className="space-y-2" data-testid="asistan-devir-formu" noValidate>
            <p className="text-sm font-semibold text-zinc-800">{t('asistanSayfa.devir.baslik')}</p>
            <p className="text-xs text-zinc-500">{yap.mesai.aktif && yap.mesai.ici === false ? t('asistanSayfa.devir.aciklamaMesaiDisi') : t('asistanSayfa.devir.aciklama')}</p>
            <label className="block">
              <span className="sr-only">{t('asistanSayfa.devir.ad')}</span>
              <input className={GIRDI} value={ad} onChange={(e) => setAd(e.target.value)} placeholder={t('asistanSayfa.devir.ad')} maxLength={120} autoComplete="name" data-testid="asistan-devir-ad" />
            </label>
            <div className="grid gap-2 min-[420px]:grid-cols-2">
              <label className="block">
                <span className="sr-only">{t('asistanSayfa.devir.eposta')}</span>
                <input className={GIRDI} type="email" value={eposta} onChange={(e) => setEposta(e.target.value)} placeholder={t('asistanSayfa.devir.eposta')} maxLength={254} autoComplete="email" dir="ltr" data-testid="asistan-devir-eposta" />
              </label>
              <label className="block">
                <span className="sr-only">{t('asistanSayfa.devir.telefon')}</span>
                <input className={GIRDI} type="tel" value={telefon} onChange={(e) => setTelefon(e.target.value)} placeholder={t('asistanSayfa.devir.telefon')} maxLength={32} autoComplete="tel" dir="ltr" data-testid="asistan-devir-telefon" />
              </label>
            </div>
            <label className="block">
              <span className="sr-only">{t('asistanSayfa.devir.not')}</span>
              <textarea className={`${GIRDI} min-h-[56px] resize-none`} value={not} onChange={(e) => setNot(e.target.value)} placeholder={t('asistanSayfa.devir.not')} maxLength={1000} rows={2} data-testid="asistan-devir-not" />
            </label>
            {formHatasi && (
              <p className="text-xs font-medium text-red-600" role="alert" data-testid="asistan-devir-hata">
                {formHatasi}
              </p>
            )}
            <p className="text-[11px] leading-snug text-zinc-500" data-testid="asistan-devir-aydinlatma">
              {t('asistanSayfa.devir.aydinlatma', { ad: yap.ad })}{' '}
              <a href={yap.aydinlatma.baglanti} target="_blank" rel="noopener noreferrer" className="underline">
                {t('asistanSayfa.gizlilik')}
              </a>
            </p>
            <div className="flex gap-2">
              <button type="submit" disabled={gonderiliyor} className="flex-1 rounded-xl px-3 py-2 text-sm font-semibold disabled:opacity-60" style={{ background: renk, color: yazi }} data-testid="asistan-devir-gonder">
                {gonderiliyor ? <Loader2 className="mx-auto h-4 w-4 animate-spin" aria-hidden="true" /> : t('asistanSayfa.devir.gonder')}
              </button>
              <button type="button" onClick={() => setDevirAcik(false)} className="rounded-xl border border-zinc-300 px-3 py-2 text-sm text-zinc-700">
                {t('asistanSayfa.vazgec')}
              </button>
            </div>
          </form>
        ) : (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void gonder(girdi);
            }}
            className="flex items-end gap-2"
          >
            <label className="min-w-0 flex-1">
              <span className="sr-only">{t('asistanSayfa.yaz')}</span>
              <textarea
                ref={girdiRef}
                value={girdi}
                onChange={(e) => setGirdi(e.target.value)}
                onKeyDown={tus}
                rows={1}
                maxLength={yap.mesaj_siniri}
                placeholder={t('asistanSayfa.yaz')}
                className={`${GIRDI} max-h-28 min-h-[40px] resize-none`}
                data-testid="asistan-girdi"
              />
            </label>
            <button
              type="submit"
              disabled={gonderiliyor || !girdi.trim()}
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl disabled:opacity-50"
              style={{ background: renk, color: yazi }}
              aria-label={t('asistanSayfa.gonder')}
              data-testid="asistan-gonder"
            >
              {gonderiliyor ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Send className={`h-4 w-4 ${yon === 'rtl' ? '-scale-x-100' : ''}`} aria-hidden="true" />}
            </button>
          </form>
        )}
        {!devirAcik && (
          <p className="mt-1.5 text-[10.5px] leading-snug text-zinc-500" data-testid="asistan-aydinlatma">
            {aydinlatma}{' '}
            <a href={yap.aydinlatma.baglanti} target="_blank" rel="noopener noreferrer" className="underline">
              {t('asistanSayfa.gizlilik')}
            </a>
          </p>
        )}
      </div>
    </div>
  );
}

function Balon({ rol, renk, yazi, hata, children }: { rol: 'kullanici' | 'asistan'; renk: string; yazi: string; hata?: boolean; children: ReactNode }) {
  const kullanici = rol === 'kullanici';
  return (
    <div className={`flex ${kullanici ? 'justify-end' : 'justify-start'}`} data-rol={rol}>
      <div
        className={`max-w-[88%] rounded-2xl px-3.5 py-2.5 text-sm shadow-sm ${kullanici ? 'rounded-ee-md' : `rounded-es-md border ${hata ? 'border-amber-300 bg-amber-50' : 'border-zinc-200 bg-white'}`}`}
        style={kullanici ? { background: renk, color: yazi } : undefined}
      >
        {children}
      </div>
    </div>
  );
}
