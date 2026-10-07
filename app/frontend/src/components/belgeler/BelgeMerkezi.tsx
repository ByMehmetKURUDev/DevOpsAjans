import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { BookText, FilePlus2, LayoutGrid, ListChecks, Pin, RefreshCw, Search, Share2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { client } from '@/lib/sdkClient';
import { modulMusterileriGetir } from '@/lib/moduller';
import {
  belgeApi,
  hataMetni,
  tarihYaz,
  type Belge,
  type BelgeAyrintisi,
  type BelgeMod,
  type Kategori,
  type Liste,
  type Meta,
} from '@/lib/belgeler';

import BelgeDuzenle, { type MusteriSecenegi, type ProjeSecenegi } from './BelgeDuzenle';
import BelgeGoruntule from './BelgeGoruntule';
import { BelgeStilleri, KART, Rozet, SECIM, Yukleniyor } from './ortak';
import Yapilacaklarim from './Yapilacaklarim';

/**
 * Faz 5B — Belgeler / Strateji alt bölümü (yönetici ve müşteri paneli aynı bileşen).
 *
 * Solda liste (arama: başlık + içerik, etiket süzgeci; yöneticide alan ve kaynak süzgeci),
 * sağda seçili belgenin okuma görünümü ya da düzenleyici. Telefonda liste ve ayrıntı sırayla.
 * Belgeler kategorisinde "Yapılacaklarım" görünümü; strateji kategorisinde yeni çalışma için
 * şablon seçici (SWOT, İş Modeli Kanvası, Lean Canvas, PESTLE, Porter, McKinsey 7S, Mavi
 * Okyanus, Ikigai).
 */

type Gorunum = { tur: 'bos' } | { tur: 'oku'; id: number } | { tur: 'yeni'; belgeTuru: string } | { tur: 'duzenle'; id: number } | { tur: 'sablon' } | { tur: 'yapilacak' };

interface Ozellikler {
  mod: BelgeMod;
  kategori: Kategori;
  baslangicBelge?: number | null;
}

export default function BelgeMerkezi({ mod, kategori, baslangicBelge }: Ozellikler) {
  const { t, i18n } = useTranslation();
  const api = useMemo(() => belgeApi(mod), [mod]);
  const yonetici = mod === 'yonetici';

  const [meta, setMeta] = useState<Meta | null>(null);
  const [liste, setListe] = useState<Liste | null>(null);
  const [q, setQ] = useState('');
  const [arananQ, setArananQ] = useState('');
  const [etiket, setEtiket] = useState('');
  const [alan, setAlan] = useState('');
  const [kaynak, setKaynak] = useState('');
  const [gorunum, setGorunum] = useState<Gorunum>({ tur: 'bos' });
  const [ayrinti, setAyrinti] = useState<BelgeAyrintisi | null>(null);
  const [musteriler, setMusteriler] = useState<MusteriSecenegi[]>([]);
  const [projeler, setProjeler] = useState<ProjeSecenegi[]>([]);
  const baslangicKullanildi = useRef(false);
  const ayrintiRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let iptal = false;
    api
      .meta()
      .then((m) => {
        if (!iptal) setMeta(m);
      })
      .catch((e) => toast.error(hataMetni(t, e)));
    if (yonetici) {
      modulMusterileriGetir()
        .then((m) => {
          if (!iptal) setMusteriler(m);
        })
        .catch(() => undefined);
      client.entities.projects
        .query({ sort: '-created_at', limit: 200 })
        .then((y: { data?: { items?: ProjeSecenegi[] } }) => {
          if (!iptal) setProjeler(y?.data?.items ?? []);
        })
        .catch(() => undefined);
    }
    return () => {
      iptal = true;
    };
  }, [api, yonetici, t]);

  // Aramayı yazarken her tuşta istek atmayalım.
  useEffect(() => {
    const z = window.setTimeout(() => setArananQ(q.trim()), 300);
    return () => window.clearTimeout(z);
  }, [q]);

  const listeYukle = useCallback(async () => {
    try {
      setListe(
        await api.liste({
          q: arananQ || undefined,
          etiket: etiket || undefined,
          tur: kategori,
          alan: yonetici ? alan || undefined : undefined,
          kaynak: yonetici ? kaynak || undefined : undefined,
        })
      );
    } catch (e) {
      toast.error(hataMetni(t, e));
      setListe({ items: [], etiketler: [] });
    }
  }, [api, arananQ, etiket, kategori, alan, kaynak, yonetici, t]);

  useEffect(() => {
    void listeYukle();
  }, [listeYukle]);

  const ac = useCallback(
    async (id: number) => {
      setGorunum({ tur: 'oku', id });
      setAyrinti(null);
      try {
        setAyrinti(await api.getir(id));
        window.requestAnimationFrame(() => {
          if (window.innerWidth < 1024) ayrintiRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
      } catch (e) {
        toast.error(hataMetni(t, e));
        setGorunum({ tur: 'bos' });
      }
    },
    [api, t]
  );

  // Bildirim bağlantısı (`?belge=12`) — bir kez.
  useEffect(() => {
    if (baslangicBelge && !baslangicKullanildi.current) {
      baslangicKullanildi.current = true;
      void ac(baslangicBelge);
    }
  }, [baslangicBelge, ac]);

  const degisti = (b: BelgeAyrintisi) => {
    setAyrinti(b);
    setGorunum({ tur: 'oku', id: b.id });
    setListe((l) => (l ? { ...l, items: l.items.map((x) => (x.id === b.id ? { ...x, ...b } : x)) } : l));
    void listeYukle();
  };

  const kendiBelgesiVar = yonetici || !!meta?.kendi_belge;
  const sinirDolu = !yonetici && meta?.belge_siniri !== undefined && (meta.belge_sayisi ?? 0) >= meta.belge_siniri;
  const yeni = () => {
    if (kategori === 'strateji') setGorunum({ tur: 'sablon' });
    else setGorunum({ tur: 'yeni', belgeTuru: 'belge' });
  };

  const BaslikIkonu = kategori === 'strateji' ? LayoutGrid : BookText;
  const ayrintiGorunur = gorunum.tur !== 'bos';

  return (
    <section className="min-w-0" data-testid={`belge-merkezi-${kategori}`} data-mod={mod}>
      <BelgeStilleri />
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <h2 className="flex items-center gap-2 text-xl font-semibold">
            <BaslikIkonu className="h-5 w-5 text-purple-300" aria-hidden="true" />
            {t(`belgeler.baslik.${kategori}`)}
          </h2>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
            {t(`belgeler.aciklama.${yonetici ? kategori : kategori === 'strateji' ? 'musteriStrateji' : 'musteriBelge'}`)}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {kategori === 'belge' && (
            <Button
              variant={gorunum.tur === 'yapilacak' ? 'default' : 'outline'}
              className={`gap-1.5 ${gorunum.tur === 'yapilacak' ? '' : '!bg-transparent'}`}
              onClick={() => setGorunum(gorunum.tur === 'yapilacak' ? { tur: 'bos' } : { tur: 'yapilacak' })}
              data-testid="belge-yapilacaklarim"
            >
              <ListChecks className="h-4 w-4" aria-hidden="true" />
              {t('belgeler.yapilacak.baslik')}
            </Button>
          )}
          {kendiBelgesiVar && (
            <Button className="gap-1.5" onClick={yeni} disabled={sinirDolu} title={sinirDolu ? t('belgeler.hata.belge_siniri', { sinir: meta?.belge_siniri }) : undefined} data-testid="belge-yeni">
              <FilePlus2 className="h-4 w-4" aria-hidden="true" />
              {t(`belgeler.yeni.${kategori}`)}
            </Button>
          )}
        </div>
      </div>

      <div className="belge-duzen">
        {/* --- Liste --- */}
        <aside className={`${ayrintiGorunur ? 'hidden lg:block' : ''} min-w-0 space-y-3`} data-testid="belge-liste">
          <div className={KART}>
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
              <Input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder={t('belgeler.ara')}
                className="bg-white/5 pl-9"
                aria-label={t('belgeler.ara')}
                data-testid="belge-ara"
              />
            </div>
            {yonetici && (
              <div className="mt-2 grid grid-cols-2 gap-2">
                <select className={SECIM} value={alan} onChange={(e) => setAlan(e.target.value)} aria-label={t('belgeler.alan.baslik')} data-testid="belge-suz-alan">
                  <option value="">{t('belgeler.alan.tumu')}</option>
                  <option value="ajans">{t('belgeler.alan.ajans')}</option>
                  <option value="musteri">{t('belgeler.alan.musteriSecenek')}</option>
                  <option value="proje">{t('belgeler.alan.projeSecenek')}</option>
                </select>
                <select className={SECIM} value={kaynak} onChange={(e) => setKaynak(e.target.value)} aria-label={t('belgeler.kaynak.baslik')} data-testid="belge-suz-kaynak">
                  <option value="">{t('belgeler.kaynak.tumu')}</option>
                  <option value="ajans">{t('belgeler.kaynak.ajans')}</option>
                  <option value="musteri">{t('belgeler.kaynak.musteri')}</option>
                </select>
              </div>
            )}
            {liste && liste.etiketler.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1.5" aria-label={t('belgeler.etiketSuzgeci')}>
                <button
                  type="button"
                  onClick={() => setEtiket('')}
                  className={`rounded-full px-2.5 py-0.5 text-xs ${!etiket ? 'bg-purple-500/25 text-white' : 'bg-white/5 text-muted-foreground hover:text-white'}`}
                >
                  {t('belgeler.tumEtiketler')}
                </button>
                {liste.etiketler.map((e) => (
                  <button
                    key={e.ad}
                    type="button"
                    onClick={() => setEtiket(etiket === e.ad ? '' : e.ad)}
                    className={`rounded-full px-2.5 py-0.5 text-xs ${etiket === e.ad ? 'bg-purple-500/25 text-white' : 'bg-white/5 text-muted-foreground hover:text-white'}`}
                    data-etiket={e.ad}
                  >
                    #{e.ad} <span className="opacity-60">{e.sayi}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className={KART} style={{ padding: '0.5rem' }}>
            <div className="flex items-center justify-between px-2 pb-1">
              <span className="text-xs text-muted-foreground">{t('belgeler.sayi', { sayi: liste?.items.length ?? 0 })}</span>
              <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => void listeYukle()} aria-label={t('belgeler.eylem.yenile')}>
                <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
              </Button>
            </div>
            {!liste ? (
              <Yukleniyor />
            ) : liste.items.length === 0 ? (
              <p className="px-3 py-8 text-center text-sm text-muted-foreground" data-testid="belge-liste-bos">
                {arananQ || etiket ? t('belgeler.bos.arama') : t(`belgeler.bos.${yonetici ? kategori : kendiBelgesiVar ? kategori : 'musteri'}`)}
              </p>
            ) : (
              <ul className="max-h-[70vh] space-y-1 overflow-y-auto">
                {liste.items.map((b) => (
                  <ListeSatiri key={b.id} b={b} secili={'id' in gorunum && gorunum.id === b.id} onAc={() => void ac(b.id)} dil={i18n.language} yonetici={yonetici} />
                ))}
              </ul>
            )}
          </div>
        </aside>

        {/* --- Ayrıntı --- */}
        <div ref={ayrintiRef} className="min-w-0 scroll-mt-24">
          {gorunum.tur === 'bos' && (
            <div className={`${KART} hidden text-sm text-muted-foreground lg:block`}>{t(`belgeler.secin.${kategori}`)}</div>
          )}
          {gorunum.tur === 'yapilacak' && (
            <Yapilacaklarim api={api} onBelgeAc={(id) => void ac(id)} />
          )}
          {gorunum.tur === 'sablon' && meta && (
            <div className={KART} data-testid="strateji-sablon-sec">
              <div className="mb-3 flex items-center justify-between gap-2">
                <h3 className="font-semibold">{t('belgeler.yeni.sablonSec')}</h3>
                <Button size="sm" variant="ghost" onClick={() => setGorunum({ tur: 'bos' })}>
                  {t('belgeler.eylem.vazgec')}
                </Button>
              </div>
              <div className="grid gap-2 sm:grid-cols-2">
                {meta.strateji_sablonlari.map((s) => (
                  <button
                    key={s.tur}
                    type="button"
                    onClick={() => setGorunum({ tur: 'yeni', belgeTuru: s.tur })}
                    className="rounded-xl border border-white/10 bg-white/[0.02] p-3 text-left hover:border-purple-400/40 hover:bg-purple-500/10"
                    data-sablon={s.tur}
                  >
                    <span className="block font-medium">{t(`belgeler.sablon.${s.tur}.ad`)}</span>
                    <span className="mt-0.5 block text-xs text-muted-foreground">{t(`belgeler.sablon.${s.tur}.aciklama`)}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
          {gorunum.tur === 'yeni' && meta && (
            <BelgeDuzenle
              key={`yeni-${gorunum.belgeTuru}`}
              api={api}
              meta={meta}
              tur={gorunum.belgeTuru}
              musteriler={musteriler}
              projeler={projeler}
              onKaydedildi={(b) => {
                degisti(b);
                void api.meta().then(setMeta).catch(() => undefined);
              }}
              onVazgec={() => setGorunum({ tur: 'bos' })}
            />
          )}
          {gorunum.tur === 'duzenle' && meta && ayrinti && ayrinti.id === gorunum.id && (
            <BelgeDuzenle
              key={`duzenle-${ayrinti.id}-${ayrinti.surum}`}
              api={api}
              meta={meta}
              belge={ayrinti}
              tur={ayrinti.tur}
              musteriler={musteriler}
              projeler={projeler}
              onKaydedildi={degisti}
              onVazgec={() => setGorunum({ tur: 'oku', id: ayrinti.id })}
            />
          )}
          {gorunum.tur === 'oku' &&
            (!ayrinti || !meta ? (
              <Yukleniyor />
            ) : (
              <BelgeGoruntule
                api={api}
                meta={meta}
                belge={ayrinti}
                onDuzenle={() => setGorunum({ tur: 'duzenle', id: ayrinti.id })}
                onDegisti={degisti}
                onSilindi={(id) => {
                  setAyrinti(null);
                  setGorunum({ tur: 'bos' });
                  setListe((l) => (l ? { ...l, items: l.items.filter((x) => x.id !== id) } : l));
                  void api.meta().then(setMeta).catch(() => undefined);
                }}
                onGeri={() => setGorunum({ tur: 'bos' })}
              />
            ))}
        </div>
      </div>
    </section>
  );
}

function ListeSatiri({ b, secili, onAc, dil, yonetici }: { b: Belge; secili: boolean; onAc: () => void; dil: string; yonetici: boolean }) {
  const { t } = useTranslation();
  return (
    <li>
      <button
        type="button"
        onClick={onAc}
        className={`w-full rounded-xl px-3 py-2.5 text-left transition-colors ${secili ? 'bg-purple-500/15 ring-1 ring-purple-400/40' : 'hover:bg-white/5'}`}
        data-testid={`belge-satir-${b.id}`}
        data-belge-baslik={b.baslik}
      >
        <span className="flex items-start gap-1.5">
          {b.sabit && <Pin className="mt-0.5 h-3.5 w-3.5 shrink-0 text-sky-300" aria-label={t('belgeler.rozet.sabit')} />}
          <span className="min-w-0 flex-1 break-words text-sm font-medium">{b.baslik}</span>
          {b.gorunurluk === 'paylasilan' && <Share2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-300" aria-label={t('belgeler.rozet.paylasilan')} />}
        </span>
        {b.ozet && <span className="mt-0.5 line-clamp-2 block break-words text-xs text-muted-foreground">{b.ozet}</span>}
        <span className="mt-1 flex flex-wrap items-center gap-1">
          {b.strateji && <Rozet renk="fuchsia">{t(`belgeler.sablon.${b.tur}.ad`)}</Rozet>}
          {yonetici && b.alan !== 'ajans' && <Rozet>{b.alan === 'proje' ? b.proje_adi || `#${b.proje_id}` : b.musteri_email}</Rozet>}
          {yonetici && b.musteri_belgesi && <Rozet renk="sky">{t('belgeler.rozet.musteriBelgesi')}</Rozet>}
          {b.acik_yapilacak > 0 && <Rozet renk="amber">{t('belgeler.rozet.yapilacak', { sayi: b.acik_yapilacak })}</Rozet>}
          <span className="text-[11px] text-muted-foreground">{tarihYaz(b.updated_at, dil)}</span>
        </span>
      </button>
    </li>
  );
}
