import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ComponentType, type CSSProperties } from 'react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import {
  Bell,
  Filter,
  History,
  Hourglass,
  Layers,
  LifeBuoy,
  ListChecks,
  Mail,
  MessageSquare,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  ShieldCheck,
  Tag,
  UserCheck,
  Users,
  Webhook,
  Zap,
} from 'lucide-react';

import { Kivilcim } from '@/components/panel/grafikler';
import { alanAdi, anahtarAdi, tarihYaz, type AkisOzeti, type Eylem, type Kural, type OtoMeta, type OtomasyonApi } from '@/lib/otomasyon';
import './akisGorunumu.css';

/**
 * Faz 11C — Otomasyon › Kurallar › "Akış" görünümü (Panel v2, önizleme 3).
 *
 * Kural yapısı doğrusal: tetikleyici → (varsa) koşul grubu → en çok 5 eylem ("bekle" dahil). Dallanma
 * olmadığı için akış da doğrusal çiziliyor (önizlemedeki paralel dallar modelde yok — uydurulmadı).
 * Düğüme tıklamak mevcut kural düzenleyiciyi açar; sürükle-bırak düzenleme yok (plan: ikinci adım).
 * Sağ sütundaki sayılar `GET .../akis-ozeti` (son 30 gün, `otomasyon_calismalari`) — veri gelmezse kart yok.
 *
 * Bağlantılar: düğümlerin gerçek konumlarından (getBoundingClientRect) hesaplanan kübik eğriler; RTL'de
 * ölçü zaten aynalı geldiği için ayrı hesap yok. Yerleşim kapsayıcı sorgularıyla (panel kabuğunun içi dar
 * ya da geniş olabilir; ekran genişliği yanıltıcı).
 */

type DugumTuru = 'tetik' | 'kosul' | Eylem['tur'];

interface Dugum {
  anahtar: string;
  tur: DugumTuru;
  baslik: string;
  satirlar: string[];
  not?: string;
  renk: string;
  Ikon: ComponentType<{ className?: string; 'aria-hidden'?: boolean | 'true' }>;
}

const RENK: Record<string, string> = {
  tetik: '#38d1ff',
  kosul: '#ffc542',
  eposta: '#2ef596',
  bildirim: '#38d1ff',
  gorev: '#ff4fd8',
  crm_asama: '#b266ff',
  crm_etiket: '#b266ff',
  crm_sahip: '#b266ff',
  crm_aktivite: '#b266ff',
  destek: '#ff7a2f',
  webhook: '#60a5fa',
  bekle: '#c4b5fd',
};

const IKON: Record<string, Dugum['Ikon']> = {
  tetik: Play,
  kosul: Filter,
  eposta: Mail,
  bildirim: Bell,
  gorev: ListChecks,
  crm_asama: Users,
  crm_etiket: Tag,
  crm_sahip: UserCheck,
  crm_aktivite: MessageSquare,
  destek: LifeBuoy,
  webhook: Webhook,
  bekle: Hourglass,
};

const GORUNUM_KURAL = 'mk_oto_akis_kural';

function yerelOku(anahtar: string): string | null {
  try {
    return window.localStorage.getItem(anahtar);
  } catch {
    return null;
  }
}

function yerelYaz(anahtar: string, deger: string) {
  try {
    window.localStorage.setItem(anahtar, deger);
  } catch {
    /* gizli pencere / kapalı depo: yalnız hatırlanmaz */
  }
}

const metin = (v: unknown): string => (typeof v === 'string' ? v.trim() : typeof v === 'number' ? String(v) : '');

function kisalt(s: string, n = 80): string {
  const tek = s.replace(/\s+/g, ' ').trim();
  return tek.length > n ? `${tek.slice(0, n - 1)}…` : tek;
}

/** Eylemin kartta görünen kısa özeti — kullanıcının girdiği metinler + seçimlerin çevirisi. */
function eylemSatirlari(t: TFunction, e: Eylem, meta: OtoMeta | null, dil: string): { satirlar: string[]; not?: string } {
  const s: string[] = [];
  let not: string | undefined;
  switch (e.tur) {
    case 'eposta': {
      if (metin(e.konu)) s.push(kisalt(metin(e.konu)));
      const alici = metin(e.alici);
      if (alici) s.push(`${t('otomasyon.eposta.alici')}: ${alici === 'sabit' && metin(e.adres) ? metin(e.adres) : t(`otomasyon.eposta.alici_${alici}`, { defaultValue: alici })}`);
      if (e.nitelik === 'pazarlama') not = t('otomasyon.akis.pazarlamaNotu');
      break;
    }
    case 'bildirim': {
      if (metin(e.baslik)) s.push(kisalt(metin(e.baslik)));
      const alici = metin(e.alici);
      if (alici) s.push(`${t('otomasyon.bildirim.alici')}: ${t(`otomasyon.bildirim.alici_${alici}`, { defaultValue: alici })}`);
      break;
    }
    case 'gorev': {
      if (metin(e.baslik)) s.push(kisalt(metin(e.baslik)));
      const gun = typeof e.son_tarih_gun === 'number' ? e.son_tarih_gun : null;
      const parca = [e.oncelik ? t(`otomasyon.oncelik.${metin(e.oncelik)}`, { defaultValue: metin(e.oncelik) }) : '', gun ? t('otomasyon.akis.gunSonra', { sayi: gun }) : '']
        .filter(Boolean)
        .join(' · ');
      if (parca) s.push(parca);
      break;
    }
    case 'crm_asama': {
      const a = meta?.crm_asamalari?.find((x) => x.anahtar === e.asama);
      const ad = a?.ceviriler?.[dil]?.ad || a?.ad || metin(e.asama);
      if (ad) s.push(`→ ${ad}`);
      break;
    }
    case 'crm_etiket':
      if (metin(e.etiket)) s.push(`${t(`otomasyon.crm.${e.islem === 'kaldir' ? 'kaldir' : 'ekle'}`)}: ${metin(e.etiket)}`);
      break;
    case 'crm_sahip':
      if (metin(e.sorumlu)) s.push(metin(e.sorumlu));
      break;
    case 'crm_aktivite':
      s.push(t(`otomasyon.crm.aktivite_${metin(e.aktivite_tur) || 'not'}`, { defaultValue: metin(e.aktivite_tur) }));
      if (metin(e.metin)) s.push(kisalt(metin(e.metin), 60));
      break;
    case 'destek':
      if (metin(e.oncelik)) s.push(`${t('otomasyon.destek.oncelik')}: ${t(`otomasyon.oncelik.${metin(e.oncelik)}`, { defaultValue: metin(e.oncelik) })}`);
      if (metin(e.etiket)) s.push(`${t('otomasyon.destek.etiket')}: ${metin(e.etiket)}`);
      break;
    case 'webhook': {
      const uc = meta?.webhook_uclari?.find((u) => u.id === e.uc_id);
      if (uc) s.push(kisalt(uc.url, 48));
      if (metin(e.etiket)) s.push(`otomasyon.${metin(e.etiket)}`);
      break;
    }
    case 'bekle': {
      const miktar = typeof e.miktar === 'number' ? e.miktar : Number(e.miktar) || 0;
      s.push(`${miktar} ${t(`otomasyon.bekle.${metin(e.birim) || 'saat'}`)}`);
      break;
    }
    default:
      break;
  }
  return { satirlar: s, not };
}

function dugumleriKur(t: TFunction, k: Kural, meta: OtoMeta | null, dil: string): Dugum[] {
  const olay = meta?.olaylar.find((o) => o.anahtar === k.tetik);
  const liste: Dugum[] = [
    {
      anahtar: 'tetik',
      tur: 'tetik',
      baslik: t('otomasyon.akis.tetikleyici'),
      satirlar: [t(`otomasyon.olay.${anahtarAdi(k.tetik)}`), t(`otomasyon.olayAciklama.${anahtarAdi(k.tetik)}`, { defaultValue: '' })].filter(Boolean),
      renk: RENK.tetik,
      Ikon: IKON.tetik,
    },
  ];
  const kosullar = k.kosullar?.kosullar ?? [];
  if (kosullar.length) {
    const degersiz = new Set(meta?.degersiz_islecler ?? ['bos', 'dolu', 'degisti']);
    const satirlar = kosullar.map((c) => {
      const a = olay?.sema.find((x) => x.yol === c.alan);
      const deger = degersiz.has(c.islec) || c.deger == null || c.deger === '' ? '' : ` "${kisalt(String(c.deger), 40)}"`;
      return `${alanAdi(t, a, c.alan)} ${t(`otomasyon.islec.${c.islec}`)}${deger}`;
    });
    liste.push({
      anahtar: 'kosul',
      tur: 'kosul',
      baslik: t('otomasyon.akis.kosul'),
      satirlar: kosullar.length > 1 ? [t(`otomasyon.baglac.${k.kosullar.baglac}`), ...satirlar] : satirlar,
      renk: RENK.kosul,
      Ikon: IKON.kosul,
    });
  }
  k.eylemler.forEach((e, i) => {
    const { satirlar, not } = eylemSatirlari(t, e, meta, dil);
    const ek = e.tur === 'bekle' && k.bekleme_sonrasi_denetim && kosullar.length ? t('otomasyon.akis.bekleSonraDenetim') : undefined;
    liste.push({
      anahtar: `eylem-${i}`,
      tur: e.tur,
      baslik: t(`otomasyon.eylem.${e.tur}`),
      satirlar,
      not: not || ek,
      renk: RENK[e.tur] || '#b266ff',
      Ikon: IKON[e.tur] || Zap,
    });
  });
  return liste;
}

interface Yol {
  d: string;
  renk: string;
}

interface Props {
  api: OtomasyonApi;
  meta: OtoMeta | null;
  liste: Kural[];
  yeniKapali: boolean;
  onDuzenle: (k: Kural, adim?: 'tetik' | 'kosullar' | 'eylemler') => void;
  onYeni: () => void;
  onGunluk: (kuralId: number) => void;
  onSablonlar?: () => void;
}

export default function AkisGorunumu({ api, meta, liste, yeniKapali, onDuzenle, onYeni, onGunluk, onSablonlar }: Props) {
  const { t, i18n } = useTranslation();
  const dil = (i18n.language || 'tr').split('-')[0];
  const [secili, setSecili] = useState<number | null>(() => {
    const kayit = Number(yerelOku(GORUNUM_KURAL));
    return Number.isFinite(kayit) && kayit > 0 ? kayit : null;
  });
  const kural = useMemo(() => liste.find((k) => k.id === secili) ?? liste[0] ?? null, [liste, secili]);
  const [ozet, setOzet] = useState<AkisOzeti | null>(null);
  const [ozetDurumu, setOzetDurumu] = useState<'yukleniyor' | 'hazir' | 'yok'>('yukleniyor');

  const sec = (k: Kural) => {
    setSecili(k.id);
    yerelYaz(GORUNUM_KURAL, String(k.id));
  };

  const kuralId = kural?.id ?? null;
  useEffect(() => {
    let iptal = false;
    setOzetDurumu('yukleniyor');
    api
      .akisOzeti(kuralId)
      .then((o) => {
        if (iptal) return;
        setOzet(o);
        setOzetDurumu('hazir');
      })
      .catch(() => {
        if (iptal) return;
        setOzet(null);
        setOzetDurumu('yok');
      });
    return () => {
      iptal = true;
    };
  }, [api, kuralId]);

  const dugumler = useMemo(() => (kural ? dugumleriKur(t, kural, meta, dil) : []), [kural, meta, t, dil]);

  // Bağlantı eğrileri: düğümlerin gerçek konumlarından.
  const tuvalRef = useRef<HTMLDivElement>(null);
  const [yollar, setYollar] = useState<Yol[]>([]);
  const [boyut, setBoyut] = useState({ w: 0, h: 0 });
  const olc = useCallback(() => {
    const kap = tuvalRef.current;
    if (!kap) return;
    const kr = kap.getBoundingClientRect();
    const ogeler = Array.from(kap.querySelectorAll<HTMLElement>('[data-oak-dugum]'));
    const yeni: Yol[] = [];
    for (let i = 0; i < ogeler.length - 1; i++) {
      const a = ogeler[i].getBoundingClientRect();
      const b = ogeler[i + 1].getBoundingClientRect();
      const ax = a.left + a.width / 2 - kr.left;
      const ay = a.bottom - kr.top;
      const bx = b.left + b.width / 2 - kr.left;
      const by = b.top - kr.top;
      const orta = (ay + by) / 2;
      yeni.push({
        d: `M${ax.toFixed(1)},${ay.toFixed(1)} C${ax.toFixed(1)},${orta.toFixed(1)} ${bx.toFixed(1)},${orta.toFixed(1)} ${bx.toFixed(1)},${by.toFixed(1)}`,
        renk: ogeler[i + 1].dataset.renk || '#b266ff',
      });
    }
    setYollar(yeni);
    setBoyut({ w: Math.round(kr.width), h: Math.round(kr.height) });
  }, []);

  useLayoutEffect(() => {
    olc();
    const kap = tuvalRef.current;
    if (!kap || typeof ResizeObserver === 'undefined') return;
    const g = new ResizeObserver(() => olc());
    g.observe(kap);
    return () => g.disconnect();
  }, [olc, dugumler, dil]);

  useEffect(() => {
    const fonts = (document as Document & { fonts?: { ready?: Promise<unknown> } }).fonts;
    fonts?.ready?.then(() => olc()).catch(() => undefined);
  }, [olc]);

  const kk = ozet?.kural ?? null;
  const oran = kk?.basari.oran ?? null;
  const toplamAdim = dugumler.length;

  return (
    <div className="oak-kap" data-testid="oto-akis">
      <div className="oak">
        {/* Sol: başlık + kural listesi */}
        <aside className="oak-sol">
          <p className="oak-ust-etiket">{t('otomasyon.akis.ust')}</p>
          <h2 className="oak-slogan">
            {t('otomasyon.akis.slogan1')} <span>{t('otomasyon.akis.slogan2')}</span>
          </h2>
          <div className="oak-cizgi" aria-hidden="true" />
          <p className="oak-aciklama">{t('otomasyon.akis.aciklama')}</p>
          <p className="oak-ust-etiket oak-kurallar-etiket" id="oak-kurallar">
            {t('otomasyon.akis.kurallar')}
          </p>
          <ul className="oak-kurallar" aria-labelledby="oak-kurallar">
            {liste.map((k) => {
              const adim = 1 + (k.kosullar?.kosullar?.length ? 1 : 0) + k.eylemler.length;
              const secMi = kural?.id === k.id;
              return (
                <li key={k.id}>
                  <button
                    type="button"
                    className="oak-kural"
                    aria-current={secMi ? 'true' : undefined}
                    data-oak-kural-sec={k.id}
                    onClick={() => sec(k)}
                  >
                    <Zap className="oak-kural-ikon" aria-hidden="true" />
                    <span className="oak-kural-yazi">
                      <span className="oak-kural-ad">{k.ad}</span>
                      <span className="oak-kural-alt">{t('otomasyon.akis.adimSayisi', { sayi: adim })}</span>
                    </span>
                    <span className={`oak-nokta ${k.aktif ? 'oak-nokta-acik' : ''}`} aria-hidden="true" />
                    <span className="sr-only">{k.aktif ? t('otomasyon.kural.aktif') : t('otomasyon.kural.pasif')}</span>
                  </button>
                </li>
              );
            })}
          </ul>
          <button type="button" className="oak-yeni" onClick={onYeni} disabled={yeniKapali} data-testid="oto-akis-yeni">
            <Plus className="h-4 w-4" aria-hidden="true" />
            {t('otomasyon.kural.yeni')}
          </button>
        </aside>

        {/* Orta: seçili kuralın akışı */}
        <section className="oak-orta" aria-labelledby="oak-kural-baslik">
          {kural && (
            <>
              <header className="oak-kural-baslik">
                <div className="min-w-0">
                  <h3 id="oak-kural-baslik" data-testid="oto-akis-kural-ad">
                    {kural.ad}
                  </h3>
                  {kural.aciklama && <p>{kural.aciklama}</p>}
                </div>
                <div className="oak-baslik-dugmeler">
                  <button type="button" className="oak-ikincil" onClick={() => onDuzenle(kural)} data-testid="oto-akis-duzenle">
                    <Pencil className="h-4 w-4" aria-hidden="true" />
                    {t('otomasyon.kural.duzenle')}
                  </button>
                  <button type="button" className="oak-ikincil" onClick={() => onGunluk(kural.id)} data-testid="oto-akis-gunluk">
                    <History className="h-4 w-4" aria-hidden="true" />
                    {t('otomasyon.kural.gunluk')}
                  </button>
                </div>
              </header>
              <div className="oak-tuval" ref={tuvalRef} data-oak-kural={kural.id} data-oak-durum={kural.aktif ? 'aktif' : 'pasif'}>
                <svg className="oak-baglantilar" width={boyut.w} height={boyut.h} aria-hidden="true" focusable="false">
                  {yollar.map((y, i) => (
                    <g key={i} style={{ color: y.renk }}>
                      <path d={y.d} className="oak-yol-isik" />
                      <path d={y.d} className="oak-yol" />
                      <path d={y.d} className="oak-yol-akis" />
                    </g>
                  ))}
                </svg>
                <ol className="oak-dugumler">
                  {dugumler.map((d, i) => (
                    <li key={d.anahtar} className="oak-dugum-li">
                      <button
                        type="button"
                        className="oak-dugum"
                        style={{ '--oak-renk': d.renk } as CSSProperties}
                        data-oak-dugum={d.tur}
                        data-oak-sira={i + 1}
                        data-renk={d.renk}
                        onClick={() => onDuzenle(kural, d.tur === 'tetik' ? 'tetik' : d.tur === 'kosul' ? 'kosullar' : 'eylemler')}
                        title={t('otomasyon.akis.duzenleIpucu')}
                      >
                        <span className="oak-dugum-ust">
                          <span className="oak-dugum-ikon">
                            <d.Ikon className="h-[18px] w-[18px]" aria-hidden="true" />
                          </span>
                          <span className="oak-dugum-baslik">{d.baslik}</span>
                          <span className="oak-dugum-sira">{t('otomasyon.akis.adim', { sira: i + 1, toplam: toplamAdim })}</span>
                        </span>
                        {d.satirlar.map((s, j) => (
                          <span key={j} className="oak-dugum-satir">
                            {s}
                          </span>
                        ))}
                        {d.not && <span className="oak-dugum-not">{d.not}</span>}
                        <span className={`oak-durum ${kural.aktif ? '' : 'oak-durum-kapali'}`}>
                          <span className="oak-nokta oak-nokta-acik" aria-hidden="true" />
                          {kural.aktif ? t('otomasyon.kural.aktif') : t('otomasyon.kural.pasif')}
                        </span>
                        <span className="sr-only">{t('otomasyon.akis.duzenleIpucu')}</span>
                      </button>
                    </li>
                  ))}
                </ol>
              </div>
            </>
          )}
        </section>

        {/* Sağ: gerçek çalışma sayıları */}
        <aside className="oak-istat" aria-label={t('otomasyon.akis.istatistik')} data-oak-ozet={ozetDurumu}>
          {ozetDurumu === 'hazir' && ozet && kk && (
            <>
              <div className="oak-kart" data-testid="oto-akis-calisma">
                <p className="oak-ust-etiket">{t('otomasyon.akis.calisma', { gun: ozet.pencere_gun })}</p>
                <p className="oak-buyuk" data-deger={kk.toplam}>
                  {kk.toplam.toLocaleString(dil)}
                </p>
                <Kivilcim degerler={kk.seri} renk="#ff4fd8" yukseklik={34} />
                <p className="oak-kart-alt">{t('otomasyon.akis.tumKurallar', { sayi: ozet.tumu.toplam.toLocaleString(dil) })}</p>
              </div>
              <div className="oak-kart" data-testid="oto-akis-basari">
                <p className="oak-ust-etiket">{t('otomasyon.akis.basari')}</p>
                <p className="oak-buyuk" data-deger={oran === null ? '' : Math.round(oran * 100)}>
                  {oran === null ? '—' : `%${Math.round(oran * 100)}`}
                </p>
                <div className="oak-cubuk" aria-hidden="true">
                  <span style={{ width: `${oran === null ? 0 : Math.round(oran * 100)}%` }} />
                </div>
                <p className="oak-kart-alt">
                  {oran === null
                    ? t('otomasyon.akis.basariYok')
                    : t('otomasyon.akis.basariAlt', { basarili: kk.basari.basarili, basarisiz: kk.basari.basarisiz })}
                </p>
              </div>
              <div className="oak-kart" data-testid="oto-akis-son">
                <p className="oak-ust-etiket">{t('otomasyon.akis.son')}</p>
                {kk.son.length ? (
                  <ul className="oak-son">
                    {kk.son.map((c) => (
                      <li key={c.id} data-durum={c.durum}>
                        <span className={`oak-nokta oak-nokta-${c.durum}`} aria-hidden="true" />
                        <span className="oak-son-yazi">
                          {t(`otomasyon.durum.${c.durum}`)}
                          {c.olay_hesap ? <span className="oak-son-hesap"> · {c.olay_hesap}</span> : null}
                        </span>
                        <span className="oak-son-zaman">{tarihYaz(c.zaman, i18n.language)}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="oak-kart-alt">{t('otomasyon.akis.sonYok', { gun: ozet.pencere_gun })}</p>
                )}
                <p className="oak-kart-alt">{t('otomasyon.akis.omur', { sayi: kk.toplam_omur })}</p>
              </div>
              <p className="oak-merkez">
                <span className="oak-nokta oak-nokta-pembe" aria-hidden="true" />
                {t('otomasyon.akis.etkinKural', { etkin: ozet.etkin_kural, toplam: ozet.kural_sayisi })}
              </p>
            </>
          )}
        </aside>

        {/* Alt şerit: sistemin gerçekten yaptıkları */}
        <ul className="oak-serit">
          <li>
            <Zap className="h-5 w-5" aria-hidden="true" />
            <span>
              <b>{t('otomasyon.akis.serit.kodsuz')}</b>
              {t('otomasyon.akis.serit.kodsuzAlt')}
            </span>
          </li>
          <li>
            <ShieldCheck className="h-5 w-5" aria-hidden="true" />
            <span>
              <b>{t('otomasyon.akis.serit.deneme')}</b>
              {t('otomasyon.akis.serit.denemeAlt')}
            </span>
          </li>
          <li>
            <Layers className="h-5 w-5" aria-hidden="true" />
            <span>
              {onSablonlar ? (
                <button type="button" className="oak-serit-baglanti" onClick={onSablonlar} data-testid="oto-akis-sablonlar">
                  {t('otomasyon.akis.serit.sablon')}
                </button>
              ) : (
                <b>{t('otomasyon.akis.serit.sablon')}</b>
              )}
              {t('otomasyon.akis.serit.sablonAlt')}
            </span>
          </li>
          <li>
            <RefreshCw className="h-5 w-5" aria-hidden="true" />
            <span>
              <b>{t('otomasyon.akis.serit.bekle')}</b>
              {t('otomasyon.akis.serit.bekleAlt')}
            </span>
          </li>
        </ul>
      </div>
    </div>
  );
}
