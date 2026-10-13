import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ComponentType } from 'react';
import {
  Download,
  Eye,
  EyeOff,
  File as DosyaIkonu,
  FileArchive,
  FileImage,
  FileSpreadsheet,
  FileText,
  Folder,
  FolderOpen,
  Link2,
  Loader2,
  MailOpen,
  Share2,
  Trash2,
  UserRound,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { boyutBicimle, dosyaSurumleri, tarihBicimle, type Dosya, type Gorunurluk, type Klasor } from '@/lib/dosyalar';

import './dosyaAgaci.css';

/**
 * Faz 11D — Yönetici › Dosyalar › Ağaç görünümü (Panel v2, önizleme 4: turkuaz zihin haritası).
 *
 * Seçili müşterinin klasörleri ve dosyaları ışıyan dallarla: müşteri (kök) → klasörler → dosyalar.
 * Kapsayıcı genişliğine göre üç yerleşim: geniş alanda iki yanlı zihin haritası, orta genişlikte tek yanlı
 * yatay ağaç, dar alanda (telefon) dikey ağaç. Dallar düğümlerin gerçek konumlarından çiziliyor (ResizeObserver);
 * Arapçada yerleşim aynalanıyor. Sağdaki panel seçili dosyanın sürümünü, paylaşımını ve müşterinin dosyayı
 * açıp açmadığını gösteriyor; seçim yokken müşterinin dosya özeti.
 *
 * Veri listeyle aynı (GET /api/v1/dosyalar?client_email=); ek uç yalnız sürüm geçmişi için.
 * İndir / paylaş / sil üst bileşenin mevcut işlemleri.
 */

type Yerlesim = 'iki' | 'tek' | 'dikey';
type IkonTipi = ComponentType<{ className?: string; 'aria-hidden'?: boolean | 'true' | 'false' }>;

const GORUNEN_DOSYA = 6;

interface Props {
  musteri: string;
  musteriAd?: string | null;
  dosyalar: Dosya[];
  klasorler: Klasor[];
  onIndir: (d: Dosya) => void;
  onPaylas: (d: Dosya) => void;
  onSil: (d: Dosya) => void;
}

interface Grup {
  ad: string;
  gorunurluk: Gorunurluk;
  dosyalar: Dosya[];
}

interface Dal {
  d: string;
  vurgu: boolean;
  ince: boolean;
}

function dosyaIkonu(d: Dosya): IkonTipi {
  const u = (d.uzanti || '').toLowerCase();
  if (d.tur?.startsWith('image/')) return FileImage;
  if (['xls', 'xlsx', 'csv', 'ods'].includes(u)) return FileSpreadsheet;
  if (['zip', 'rar', '7z', 'gz', 'tar'].includes(u)) return FileArchive;
  if (['pdf', 'doc', 'docx', 'txt', 'odt', 'rtf', 'md'].includes(u)) return FileText;
  return DosyaIkonu;
}

/** İki dikdörtgen arasında dal: yatay yerleşimde yumuşak eğri, dikeyde dirsek. */
function dalYolu(a: DOMRect, b: DOMRect, k: DOMRect, dikey: boolean, rtl: boolean): string {
  const f = (n: number) => n.toFixed(1);
  if (dikey) {
    // Dirsek: üst düğümün başlangıç kenarına yakın bir noktadan aşağı, sonra alt düğümün başlangıç kenarına.
    const ic = Math.min(22, a.width / 2);
    const x1 = rtl ? a.right - k.left - ic : a.left - k.left + ic;
    const x2 = rtl ? b.right - k.left : b.left - k.left;
    const y1 = a.bottom - k.top;
    const y2 = b.top + b.height / 2 - k.top;
    const yon = x2 >= x1 ? 1 : -1;
    const r = Math.min(10, Math.max(0, y2 - y1) / 2, Math.abs(x2 - x1) / 2);
    return `M${f(x1)},${f(y1)} V${f(y2 - r)} Q${f(x1)},${f(y2)} ${f(x1 + yon * r)},${f(y2)} H${f(x2)}`;
  }
  const aOrta = a.left + a.width / 2;
  const bOrta = b.left + b.width / 2;
  const saga = bOrta >= aOrta;
  const x1 = (saga ? a.right : a.left) - k.left;
  const x2 = (saga ? b.left : b.right) - k.left;
  const y1 = a.top + a.height / 2 - k.top;
  const y2 = b.top + b.height / 2 - k.top;
  const orta = (x1 + x2) / 2;
  return `M${f(x1)},${f(y1)} C${f(orta)},${f(y1)} ${f(orta)},${f(y2)} ${f(x2)},${f(y2)}`;
}

export default function DosyaAgaci({ musteri, musteriAd, dosyalar, klasorler, onIndir, onPaylas, onSil }: Props) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;

  const gruplar: Grup[] = useMemo(() => {
    const harita = new Map<string, Dosya[]>();
    for (const d of dosyalar) {
      if (!harita.has(d.klasor)) harita.set(d.klasor, []);
      harita.get(d.klasor)!.push(d);
    }
    for (const k of klasorler) if (!harita.has(k.ad)) harita.set(k.ad, []);
    return [...harita.entries()]
      .sort(([a], [b]) => a.localeCompare(b, dil))
      .map(([ad, liste]) => ({
        ad,
        gorunurluk: klasorler.find((k) => k.ad === ad)?.gorunurluk ?? liste[0]?.gorunurluk ?? 'ekip',
        dosyalar: [...liste].sort((a, b) => (b.created_at || '').localeCompare(a.created_at || '')),
      }));
  }, [dosyalar, klasorler, dil]);

  const [secili, setSecili] = useState<number | null>(null);
  const [acik, setAcik] = useState<Set<string>>(() => new Set());
  const seciliDosya = secili == null ? null : dosyalar.find((d) => d.id === secili) ?? null;

  // Silinen / değişen müşteride seçim boşa düşmesin.
  useEffect(() => {
    if (secili != null && !dosyalar.some((d) => d.id === secili)) setSecili(null);
  }, [dosyalar, secili]);
  useEffect(() => {
    setSecili(null);
    setAcik(new Set());
  }, [musteri]);

  // Yerleşim: kapsayıcının genişliğinden (panel kabuğunun kenar çubuğu açık/kapalı fark etmez).
  const kapRef = useRef<HTMLDivElement>(null);
  const tuvalRef = useRef<HTMLDivElement>(null);
  const [yerlesim, setYerlesim] = useState<Yerlesim>('tek');
  useLayoutEffect(() => {
    const kap = kapRef.current;
    if (!kap) return;
    const ayarla = (w: number) => setYerlesim(w >= 1460 ? 'iki' : w >= 640 ? 'tek' : 'dikey');
    ayarla(kap.getBoundingClientRect().width);
    if (typeof ResizeObserver === 'undefined') return;
    const g = new ResizeObserver((e) => ayarla(e[0].contentRect.width));
    g.observe(kap);
    return () => g.disconnect();
  }, []);

  // İki yanlı haritada klasörleri satır sayısına göre dengeli böl (ilk klasör sağda).
  const [sag, sol] = useMemo(() => {
    const s: Grup[] = [];
    const l: Grup[] = [];
    let hs = 0;
    let hl = 0;
    for (const g of gruplar) {
      const satir = Math.max(1, Math.min(g.dosyalar.length, GORUNEN_DOSYA + 1));
      if (hs <= hl) {
        s.push(g);
        hs += satir;
      } else {
        l.push(g);
        hl += satir;
      }
    }
    return [s, l];
  }, [gruplar]);

  // Dallar
  const [dallar, setDallar] = useState<Dal[]>([]);
  const [boyut, setBoyut] = useState({ w: 0, h: 0 });
  const olc = useCallback(() => {
    const kap = tuvalRef.current;
    if (!kap) return;
    const k = kap.getBoundingClientRect();
    const kok = kap.querySelector<HTMLElement>('[data-dag-kok]');
    if (!kok) return;
    const kr = kok.getBoundingClientRect();
    const dikey = yerlesim === 'dikey';
    const rtl = getComputedStyle(kap).direction === 'rtl';
    const yeni: Dal[] = [];
    const seciliKlasor = seciliDosya?.klasor ?? null;
    kap.querySelectorAll<HTMLElement>('[data-dag-klasor]').forEach((el) => {
      const ad = el.dataset.dagKlasor || '';
      const r = el.getBoundingClientRect();
      yeni.push({ d: dalYolu(kr, r, k, dikey, rtl), vurgu: ad === seciliKlasor, ince: false });
      kap.querySelectorAll<HTMLElement>(`[data-dag-ust="${CSS.escape(ad)}"]`).forEach((c) => {
        yeni.push({
          d: dalYolu(r, c.getBoundingClientRect(), k, dikey, rtl),
          vurgu: secili != null && c.dataset.dagDosya === String(secili),
          ince: true,
        });
      });
    });
    setDallar(yeni);
    setBoyut({ w: Math.round(k.width), h: Math.round(k.height) });
  }, [yerlesim, secili, seciliDosya?.klasor]);

  useLayoutEffect(() => {
    olc();
    const kap = tuvalRef.current;
    if (!kap || typeof ResizeObserver === 'undefined') return;
    const g = new ResizeObserver(() => olc());
    g.observe(kap);
    return () => g.disconnect();
  }, [olc, gruplar, acik, dil]);

  useEffect(() => {
    const fonts = (document as Document & { fonts?: { ready?: Promise<unknown> } }).fonts;
    fonts?.ready?.then(() => olc()).catch(() => undefined);
  }, [olc]);

  // Panel haritanın altındaysa (dar alan) seçilen dosyanın ayrıntısı görünür alana gelsin.
  const panelRef = useRef<HTMLElement>(null);
  useEffect(() => {
    const panel = panelRef.current;
    const tuval = tuvalRef.current;
    if (secili == null || !panel || !tuval) return;
    if (panel.getBoundingClientRect().top <= tuval.getBoundingClientRect().top + 4) return; // yan yana
    const azalt = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    panel.scrollIntoView({ block: 'nearest', behavior: azalt ? 'auto' : 'smooth' });
  }, [secili]);

  const toplamBoyut = dosyalar.reduce((s, d) => s + (d.boyut || 0), 0);
  const musteriGorur = dosyalar.filter((d) => d.gorunurluk === 'musteri');
  const acilan = musteriGorur.filter((d) => d.musteri_acti_at).length;
  const paylasimda = dosyalar.filter((d) => (d.aktif_paylasim ?? 0) > 0).length;

  const grupCiz = (g: Grup, yon: 'sag' | 'sol') => {
    const acikMi = acik.has(g.ad);
    const gorunen = acikMi ? g.dosyalar : g.dosyalar.slice(0, GORUNEN_DOSYA);
    const kalan = g.dosyalar.length - gorunen.length;
    const KlasorIkon = g.dosyalar.length ? FolderOpen : Folder;
    return (
      <div key={g.ad} className={`dag-grup dag-grup-${yon}`} data-testid={`dag-grup-${g.ad}`}>
        <div
          className="dag-klasor"
          data-dag-klasor={g.ad}
          data-gorunurluk={g.gorunurluk}
          data-vurgu={seciliDosya?.klasor === g.ad ? 'true' : undefined}
        >
          <span className="dag-klasor-ikon">
            <KlasorIkon className="h-4 w-4" aria-hidden="true" />
          </span>
          <span className="dag-klasor-yazi">
            <span className="dag-klasor-ad" title={g.ad}>
              {g.ad}
            </span>
            <span className="dag-klasor-alt">
              <span className="dag-mono">{g.dosyalar.length}</span> {t('dosyalar.agac.dosyaSayisi', { count: g.dosyalar.length })}
            </span>
          </span>
          <span className={`dag-yetki dag-yetki-${g.gorunurluk}`} title={t(`dosyalar.gorunurluk.${g.gorunurluk}`)}>
            {g.gorunurluk === 'musteri' ? <Eye className="h-3 w-3" aria-hidden="true" /> : <EyeOff className="h-3 w-3" aria-hidden="true" />}
            <span className="sr-only">{t(`dosyalar.gorunurluk.${g.gorunurluk}`)}</span>
          </span>
        </div>
        <ul className="dag-dosyalar" aria-label={g.ad}>
          {g.dosyalar.length === 0 && (
            <li className="dag-bos" data-dag-ust={g.ad}>
              {t('dosyalar.agac.bosKlasor')}
            </li>
          )}
          {gorunen.map((d) => {
            const Ikon = dosyaIkonu(d);
            const secMi = secili === d.id;
            const okundu = !!d.musteri_acti_at;
            return (
              <li key={d.id}>
                <button
                  type="button"
                  className="dag-dosya"
                  data-dag-ust={g.ad}
                  data-dag-dosya={d.id}
                  data-testid={`dag-dosya-${d.id}`}
                  aria-pressed={secMi}
                  onClick={() => setSecili(secMi ? null : d.id)}
                  title={d.ad}
                >
                  <Ikon className="dag-dosya-ikon" aria-hidden="true" />
                  <span className="dag-dosya-ad">{d.ad}</span>
                  {d.surum > 1 && <span className="dag-rozet dag-mono">v{d.surum}</span>}
                  {(d.aktif_paylasim ?? 0) > 0 && (
                    <span className="dag-rozet dag-rozet-paylasim" title={t('dosyalar.agac.paylasimda', { count: d.aktif_paylasim })}>
                      <Link2 className="h-3 w-3" aria-hidden="true" />
                      <span className="sr-only">{t('dosyalar.agac.paylasimda', { count: d.aktif_paylasim })}</span>
                    </span>
                  )}
                  {d.gorunurluk === 'musteri' && (
                    <span
                      className={`dag-okundu ${okundu ? 'dag-okundu-evet' : ''}`}
                      title={okundu ? t('dosyalar.agac.musteriActi') : t('dosyalar.agac.musteriAcmadi')}
                    >
                      <span className="sr-only">{okundu ? t('dosyalar.agac.musteriActi') : t('dosyalar.agac.musteriAcmadi')}</span>
                    </span>
                  )}
                </button>
              </li>
            );
          })}
          {(kalan > 0 || (acikMi && g.dosyalar.length > GORUNEN_DOSYA)) && (
            <li>
              <button
                type="button"
                className="dag-daha"
                data-dag-ust={g.ad}
                aria-expanded={acikMi}
                onClick={() =>
                  setAcik((s) => {
                    const y = new Set(s);
                    if (y.has(g.ad)) y.delete(g.ad);
                    else y.add(g.ad);
                    return y;
                  })
                }
              >
                {acikMi ? t('dosyalar.agac.daralt') : t('dosyalar.agac.dahaFazla', { sayi: kalan })}
              </button>
            </li>
          )}
        </ul>
      </div>
    );
  };

  const kok = (
    <div className="dag-kok" data-dag-kok="" data-testid="dag-kok">
      <span className="dag-kok-ikon">
        <UserRound className="h-5 w-5" aria-hidden="true" />
      </span>
      <span className="dag-kok-ad" title={musteri}>
        {musteriAd || musteri}
      </span>
      {musteriAd && <span className="dag-kok-eposta">{musteri}</span>}
      <span className="dag-kok-alt">{t('dosyalar.agac.kokOzet', { klasor: gruplar.length, dosya: dosyalar.length })}</span>
      <span className="dag-kok-boyut dag-mono">{boyutBicimle(toplamBoyut, dil)}</span>
    </div>
  );

  return (
    <div className="dag-kap" ref={kapRef} data-testid="dosya-agaci" data-yerlesim={yerlesim}>
      <div className="dag">
        <div className="dag-ust">
          <p className="dag-ust-etiket">{t('dosyalar.agac.ust')}</p>
          <ul className="dag-lejant" aria-label={t('dosyalar.agac.lejant')}>
            <li>
              <span className="dag-okundu dag-okundu-evet" aria-hidden="true" /> {t('dosyalar.agac.musteriActi')}
            </li>
            <li>
              <span className="dag-okundu" aria-hidden="true" /> {t('dosyalar.agac.musteriAcmadi')}
            </li>
            <li>
              <Link2 className="h-3 w-3 text-[rgb(var(--dag-c))]" aria-hidden="true" /> {t('dosyalar.agac.paylasimdaKisa')}
            </li>
            <li>
              <EyeOff className="h-3 w-3 text-amber-300" aria-hidden="true" /> {t('dosyalar.gorunurluk.ekip')}
            </li>
          </ul>
        </div>

        <div className="dag-govde">
          <div className="dag-tuval-kap">
            {gruplar.length === 0 ? (
              <p className="dag-hic">{t('dosyalar.bos')}</p>
            ) : (
              <div className={`dag-tuval dag-tuval-${yerlesim}`} ref={tuvalRef}>
                <svg className="dag-dallar" width={boyut.w} height={boyut.h} aria-hidden="true" focusable="false">
                  {dallar.map((y, i) => (
                    <g key={i} className={`${y.ince ? 'dag-dal-ince' : 'dag-dal-kalin'} ${y.vurgu ? 'dag-dal-vurgu' : ''}`}>
                      <path d={y.d} className="dag-dal-isik" />
                      <path d={y.d} className="dag-dal" />
                    </g>
                  ))}
                </svg>
                {yerlesim === 'iki' ? (
                  <>
                    <div className="dag-yan dag-yan-sol">{sol.map((g) => grupCiz(g, 'sol'))}</div>
                    <div className="dag-kok-kol">{kok}</div>
                    <div className="dag-yan dag-yan-sag">{sag.map((g) => grupCiz(g, 'sag'))}</div>
                  </>
                ) : (
                  <>
                    <div className="dag-kok-kol">{kok}</div>
                    <div className="dag-yan dag-yan-sag">{gruplar.map((g) => grupCiz(g, 'sag'))}</div>
                  </>
                )}
              </div>
            )}
          </div>

          <aside className="dag-panel" ref={panelRef} aria-live="polite" data-testid="dag-panel">
            {seciliDosya ? (
              <DosyaPaneli d={seciliDosya} onIndir={onIndir} onPaylas={onPaylas} onSil={onSil} />
            ) : (
              <div className="dag-ozet">
                <p className="dag-ust-etiket">{t('dosyalar.agac.ozet')}</p>
                <dl className="dag-ozet-izgara">
                  <div>
                    <dt>{t('dosyalar.agac.toplamDosya')}</dt>
                    <dd className="dag-mono">{dosyalar.length}</dd>
                  </div>
                  <div>
                    <dt>{t('dosyalar.agac.toplamBoyut')}</dt>
                    <dd className="dag-mono">{boyutBicimle(toplamBoyut, dil)}</dd>
                  </div>
                  <div>
                    <dt>{t('dosyalar.agac.musteriActi')}</dt>
                    <dd className="dag-mono" data-testid="dag-ozet-acilan">
                      {acilan}/{musteriGorur.length}
                    </dd>
                  </div>
                  <div>
                    <dt>{t('dosyalar.agac.paylasimdaKisa')}</dt>
                    <dd className="dag-mono">{paylasimda}</dd>
                  </div>
                </dl>
                <div className="dag-cubuk" aria-hidden="true">
                  <span style={{ width: `${musteriGorur.length ? Math.round((acilan / musteriGorur.length) * 100) : 0}%` }} />
                </div>
                <p className="dag-ipucu">{t('dosyalar.agac.secIpucu')}</p>
              </div>
            )}
          </aside>
        </div>
      </div>
    </div>
  );
}

function DosyaPaneli({
  d,
  onIndir,
  onPaylas,
  onSil,
}: {
  d: Dosya;
  onIndir: (d: Dosya) => void;
  onPaylas: (d: Dosya) => void;
  onSil: (d: Dosya) => void;
}) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [surumler, setSurumler] = useState<Dosya[] | null>(null);
  const Ikon = dosyaIkonu(d);

  useEffect(() => {
    let iptal = false;
    setSurumler(null);
    dosyaSurumleri(d.id)
      .then((s) => {
        if (!iptal) setSurumler(s);
      })
      .catch(() => {
        if (!iptal) setSurumler([]);
      });
    return () => {
      iptal = true;
    };
  }, [d.id]);

  const okundu = d.musteri_acti_at;
  const sayi = d.musteri_acma_sayisi ?? 0;

  return (
    <div className="dag-detay" data-testid="dag-detay" data-dosya={d.id}>
      <div className="dag-detay-bas">
        <span className="dag-detay-ikon">
          <Ikon className="h-5 w-5" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <p className="dag-detay-ad">{d.ad}</p>
          <p className="dag-detay-alt">
            {d.klasor} · <span className="dag-mono">{boyutBicimle(d.boyut, dil)}</span> · {(d.uzanti || '').toUpperCase()}
          </p>
        </div>
      </div>

      <div className={`dag-durum ${d.gorunurluk !== 'musteri' ? 'dag-durum-ekip' : okundu ? 'dag-durum-evet' : 'dag-durum-hayir'}`} data-testid="dag-musteri-durum">
        <MailOpen className="h-4 w-4 shrink-0" aria-hidden="true" />
        <span>
          {d.gorunurluk !== 'musteri'
            ? t('dosyalar.agac.musteriGoremez')
            : okundu
              ? t('dosyalar.agac.actiTarih', { tarih: tarihBicimle(okundu, dil, true), count: sayi })
              : t('dosyalar.agac.henuzAcmadi')}
        </span>
      </div>

      <dl className="dag-bilgi">
        <div>
          <dt>{t('dosyalar.agac.yukleyen')}</dt>
          <dd>{d.yukleyen_rol === 'client' ? t('dosyalar.agac.yukleyenMusteri') : t('dosyalar.agac.yukleyenAjans')}</dd>
        </div>
        <div>
          <dt>{t('dosyalar.agac.tarih')}</dt>
          <dd>{tarihBicimle(d.created_at, dil, true)}</dd>
        </div>
        <div>
          <dt>{t('dosyalar.gorunurluk.baslik')}</dt>
          <dd>{t(`dosyalar.gorunurluk.${d.gorunurluk ?? 'ekip'}`)}</dd>
        </div>
        <div>
          <dt>{t('dosyalar.agac.paylasimKisa')}</dt>
          <dd>{(d.aktif_paylasim ?? 0) > 0 ? t('dosyalar.agac.paylasimda', { count: d.aktif_paylasim }) : t('dosyalar.agac.paylasimYok')}</dd>
        </div>
      </dl>

      <p className="dag-ust-etiket">{t('dosyalar.agac.surumler')}</p>
      {surumler === null ? (
        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" aria-label={t('dosyalar.agac.yukleniyor')} />
      ) : (
        <ol className="dag-surumler" data-testid="dag-surumler">
          {(surumler.length ? surumler : [d]).map((s) => (
            <li key={s.id} data-guncel={s.id === d.id ? 'true' : undefined}>
              <span className="dag-rozet dag-mono">v{s.surum}</span>
              <span className="dag-surum-tarih">{tarihBicimle(s.created_at, dil)}</span>
              {d.gorunurluk === 'musteri' && (
                <span className={`dag-okundu ${s.musteri_acti_at ? 'dag-okundu-evet' : ''}`} title={s.musteri_acti_at ? t('dosyalar.agac.musteriActi') : t('dosyalar.agac.musteriAcmadi')}>
                  <span className="sr-only">{s.musteri_acti_at ? t('dosyalar.agac.musteriActi') : t('dosyalar.agac.musteriAcmadi')}</span>
                </span>
              )}
            </li>
          ))}
        </ol>
      )}

      <div className="dag-dugmeler">
        <button type="button" className="dag-dugme dag-dugme-ana" onClick={() => onIndir(d)} data-testid="dag-indir">
          <Download className="h-4 w-4" aria-hidden="true" />
          {t('dosyalar.indir')}
        </button>
        <button type="button" className="dag-dugme" onClick={() => onPaylas(d)} data-testid="dag-paylas">
          <Share2 className="h-4 w-4" aria-hidden="true" />
          {t('dosyalar.agac.paylasDugme')}
        </button>
        <button type="button" className="dag-dugme dag-dugme-sil" onClick={() => onSil(d)} aria-label={t('dosyalar.yonetim.sil')} title={t('dosyalar.yonetim.sil')}>
          <Trash2 className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}
