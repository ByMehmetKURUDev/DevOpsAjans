import { lazy, Suspense, useCallback, useEffect, useMemo, useState, type DragEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import {
  AlarmClock,
  BarChart3,
  Download,
  FileCode2,
  GripVertical,
  LayoutGrid,
  List,
  Loader2,
  Plus,
  RefreshCw,
  Search,
  Settings2,
  X,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { AlanEtiketi, Bekle, PuanRozeti, SECIM } from './ortak';
import {
  adayListesi,
  adayOlustur,
  asamaAdi,
  asamaTasi,
  CrmHatasi,
  hataMetni,
  iceAktar,
  kanbanGetir,
  metaGetir,
  paraGoster,
  renk,
  tarihGoster,
  toplamlarGoster,
  type Aday,
  type CrmMeta,
  type KanbanSutunu,
  type Suzgec,
} from '@/lib/crm';

const AdayCekmecesi = lazy(() => import('./AdayCekmecesi'));
const CrmOzeti = lazy(() => import('./CrmOzeti'));
const CrmFormlari = lazy(() => import('./CrmFormlari'));
const CrmAsamalari = lazy(() => import('./CrmAsamalari'));

type Gorunum = 'kanban' | 'liste' | 'ozet' | 'formlar' | 'asamalar';
const GORUNUMLER: { anahtar: Gorunum; ikon: typeof LayoutGrid }[] = [
  { anahtar: 'kanban', ikon: LayoutGrid },
  { anahtar: 'liste', ikon: List },
  { anahtar: 'ozet', ikon: BarChart3 },
  { anahtar: 'formlar', ikon: FileCode2 },
  { anahtar: 'asamalar', ikon: Settings2 },
];
const LISTE_BOYUTU = 25;

interface Props {
  /** Bağlı kayıt bağlantıları (Talepler / Fiyatlandırma sekmeleri). */
  onSekmeGit?: (sekme: string) => void;
}

function adresAdayi(): number | null {
  try {
    const n = Number(new URLSearchParams(window.location.search).get('aday'));
    return Number.isFinite(n) && n > 0 ? n : null;
  } catch {
    return null;
  }
}

/**
 * Yönetici › CRM (Faz 3C): ajansın kendi satış hunisi.
 *
 * Görünümler: kanban (HTML5 sürükle-bırak; her kartta klavyeyle kullanılabilen
 * "Taşı" seçimi — 2B görev kanbanıyla aynı düzen), liste (süzgeç, sıralama,
 * sayfa), özet (huni dönüşümü, kaynaklar, aşama süreleri — kütüphanesiz),
 * formlar (gömülebilir form + gömme kodu) ve aşama yönetimi. Aday ayrıntısı
 * sağdan açılan çekmecede (mobilde tam ekran). Bildirim bağlantısı
 * `/admin?sekme=crm&aday=<id>` çekmeceyi doğrudan açıyor.
 */
export default function CrmPaneli({ onSekmeGit }: Props) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [gorunum, setGorunum] = useState<Gorunum>('kanban');
  const [meta, setMeta] = useState<CrmMeta | null>(null);
  const [sutunlar, setSutunlar] = useState<KanbanSutunu[] | null>(null);
  const [liste, setListe] = useState<{ items: Aday[]; toplam: number } | null>(null);
  const [sayfa, setSayfa] = useState(1);
  const [siralama, setSiralama] = useState('-puan');
  const [asamaSuzgeci, setAsamaSuzgeci] = useState('');
  const [suzgec, setSuzgec] = useState<Suzgec>({});
  const [araMetni, setAraMetni] = useState('');
  const [seciliId, setSeciliId] = useState<number | null>(adresAdayi);
  const [yeniAcik, setYeniAcik] = useState(false);
  const [surukle, setSurukle] = useState<number | null>(null);
  const [hedefSutun, setHedefSutun] = useState<string | null>(null);
  const [aktariliyor, setAktariliyor] = useState(false);

  const asamaHaritasi = useMemo(() => new Map((meta?.asamalar ?? []).map((a) => [a.anahtar, a])), [meta]);

  const metaYukle = useCallback(async () => {
    try {
      setMeta(await metaGetir());
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  }, [t]);

  const veriYukle = useCallback(async () => {
    try {
      if (gorunum === 'kanban') setSutunlar((await kanbanGetir(suzgec)).asamalar);
      if (gorunum === 'liste') {
        const y = await adayListesi({ ...suzgec, asama: asamaSuzgeci || undefined, siralama, sayfa, boyut: LISTE_BOYUTU });
        setListe({ items: y.items, toplam: y.toplam });
      }
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  }, [gorunum, suzgec, asamaSuzgeci, siralama, sayfa, t]);

  useEffect(() => {
    void metaYukle();
  }, [metaYukle]);
  useEffect(() => {
    void veriYukle();
  }, [veriYukle]);
  // Arama kutusu: yazmayı bitirince (350 ms) süz.
  useEffect(() => {
    const zaman = window.setTimeout(() => {
      setSuzgec((s) => (s.ara === (araMetni.trim() || undefined) ? s : { ...s, ara: araMetni.trim() || undefined }));
      setSayfa(1);
    }, 350);
    return () => window.clearTimeout(zaman);
  }, [araMetni]);

  const yenile = () => {
    void metaYukle();
    void veriYukle();
  };

  const tasi = async (id: number, asama: string) => {
    const kart = sutunlar?.flatMap((s) => s.adaylar).find((a) => a.id === id);
    if (kart && kart.asama === asama) return;
    try {
      await asamaTasi(id, asama);
      toast.success(t('crm.tasindi', { asama: asamaAdi(asamaHaritasi.get(asama), dil) }));
      void veriYukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const suruklemeBasla = (e: DragEvent, id: number) => {
    setSurukle(id);
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', String(id));
  };
  const sutunaBirak = (e: DragEvent, asama: string) => {
    e.preventDefault();
    const id = Number(e.dataTransfer.getData('text/plain')) || surukle;
    setSurukle(null);
    setHedefSutun(null);
    if (id) void tasi(id, asama);
  };

  const aktar = async () => {
    if (!window.confirm(t('crm.iceAktarOnay'))) return;
    setAktariliyor(true);
    try {
      const s = await iceAktar();
      toast.success(t('crm.iceAktarildi', { olusturulan: s.olusturulan, eklenen: s.eklenen }));
      yenile();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setAktariliyor(false);
    }
  };

  const suzgecGerekli = gorunum === 'kanban' || gorunum === 'liste';

  return (
    <section className="min-w-0 space-y-5" data-testid="crm-paneli" aria-labelledby="crm-baslik">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 id="crm-baslik" className="text-xl font-semibold">
            {t('crm.baslik')}
          </h2>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{t('crm.aciklama')}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" onClick={() => setYeniAcik(true)} className="gap-1" data-testid="crm-yeni-aday">
            <Plus className="h-4 w-4" /> {t('crm.yeniAday')}
          </Button>
          <Button size="sm" variant="outline" onClick={() => void aktar()} disabled={aktariliyor} className="gap-1" data-testid="crm-ice-aktar">
            {aktariliyor ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
            {t('crm.iceAktar')}
          </Button>
          <Button size="sm" variant="ghost" onClick={yenile} aria-label={t('crm.yenile')}>
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap gap-1 border-b border-white/10" role="tablist" aria-label={t('crm.gorunumler')}>
        {GORUNUMLER.map(({ anahtar, ikon: Ikon }) => (
          <button
            key={anahtar}
            type="button"
            role="tab"
            aria-selected={gorunum === anahtar}
            onClick={() => setGorunum(anahtar)}
            className={`inline-flex items-center gap-1.5 px-3 py-2 text-sm ${
              gorunum === anahtar ? 'border-b-2 border-purple-400 text-foreground' : 'text-muted-foreground hover:text-foreground'
            }`}
            data-crm-gorunum={anahtar}
          >
            <Ikon className="h-4 w-4" aria-hidden="true" />
            {t(`crm.gorunum.${anahtar}`)}
          </button>
        ))}
      </div>

      {suzgecGerekli && meta && (
        <div className="cam-kart grid gap-2 rounded-2xl border border-white/10 bg-white/[0.03] p-3 sm:grid-cols-2 lg:grid-cols-4">
          <label className="relative block">
            <span className="sr-only">{t('crm.ara')}</span>
            <Search className="pointer-events-none absolute start-2.5 top-2.5 h-4 w-4 text-muted-foreground" aria-hidden="true" />
            <Input
              value={araMetni}
              onChange={(e) => setAraMetni(e.target.value)}
              placeholder={t('crm.araOrnek')}
              className="h-9 ps-8"
              maxLength={100}
              data-testid="crm-ara"
            />
          </label>
          <select
            aria-label={t('crm.alan.sorumlu')}
            className={SECIM}
            value={suzgec.sorumlu ?? ''}
            onChange={(e) => {
              setSuzgec((s) => ({ ...s, sorumlu: e.target.value || undefined }));
              setSayfa(1);
            }}
          >
            <option value="">{t('crm.tumSorumlular')}</option>
            <option value="-">{t('crm.sorumsuz')}</option>
            {meta.sorumlular.map((s) => (
              <option key={s.email} value={s.email}>
                {s.ad ? `${s.ad} (${s.email})` : s.email}
              </option>
            ))}
          </select>
          <select
            aria-label={t('crm.alan.kaynak')}
            className={SECIM}
            value={suzgec.kaynak ?? ''}
            onChange={(e) => {
              setSuzgec((s) => ({ ...s, kaynak: e.target.value || undefined }));
              setSayfa(1);
            }}
          >
            <option value="">{t('crm.tumKaynaklar')}</option>
            {meta.kaynaklar.map((k) => (
              <option key={k} value={k}>
                {t(`crm.kaynak.${k}`)}
              </option>
            ))}
          </select>
          {gorunum === 'liste' ? (
            <div className="grid grid-cols-2 gap-2">
              <select
                aria-label={t('crm.alan.asama')}
                className={SECIM}
                value={asamaSuzgeci}
                onChange={(e) => {
                  setAsamaSuzgeci(e.target.value);
                  setSayfa(1);
                }}
              >
                <option value="">{t('crm.tumAsamalar')}</option>
                {meta.asamalar.map((a) => (
                  <option key={a.anahtar} value={a.anahtar}>
                    {asamaAdi(a, dil)}
                  </option>
                ))}
              </select>
              <select aria-label={t('crm.siralama')} className={SECIM} value={siralama} onChange={(e) => setSiralama(e.target.value)}>
                {meta.siralamalar.map((s) => (
                  <option key={s} value={s}>
                    {t(`crm.sirala.${s.startsWith('-') ? `${s.slice(1)}_azalan` : `${s}_artan`}`)}
                  </option>
                ))}
              </select>
            </div>
          ) : (
            <p className="self-center text-xs text-muted-foreground">{t('crm.surukleIpucu')}</p>
          )}
        </div>
      )}

      {gorunum === 'kanban' &&
        (!sutunlar || !meta ? (
          <Bekle />
        ) : (
          <div className="-mx-1 max-w-full overflow-x-auto pb-2" data-testid="crm-kanban">
            <p className="sr-only">{t('crm.surukleIpucu')}</p>
            <div className="flex min-w-max gap-3 px-1">
              {sutunlar.map((s) => (
                <div
                  key={s.anahtar}
                  onDragOver={(e) => {
                    e.preventDefault();
                    if (hedefSutun !== s.anahtar) setHedefSutun(s.anahtar);
                  }}
                  onDragLeave={() => setHedefSutun((h) => (h === s.anahtar ? null : h))}
                  onDrop={(e) => sutunaBirak(e, s.anahtar)}
                  className={`w-[17rem] shrink-0 rounded-2xl border bg-white/[0.02] p-3 transition-colors ${renk(s.renk).kenar} ${
                    hedefSutun === s.anahtar ? 'bg-purple-500/10 ring-1 ring-purple-400/40' : ''
                  }`}
                  role="group"
                  aria-label={asamaAdi(s, dil)}
                  data-crm-sutun={s.anahtar}
                >
                  <h3 className="flex items-center gap-2 text-sm font-semibold">
                    <span className={`h-2 w-2 rounded-full ${renk(s.renk).nokta}`} aria-hidden="true" />
                    <span className="min-w-0 truncate">{asamaAdi(s, dil)}</span>
                    <span className="text-xs text-muted-foreground">({s.sayi})</span>
                  </h3>
                  <p className="mb-2 mt-0.5 min-h-[1rem] text-xs text-muted-foreground">{toplamlarGoster(s.toplam_deger, dil)}</p>
                  <ul className="min-h-[3rem] space-y-2">
                    {s.adaylar.map((a) => (
                      <AdayKarti
                        key={a.id}
                        a={a}
                        meta={meta}
                        surukleniyor={surukle === a.id}
                        onAc={() => setSeciliId(a.id)}
                        onTasi={(asama) => void tasi(a.id, asama)}
                        onSurukle={(e) => suruklemeBasla(e, a.id)}
                        onBitir={() => {
                          setSurukle(null);
                          setHedefSutun(null);
                        }}
                      />
                    ))}
                    {s.adaylar.length === 0 && <li className="py-2 text-center text-xs text-muted-foreground">{t('crm.bosSutun')}</li>}
                  </ul>
                </div>
              ))}
            </div>
          </div>
        ))}

      {gorunum === 'liste' &&
        (!liste || !meta ? (
          <Bekle />
        ) : (
          <AdayTablosu
            liste={liste}
            meta={meta}
            sayfa={sayfa}
            onSayfa={setSayfa}
            onAc={setSeciliId}
            onTasi={async (id, asama) => {
              try {
                await asamaTasi(id, asama);
                toast.success(t('crm.tasindi', { asama: asamaAdi(asamaHaritasi.get(asama), dil) }));
                void veriYukle();
              } catch (e) {
                toast.error(hataMetni(t, e));
              }
            }}
          />
        ))}

      <Suspense fallback={<Bekle />}>
        {gorunum === 'ozet' && <CrmOzeti asamalar={meta?.asamalar ?? []} />}
        {gorunum === 'formlar' && meta && <CrmFormlari asamalar={meta.asamalar} />}
        {gorunum === 'asamalar' && <CrmAsamalari onDegisti={yenile} />}
      </Suspense>

      {yeniAcik && meta && (
        <YeniAdayPenceresi
          meta={meta}
          onKapat={() => setYeniAcik(false)}
          onOlustu={(id) => {
            setYeniAcik(false);
            setSeciliId(id);
            void veriYukle();
          }}
        />
      )}

      {seciliId !== null && meta && (
        <Suspense fallback={null}>
          <AdayCekmecesi
            adayId={seciliId}
            meta={meta}
            onKapat={() => setSeciliId(null)}
            onDegisti={() => void veriYukle()}
            onSekmeGit={(s) => {
              if (s === 'crmFormlar') {
                setSeciliId(null);
                setGorunum('formlar');
              } else onSekmeGit?.(s);
            }}
          />
        </Suspense>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Kanban kartı
// ---------------------------------------------------------------------------
function AdayKarti({
  a,
  meta,
  surukleniyor,
  onAc,
  onTasi,
  onSurukle,
  onBitir,
}: {
  a: Aday;
  meta: CrmMeta;
  surukleniyor: boolean;
  onAc: () => void;
  onTasi: (asama: string) => void;
  onSurukle: (e: DragEvent) => void;
  onBitir: () => void;
}) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  return (
    <li
      draggable
      onDragStart={onSurukle}
      onDragEnd={onBitir}
      className={`cam-kart rounded-xl border border-white/10 bg-white/[0.04] p-2.5 text-sm ${surukleniyor ? 'opacity-50' : ''}`}
      data-crm-aday={a.id}
    >
      <div className="flex items-start gap-1.5">
        <GripVertical className="mt-0.5 h-4 w-4 shrink-0 cursor-grab text-muted-foreground" aria-hidden="true" />
        <button type="button" onClick={onAc} className="min-w-0 flex-1 text-start font-medium hover:text-purple-200">
          <span className="block break-words">{a.ad}</span>
          {a.firma && <span className="block truncate text-xs font-normal text-muted-foreground">{a.firma}</span>}
        </button>
        <PuanRozeti puan={a.puan} />
      </div>
      <div className="mt-1.5 flex flex-wrap items-center gap-1 text-[11px] text-muted-foreground">
        <span className="rounded bg-white/5 px-1.5 py-0.5">{t(`crm.kaynak.${a.kaynak}`)}</span>
        {a.deger_tahmini ? <span className="tabular-nums">{paraGoster(a.deger_tahmini, a.para_birimi, dil)}</span> : null}
        {a.sonraki_adim_tarihi && (
          <span
            className={`inline-flex items-center gap-0.5 ${a.gecikti ? 'text-rose-300' : a.bugun ? 'text-amber-200' : ''}`}
            title={a.sonraki_adim || undefined}
          >
            <AlarmClock className="h-3 w-3" aria-hidden="true" />
            {tarihGoster(a.sonraki_adim_tarihi, dil)}
          </span>
        )}
        {a.musteri_email && <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-emerald-200">{t('crm.musteri')}</span>}
      </div>
      <label className="mt-2 flex items-center gap-2 text-[11px] text-muted-foreground">
        <span className="shrink-0">{t('crm.tasi')}</span>
        <select
          value={a.asama}
          onChange={(e) => onTasi(e.target.value)}
          aria-label={t('crm.tasiAria', { ad: a.ad })}
          className={SECIM + ' h-7 text-xs'}
          data-crm-tasi={a.id}
        >
          {meta.asamalar.map((x) => (
            <option key={x.anahtar} value={x.anahtar}>
              {asamaAdi(x, dil)}
            </option>
          ))}
        </select>
      </label>
    </li>
  );
}

// ---------------------------------------------------------------------------
// Liste
// ---------------------------------------------------------------------------
function AdayTablosu({
  liste,
  meta,
  sayfa,
  onSayfa,
  onAc,
  onTasi,
}: {
  liste: { items: Aday[]; toplam: number };
  meta: CrmMeta;
  sayfa: number;
  onSayfa: (s: number) => void;
  onAc: (id: number) => void;
  onTasi: (id: number, asama: string) => void;
}) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const sayfaSayisi = Math.max(1, Math.ceil(liste.toplam / LISTE_BOYUTU));
  return (
    <div className="space-y-3" data-testid="crm-liste">
      <div className="max-w-full overflow-x-auto rounded-2xl border border-white/10">
        <table className="w-full min-w-[760px] text-sm">
          <thead className="bg-white/[0.03] text-start text-xs text-muted-foreground">
            <tr>
              <th className="p-2 text-start font-medium">{t('crm.alan.ad')}</th>
              <th className="p-2 text-start font-medium">{t('crm.alan.asama')}</th>
              <th className="p-2 text-start font-medium">{t('crm.puan.kisa')}</th>
              <th className="p-2 text-start font-medium">{t('crm.alan.deger_tahmini')}</th>
              <th className="p-2 text-start font-medium">{t('crm.alan.kaynak')}</th>
              <th className="p-2 text-start font-medium">{t('crm.alan.sorumlu')}</th>
              <th className="p-2 text-start font-medium">{t('crm.alan.sonraki_adim')}</th>
            </tr>
          </thead>
          <tbody>
            {liste.items.map((a) => (
              <tr key={a.id} className="border-t border-white/5 align-top" data-crm-satir={a.id}>
                <td className="p-2">
                  <button type="button" className="text-start font-medium hover:text-purple-200" onClick={() => onAc(a.id)}>
                    {a.ad}
                  </button>
                  <div className="text-xs text-muted-foreground">{[a.firma, a.email].filter(Boolean).join(' · ')}</div>
                </td>
                <td className="p-2">
                  <select
                    value={a.asama}
                    onChange={(e) => onTasi(a.id, e.target.value)}
                    aria-label={t('crm.tasiAria', { ad: a.ad })}
                    className={SECIM + ' h-8 text-xs'}
                  >
                    {meta.asamalar.map((x) => (
                      <option key={x.anahtar} value={x.anahtar}>
                        {asamaAdi(x, dil)}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="p-2">
                  <PuanRozeti puan={a.puan} />
                </td>
                <td className="p-2 text-xs tabular-nums">{a.deger_tahmini ? paraGoster(a.deger_tahmini, a.para_birimi, dil) : '—'}</td>
                <td className="p-2 text-xs">{t(`crm.kaynak.${a.kaynak}`)}</td>
                <td className="p-2 text-xs">{a.sorumlu || '—'}</td>
                <td className={`p-2 text-xs ${a.gecikti ? 'text-rose-300' : ''}`}>
                  {a.sonraki_adim || '—'}
                  {a.sonraki_adim_tarihi ? <div className="text-muted-foreground">{tarihGoster(a.sonraki_adim_tarihi, dil)}</div> : null}
                </td>
              </tr>
            ))}
            {liste.items.length === 0 && (
              <tr>
                <td colSpan={7} className="p-6 text-center text-muted-foreground">
                  {t('crm.bos')}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
        <span>{t('crm.toplamAday', { sayi: liste.toplam })}</span>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" disabled={sayfa <= 1} onClick={() => onSayfa(sayfa - 1)}>
            {t('crm.onceki')}
          </Button>
          <span className="tabular-nums">
            {sayfa} / {sayfaSayisi}
          </span>
          <Button size="sm" variant="outline" disabled={sayfa >= sayfaSayisi} onClick={() => onSayfa(sayfa + 1)}>
            {t('crm.sonraki')}
          </Button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Yeni aday
// ---------------------------------------------------------------------------
function YeniAdayPenceresi({ meta, onKapat, onOlustu }: { meta: CrmMeta; onKapat: () => void; onOlustu: (id: number) => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [form, setForm] = useState({
    ad: '',
    firma: '',
    email: '',
    telefon: '',
    deger_tahmini: '',
    para_birimi: 'TRY',
    kaynak: 'manuel',
    asama: meta.asamalar.find((a) => a.tur === 'acik')?.anahtar ?? '',
    sorumlu: '',
  });
  const [mesgul, setMesgul] = useState(false);
  const [mevcut, setMevcut] = useState<number | null>(null);
  const yaz = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const kaydet = async () => {
    setMesgul(true);
    setMevcut(null);
    try {
      const a = await adayOlustur({
        ...form,
        deger_tahmini: form.deger_tahmini === '' ? null : Number(form.deger_tahmini),
        sorumlu: form.sorumlu || null,
      });
      toast.success(t('crm.olusturuldu'));
      onOlustu(a.id);
    } catch (e) {
      if (e instanceof CrmHatasi && e.kod === 'ayni_eposta_acik_aday') setMevcut(Number(e.ek.aday_id));
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[70] overflow-y-auto bg-background/80 p-4 backdrop-blur-sm">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="crm-yeni-baslik"
        className="relative mx-auto my-8 max-w-xl rounded-2xl border border-white/10 bg-background p-6 shadow-2xl"
      >
        <button type="button" className="absolute end-4 top-4 rounded-lg p-2 hover:bg-white/5" onClick={onKapat} aria-label={t('crm.kapat')}>
          <X className="h-4 w-4" />
        </button>
        <h3 id="crm-yeni-baslik" className="mb-4 text-xl font-bold">
          {t('crm.yeniAday')}
        </h3>
        <form
          className="grid gap-3 sm:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault();
            void kaydet();
          }}
        >
          <AlanEtiketi ad={t('crm.alan.ad')} zorunlu>
            <Input value={form.ad} onChange={yaz('ad')} required maxLength={120} data-testid="crm-yeni-ad" />
          </AlanEtiketi>
          <AlanEtiketi ad={t('crm.alan.firma')}>
            <Input value={form.firma} onChange={yaz('firma')} maxLength={160} />
          </AlanEtiketi>
          <AlanEtiketi ad={t('crm.alan.email')}>
            <Input type="email" value={form.email} onChange={yaz('email')} maxLength={254} data-testid="crm-yeni-email" />
          </AlanEtiketi>
          <AlanEtiketi ad={t('crm.alan.telefon')}>
            <Input value={form.telefon} onChange={yaz('telefon')} maxLength={40} />
          </AlanEtiketi>
          <AlanEtiketi ad={t('crm.alan.deger_tahmini')}>
            <div className="flex gap-2">
              <Input type="number" min={0} step="any" value={form.deger_tahmini} onChange={yaz('deger_tahmini')} />
              <select aria-label={t('crm.alan.para_birimi')} className={SECIM + ' w-24'} value={form.para_birimi} onChange={yaz('para_birimi')}>
                {meta.para_birimleri.map((p) => (
                  <option key={p}>{p}</option>
                ))}
              </select>
            </div>
          </AlanEtiketi>
          <AlanEtiketi ad={t('crm.alan.kaynak')}>
            <select className={SECIM} value={form.kaynak} onChange={yaz('kaynak')}>
              {meta.kaynaklar.map((k) => (
                <option key={k} value={k}>
                  {t(`crm.kaynak.${k}`)}
                </option>
              ))}
            </select>
          </AlanEtiketi>
          <AlanEtiketi ad={t('crm.alan.asama')}>
            <select className={SECIM} value={form.asama} onChange={yaz('asama')}>
              {meta.asamalar.map((a) => (
                <option key={a.anahtar} value={a.anahtar}>
                  {asamaAdi(a, dil)}
                </option>
              ))}
            </select>
          </AlanEtiketi>
          <AlanEtiketi ad={t('crm.alan.sorumlu')}>
            <select className={SECIM} value={form.sorumlu} onChange={yaz('sorumlu')}>
              <option value="">{t('crm.sorumsuz')}</option>
              {meta.sorumlular.map((s) => (
                <option key={s.email} value={s.email}>
                  {s.ad || s.email}
                </option>
              ))}
            </select>
          </AlanEtiketi>
          {mevcut !== null && (
            <p className="text-xs text-amber-200 sm:col-span-2">
              {t('crm.mevcutAday')}{' '}
              <button type="button" className="underline" onClick={() => onOlustu(mevcut)}>
                {t('crm.mevcutAc')}
              </button>
            </p>
          )}
          <div className="flex justify-end gap-2 sm:col-span-2">
            <Button type="button" variant="ghost" onClick={onKapat}>
              {t('crm.vazgec')}
            </Button>
            <Button type="submit" disabled={mesgul || !form.ad.trim()} data-testid="crm-yeni-kaydet">
              {mesgul ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
              {t('crm.olustur')}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
