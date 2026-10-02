import { Suspense, useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from 'react';
import {
  AlertTriangle,
  Bug,
  Eye,
  EyeOff,
  Flag,
  GripVertical,
  LayoutGrid,
  List,
  Loader2,
  Plus,
  RefreshCw,
  Trash2,
  X,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import GorevSayacDugmesi from '@/components/admin/GorevSayacDugmesi';
import { ekliLazy } from '@/i18n/ekliLazy';

// Faz 4W: proje ayrıntısında özel alanlar (tanım yoksa hiçbir şey çizmez).
const OzelAlanlarBolumu = ekliLazy('ozelAlanlar', () => import('@/components/OzelAlanlarBolumu'));
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  GOREV_DURUMLARI,
  ONCELIKLER,
  ProjeHatasi,
  bagimlilikEkle,
  bagimlilikSil,
  ekAdresi,
  gorevEkle,
  gorevGuncelle,
  gorevSil,
  goreveDonustur,
  kontrolEkle,
  kontrolGuncelle,
  kontrolSil,
  projeGorevleri,
  revizyonHakkiAyarla,
  saatGir,
  saatGoster,
  saatSil,
  saatiKredidenDus,
  saatleriGetir,
  siraKaydet,
  tarihGoster,
  type GeriBildirim,
  type Gorev,
  type GorevDurumu,
  type ProjeGorevleriYaniti,
  type RevizyonSayaci,
  type SaatGirisi,
} from '@/lib/projeYonetimi';

const SECIM =
  'h-9 w-full rounded-md border border-white/10 bg-white/5 px-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-purple-500/40';

const SUTUN_RENGI: Record<GorevDurumu, string> = {
  yapilacak: 'border-white/10',
  suruyor: 'border-sky-400/30',
  incelemede: 'border-amber-400/30',
  tamam: 'border-emerald-400/30',
};

const ONCELIK_RENGI: Record<string, string> = {
  dusuk: 'bg-white/5 text-muted-foreground',
  normal: 'bg-white/10 text-foreground/80',
  yuksek: 'bg-amber-500/15 text-amber-200',
  acil: 'bg-rose-500/20 text-rose-200',
};

interface Props {
  projeId: number;
  projeBasligi?: string;
  onKapat?: () => void;
}

/**
 * Yönetici › Projeler › proje görevleri (Faz 2B).
 *
 * Kanban (HTML5 sürükle-bırak; ek kütüphane yok) + Liste görünümü. Her
 * kartta klavyeyle kullanılabilen bir "Taşı" seçimi var: sürükleyemeyen
 * (klavye, ekran okuyucu, dokunmatik) aynı işi oradan yapıyor. Bağımlılığı
 * bitmemiş görevi "Tamamlandı"ya bırakmak uyarı veriyor; sunucu da aynı
 * kuralı uyguluyor (hep ya da hiç).
 */
export default function ProjeGorevleri({ projeId, projeBasligi, onKapat }: Props) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [veri, setVeri] = useState<ProjeGorevleriYaniti | null>(null);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [gorunum, setGorunum] = useState<'kanban' | 'liste'>('kanban');
  const [seciliId, setSeciliId] = useState<number | null>(null);
  const [uyari, setUyari] = useState<string | null>(null);
  const [surukle, setSurukle] = useState<number | null>(null);
  const [hedefSutun, setHedefSutun] = useState<GorevDurumu | null>(null);
  const [yeni, setYeni] = useState({ baslik: '', durum: 'yapilacak' as GorevDurumu, gorunur: true });
  const [mesgul, setMesgul] = useState(false);

  const yukle = useCallback(async () => {
    try {
      setVeri(await projeGorevleri(projeId));
    } catch {
      toast.error(t('gorevler.hata.yuklenemedi'));
    } finally {
      setYukleniyor(false);
    }
  }, [projeId, t]);

  useEffect(() => {
    setYukleniyor(true);
    setSeciliId(null);
    void yukle();
  }, [yukle]);

  const gorevler = veri?.gorevler ?? [];
  const adlar = useMemo(() => new Map(gorevler.map((g) => [g.id, g.baslik])), [gorevler]);
  const sutunlar = useMemo(() => {
    const s: Record<GorevDurumu, Gorev[]> = { yapilacak: [], suruyor: [], incelemede: [], tamam: [] };
    for (const g of gorevler) s[g.durum]?.push(g);
    for (const d of GOREV_DURUMLARI) s[d].sort((a, b) => a.sira - b.sira || a.id - b.id);
    return s;
  }, [gorevler]);
  const secili = gorevler.find((g) => g.id === seciliId) || null;

  const hataMetni = (h: unknown) => {
    if (h instanceof ProjeHatasi) {
      if (h.kod === 'bagimlilik_bitmedi') {
        const ids = (h.ek.gorevler as number[]) || [];
        return t('gorevler.uyari.bagimlilik', { liste: ids.map((i) => adlar.get(i) || `#${i}`).join(', ') });
      }
      return t(`gorevler.hata.${h.kod}`, { defaultValue: t('gorevler.hata.genel') });
    }
    return t('gorevler.hata.genel');
  };

  const gorevDegistir = (g: Gorev) =>
    setVeri((v) => (v ? { ...v, gorevler: v.gorevler.map((x) => (x.id === g.id ? g : x)) } : v));

  /** Kartı `durum` sütununda `indeks` konumuna taşır (sunucuya toplu sıra). */
  const tasi = async (id: number, durum: GorevDurumu, indeks?: number) => {
    const g = gorevler.find((x) => x.id === id);
    if (!g || !veri) return;
    setUyari(null);
    if (durum === 'tamam' && g.durum !== 'tamam' && g.bekleyen_bagimliliklar.length) {
      setUyari(
        t('gorevler.uyari.bagimlilik', {
          liste: g.bekleyen_bagimliliklar.map((i) => adlar.get(i) || `#${i}`).join(', '),
        }),
      );
      return;
    }
    const yeniSutunlar: Record<GorevDurumu, Gorev[]> = {
      yapilacak: [...sutunlar.yapilacak],
      suruyor: [...sutunlar.suruyor],
      incelemede: [...sutunlar.incelemede],
      tamam: [...sutunlar.tamam],
    };
    yeniSutunlar[g.durum] = yeniSutunlar[g.durum].filter((x) => x.id !== id);
    const hedef = yeniSutunlar[durum];
    const yer = indeks === undefined || indeks < 0 || indeks > hedef.length ? hedef.length : indeks;
    hedef.splice(yer, 0, { ...g, durum });
    const etkilenen = new Set<GorevDurumu>([g.durum, durum]);
    const yuk = [...etkilenen].flatMap((d) => yeniSutunlar[d].map((x, i) => ({ id: x.id, durum: d, sira: i })));
    const onceki = veri;
    // İyimser güncelleme; hata olursa geri al.
    const eslem = new Map(yuk.map((y) => [y.id, y]));
    setVeri({
      ...veri,
      gorevler: veri.gorevler.map((x) => (eslem.has(x.id) ? { ...x, durum: eslem.get(x.id)!.durum, sira: eslem.get(x.id)!.sira } : x)),
    });
    try {
      const yanit = await siraKaydet(projeId, yuk);
      setVeri((v) => (v ? { ...v, gorevler: yanit.gorevler } : v));
      if (g.durum !== durum) toast.success(t('gorevler.tasindi', { durum: t(`gorevler.durum.${durum}`) }));
    } catch (h) {
      setVeri(onceki);
      setUyari(hataMetni(h));
    }
  };

  const hizliEkle = async () => {
    if (!yeni.baslik.trim()) {
      toast.error(t('gorevler.hata.baslik_gerekli'));
      return;
    }
    setMesgul(true);
    try {
      const g = await gorevEkle(projeId, { baslik: yeni.baslik.trim(), durum: yeni.durum, musteriye_gorunur: yeni.gorunur });
      setVeri((v) => (v ? { ...v, gorevler: [...v.gorevler, g] } : v));
      setYeni((y) => ({ ...y, baslik: '' }));
    } catch (h) {
      toast.error(hataMetni(h));
    } finally {
      setMesgul(false);
    }
  };

  const donustur = async (fb: GeriBildirim) => {
    try {
      const { gorev } = await goreveDonustur(fb.id, true);
      setVeri((v) =>
        v ? { ...v, gorevler: [...v.gorevler, gorev], geri_bildirimler: v.geri_bildirimler.filter((x) => x.id !== fb.id) } : v,
      );
      toast.success(t('gorevler.donusturuldu'));
    } catch (h) {
      toast.error(hataMetni(h));
    }
  };

  // --- Sürükle-bırak ---------------------------------------------------------
  const suruklemeBasla = (e: DragEvent, id: number) => {
    setSurukle(id);
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', String(id));
  };
  const suruklenenId = (e: DragEvent) => Number(e.dataTransfer.getData('text/plain')) || surukle;
  const sutunaBirak = (e: DragEvent, durum: GorevDurumu) => {
    e.preventDefault();
    const id = suruklenenId(e);
    setSurukle(null);
    setHedefSutun(null);
    if (id) void tasi(id, durum);
  };
  const kartaBirak = (e: DragEvent, hedef: Gorev) => {
    e.preventDefault();
    e.stopPropagation();
    const id = suruklenenId(e);
    setSurukle(null);
    setHedefSutun(null);
    if (!id || id === hedef.id) return;
    const liste = sutunlar[hedef.durum].filter((x) => x.id !== id);
    void tasi(id, hedef.durum, liste.findIndex((x) => x.id === hedef.id));
  };

  if (yukleniyor) {
    return (
      <div className="flex items-center justify-center py-10 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" />
      </div>
    );
  }
  if (!veri) return null;

  return (
    <section className="min-w-0 space-y-4" data-testid="gorev-panosu" aria-labelledby="gorev-panosu-baslik">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 id="gorev-panosu-baslik" className="text-lg font-semibold">
            {t('gorevler.baslik')}
            {projeBasligi ? <span className="text-muted-foreground"> · {projeBasligi}</span> : null}
          </h3>
          <p className="mt-1 text-xs text-muted-foreground">{t('gorevler.aciklama')}</p>
        </div>
        <div className="flex flex-wrap items-center gap-1">
          <Button
            size="sm"
            variant="ghost"
            aria-pressed={gorunum === 'kanban'}
            onClick={() => setGorunum('kanban')}
            className={gorunum === 'kanban' ? 'text-purple-300' : ''}
            data-testid="gorunum-kanban"
          >
            <LayoutGrid className="mr-1 h-4 w-4" /> {t('gorevler.kanban')}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            aria-pressed={gorunum === 'liste'}
            onClick={() => setGorunum('liste')}
            className={gorunum === 'liste' ? 'text-purple-300' : ''}
            data-testid="gorunum-liste"
          >
            <List className="mr-1 h-4 w-4" /> {t('gorevler.liste')}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => void yukle()} aria-label={t('gorevler.yenile')}>
            <RefreshCw className="h-4 w-4" />
          </Button>
          {onKapat && (
            <Button size="sm" variant="ghost" onClick={onKapat} aria-label={t('gorevler.kapat')}>
              <X className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>

      <RevizyonKutusu
        projeId={projeId}
        revizyon={veri.revizyon}
        elleHak={veri.proje.aylik_revizyon_saati}
        musteriVar={!!veri.proje.client_email}
        onDegisti={(r, hak) => setVeri((v) => (v ? { ...v, revizyon: r, proje: { ...v.proje, aylik_revizyon_saati: hak } } : v))}
      />

      {/* Hızlı ekle */}
      <form
        className="cam-kart grid gap-2 rounded-2xl border border-white/10 bg-white/[0.03] p-3 sm:grid-cols-[1fr_auto_auto_auto] sm:items-center"
        onSubmit={(e) => {
          e.preventDefault();
          void hizliEkle();
        }}
      >
        <label className="sr-only" htmlFor={`gorev-yeni-${projeId}`}>
          {t('gorevler.alan.baslik')}
        </label>
        <Input
          id={`gorev-yeni-${projeId}`}
          value={yeni.baslik}
          onChange={(e) => setYeni((y) => ({ ...y, baslik: e.target.value }))}
          placeholder={t('gorevler.yeni')}
          maxLength={200}
          data-testid="gorev-yeni-baslik"
        />
        <select
          aria-label={t('gorevler.alan.durum')}
          value={yeni.durum}
          onChange={(e) => setYeni((y) => ({ ...y, durum: e.target.value as GorevDurumu }))}
          className={SECIM + ' sm:w-40'}
        >
          {GOREV_DURUMLARI.map((d) => (
            <option key={d} value={d}>
              {t(`gorevler.durum.${d}`)}
            </option>
          ))}
        </select>
        <label className="inline-flex items-center gap-2 text-xs">
          <input
            type="checkbox"
            checked={yeni.gorunur}
            onChange={(e) => setYeni((y) => ({ ...y, gorunur: e.target.checked }))}
            className="h-4 w-4 accent-purple-500"
            data-testid="gorev-yeni-gorunur"
          />
          {t('gorevler.alan.gorunur')}
        </label>
        <Button type="submit" size="sm" disabled={mesgul} className="gap-1" data-testid="gorev-yeni-ekle">
          {mesgul ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
          {t('gorevler.ekle')}
        </Button>
      </form>

      {uyari && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-xl border border-amber-400/40 bg-amber-500/10 p-3 text-sm text-amber-100"
          data-testid="gorev-uyari"
        >
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span className="min-w-0 flex-1">{uyari}</span>
          <button type="button" onClick={() => setUyari(null)} aria-label={t('gorevler.kapat')} className="shrink-0">
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      {gorunum === 'kanban' ? (
        <div className="-mx-1 max-w-full overflow-x-auto pb-2">
          <p className="sr-only">{t('gorevler.surukle')}</p>
          <div className="flex min-w-max gap-3 px-1">
            {veri.geri_bildirimler.length > 0 && (
              <div
                className="w-64 shrink-0 rounded-2xl border border-rose-400/30 bg-rose-500/[0.04] p-3"
                data-testid="sutun-geri-bildirim"
              >
                <h4 className="mb-2 flex items-center gap-2 text-sm font-semibold">
                  <Bug className="h-4 w-4 text-rose-300" aria-hidden="true" />
                  {t('gorevler.geriBildirimSutunu')}
                  <span className="text-xs text-muted-foreground">({veri.geri_bildirimler.length})</span>
                </h4>
                <ul className="space-y-2">
                  {veri.geri_bildirimler.map((fb) => (
                    <GeriBildirimKarti key={fb.id} fb={fb} onDonustur={() => void donustur(fb)} />
                  ))}
                </ul>
              </div>
            )}
            {GOREV_DURUMLARI.map((d) => (
              <div
                key={d}
                onDragOver={(e) => {
                  e.preventDefault();
                  if (hedefSutun !== d) setHedefSutun(d);
                }}
                onDragLeave={() => setHedefSutun((h) => (h === d ? null : h))}
                onDrop={(e) => sutunaBirak(e, d)}
                className={`w-64 shrink-0 rounded-2xl border bg-white/[0.02] p-3 transition-colors ${SUTUN_RENGI[d]} ${
                  hedefSutun === d ? 'bg-purple-500/10 ring-1 ring-purple-400/40' : ''
                }`}
                data-testid={`sutun-${d}`}
                aria-label={t(`gorevler.durum.${d}`)}
                role="group"
              >
                <h4 className="mb-2 text-sm font-semibold">
                  {t(`gorevler.durum.${d}`)} <span className="text-xs text-muted-foreground">({sutunlar[d].length})</span>
                </h4>
                <ul className="min-h-[3rem] space-y-2">
                  {sutunlar[d].map((g) => (
                    <li
                      key={g.id}
                      draggable
                      onDragStart={(e) => suruklemeBasla(e, g.id)}
                      onDragEnd={() => {
                        setSurukle(null);
                        setHedefSutun(null);
                      }}
                      onDragOver={(e) => e.preventDefault()}
                      onDrop={(e) => kartaBirak(e, g)}
                      className={`cam-kart rounded-xl border border-white/10 bg-white/[0.04] p-2.5 text-sm ${
                        surukle === g.id ? 'opacity-50' : ''
                      } ${seciliId === g.id ? 'ring-1 ring-purple-400/60' : ''}`}
                      data-testid={`gorev-karti-${g.id}`}
                    >
                      <div className="flex items-start gap-1.5">
                        <GripVertical className="mt-0.5 h-4 w-4 shrink-0 cursor-grab text-muted-foreground" aria-hidden="true" />
                        <button
                          type="button"
                          onClick={() => setSeciliId(seciliId === g.id ? null : g.id)}
                          className="min-w-0 flex-1 text-left font-medium hover:text-purple-200"
                          aria-expanded={seciliId === g.id}
                        >
                          <span className="break-words">{g.baslik}</span>
                        </button>
                        {/* Faz 3Z: bu görev için zaman sayacını başlat. */}
                        {g.durum !== 'tamam' && <GorevSayacDugmesi projeId={projeId} gorevId={g.id} baslik={g.baslik} />}
                      </div>
                      <GorevRozetleri g={g} adlar={adlar} dil={dil} />
                      <label className="mt-2 flex items-center gap-2 text-[11px] text-muted-foreground">
                        <span className="shrink-0">{t('gorevler.tasi')}</span>
                        <select
                          value={g.durum}
                          onChange={(e) => void tasi(g.id, e.target.value as GorevDurumu)}
                          aria-label={t('gorevler.tasiAria', { baslik: g.baslik })}
                          className={SECIM + ' h-7 text-xs'}
                          data-testid={`gorev-tasi-${g.id}`}
                        >
                          {GOREV_DURUMLARI.map((x) => (
                            <option key={x} value={x}>
                              {t(`gorevler.durum.${x}`)}
                            </option>
                          ))}
                        </select>
                      </label>
                    </li>
                  ))}
                  {sutunlar[d].length === 0 && <li className="py-2 text-center text-xs text-muted-foreground">{t('gorevler.bos')}</li>}
                </ul>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="max-w-full overflow-x-auto rounded-2xl border border-white/10" data-testid="gorev-listesi">
          <table className="w-full min-w-[640px] text-sm">
            <thead className="bg-white/[0.03] text-left text-xs text-muted-foreground">
              <tr>
                <th className="p-2 font-medium">{t('gorevler.alan.baslik')}</th>
                <th className="p-2 font-medium">{t('gorevler.alan.durum')}</th>
                <th className="p-2 font-medium">{t('gorevler.alan.oncelik')}</th>
                <th className="p-2 font-medium">{t('gorevler.alan.atanan')}</th>
                <th className="p-2 font-medium">{t('gorevler.alan.bitis')}</th>
                <th className="p-2 font-medium">{t('gorevler.alan.harcanan')}</th>
              </tr>
            </thead>
            <tbody>
              {GOREV_DURUMLARI.flatMap((d) => sutunlar[d]).map((g) => (
                <tr key={g.id} className="border-t border-white/5 align-top">
                  <td className="p-2">
                    <button type="button" className="text-left hover:text-purple-200" onClick={() => setSeciliId(g.id)}>
                      {g.ust_gorev_id ? <span className="text-muted-foreground">↳ </span> : null}
                      {g.baslik}
                    </button>
                    <GorevRozetleri g={g} adlar={adlar} dil={dil} kucuk />
                  </td>
                  <td className="p-2">
                    <select
                      value={g.durum}
                      onChange={(e) => void tasi(g.id, e.target.value as GorevDurumu)}
                      aria-label={t('gorevler.tasiAria', { baslik: g.baslik })}
                      className={SECIM + ' h-8 text-xs'}
                    >
                      {GOREV_DURUMLARI.map((x) => (
                        <option key={x} value={x}>
                          {t(`gorevler.durum.${x}`)}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="p-2 text-xs">{t(`gorevler.oncelik.${g.oncelik}`)}</td>
                  <td className="p-2 text-xs">{g.atanan || t('gorevler.alan.atanmamis')}</td>
                  <td className="p-2 text-xs">{tarihGoster(g.bitis_tarihi, dil) || '—'}</td>
                  <td className="p-2 text-xs">
                    {saatGoster(g.harcanan_saat, dil)}
                    {g.tahmini_saat != null ? ` / ${saatGoster(g.tahmini_saat, dil)}` : ''}
                  </td>
                </tr>
              ))}
              {gorevler.length === 0 && (
                <tr>
                  <td colSpan={6} className="p-6 text-center text-muted-foreground">
                    {t('gorevler.hicGorev')}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {secili && (
        <GorevDetayi
          key={secili.id}
          g={secili}
          tumu={gorevler}
          veri={veri}
          onDegisti={gorevDegistir}
          onRevizyon={(r) => setVeri((v) => (v ? { ...v, revizyon: r } : v))}
          onSilindi={() => {
            setSeciliId(null);
            void yukle();
          }}
          onKapat={() => setSeciliId(null)}
          hataMetni={hataMetni}
        />
      )}
      <Suspense fallback={null}>
        <OzelAlanlarBolumu varlik="proje" kimlik={projeId} />
      </Suspense>
    </section>
  );
}

function GorevRozetleri({ g, adlar, dil, kucuk }: { g: Gorev; adlar: Map<number, string>; dil: string; kucuk?: boolean }) {
  const { t } = useTranslation();
  const tamamKontrol = g.kontrol_listesi.filter((k) => k.tamam).length;
  return (
    <div className={`mt-1.5 flex flex-wrap gap-1 ${kucuk ? 'text-[10px]' : 'text-[10px]'}`}>
      <span className={`rounded-full px-1.5 py-0.5 ${ONCELIK_RENGI[g.oncelik] || ''}`}>{t(`gorevler.oncelik.${g.oncelik}`)}</span>
      <span
        className={`inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 ${
          g.musteriye_gorunur ? 'bg-emerald-500/15 text-emerald-200' : 'bg-white/5 text-muted-foreground'
        }`}
      >
        {g.musteriye_gorunur ? <Eye className="h-3 w-3" aria-hidden="true" /> : <EyeOff className="h-3 w-3" aria-hidden="true" />}
        {g.musteriye_gorunur ? t('gorevler.rozet.gorunur') : t('gorevler.rozet.gizli')}
      </span>
      {g.kilometre_tasi && (
        <span className="inline-flex items-center gap-1 rounded-full bg-purple-500/20 px-1.5 py-0.5 text-purple-200">
          <Flag className="h-3 w-3" aria-hidden="true" />
          {t('gorevler.rozet.kilometre')}
        </span>
      )}
      {g.kontrol_listesi.length > 0 && (
        <span className="rounded-full bg-white/5 px-1.5 py-0.5 text-muted-foreground">
          ☑ {t('gorevler.kontrol.ilerleme', { tamam: tamamKontrol, toplam: g.kontrol_listesi.length })}
        </span>
      )}
      {g.bitis_tarihi && <span className="rounded-full bg-white/5 px-1.5 py-0.5 text-muted-foreground">{tarihGoster(g.bitis_tarihi, dil)}</span>}
      {g.etiketler.map((e) => (
        <span key={e} className="rounded-full bg-sky-500/10 px-1.5 py-0.5 text-sky-200">
          #{e}
        </span>
      ))}
      {g.ust_gorev_id && (
        <span className="rounded-full bg-white/5 px-1.5 py-0.5 text-muted-foreground">
          {t('gorevler.rozet.altGorev', { baslik: adlar.get(g.ust_gorev_id) || `#${g.ust_gorev_id}` })}
        </span>
      )}
      {g.bekleyen_bagimliliklar.length > 0 && (
        <span className="rounded-full bg-amber-500/15 px-1.5 py-0.5 text-amber-200">
          {t('gorevler.rozet.bekliyor', { sayi: g.bekleyen_bagimliliklar.length })}
        </span>
      )}
    </div>
  );
}

function GeriBildirimKarti({ fb, onDonustur }: { fb: GeriBildirim; onDonustur: () => void }) {
  const { t } = useTranslation();
  const [gorsel, setGorsel] = useState<string | null>(null);
  const gorselAc = async () => {
    if (gorsel || !fb.ekler[0]) return;
    try {
      setGorsel(await ekAdresi(fb.ekler[0].adres));
    } catch {
      toast.error(t('gorevler.hata.genel'));
    }
  };
  useEffect(() => () => {
    if (gorsel) URL.revokeObjectURL(gorsel);
  }, [gorsel]);
  return (
    <li className="rounded-xl border border-white/10 bg-white/[0.04] p-2.5 text-sm" data-testid={`gb-karti-${fb.id}`}>
      <p className="break-words font-medium">{fb.baslik}</p>
      <p className="mt-1 break-all text-[11px] text-muted-foreground">
        {t(`geriBildirim.tur.${fb.tur}`)} · {fb.musteri_eposta}
      </p>
      {fb.ekler.length > 0 && (
        <div className="mt-1.5">
          {gorsel ? (
            <img src={gorsel} alt={fb.baslik} className="max-h-40 w-full rounded-md object-contain" />
          ) : (
            <button type="button" onClick={() => void gorselAc()} className="text-[11px] text-purple-300 hover:text-pink-300">
              {t('geriBildirim.yonetici.ekGoster')}
            </button>
          )}
        </div>
      )}
      <Button size="sm" variant="outline" className="mt-2 h-7 w-full !bg-transparent text-xs" onClick={onDonustur} data-testid={`gb-donustur-${fb.id}`}>
        {t('gorevler.donustur')}
      </Button>
    </li>
  );
}

function RevizyonKutusu({
  projeId,
  revizyon,
  elleHak,
  musteriVar,
  onDegisti,
}: {
  projeId: number;
  revizyon: RevizyonSayaci | null;
  elleHak: number | null;
  musteriVar: boolean;
  onDegisti: (r: RevizyonSayaci | null, hak: number | null) => void;
}) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [hak, setHak] = useState(elleHak != null ? String(elleHak) : '');
  const [mesgul, setMesgul] = useState(false);
  if (!musteriVar) return null;
  const kaydet = async () => {
    setMesgul(true);
    try {
      const deger = hak.trim() === '' ? null : Number(hak.replace(',', '.'));
      const y = await revizyonHakkiAyarla(projeId, deger);
      onDegisti(y.revizyon, y.aylik_revizyon_saati);
      toast.success(t('gorevler.kaydedildi'));
    } catch (h) {
      toast.error(h instanceof ProjeHatasi ? t(`gorevler.hata.${h.kod}`, { defaultValue: t('gorevler.hata.genel') }) : t('gorevler.hata.genel'));
    } finally {
      setMesgul(false);
    }
  };
  return (
    <div className="cam-kart flex flex-wrap items-center gap-3 rounded-2xl border border-white/10 bg-white/[0.03] p-3 text-sm" data-testid="yonetici-revizyon">
      {revizyon && <RevizyonMetni r={revizyon} dil={dil} />}
      {revizyon?.kaynak !== 'paket' && (
        <form
          className="flex items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void kaydet();
          }}
        >
          <label htmlFor={`rev-hak-${projeId}`} className="text-xs text-muted-foreground">
            {t('gorevler.revizyon.elleHak')}
          </label>
          <Input
            id={`rev-hak-${projeId}`}
            value={hak}
            onChange={(e) => setHak(e.target.value)}
            inputMode="decimal"
            className="h-8 w-20"
          />
          <Button size="sm" type="submit" variant="outline" className="h-8 !bg-transparent" disabled={mesgul}>
            {t('gorevler.kaydet')}
          </Button>
        </form>
      )}
    </div>
  );
}

export function RevizyonMetni({ r, dil }: { r: RevizyonSayaci; dil: string }) {
  const { t } = useTranslation();
  const kullanilan = saatGoster(r.kullanilan, dil);
  return (
    <div className="min-w-0">
      <p className={`font-medium ${r.asildi ? 'text-amber-200' : ''}`}>
        {r.hak != null
          ? t('gorevler.revizyon.gosterge', { kullanilan, hak: saatGoster(r.hak, dil) })
          : t('gorevler.revizyon.hakYok', { kullanilan })}
      </p>
      <p className="text-[11px] text-muted-foreground">
        {[
          r.kaynak === 'paket' ? t('gorevler.revizyon.kaynakPaket') : r.kaynak === 'proje' ? t('gorevler.revizyon.kaynakProje') : null,
          r.asildi
            ? t('gorevler.revizyon.asildi', { saat: saatGoster(r.asim, dil) })
            : r.kalan != null
              ? t('gorevler.revizyon.kalan', { saat: saatGoster(r.kalan, dil) })
              : null,
          r.istek_sayisi ? t('gorevler.revizyon.istek', { sayi: r.istek_sayisi }) : null,
        ]
          .filter(Boolean)
          .join(' · ')}
      </p>
    </div>
  );
}

function GorevDetayi({
  g,
  tumu,
  veri,
  onDegisti,
  onRevizyon,
  onSilindi,
  onKapat,
  hataMetni,
}: {
  g: Gorev;
  tumu: Gorev[];
  veri: ProjeGorevleriYaniti;
  onDegisti: (g: Gorev) => void;
  onRevizyon: (r: RevizyonSayaci | null) => void;
  onSilindi: () => void;
  onKapat: () => void;
  hataMetni: (h: unknown) => string;
}) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [form, setForm] = useState({
    baslik: g.baslik,
    aciklama: g.aciklama || '',
    oncelik: g.oncelik,
    atanan: g.atanan || '',
    bitis_tarihi: g.bitis_tarihi || '',
    tahmini_saat: g.tahmini_saat != null ? String(g.tahmini_saat) : '',
    etiketler: g.etiketler.join(', '),
    musteriye_gorunur: g.musteriye_gorunur,
    kilometre_tasi: g.kilometre_tasi,
    ust_gorev_id: g.ust_gorev_id ? String(g.ust_gorev_id) : '',
  });
  const [mesgul, setMesgul] = useState(false);
  const [yeniMadde, setYeniMadde] = useState('');
  const [bagli, setBagli] = useState('');
  const [girisler, setGirisler] = useState<SaatGirisi[]>([]);
  const [saatForm, setSaatForm] = useState({ saat: '', tarih: '', not: '', kredi: false });
  const [oneri, setOneri] = useState<{ girisId: number; saat: number } | null>(null);
  const [bakiye, setBakiye] = useState<number | null>(null);
  const ilk = useRef(true);

  useEffect(() => {
    if (!ilk.current) return;
    ilk.current = false;
    saatleriGetir(g.id).then(setGirisler).catch(() => setGirisler([]));
  }, [g.id]);

  const guncelle = async (girdi: Parameters<typeof gorevGuncelle>[1]) => {
    setMesgul(true);
    try {
      onDegisti(await gorevGuncelle(g.id, girdi));
      toast.success(t('gorevler.kaydedildi'));
    } catch (h) {
      toast.error(hataMetni(h));
    } finally {
      setMesgul(false);
    }
  };

  const kaydet = () =>
    guncelle({
      baslik: form.baslik,
      aciklama: form.aciklama || null,
      oncelik: form.oncelik,
      atanan: form.atanan || null,
      bitis_tarihi: form.bitis_tarihi || null,
      tahmini_saat: form.tahmini_saat.trim() ? Number(form.tahmini_saat.replace(',', '.')) : null,
      etiketler: form.etiketler.split(',').map((x) => x.trim()).filter(Boolean),
      musteriye_gorunur: form.musteriye_gorunur,
      kilometre_tasi: form.kilometre_tasi,
      ust_gorev_id: form.ust_gorev_id ? Number(form.ust_gorev_id) : null,
    });

  const islem = async (fn: () => Promise<Gorev>) => {
    try {
      onDegisti(await fn());
    } catch (h) {
      toast.error(hataMetni(h));
    }
  };

  const saatGonder = async () => {
    const saat = Number(saatForm.saat.replace(',', '.'));
    if (!saat) {
      toast.error(t('gorevler.hata.saat_gecersiz'));
      return;
    }
    try {
      const y = await saatGir(g.id, {
        saat,
        tarih: saatForm.tarih || undefined,
        aciklama: saatForm.not || undefined,
        krediden_dus: saatForm.kredi,
      });
      onDegisti(y.gorev);
      onRevizyon(y.revizyon);
      setBakiye(y.kredi_bakiye);
      if (y.giris) setGirisler((l) => [y.giris!, ...l]);
      setSaatForm({ saat: '', tarih: '', not: '', kredi: false });
      if (y.giris && y.revizyon?.asildi && !y.giris.kredi_saat && veri.kredi_modulu) {
        setOneri({ girisId: y.giris.id, saat: Math.min(y.revizyon.asim, y.giris.saat) });
      } else {
        setOneri(null);
      }
    } catch (h) {
      toast.error(hataMetni(h));
    }
  };

  const kredidenDus = async (girisId: number, saat?: number) => {
    try {
      const y = await saatiKredidenDus(girisId, saat);
      onRevizyon(y.revizyon);
      setBakiye(y.kredi_bakiye);
      if (y.giris) setGirisler((l) => l.map((x) => (x.id === y.giris!.id ? y.giris! : x)));
      setOneri(null);
    } catch (h) {
      toast.error(hataMetni(h));
    }
  };

  const sil = async () => {
    if (!window.confirm(t('gorevler.silOnay'))) return;
    try {
      await gorevSil(g.id);
      onSilindi();
    } catch (h) {
      toast.error(hataMetni(h));
    }
  };

  const adaylar = tumu.filter((x) => x.id !== g.id && !g.bagimliliklar.includes(x.id));
  const ad = (id: number) => tumu.find((x) => x.id === id)?.baslik || `#${id}`;

  return (
    <div className="cam-kart space-y-5 rounded-2xl border border-purple-500/30 bg-white/[0.03] p-4" data-testid="gorev-detay">
      <div className="flex items-start justify-between gap-2">
        <h4 className="min-w-0 break-words font-semibold">{g.baslik}</h4>
        <div className="flex shrink-0 gap-1">
          <Button size="sm" variant="ghost" onClick={() => void sil()} className="text-destructive" aria-label={t('gorevler.sil')}>
            <Trash2 className="h-4 w-4" />
          </Button>
          <Button size="sm" variant="ghost" onClick={onKapat} aria-label={t('gorevler.kapat')}>
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <form
        className="grid gap-3 sm:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          void kaydet();
        }}
      >
        <label className="grid gap-1 text-xs sm:col-span-2">
          {t('gorevler.alan.baslik')}
          <Input value={form.baslik} onChange={(e) => setForm({ ...form, baslik: e.target.value })} maxLength={200} />
        </label>
        <label className="grid gap-1 text-xs sm:col-span-2">
          {t('gorevler.alan.aciklama')}
          <textarea
            value={form.aciklama}
            onChange={(e) => setForm({ ...form, aciklama: e.target.value })}
            rows={3}
            maxLength={4000}
            className="rounded-md border border-white/10 bg-white/5 p-2 text-sm"
          />
        </label>
        <label className="grid gap-1 text-xs">
          {t('gorevler.alan.oncelik')}
          <select value={form.oncelik} onChange={(e) => setForm({ ...form, oncelik: e.target.value as Gorev['oncelik'] })} className={SECIM}>
            {ONCELIKLER.map((o) => (
              <option key={o} value={o}>
                {t(`gorevler.oncelik.${o}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="grid gap-1 text-xs">
          {t('gorevler.alan.atanan')}
          <select value={form.atanan} onChange={(e) => setForm({ ...form, atanan: e.target.value })} className={SECIM}>
            <option value="">{t('gorevler.alan.atanmamis')}</option>
            {veri.ekip.map((k) => (
              <option key={k.email} value={k.email}>
                {k.ad} ({k.email})
              </option>
            ))}
          </select>
        </label>
        <label className="grid gap-1 text-xs">
          {t('gorevler.alan.bitis')}
          <Input type="date" value={form.bitis_tarihi} onChange={(e) => setForm({ ...form, bitis_tarihi: e.target.value })} />
        </label>
        <label className="grid gap-1 text-xs">
          {t('gorevler.alan.tahmini')}
          <Input value={form.tahmini_saat} onChange={(e) => setForm({ ...form, tahmini_saat: e.target.value })} inputMode="decimal" />
        </label>
        <label className="grid gap-1 text-xs">
          {t('gorevler.alan.ustGorev')}
          <select value={form.ust_gorev_id} onChange={(e) => setForm({ ...form, ust_gorev_id: e.target.value })} className={SECIM}>
            <option value="">{t('gorevler.alan.ustYok')}</option>
            {tumu
              .filter((x) => x.id !== g.id)
              .map((x) => (
                <option key={x.id} value={x.id}>
                  {x.baslik}
                </option>
              ))}
          </select>
        </label>
        <label className="grid gap-1 text-xs">
          {t('gorevler.alan.etiketler')}
          <Input value={form.etiketler} onChange={(e) => setForm({ ...form, etiketler: e.target.value })} />
          <span className="text-[10px] text-muted-foreground">{t('gorevler.alan.etiketIpucu')}</span>
        </label>
        <div className="flex flex-wrap gap-4 text-xs sm:col-span-2">
          <label className="inline-flex items-center gap-2">
            <input
              type="checkbox"
              checked={form.musteriye_gorunur}
              onChange={(e) => setForm({ ...form, musteriye_gorunur: e.target.checked })}
              className="h-4 w-4 accent-purple-500"
            />
            {t('gorevler.alan.gorunur')}
          </label>
          <label className="inline-flex items-center gap-2">
            <input
              type="checkbox"
              checked={form.kilometre_tasi}
              onChange={(e) => setForm({ ...form, kilometre_tasi: e.target.checked })}
              className="h-4 w-4 accent-purple-500"
            />
            {t('gorevler.alan.kilometre')}
          </label>
        </div>
        <div className="sm:col-span-2">
          <Button type="submit" size="sm" disabled={mesgul}>
            {mesgul ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : null}
            {t('gorevler.kaydet')}
          </Button>
        </div>
      </form>

      {/* Kontrol listesi */}
      <div>
        <h5 className="mb-2 text-sm font-semibold">{t('gorevler.kontrol.baslik')}</h5>
        <ul className="space-y-1">
          {g.kontrol_listesi.map((k) => (
            <li key={k.id} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={k.tamam}
                onChange={(e) => void islem(() => kontrolGuncelle(k.id, { tamam: e.target.checked }))}
                className="h-4 w-4 accent-emerald-500"
                aria-label={k.metin}
              />
              <span className={`min-w-0 flex-1 break-words ${k.tamam ? 'text-muted-foreground line-through' : ''}`}>{k.metin}</span>
              <button type="button" onClick={() => void islem(() => kontrolSil(k.id))} aria-label={t('gorevler.sil')}>
                <X className="h-3.5 w-3.5 text-muted-foreground" />
              </button>
            </li>
          ))}
        </ul>
        <form
          className="mt-2 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (!yeniMadde.trim()) return;
            void islem(() => kontrolEkle(g.id, yeniMadde.trim())).then(() => setYeniMadde(''));
          }}
        >
          <Input value={yeniMadde} onChange={(e) => setYeniMadde(e.target.value)} placeholder={t('gorevler.kontrol.yeni')} className="h-8" maxLength={300} />
          <Button type="submit" size="sm" variant="outline" className="h-8 !bg-transparent">
            <Plus className="h-4 w-4" />
          </Button>
        </form>
      </div>

      {/* Bağımlılıklar */}
      <div>
        <h5 className="text-sm font-semibold">{t('gorevler.bagimlilik.baslik')}</h5>
        <p className="mb-2 text-[11px] text-muted-foreground">{t('gorevler.bagimlilik.aciklama')}</p>
        {g.bagimliliklar.length === 0 ? (
          <p className="text-xs text-muted-foreground">{t('gorevler.bagimlilik.yok')}</p>
        ) : (
          <ul className="flex flex-wrap gap-1.5">
            {g.bagimliliklar.map((b) => (
              <li
                key={b}
                className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs ${
                  g.bekleyen_bagimliliklar.includes(b) ? 'bg-amber-500/15 text-amber-200' : 'bg-emerald-500/15 text-emerald-200'
                }`}
              >
                {ad(b)}
                <button type="button" onClick={() => void islem(() => bagimlilikSil(g.id, b))} aria-label={t('gorevler.sil')}>
                  <X className="h-3 w-3" />
                </button>
              </li>
            ))}
          </ul>
        )}
        <div className="mt-2 flex gap-2">
          <select
            value={bagli}
            onChange={(e) => setBagli(e.target.value)}
            className={SECIM + ' h-8'}
            aria-label={t('gorevler.bagimlilik.sec')}
            data-testid="bagimlilik-sec"
          >
            <option value="">{t('gorevler.bagimlilik.sec')}</option>
            {adaylar.map((x) => (
              <option key={x.id} value={x.id}>
                {x.baslik}
              </option>
            ))}
          </select>
          <Button
            size="sm"
            variant="outline"
            className="h-8 shrink-0 !bg-transparent"
            disabled={!bagli}
            onClick={() => void islem(() => bagimlilikEkle(g.id, Number(bagli))).then(() => setBagli(''))}
            data-testid="bagimlilik-ekle"
          >
            {t('gorevler.bagimlilik.ekle')}
          </Button>
        </div>
      </div>

      {/* Saat girişleri */}
      <div>
        <h5 className="mb-2 text-sm font-semibold">
          {t('gorevler.saat.baslik')}{' '}
          <span className="text-xs font-normal text-muted-foreground">
            ({saatGoster(g.harcanan_saat, dil)}
            {g.tahmini_saat != null ? ` / ${saatGoster(g.tahmini_saat, dil)}` : ''})
          </span>
        </h5>
        <form
          className="grid gap-2 sm:grid-cols-[6rem_10rem_1fr_auto]"
          onSubmit={(e) => {
            e.preventDefault();
            void saatGonder();
          }}
        >
          <Input
            value={saatForm.saat}
            onChange={(e) => setSaatForm({ ...saatForm, saat: e.target.value })}
            placeholder={t('gorevler.saat.saat')}
            aria-label={t('gorevler.saat.saat')}
            inputMode="decimal"
            className="h-8"
            data-testid="saat-miktar"
          />
          <Input
            type="date"
            value={saatForm.tarih}
            onChange={(e) => setSaatForm({ ...saatForm, tarih: e.target.value })}
            aria-label={t('gorevler.saat.tarih')}
            className="h-8"
          />
          <Input
            value={saatForm.not}
            onChange={(e) => setSaatForm({ ...saatForm, not: e.target.value })}
            placeholder={t('gorevler.saat.not')}
            aria-label={t('gorevler.saat.not')}
            className="h-8"
            maxLength={300}
          />
          <Button type="submit" size="sm" className="h-8" data-testid="saat-gir">
            {t('gorevler.saat.gir')}
          </Button>
          <label className="inline-flex items-center gap-2 text-xs sm:col-span-4">
            <input
              type="checkbox"
              checked={saatForm.kredi}
              disabled={!veri.kredi_modulu}
              onChange={(e) => setSaatForm({ ...saatForm, kredi: e.target.checked })}
              className="h-4 w-4 accent-purple-500"
            />
            {t('gorevler.saat.krediden')}
            {!veri.kredi_modulu && <span className="text-muted-foreground">— {t('gorevler.saat.krediKapali')}</span>}
            {bakiye != null && <span className="text-muted-foreground">· {t('gorevler.saat.bakiye', { saat: saatGoster(bakiye, dil) })}</span>}
          </label>
        </form>
        {oneri && (
          <div role="status" className="mt-2 flex flex-wrap items-center gap-2 rounded-xl border border-amber-400/40 bg-amber-500/10 p-2 text-xs text-amber-100">
            <span className="min-w-0 flex-1">{t('gorevler.revizyon.krediOneri', { saat: saatGoster(oneri.saat, dil) })}</span>
            <Button size="sm" variant="outline" className="h-7 !bg-transparent text-xs" onClick={() => void kredidenDus(oneri.girisId, oneri.saat)}>
              {t('gorevler.revizyon.krediden')}
            </Button>
          </div>
        )}
        <ul className="mt-2 space-y-1 text-xs">
          {girisler.map((e) => (
            <li key={e.id} className="flex flex-wrap items-center gap-2 border-b border-white/5 py-1">
              <span className="font-medium">{saatGoster(e.saat, dil)} sa</span>
              <span className="text-muted-foreground">{tarihGoster(e.tarih, dil)}</span>
              {e.aciklama && <span className="min-w-0 flex-1 break-words">{e.aciklama}</span>}
              {e.kredi_saat ? (
                <span className="rounded-full bg-purple-500/15 px-1.5 py-0.5 text-purple-200">
                  {t('gorevler.saat.krediDusuldu')} ({saatGoster(e.kredi_saat, dil)})
                </span>
              ) : (
                <>
                  {veri.kredi_modulu && (
                    <button type="button" className="text-purple-300 hover:text-pink-300" onClick={() => void kredidenDus(e.id)}>
                      {t('gorevler.saat.sonradanDus')}
                    </button>
                  )}
                  <button
                    type="button"
                    aria-label={t('gorevler.sil')}
                    onClick={async () => {
                      try {
                        await saatSil(e.id);
                        setGirisler((l) => l.filter((x) => x.id !== e.id));
                        onDegisti({ ...g, harcanan_saat: Math.max(0, Math.round((g.harcanan_saat - e.saat) * 100) / 100) });
                      } catch (h) {
                        toast.error(hataMetni(h));
                      }
                    }}
                  >
                    <X className="h-3 w-3 text-muted-foreground" />
                  </button>
                </>
              )}
            </li>
          ))}
          {girisler.length === 0 && <li className="text-muted-foreground">{t('gorevler.saat.yok')}</li>}
        </ul>
      </div>
    </div>
  );
}
