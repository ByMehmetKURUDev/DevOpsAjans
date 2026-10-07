import { useEffect, useState, type FormEvent } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ExternalLink, Loader2, MessageSquareText, Send, Star } from 'lucide-react';

import {
  AcikHata,
  apiAdresi,
  cevirmen,
  isaretGonder,
  metinleriYukle,
  temaStili,
  yaziTipiYukle,
  yorumGeriBildirim,
  yorumGetir,
  type AcikYorum,
  type Cevirmen,
} from '@/lib/kartvizitAcik';
import '@/components/kartvizit/kartvizit.css';
import { rozetGorunur } from '@/components/marka/MarkaParcalari';
import { ZEMIN_RENKLERI, markaDegiskenleri, markaLogoAdresi, markaTemasi, markaYaziTipi } from '@/lib/marka';

/**
 * Faz 4K — herkese açık Google yorum sayfası: `/yorum/<slug>` (masa kartı / fiş QR'ı).
 *
 * GOOGLE POLİTİKASI: puan SORULMUYOR, ziyaretçi ayrıştırılmıyor ("review
 * gating" yok). Büyük "Google'da yorum yaz" düğmesi HER ziyaretçiye, her
 * koşulda aynı adresle görünüyor; "Bize özel geri bildirim gönder" yalnız ek
 * bir seçenek ve Google düğmesinin ALTINDA, onu gizlemeden duruyor.
 *
 * Noindex, prerender yok, site düzeni yok; metinler sayfanın kendi dilinde.
 *
 * Faz 4L — marka teması: sayfanın kendi rengi seçilmediyse markanın ana rengi; markanın
 * zemini, yazı tipi ve köşeleri; sayfada logo yoksa marka logosu; rozet yönetici gizlediyse yok.
 */

type Durum = 'yukleniyor' | 'aktif' | 'yok' | 'pasif' | 'hata';

export default function YorumSayfasi() {
  const { slug = '' } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const { i18n } = useTranslation();
  const [durum, setDurum] = useState<Durum>('yukleniyor');
  const [sayfa, setSayfa] = useState<AcikYorum | null>(null);
  const [m, setM] = useState<Cevirmen>(() => cevirmen(null));
  const [formAcik, setFormAcik] = useState(false);
  const dil = sayfa?.dil || i18n.language || 'tr';

  useEffect(() => {
    let iptal = false;
    yaziTipiYukle(dil);
    void metinleriYukle(dil).then((s) => {
      if (!iptal) setM(() => cevirmen(s));
    });
    return () => {
      iptal = true;
    };
  }, [dil]);

  useEffect(() => {
    let iptal = false;
    setDurum('yukleniyor');
    yorumGetir(slug)
      .then((y) => {
        if (iptal) return;
        if (y.durum === 'yonlendir') {
          navigate(`/yorum/${encodeURIComponent(y.yonlendir)}`, { replace: true });
          return;
        }
        setSayfa(y);
        setDurum('aktif');
        if (y.slug !== slug) {
          window.history.replaceState(window.history.state, '', `/yorum/${encodeURIComponent(y.slug)}${window.location.search}`);
        }
      })
      .catch((e: unknown) => {
        if (iptal) return;
        const d = e instanceof AcikHata ? e.durum : 0;
        setDurum(d === 404 ? 'yok' : d === 410 ? 'pasif' : 'hata');
      });
    return () => {
      iptal = true;
    };
  }, [slug, navigate]);

  useEffect(() => {
    const etiket = document.createElement('meta');
    etiket.name = 'robots';
    etiket.content = 'noindex, nofollow';
    document.head.appendChild(etiket);
    return () => etiket.remove();
  }, []);
  useEffect(() => {
    if (!sayfa) return;
    const onceki = document.title;
    document.title = sayfa.isletme_adi;
    return () => {
      document.title = onceki;
    };
  }, [sayfa]);

  const mt = markaTemasi(sayfa?.marka);
  const renk = mt && !sayfa?.marka?.sayfa_ozel ? mt.ana : sayfa?.renk || '#4285f4';
  const stil = {
    ...temaStili({ sablon: 'beyaz', renk, yazi_tipi: 'jakarta', kose: mt ? mt.kose : 'yumusak' }, dil),
    ...(mt ? { ...markaDegiskenleri(mt, dil, renk), background: ZEMIN_RENKLERI[mt.zemin].zemin, fontFamily: markaYaziTipi(mt, dil) } : {}),
  };
  const markaLogo = mt ? markaLogoAdresi(mt.logo) : null;
  const yon = dil === 'ar' ? 'rtl' : 'ltr';

  if (durum !== 'aktif' || !sayfa) {
    return (
      <main className="flex min-h-screen items-center justify-center px-4" style={stil} lang={dil} dir={yon} aria-busy={durum === 'yukleniyor'}>
        {durum === 'yukleniyor' ? (
          <Loader2 className="h-7 w-7 animate-spin opacity-60" aria-hidden="true" />
        ) : (
          <div className="kv-cerceve kv-durum-kart bg-white" data-testid={`yorum-durum-${durum}`}>
            <h1 className="text-lg font-semibold kv-baslik">{m(durum === 'pasif' ? 'yorum.pasifBaslik' : 'yorum.yokBaslik')}</h1>
            <p className="mt-2 text-sm kv-soluk">{m(durum === 'pasif' ? 'yorum.pasifAciklama' : 'yorum.yokAciklama')}</p>
          </div>
        )}
      </main>
    );
  }

  return (
    <main className="min-h-screen px-4 py-8" style={stil} lang={dil} dir={yon} data-testid="yorum-sayfasi">
      <div className="mx-auto w-full max-w-md space-y-4">
        <section className="kv-cerceve rounded-3xl bg-white p-6 text-center shadow-sm">
          {sayfa.logo ? (
            <img
              src={apiAdresi(sayfa.logo.url)}
              alt={m('logo', { ad: sayfa.isletme_adi })}
              width={sayfa.logo.genislik}
              height={sayfa.logo.yukseklik}
              className="kv-logo"
              decoding="async"
            />
          ) : markaLogo && mt ? (
            <img
              src={markaLogo}
              alt={m('logo', { ad: sayfa.isletme_adi })}
              width={mt.logo?.genislik ?? undefined}
              height={mt.logo?.yukseklik ?? undefined}
              className="kv-logo"
              decoding="async"
              data-testid="marka-logo"
            />
          ) : (
            <div
              className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl text-2xl font-bold"
              style={{ background: 'var(--kv-vurgu)', color: 'var(--kv-vurgu-metin)' }}
              aria-hidden="true"
            >
              {sayfa.isletme_adi.trim().charAt(0).toUpperCase()}
            </div>
          )}
          <h1 className="mt-4 break-words text-2xl font-bold kv-baslik" data-testid="yorum-isletme">
            {sayfa.isletme_adi}
          </h1>
          <p className="mt-2 whitespace-pre-line text-sm kv-soluk">{sayfa.tesekkur || m('yorum.varsayilanTesekkur')}</p>

          {/* Google düğmesi: her ziyaretçiye her koşulda aynı (review gating yok). */}
          <a
            href={sayfa.google_adresi}
            target="_blank"
            rel="noopener noreferrer"
            onClick={() => isaretGonder(`/api/v1/yorum/${encodeURIComponent(sayfa.slug)}/olay`, { tur: 'google' })}
            className="kv-google mt-6"
            data-testid="yorum-google"
          >
            <Star className="h-6 w-6" aria-hidden="true" />
            {m('yorum.googleYaz')}
            <ExternalLink className="h-4 w-4 opacity-80" aria-hidden="true" />
          </a>
          <p className="mt-3 text-xs kv-soluk">{m('yorum.googleAciklama')}</p>
        </section>

        {sayfa.geri_bildirim.acik && (
          <section className="kv-cerceve rounded-3xl bg-white p-5">
            {formAcik ? (
              <GeriBildirimFormu sayfa={sayfa} m={m} />
            ) : (
              <button
                type="button"
                onClick={() => setFormAcik(true)}
                className="kv-ozel-dugme kv-cerceve"
                data-testid="yorum-ozel-ac"
              >
                <MessageSquareText className="h-4 w-4" aria-hidden="true" />
                {m('yorum.ozelBaslik')}
              </button>
            )}
          </section>
        )}
        {rozetGorunur(sayfa.marka) && (
          <p className="kv-soluk text-center text-xs" style={mt ? { color: 'var(--marka-soluk)' } : undefined} data-testid="marka-rozet">
            <a href="https://mehmetkuru.dev/" target="_blank" rel="noopener" className="hover:underline">
              {m('yorum.altBilgi')}
            </a>
          </p>
        )}
      </div>
    </main>
  );
}

function GeriBildirimFormu({ sayfa, m }: { sayfa: AcikYorum; m: Cevirmen }) {
  const [v, setV] = useState({ ad: '', eposta: '', mesaj: '', web_sitesi: '' });
  const [durum, setDurum] = useState<'bos' | 'gonderiliyor' | 'tamam' | 'hata' | 'cok_hizli'>('bos');
  const alan = 'kv-girdi';

  const gonder = async (e: FormEvent) => {
    e.preventDefault();
    if (!v.mesaj.trim()) return;
    setDurum('gonderiliyor');
    try {
      await yorumGeriBildirim(sayfa.slug, { ...v, form_jetonu: sayfa.geri_bildirim.jeton });
      setDurum('tamam');
    } catch (h) {
      setDurum(h instanceof AcikHata && h.durum === 429 ? 'cok_hizli' : 'hata');
    }
  };
  if (durum === 'tamam') {
    return (
      <p className="py-2 text-center text-sm font-medium" role="status" data-testid="yorum-tesekkur">
        {m('yorum.tesekkur')}
      </p>
    );
  }
  return (
    <form onSubmit={gonder} className="space-y-2.5" aria-labelledby="yorum-form-baslik" data-testid="yorum-form" noValidate>
      <h2 id="yorum-form-baslik" className="text-base font-semibold kv-baslik">
        {m('yorum.ozelBaslik')}
      </h2>
      <p className="text-xs kv-soluk">{m('yorum.ozelAciklama')}</p>
      <label className="block">
        <span className="sr-only">{m('yorum.mesaj')}</span>
        <textarea className={alan} required maxLength={2000} placeholder={m('yorum.mesaj')} value={v.mesaj}
          onChange={(e) => setV({ ...v, mesaj: e.target.value })} name="mesaj" />
      </label>
      <div className="grid gap-2.5 sm:grid-cols-2">
        <label className="block">
          <span className="sr-only">{m('yorum.ad')}</span>
          <input className={alan} maxLength={120} autoComplete="name" placeholder={m('yorum.ad')} value={v.ad}
            onChange={(e) => setV({ ...v, ad: e.target.value })} name="ad" />
        </label>
        <label className="block">
          <span className="sr-only">{m('yorum.iletisim')}</span>
          <input className={alan} type="email" maxLength={254} autoComplete="email" placeholder={m('yorum.iletisim')} value={v.eposta}
            onChange={(e) => setV({ ...v, eposta: e.target.value })} name="eposta" dir="ltr" />
        </label>
      </div>
      <div aria-hidden="true" style={{ position: 'absolute', left: '-10000px', width: 1, height: 1, overflow: 'hidden' }}>
        <label>
          {m('form.tuzak')}
          <input tabIndex={-1} autoComplete="off" name="web_sitesi" value={v.web_sitesi} onChange={(e) => setV({ ...v, web_sitesi: e.target.value })} />
        </label>
      </div>
      {(durum === 'hata' || durum === 'cok_hizli') && (
        <p className="text-xs font-medium text-red-600" role="alert">
          {m(durum === 'cok_hizli' ? 'form.cokHizli' : 'form.hata')}
        </p>
      )}
      <button
        type="submit"
        disabled={durum === 'gonderiliyor' || !v.mesaj.trim()}
        className="kv-ozel-dugme kv-cerceve disabled:opacity-60"
        data-testid="yorum-form-gonder"
      >
        {durum === 'gonderiliyor' ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Send className="rtl-flip h-4 w-4" aria-hidden="true" />}
        {m('yorum.gonder')}
      </button>
      <p className="kv-soluk text-center text-xs leading-relaxed" data-aydinlatma>
        {m('form.aydinlatma')}{' '}
        <a href={sayfa.geri_bildirim.aydinlatma_adresi} target="_blank" rel="noopener" className="underline underline-offset-2">
          {m('form.gizlilik')}
        </a>
      </p>
    </form>
  );
}
