import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowLeft, BarChart3, BookOpen, Bot, Code2, ExternalLink, MessageSquareText, MessagesSquare, Plus, Settings2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { KART, Rozet, Yukleniyor, sayiYaz } from '@/components/aiAsistan/ortak';
import { asistanApi, hataMetni, type Asistan, type AsistanMod, type Meta } from '@/lib/aiAsistan';

const Kaynaklar = lazy(() => import('@/components/aiAsistan/Kaynaklar'));
const Onizleme = lazy(() => import('@/components/aiAsistan/Onizleme'));
const Ayarlar = lazy(() => import('@/components/aiAsistan/Ayarlar'));
const Gomme = lazy(() => import('@/components/aiAsistan/Gomme'));
const Sohbetler = lazy(() => import('@/components/aiAsistan/Sohbetler'));
const Kullanim = lazy(() => import('@/components/aiAsistan/Kullanim'));
const GenelAyarlar = lazy(() => import('@/components/aiAsistan/GenelAyarlar'));

/**
 * Faz 5A — "AI asistan" sekmesi. Yönetici panelinde (`mod="yonetici"`: ajansın kendi
 * asistanı + müşterilerinkiler, müşteri adına kurulum, genel ayarlar) ve müşteri panelinde
 * (`mod="musteri"`: etkin hesabın tek asistanı) aynı bileşen.
 *
 * Asistan → alt sekmeler: bilgi bankası (kaynaklar), dene (canlı önizleme), ayarlar,
 * gömme kodu + izinli alan adları, sohbetler, kullanım/maliyet.
 */

type AltSekme = 'kaynaklar' | 'onizleme' | 'ayarlar' | 'gomme' | 'sohbetler' | 'kullanim';
const ALT_SEKMELER: { anahtar: AltSekme; ikon: typeof Bot }[] = [
  { anahtar: 'kaynaklar', ikon: BookOpen },
  { anahtar: 'onizleme', ikon: MessageSquareText },
  { anahtar: 'ayarlar', ikon: Settings2 },
  { anahtar: 'gomme', ikon: Code2 },
  { anahtar: 'sohbetler', ikon: MessagesSquare },
  { anahtar: 'kullanim', ikon: BarChart3 },
];

export default function AiAsistan({ mod }: { mod: AsistanMod }) {
  const { t, i18n } = useTranslation();
  const api = useMemo(() => asistanApi(mod), [mod]);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [liste, setListe] = useState<Asistan[] | null>(null);
  const [seciliId, setSeciliId] = useState<number | null>(null);
  const [secili, setSecili] = useState<Asistan | null>(null);
  const [alt, setAlt] = useState<AltSekme>('kaynaklar');
  const [yeniAd, setYeniAd] = useState('');
  const [yeniHesap, setYeniHesap] = useState('');
  const [olusturuluyor, setOlusturuluyor] = useState(false);
  const [suzgec, setSuzgec] = useState('');
  const [hata, setHata] = useState<string | null>(null);

  const yukle = useCallback(async () => {
    setHata(null);
    try {
      const [m, l] = await Promise.all([api.meta(), api.liste(mod === 'yonetici' && suzgec.trim() ? suzgec.trim() : undefined)]);
      setMeta(m);
      setListe(l.items);
      if (mod === 'musteri' && l.items.length === 1) setSeciliId(l.items[0].id);
    } catch (e) {
      setHata(hataMetni(t, e));
      setListe([]);
    }
  }, [api, mod, suzgec, t]);

  useEffect(() => {
    if (seciliId === null) void yukle();
  }, [yukle, seciliId]);

  useEffect(() => {
    if (seciliId === null) {
      setSecili(null);
      return;
    }
    let iptal = false;
    api
      .getir(seciliId)
      .then((a) => {
        if (!iptal) setSecili(a);
      })
      .catch((e) => {
        if (iptal) return;
        toast.error(hataMetni(t, e));
        setSeciliId(null);
      });
    return () => {
      iptal = true;
    };
  }, [api, seciliId, t]);

  const olustur = async () => {
    if (!yeniAd.trim()) {
      toast.error(t('aiAsistan.hata.zorunlu'));
      return;
    }
    setOlusturuluyor(true);
    try {
      const a = await api.olustur({ ad: yeniAd.trim(), ...(mod === 'yonetici' && yeniHesap.trim() ? { hesap_email: yeniHesap.trim() } : {}) });
      setYeniAd('');
      setYeniHesap('');
      toast.success(t('aiAsistan.liste.olusturuldu'));
      setAlt('kaynaklar');
      setSeciliId(a.id);
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setOlusturuluyor(false);
    }
  };

  const ust = (
    <div className="mb-6">
      <h2 className="flex items-center gap-2 text-2xl font-bold" id="ai-asistan-baslik">
        <Bot className="h-6 w-6 text-purple-300" aria-hidden="true" />
        {t('aiAsistan.baslik')}
      </h2>
      <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{t(mod === 'yonetici' ? 'aiAsistan.aciklamaYonetici' : 'aiAsistan.aciklama')}</p>
    </div>
  );

  if (seciliId !== null) {
    if (!secili || !meta) {
      return (
        <section data-testid="ai-asistan-sekmesi" aria-labelledby="ai-asistan-baslik">
          {ust}
          <Yukleniyor />
        </section>
      );
    }
    const geriVar = mod === 'yonetici' || (liste?.length ?? 0) !== 1;
    return (
      <section data-testid="ai-asistan-sekmesi" aria-labelledby="ai-asistan-baslik">
        {ust}
        <div className="mb-4 flex flex-wrap items-center gap-2" data-testid="ai-asistan-duzenleyici" data-asistan-id={secili.id} data-anahtar={secili.anahtar}>
          {geriVar && (
            <Button type="button" variant="ghost" size="sm" className="gap-1" onClick={() => setSeciliId(null)} data-testid="ai-asistan-geri">
              <ArrowLeft className={`h-4 w-4 ${i18n.dir() === 'rtl' ? 'rotate-180' : ''}`} aria-hidden="true" />
              {t('aiAsistan.geri')}
            </Button>
          )}
          <h3 className="min-w-0 truncate text-lg font-semibold">{secili.ad}</h3>
          <Rozet renk={secili.aktif ? 'border-emerald-400/30 bg-emerald-500/10 text-emerald-200' : 'border-amber-400/30 bg-amber-500/10 text-amber-200'}>
            {t(secili.aktif ? 'aiAsistan.aktif' : 'aiAsistan.pasif')}
          </Rozet>
          {mod === 'yonetici' && <Rozet>{secili.hesap_email || t('aiAsistan.liste.ajans')}</Rozet>}
          <a href={secili.adres} target="_blank" rel="noopener noreferrer" className="ms-auto inline-flex items-center gap-1 text-xs text-purple-200 hover:underline" dir="ltr">
            <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
            /asistan/{secili.anahtar}
          </a>
        </div>
        <div className="mb-5 flex gap-1 overflow-x-auto border-b border-white/10 pb-px" role="tablist">
          {ALT_SEKMELER.map(({ anahtar, ikon: Ikon }) => (
            <button
              key={anahtar}
              type="button"
              role="tab"
              aria-selected={alt === anahtar}
              onClick={() => setAlt(anahtar)}
              data-asistan-alt={anahtar}
              className={`flex shrink-0 items-center gap-1.5 border-b-2 px-3 py-2 text-sm transition-colors ${
                alt === anahtar ? 'border-purple-400 text-white' : 'border-transparent text-muted-foreground hover:text-white'
              }`}
            >
              <Ikon className="h-4 w-4" aria-hidden="true" />
              {t(`aiAsistan.alt.${anahtar}`)}
            </button>
          ))}
        </div>
        <Suspense fallback={<Yukleniyor />}>
          {alt === 'kaynaklar' && <Kaynaklar api={api} asistan={secili} meta={meta} />}
          {alt === 'onizleme' && <Onizleme api={api} asistan={secili} />}
          {alt === 'ayarlar' && <Ayarlar api={api} asistan={secili} meta={meta} onDegisti={setSecili} onSilindi={() => setSeciliId(null)} />}
          {alt === 'gomme' && <Gomme api={api} asistan={secili} meta={meta} onDegisti={setSecili} />}
          {alt === 'sohbetler' && <Sohbetler api={api} asistan={secili} mod={mod} />}
          {alt === 'kullanim' && <Kullanim api={api} asistan={secili} />}
        </Suspense>
      </section>
    );
  }

  return (
    <section data-testid="ai-asistan-sekmesi" aria-labelledby="ai-asistan-baslik">
      {ust}
      {hata && <p className="mb-4 rounded-xl border border-red-400/30 bg-red-500/10 p-3 text-sm text-red-200">{hata}</p>}
      {liste === null ? (
        <Yukleniyor />
      ) : (
        <div className="space-y-6">
          {mod === 'yonetici' && (
            <Suspense fallback={null}>
              <GenelAyarlar api={api} />
            </Suspense>
          )}
          {(mod === 'yonetici' || liste.length === 0) && (
            <div className={`${KART} p-5`}>
              <h3 className="mb-1 font-semibold">{t('aiAsistan.liste.yeniBaslik')}</h3>
              <p className="mb-3 text-xs text-muted-foreground">{t('aiAsistan.liste.yeniAciklama')}</p>
              <div className="flex flex-col gap-2 sm:flex-row">
                <Input value={yeniAd} onChange={(e) => setYeniAd(e.target.value)} placeholder={t('aiAsistan.liste.adOrnek')} maxLength={80} data-testid="ai-asistan-yeni-ad" />
                {mod === 'yonetici' && (
                  <Input value={yeniHesap} onChange={(e) => setYeniHesap(e.target.value)} placeholder={t('aiAsistan.liste.hesapOrnek')} type="email" dir="ltr" data-testid="ai-asistan-yeni-hesap" />
                )}
                <Button type="button" onClick={() => void olustur()} disabled={olusturuluyor} className="gap-1.5" data-testid="ai-asistan-olustur">
                  <Plus className="h-4 w-4" aria-hidden="true" />
                  {t('aiAsistan.liste.olustur')}
                </Button>
              </div>
            </div>
          )}
          {mod === 'yonetici' && (
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <Input value={suzgec} onChange={(e) => setSuzgec(e.target.value)} placeholder={t('aiAsistan.liste.suzgec')} className="sm:max-w-xs" dir="ltr" />
              <Button type="button" variant="outline" size="sm" className="!bg-transparent" onClick={() => void yukle()}>
                {t('aiAsistan.liste.ara')}
              </Button>
            </div>
          )}
          {liste.length === 0 ? (
            mod === 'yonetici' && <p className="text-sm text-muted-foreground">{t('aiAsistan.liste.bos')}</p>
          ) : (
            <ul className="grid gap-3 md:grid-cols-2" data-testid="ai-asistan-listesi">
              {liste.map((a) => (
                <li key={a.id} className={`${KART} flex flex-col gap-3 p-4`} data-asistan-id={a.id}>
                  <div className="flex items-start gap-3">
                    <span className="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-full" style={{ background: a.renk }}>
                      {a.avatar ? <img src={a.avatar} alt="" className="h-full w-full object-cover" /> : <Bot className="h-5 w-5 text-white" aria-hidden="true" />}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-semibold">{a.ad}</p>
                      <p className="truncate text-xs text-muted-foreground" dir="ltr">
                        {a.hesap_email || t('aiAsistan.liste.ajans')}
                      </p>
                    </div>
                    <Rozet renk={a.aktif ? 'border-emerald-400/30 bg-emerald-500/10 text-emerald-200' : undefined}>{t(a.aktif ? 'aiAsistan.aktif' : 'aiAsistan.pasif')}</Rozet>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {t('aiAsistan.liste.ozet', {
                      kaynak: sayiYaz(a.kaynak_sayisi ?? 0, i18n.language),
                      parca: sayiYaz(a.parca_sayisi ?? 0, i18n.language),
                      sohbet: sayiYaz(a.sohbet_sayisi ?? 0, i18n.language),
                    })}
                  </p>
                  <Button type="button" size="sm" className="self-start" onClick={() => setSeciliId(a.id)} data-testid="ai-asistan-ac">
                    {t('aiAsistan.liste.ac')}
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
