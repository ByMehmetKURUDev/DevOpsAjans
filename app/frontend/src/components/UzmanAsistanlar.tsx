import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowLeft, Bot, Loader2, MessageSquarePlus, RotateCcw, Send, Sparkles, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import BaglantiliMetin from '@/components/mesajlar/BaglantiliMetin';
import GuvenliMarkdown from '@/components/asistanlar/GuvenliMarkdown';
import {
  AsistanUcHatasi,
  MESAJ_SINIRI,
  hataMetni,
  asistanlariGetir,
  mesajGonder,
  sohbetAc,
  sohbetGetir,
  sohbetSil,
  sohbetleriGetir,
  type Asistan,
  type AsistanListesi,
  type AsistanMesaji,
  type Kullanim,
  type Sohbet,
} from '@/lib/uzmanAsistanlar';

/**
 * Faz 3U — müşteri paneli › Uzman Asistanlar.
 *
 * Kategori başlıklı kart ızgarası → karta tıklayınca sohbet görünümü: üstte
 * asistanın adı ve kısa açıklaması + "Yeni sohbet", solda (masaüstünde)
 * önceki sohbetler, boş sohbette örnek soru çipleri, mesaj akışı, gönderme
 * (Enter / Shift+Enter). Yanıt akış (stream) değil: istek sürerken bekleme
 * göstergesi. Sohbet ilk mesajda açılıyor (boş sohbet birikmesin).
 *
 * Asistan yanıtı GuvenliMarkdown ile çiziliyor — HTML asla.
 */

/** Model hatasında "Tekrar dene" gösterilen kodlar (kullanıcı mesajı kaydedildi). */
const YENIDEN_DENENEBILIR = new Set(['ai_hatasi', 'ai_kapali', 'ai_zaman_asimi', 'ai_bos', 'genel']);

function genisEkran(): boolean {
  try {
    return window.matchMedia('(min-width: 768px)').matches;
  } catch {
    return true;
  }
}

export default function UzmanAsistanlar() {
  const { t, i18n } = useTranslation();
  const dil = (i18n.language || 'tr').slice(0, 2);
  const [veri, setVeri] = useState<AsistanListesi | null>(null);
  const [yuklemeHatasi, setYuklemeHatasi] = useState<string | null>(null);
  const [secili, setSecili] = useState<Asistan | null>(null);

  useEffect(() => {
    let iptal = false;
    setYuklemeHatasi(null);
    asistanlariGetir(dil)
      .then((v) => {
        if (iptal) return;
        setVeri(v);
        // Dil değişince seçili asistanın metni de yeni dilde olsun.
        setSecili((s) => (s ? v.asistanlar.find((a) => a.anahtar === s.anahtar) ?? null : null));
      })
      .catch((e) => !iptal && setYuklemeHatasi(hataMetni(t, e)));
    return () => {
      iptal = true;
    };
  }, [dil, t]);

  const kullanimGuncelle = useCallback((k: Kullanim) => setVeri((v) => (v ? { ...v, kullanim: k } : v)), []);

  if (!veri) {
    return (
      <div className="py-16 text-center text-sm text-muted-foreground" data-uzman-asistanlar>
        {yuklemeHatasi ?? <Loader2 className="mx-auto h-5 w-5 animate-spin" aria-hidden="true" />}
      </div>
    );
  }

  return (
    <div className="space-y-4" data-uzman-asistanlar>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h3 className="flex items-center gap-2 text-lg font-semibold">
            <Bot className="h-5 w-5 text-purple-400" aria-hidden="true" /> {t('uzmanAsistanlar.baslik')}
          </h3>
          <p className="mt-1 text-sm text-muted-foreground">{t('uzmanAsistanlar.aciklama')}</p>
        </div>
        <KullanimRozeti kullanim={veri.kullanim} kredi={veri.kredi} />
      </div>

      {secili ? (
        <SohbetGorunumu
          key={secili.anahtar}
          asistan={secili}
          kullanim={veri.kullanim}
          onKullanim={kullanimGuncelle}
          onGeri={() => setSecili(null)}
        />
      ) : (
        <AsistanIzgarasi veri={veri} onSec={setSecili} />
      )}

      <p className="text-[11px] text-muted-foreground" data-atif>
        {t('uzmanAsistanlar.atif', { ad: veri.kaynak.ad || 'agency-agents', lisans: veri.kaynak.lisans || 'MIT' })}{' '}
        <a
          href="/lisanslar.txt"
          target="_blank"
          rel="noopener noreferrer"
          className="underline decoration-dotted underline-offset-2 hover:text-foreground"
          data-lisans-baglantisi
        >
          {t('uzmanAsistanlar.lisans')}
        </a>
      </p>
    </div>
  );
}

function KullanimRozeti({ kullanim, kredi }: { kullanim: Kullanim; kredi: AsistanListesi['kredi'] }) {
  const { t } = useTranslation();
  const bitti = kullanim.kalan <= 0;
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <span
        className={`rounded-full border px-3 py-1 ${bitti ? 'border-amber-500/40 bg-amber-500/10 text-amber-200' : 'border-white/10 bg-white/[0.04] text-muted-foreground'}`}
        data-kalan={kullanim.kalan}
      >
        {t('uzmanAsistanlar.kalanHak', { kalan: kullanim.kalan, sinir: kullanim.sinir })}
      </span>
      {kredi.mesaj_basi > 0 && (
        <span className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-muted-foreground" data-mesaj-kredi>
          {t('uzmanAsistanlar.mesajKredisi', { kredi: kredi.mesaj_basi })}
          {kredi.bakiye !== null && ` · ${t('uzmanAsistanlar.bakiye', { bakiye: kredi.bakiye })}`}
        </span>
      )}
    </div>
  );
}

function AsistanIzgarasi({ veri, onSec }: { veri: AsistanListesi; onSec: (a: Asistan) => void }) {
  const { t } = useTranslation();
  const gruplar = useMemo(
    () =>
      veri.kategoriler
        .map((k) => ({ ...k, asistanlar: veri.asistanlar.filter((a) => a.kategori === k.anahtar) }))
        .filter((g) => g.asistanlar.length > 0),
    [veri]
  );
  // Tohumda olmayan bir kategoriye taşınmış asistan da görünsün.
  const bilinen = new Set(veri.kategoriler.map((k) => k.anahtar));
  const digerleri = veri.asistanlar.filter((a) => !bilinen.has(a.kategori));

  if (!veri.asistanlar.length) {
    return <p className="py-12 text-center text-sm text-muted-foreground">{t('uzmanAsistanlar.asistanYok')}</p>;
  }
  return (
    <div className="space-y-6">
      {[...gruplar, ...(digerleri.length ? [{ anahtar: '_diger', ad: t('uzmanAsistanlar.diger'), asistanlar: digerleri }] : [])].map(
        (g) => (
          <section key={g.anahtar} data-kategori={g.anahtar}>
            <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{g.ad}</h4>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {g.asistanlar.map((a) => (
                <button
                  key={a.anahtar}
                  type="button"
                  onClick={() => onSec(a)}
                  className="cam-kart group flex flex-col items-start gap-2 rounded-2xl border border-white/10 bg-white/[0.03] p-4 text-start transition-colors hover:border-purple-400/40 hover:bg-white/[0.05]"
                  data-asistan-kart={a.anahtar}
                >
                  <span className="flex items-center gap-2 font-semibold">
                    <span className="flex h-8 w-8 flex-none items-center justify-center rounded-xl bg-purple-500/15">
                      <Sparkles className="h-4 w-4 text-purple-300" aria-hidden="true" />
                    </span>
                    {a.ad}
                  </span>
                  <span className="text-sm leading-relaxed text-muted-foreground">{a.aciklama}</span>
                  <span className="mt-auto pt-1 text-xs font-medium text-purple-300 group-hover:underline">
                    {t('uzmanAsistanlar.sohbetBaslat')}
                  </span>
                </button>
              ))}
            </div>
          </section>
        )
      )}
    </div>
  );
}

interface Bekleyen {
  metin: string;
  /** Sunucuda kaydedilmiş kullanıcı mesajı (model hatası → "Tekrar dene"). */
  kayitli: boolean;
}

function SohbetGorunumu({
  asistan,
  kullanim,
  onKullanim,
  onGeri,
}: {
  asistan: Asistan;
  kullanim: Kullanim;
  onKullanim: (k: Kullanim) => void;
  onGeri: () => void;
}) {
  const { t, i18n } = useTranslation();
  const [sohbetler, setSohbetler] = useState<Sohbet[] | null>(null);
  const [aktif, setAktif] = useState<number | null>(null);
  const [mesajlar, setMesajlar] = useState<AsistanMesaji[]>([]);
  const [yukleniyor, setYukleniyor] = useState(false);
  const [girdi, setGirdi] = useState('');
  const [bekliyor, setBekliyor] = useState(false);
  const [hata, setHata] = useState<{ kod: string; metin: string; yeniden: boolean } | null>(null);
  const [bekleyen, setBekleyen] = useState<Bekleyen | null>(null);
  const listeSonu = useRef<HTMLDivElement | null>(null);
  const kutu = useRef<HTMLTextAreaElement | null>(null);

  const sohbetleriYukle = useCallback(async () => {
    const l = await sohbetleriGetir(asistan.anahtar);
    setSohbetler(l);
    return l;
  }, [asistan.anahtar]);

  useEffect(() => {
    sohbetleriYukle().catch(() => setSohbetler([]));
    if (genisEkran()) kutu.current?.focus();
  }, [sohbetleriYukle]);

  useEffect(() => {
    listeSonu.current?.scrollIntoView({ block: 'end' });
  }, [mesajlar, bekliyor, hata]);

  const sohbetiAc = async (id: number) => {
    setAktif(id);
    setHata(null);
    setBekleyen(null);
    setYukleniyor(true);
    try {
      const d = await sohbetGetir(id);
      setMesajlar(d.mesajlar);
      // Son mesaj yanıtsız kullanıcı mesajıysa: tekrar denenebilir.
      const son = d.mesajlar[d.mesajlar.length - 1];
      if (son && son.rol === 'user') {
        setHata({ kod: 'yanitsiz', metin: t('uzmanAsistanlar.hata.yanitsiz'), yeniden: true });
      }
    } catch (e) {
      toast.error(hataMetni(t, e));
      setAktif(null);
      setMesajlar([]);
    } finally {
      setYukleniyor(false);
    }
  };

  const yeniSohbet = () => {
    setAktif(null);
    setMesajlar([]);
    setHata(null);
    setBekleyen(null);
    setGirdi('');
    kutu.current?.focus();
  };

  const sil = async (s: Sohbet) => {
    if (!window.confirm(t('uzmanAsistanlar.silOnay'))) return;
    try {
      await sohbetSil(s.id);
      if (aktif === s.id) yeniSohbet();
      await sohbetleriYukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const gonder = async (metin: string, yeniden = false) => {
    const soru = metin.trim();
    if (bekliyor || (!soru && !yeniden)) return;
    setHata(null);
    setBekliyor(true);
    if (!yeniden) {
      setBekleyen({ metin: soru, kayitli: false });
      setGirdi('');
    }
    let sohbetId = aktif;
    try {
      if (sohbetId === null) {
        const s = await sohbetAc(asistan.anahtar);
        sohbetId = s.id;
        setAktif(s.id);
      }
      const y = await mesajGonder(sohbetId, soru, yeniden);
      setMesajlar((m) => {
        const temiz = m.filter((x) => x.id !== y.kullanici_mesaji.id);
        return [...temiz, y.kullanici_mesaji, y.asistan_mesaji];
      });
      setBekleyen(null);
      onKullanim(y.kullanim);
      void sohbetleriYukle().catch(() => {});
    } catch (e) {
      const kod = e instanceof AsistanUcHatasi ? e.kod : 'genel';
      const kayitli = e instanceof AsistanUcHatasi && typeof e.ek.mesaj_id === 'number';
      if (kayitli) {
        // Kullanıcı mesajı sunucuda kaldı: akışa ekle, "Tekrar dene" yeni mesaj yazmaz.
        const id = e.ek.mesaj_id as number;
        const icerik = yeniden ? '' : soru;
        setMesajlar((m) =>
          m.some((x) => x.id === id) ? m : [...m, { id, sohbet_id: sohbetId ?? 0, rol: 'user', icerik, created_at: null }]
        );
        setBekleyen(null);
        void sohbetleriYukle().catch(() => {});
      } else if (!yeniden) {
        // Mesaj hiç kaydedilmedi (sınır, kredi…): metin kutuya geri dönsün.
        setBekleyen(null);
        setGirdi(soru);
      }
      if (kod === 'gunluk_sinir' && e instanceof AsistanUcHatasi && typeof e.ek.kalan === 'number') {
        onKullanim({ bugun: Number(e.ek.bugun) || kullanim.sinir, sinir: Number(e.ek.sinir) || kullanim.sinir, kalan: 0 });
      }
      setHata({ kod, metin: hataMetni(t, e), yeniden: kayitli || (yeniden && YENIDEN_DENENEBILIR.has(kod)) });
    } finally {
      setBekliyor(false);
    }
  };

  const tuslar = (o: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (o.key === 'Enter' && !o.shiftKey && !o.nativeEvent.isComposing) {
      o.preventDefault();
      void gonder(girdi);
    }
  };

  const tarih = (iso?: string | null) => {
    if (!iso) return '';
    const d = new Date(iso);
    return Number.isNaN(d.getTime())
      ? ''
      : d.toLocaleDateString(i18n.language, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
  };

  const hakYok = kullanim.kalan <= 0;
  const bos = aktif === null && mesajlar.length === 0 && !bekleyen;

  const liste = (
    <div className="min-h-0 flex-1 overflow-y-auto p-2" data-sohbet-listesi>
      {sohbetler === null ? (
        <p className="flex justify-center py-6 text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
        </p>
      ) : sohbetler.length === 0 ? (
        <p className="px-2 py-6 text-center text-xs text-muted-foreground">{t('uzmanAsistanlar.sohbetYok')}</p>
      ) : (
        <ul className="space-y-1">
          {sohbetler.map((s) => (
            <li key={s.id} className="group flex items-center gap-1">
              <button
                type="button"
                onClick={() => void sohbetiAc(s.id)}
                className={`min-w-0 flex-1 rounded-lg px-2.5 py-2 text-start text-sm transition-colors ${
                  aktif === s.id ? 'bg-purple-500/15 text-foreground' : 'text-muted-foreground hover:bg-white/5 hover:text-foreground'
                }`}
                data-sohbet-oge={s.id}
                aria-current={aktif === s.id ? 'true' : undefined}
              >
                <span className="block truncate" dir="auto">
                  {s.baslik || t('uzmanAsistanlar.adsizSohbet')}
                </span>
                <span className="block text-[10px] text-muted-foreground">{tarih(s.updated_at)}</span>
              </button>
              <button
                type="button"
                onClick={() => void sil(s)}
                className="rounded-md p-1.5 text-muted-foreground opacity-70 hover:bg-white/5 hover:text-red-300 group-hover:opacity-100"
                aria-label={t('uzmanAsistanlar.sohbetiSil')}
                data-sohbet-sil={s.id}
              >
                <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );

  return (
    <div className="cam-kart overflow-hidden rounded-2xl border border-white/10 bg-white/[0.03]" data-asistan-sohbeti={asistan.anahtar}>
      <div className="flex flex-wrap items-start gap-3 border-b border-white/10 px-4 py-3">
        <button
          type="button"
          onClick={onGeri}
          className="inline-flex h-9 w-9 flex-none items-center justify-center rounded-lg hover:bg-white/10"
          aria-label={t('uzmanAsistanlar.tumAsistanlar')}
          data-testid="asistan-geri"
        >
          <ArrowLeft className="h-4 w-4 rtl:rotate-180" aria-hidden="true" />
        </button>
        <div className="min-w-0 flex-1">
          <p className="font-semibold" data-asistan-adi>
            {asistan.ad}
          </p>
          <p className="text-xs leading-relaxed text-muted-foreground">{asistan.aciklama}</p>
        </div>
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="h-9 !bg-transparent border-white/20 text-xs"
          onClick={yeniSohbet}
          data-testid="yeni-sohbet"
        >
          <MessageSquarePlus className="me-1 h-3.5 w-3.5" aria-hidden="true" /> {t('uzmanAsistanlar.yeniSohbet')}
        </Button>
      </div>

      <div className="grid md:h-[68vh] md:min-h-[460px] md:grid-cols-[240px_minmax(0,1fr)]">
        {/* Önceki sohbetler: masaüstünde solda, mobilde açılır bölüm. */}
        <aside className="hidden min-h-0 flex-col border-white/10 md:flex md:border-e">
          <p className="border-b border-white/10 px-3 py-2.5 text-xs font-semibold text-muted-foreground">
            {t('uzmanAsistanlar.oncekiSohbetler')}
          </p>
          {liste}
        </aside>
        <details className="border-b border-white/10 md:hidden" data-mobil-sohbetler>
          <summary className="cursor-pointer px-4 py-2.5 text-xs font-semibold text-muted-foreground">
            {t('uzmanAsistanlar.oncekiSohbetler')} ({sohbetler?.length ?? 0})
          </summary>
          <div className="max-h-60 overflow-y-auto">{liste}</div>
        </details>

        <section className="flex min-h-[60vh] flex-col md:min-h-0">
          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-4" aria-live="polite" data-asistan-akisi>
            {yukleniyor && (
              <p className="flex justify-center py-6 text-muted-foreground">
                <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
              </p>
            )}
            {bos && !yukleniyor && (
              <div className="py-4">
                <p className="text-sm text-muted-foreground">{t('uzmanAsistanlar.karsilama', { ad: asistan.ad })}</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {asistan.ornek_sorular.map((o) => (
                    <button
                      key={o}
                      type="button"
                      disabled={bekliyor || hakYok}
                      onClick={() => void gonder(o)}
                      className="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1.5 text-start text-sm text-muted-foreground transition-colors hover:border-purple-400/40 hover:text-foreground disabled:opacity-50"
                      data-ornek-soru
                    >
                      {o}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {mesajlar.map((m) =>
              m.rol === 'user' ? (
                <div key={m.id} className="flex justify-end" data-asistan-mesaj="user">
                  <p className="max-w-[88%] whitespace-pre-wrap break-words rounded-2xl rounded-ee-md bg-gradient-to-br from-purple-600/85 to-pink-600/75 px-3.5 py-2 text-sm text-white sm:max-w-[75%]" dir="auto">
                    <BaglantiliMetin metin={m.icerik} />
                  </p>
                </div>
              ) : (
                <div key={m.id} className="flex justify-start" data-asistan-mesaj="assistant">
                  <div className="max-w-[92%] rounded-2xl rounded-es-md border border-white/10 bg-white/[0.06] px-3.5 py-2.5 text-sm sm:max-w-[80%]">
                    <GuvenliMarkdown metin={m.icerik} />
                  </div>
                </div>
              )
            )}

            {bekleyen && (
              <div className="flex justify-end opacity-80" data-asistan-mesaj="bekleyen">
                <p className="max-w-[88%] whitespace-pre-wrap break-words rounded-2xl rounded-ee-md bg-gradient-to-br from-purple-600/60 to-pink-600/50 px-3.5 py-2 text-sm text-white sm:max-w-[75%]" dir="auto">
                  {bekleyen.metin}
                </p>
              </div>
            )}

            {bekliyor && (
              <p className="flex items-center gap-2 text-sm text-muted-foreground" data-asistan-bekliyor>
                <Loader2 className="h-4 w-4 animate-spin text-purple-300" aria-hidden="true" />
                {t('uzmanAsistanlar.yaziyor')}
              </p>
            )}

            {hata && !bekliyor && (
              <div
                className="flex flex-wrap items-center gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 px-3.5 py-2.5 text-sm text-amber-200"
                data-asistan-hata={hata.kod}
                role="alert"
              >
                <span className="flex-1">{hata.metin}</span>
                {hata.yeniden && (
                  <button
                    type="button"
                    onClick={() => void gonder('', true)}
                    className="inline-flex items-center gap-1 rounded-lg border border-amber-400/40 px-2 py-1 text-xs hover:bg-amber-500/10"
                    data-testid="tekrar-dene"
                  >
                    <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" /> {t('uzmanAsistanlar.tekrarDene')}
                  </button>
                )}
              </div>
            )}
            <div ref={listeSonu} />
          </div>

          <div className="border-t border-white/10 p-3">
            {hakYok && (
              <p className="mb-2 text-xs text-amber-200" data-hak-bitti>
                {t('uzmanAsistanlar.hata.gunluk_sinir')}
              </p>
            )}
            <div className="flex items-end gap-2">
              <textarea
                ref={kutu}
                rows={2}
                value={girdi}
                maxLength={MESAJ_SINIRI}
                onChange={(e) => setGirdi(e.target.value)}
                onKeyDown={tuslar}
                disabled={hakYok}
                placeholder={t('uzmanAsistanlar.yerTutucu')}
                aria-label={t('uzmanAsistanlar.yerTutucu')}
                dir="auto"
                className="max-h-40 min-h-[44px] flex-1 resize-y rounded-xl border border-white/12 bg-white/[0.03] px-3 py-2.5 text-sm outline-none transition-colors placeholder:text-muted-foreground/60 focus:border-purple-400/50 disabled:opacity-50"
                data-testid="asistan-girdi"
              />
              <button
                type="button"
                onClick={() => void gonder(girdi)}
                disabled={!girdi.trim() || bekliyor || hakYok}
                aria-label={t('uzmanAsistanlar.gonder')}
                className="grid h-11 w-11 flex-none place-items-center rounded-xl bg-gradient-to-r from-purple-600 to-pink-600 text-white transition-opacity disabled:opacity-40"
                data-testid="asistan-gonder"
              >
                {bekliyor ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Send className="h-4 w-4 rtl:-scale-x-100" aria-hidden="true" />}
              </button>
            </div>
            <p className="mt-2 text-[10px] leading-relaxed text-muted-foreground/80">
              {t('uzmanAsistanlar.uyari')}
              {girdi.length > MESAJ_SINIRI - 500 && ` · ${girdi.length}/${MESAJ_SINIRI}`}
            </p>
          </div>
        </section>
      </div>
    </div>
  );
}
