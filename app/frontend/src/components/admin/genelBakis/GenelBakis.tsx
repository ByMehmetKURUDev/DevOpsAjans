import { useEffect, useState, type CSSProperties, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import {
  ArrowRight,
  Bell,
  CalendarClock,
  CircleCheck,
  FileText,
  Folder,
  Inbox,
  Loader2,
  Lock,
  ReceiptText,
  ShieldCheck,
  TriangleAlert,
  Wallet,
  Wrench,
  type LucideIcon,
} from 'lucide-react';
import { useYoklama } from '@/hooks/useYoklama';
import {
  bellektekiOzet,
  ozetGetir,
  type AcilTalep,
  type AlinanOzet,
  type HizmetHatti,
  type IsSayaci,
  type Kategori,
  type OzetBildirimi,
  type ParaToplami,
  type Saha,
  type SonIs,
  type YonetimOzeti,
} from '@/lib/yonetimOzeti';
import { AlanGrafik, HALKA_RENKLERI, Halka, Kivilcim } from '@/components/panel/grafikler';
import './genelBakis.css';

/**
 * Faz 11A — yönetici "Genel bakış" (komuta ekranı).
 *
 * Tek istek (`GET /api/v1/yonetim-ozeti`), 60 sn'de bir yoklama (sekme görünmüyorken durur,
 * `useYoklama`). Hesaplanamayan kalem "veri yok" der; örnek değer yok. ACİL kartındaki kalan süre
 * her saniye ilerler (sekme gizliyken durur); sunucu ile tarayıcı saati farkı yanıt anından düzeltilir.
 *
 * Yerleşim `genelBakis.css`'te kap sorgularıyla (CSS kap sorgusu): geniş içerikte önizlemedeki
 * 12 sütunlu ızgara, orta genişlikte iki sütun, telefonda önizleme 6'daki sıra (ACİL, 2×2 KPI,
 * yatay kaydırmalı hizmet hattı, saha, son işler, sonra aktivite/kategori/bildirimler).
 */

const YOKLAMA_ARALIGI = 60_000;

const RENK = {
  cyan: '#38d1ff',
  yesil: '#2ef596',
  mor: '#b266ff',
  turuncu: '#ff7a2f',
  kirmizi: '#ff4d5e',
  sari: '#ffc542',
  mavi: '#3b82f6',
} as const;

interface Props {
  onSekmeGit: (sekme: string) => void;
  onTalepAc: (talepId: number) => void;
}

// ---------------------------------------------------------------- biçim yardımcıları
function paraYaz(tutar: number, birim: string, dil: string, kisa = false): string {
  try {
    return new Intl.NumberFormat(dil, {
      style: 'currency',
      currency: birim || 'TRY',
      maximumFractionDigits: kisa ? 1 : 0,
      ...(kisa ? { notation: 'compact' as const } : {}),
    }).format(tutar);
  } catch {
    return `${Math.round(tutar)} ${birim}`;
  }
}

function sayiYaz(n: number, dil: string, kesir = 0): string {
  return new Intl.NumberFormat(dil, { maximumFractionDigits: kesir }).format(n);
}

function yuzdeYaz(n: number, dil: string): string {
  return new Intl.NumberFormat(dil, { style: 'percent', maximumFractionDigits: 1 }).format(n / 100);
}

function ilkPara(liste: ParaToplami[] | undefined, dil: string, kisa = false): string | null {
  const p = liste?.[0];
  return p ? paraYaz(p.tutar, p.para_birimi, dil, kisa) : null;
}

/** "18:24" / "01:02:03"; eksi değerde başına "−". */
function sureYaz(sn: number, saatli: boolean): string {
  const eksi = sn < 0;
  const a = Math.abs(Math.trunc(sn));
  const s = Math.floor(a / 3600);
  const d = Math.floor((a % 3600) / 60);
  const z = a % 60;
  const iki = (x: number) => String(x).padStart(2, '0');
  const govde = saatli || s > 0 ? `${iki(s)}:${iki(d)}:${iki(z)}` : `${iki(d)}:${iki(z)}`;
  return `${eksi ? '−' : ''}${govde}`;
}

function goreli(iso: string | null, t: TFunction): string {
  if (!iso) return '';
  const fark = (Date.now() - Date.parse(iso)) / 60000;
  if (!Number.isFinite(fark) || fark < 1) return t('genelBakis.bildirim.simdi');
  if (fark < 60) return t('genelBakis.bildirim.dk', { sayi: Math.floor(fark) });
  if (fark < 60 * 24) return t('genelBakis.bildirim.sa', { sayi: Math.floor(fark / 60) });
  return t('genelBakis.bildirim.gun', { sayi: Math.floor(fark / 1440) });
}

/** Sekme görünürken saniyede bir "şimdi" (gizliyken durur). */
function useSaniye(etkin: boolean): number {
  const [an, setAn] = useState(() => Date.now());
  useEffect(() => {
    if (!etkin) return;
    let zamanlayici: number | null = null;
    const baslat = () => {
      if (zamanlayici !== null) return;
      setAn(Date.now());
      zamanlayici = window.setInterval(() => setAn(Date.now()), 1000);
    };
    const durdur = () => {
      if (zamanlayici !== null) window.clearInterval(zamanlayici);
      zamanlayici = null;
    };
    const gorunurluk = () => (document.visibilityState === 'hidden' ? durdur() : baslat());
    gorunurluk();
    document.addEventListener('visibilitychange', gorunurluk);
    return () => {
      durdur();
      document.removeEventListener('visibilitychange', gorunurluk);
    };
  }, [etkin]);
  return an;
}

// ---------------------------------------------------------------- küçük parçalar
function Kart({
  sinif,
  baslik,
  sag,
  children,
  isik,
  ...ek
}: {
  sinif: string;
  baslik?: ReactNode;
  sag?: ReactNode;
  children: ReactNode;
  isik?: string;
} & Record<`data-${string}`, string | undefined>) {
  return (
    <article className={`gb-kart ${sinif}`} style={isik ? ({ '--gb-isik': isik } as CSSProperties) : undefined} {...ek}>
      {(baslik || sag) && (
        <header className="gb-kart-ust">
          {baslik && <h2 className="gb-kart-baslik">{baslik}</h2>}
          {sag}
        </header>
      )}
      {children}
    </article>
  );
}

function VeriYok({ t }: { t: TFunction }) {
  return <p className="gb-veri-yok">{t('genelBakis.veriYok')}</p>;
}

function Degisim({ deger, dil, ters = false, puan = false, t }: { deger: number | null | undefined; dil: string; ters?: boolean; puan?: boolean; t: TFunction }) {
  if (deger === null || deger === undefined) return null;
  const artis = deger >= 0;
  const iyi = ters ? !artis : artis;
  const metin = puan ? t('genelBakis.kpi.puan', { deger: sayiYaz(Math.abs(deger), dil, 1) }) : yuzdeYaz(Math.abs(deger), dil);
  return (
    <span className="gb-degisim" data-iyi={iyi ? 'evet' : 'hayir'}>
      <span aria-hidden="true">{artis ? '▲' : '▼'}</span>
      <span className="gb-gizli">{artis ? '+' : '−'}</span>
      {metin}
    </span>
  );
}

// ---------------------------------------------------------------- ACİL
function AcilKart({ acil, saatFarki, t, onTalepAc, onSekmeGit }: { acil: AcilTalep | null; saatFarki: number; t: TFunction; onTalepAc: (id: number) => void; onSekmeGit: (s: string) => void }) {
  const simdi = useSaniye(!!acil) + saatFarki;
  if (!acil) {
    return (
      <Kart sinif="gb-acil" data-seviye="yok" data-acil-kart="" isik={RENK.yesil}>
        <div className="gb-acil-ust">
          <CircleCheck className="gb-acil-ikon" aria-hidden="true" />
          <div className="gb-acil-baslik-kutu">
            <h2 className="gb-acil-baslik">{t('genelBakis.acil.yokBaslik')}</h2>
            <p className="gb-acil-alt-yazi">{t('genelBakis.acil.yokMetin')}</p>
          </div>
        </div>
        <button type="button" className="gb-bag gb-acil-tumu" onClick={() => onSekmeGit('tickets')}>
          {t('genelBakis.acil.tumu')} <ArrowRight className="gb-yon" aria-hidden="true" />
        </button>
      </Kart>
    );
  }
  const hedef = Date.parse(acil.hedef);
  const bas = Date.parse(acil.baslangic);
  const kalanSn = Math.round((hedef - simdi) / 1000);
  const asildi = kalanSn < 0;
  const durum = asildi ? 'asildi' : acil.durum === 'asildi' ? 'yaklasiyor' : acil.durum;
  const kirmizi = asildi || durum === 'yaklasiyor' || acil.oncelik === 'acil';
  const seviye = kirmizi ? 'acil' : 'sakin';
  const ilerleme = asildi ? 100 : Math.min(100, Math.max(0, ((simdi - bas) / Math.max(1, hedef - bas)) * 100));
  return (
    <Kart sinif="gb-acil" data-seviye={seviye} data-acil-kart="" data-talep={String(acil.talep_id)} isik={kirmizi ? RENK.turuncu : RENK.cyan}>
      <div className="gb-acil-ust">
        <TriangleAlert className="gb-acil-ikon" aria-hidden="true" />
        <div className="gb-acil-baslik-kutu">
          <h2 className="gb-acil-baslik">
            {kirmizi ? t('genelBakis.acil.baslik') : t('genelBakis.acil.siradakiBaslik')}
            <span className="gb-acil-sla"> · SLA</span>
          </h2>
          <p className="gb-acil-kod">
            #{acil.kod} · {t('genelBakis.acil.destek')}
          </p>
          <p className="gb-acil-mobil-ozet">
            {[acil.musteri, acil.baslik].filter(Boolean).join(' · ')}
          </p>
        </div>
        <span className="gb-acil-mini gb-mono" aria-hidden="true">
          {sureYaz(kalanSn, false)}
        </span>
      </div>
      <div className="gb-acil-govde">
        <p className="gb-acil-konu">{acil.baslik}</p>
        {acil.musteri && <p className="gb-acil-musteri">{acil.musteri}</p>}
        <p className="gb-acil-durum">
          {t(`genelBakis.acil.oncelik.${acil.oncelik}`)} · {t(`genelBakis.acil.durum.${durum}`)}
        </p>
      </div>
      <div className="gb-acil-sure">
        <p className="gb-etiket">
          {asildi ? t('genelBakis.acil.gecen') : t('genelBakis.acil.kalan')} · {t(`genelBakis.acil.hedef.${acil.hedef_turu}`)}
        </p>
        <p className="gb-acil-sayac gb-mono" data-geri-sayim={kalanSn} role="timer" aria-live="off">
          {sureYaz(kalanSn, true)}
        </p>
        <div className="gb-cubuk" aria-hidden="true">
          <span style={{ width: `${ilerleme.toFixed(1)}%` }} />
        </div>
      </div>
      <button type="button" className="gb-acil-dugme" onClick={() => onTalepAc(acil.talep_id)} data-simdi-yanitla>
        {t('genelBakis.acil.simdiYanitla')}
      </button>
      <div className="gb-acil-alt">
        <span>{acil.siradaki > 0 ? t('genelBakis.acil.siradaki', { sayi: acil.siradaki }) : t('genelBakis.acil.siradakiYok')}</span>
        <button type="button" className="gb-bag" onClick={() => onSekmeGit('tickets')}>
          {t('genelBakis.acil.tumu')} <ArrowRight className="gb-yon" aria-hidden="true" />
        </button>
      </div>
    </Kart>
  );
}

// ---------------------------------------------------------------- KPI
function KpiKart({
  etiket,
  kisaEtiket,
  deger,
  kisaDeger,
  degisim,
  alt,
  seri,
  renk,
  cubuk,
  kimlik,
}: {
  etiket: string;
  kisaEtiket: string;
  deger: string | null;
  kisaDeger?: string | null;
  degisim?: ReactNode;
  alt: string;
  seri?: number[] | null;
  renk: string;
  cubuk?: number | null;
  kimlik: string;
}) {
  return (
    <Kart sinif="gb-kpi" isik={renk} data-kpi={kimlik}>
      <h3 className="gb-etiket">
        <span className="gb-tam">{etiket}</span>
        <span className="gb-kisa">{kisaEtiket}</span>
      </h3>
      <div className="gb-kpi-satir">
        <span className="gb-kpi-deger gb-mono">
          {deger === null ? (
            '—'
          ) : (
            <>
              <span className="gb-tam">{deger}</span>
              <span className="gb-kisa">{kisaDeger ?? deger}</span>
            </>
          )}
        </span>
        {degisim}
      </div>
      <p className="gb-kpi-alt">{alt}</p>
      {seri && seri.length > 1 ? (
        <Kivilcim degerler={seri} renk={renk} />
      ) : cubuk !== null && cubuk !== undefined ? (
        <div className="gb-cubuk gb-kpi-cubuk" aria-hidden="true" style={{ '--gb-renk': renk } as CSSProperties}>
          <span style={{ width: `${Math.min(100, Math.max(0, cubuk))}%` }} />
        </div>
      ) : (
        <div className="gb-kivilcim" />
      )}
    </Kart>
  );
}

function Kpiler({ veri, dil, t }: { veri: YonetimOzeti; dil: string; t: TFunction }) {
  const { tahsilat, acik_isler: acik, tamamlanan: tamam, sla } = veri.kpi;
  const veriYok = t('genelBakis.veriYok');
  const dokum = (x: IsSayaci, anahtar: string) => t(anahtar, { gorev: x.gorev, destek: x.destek, is: x.is_emri });
  return (
    <div className="gb-kpiler" data-kpiler="">
      <KpiKart
        kimlik="tahsilat"
        etiket={t('genelBakis.kpi.tahsilat')}
        kisaEtiket={t('genelBakis.kpi.tahsilatKisa')}
        deger={tahsilat ? paraYaz(tahsilat.tutar, tahsilat.para_birimi, dil) : null}
        kisaDeger={tahsilat ? paraYaz(tahsilat.tutar, tahsilat.para_birimi, dil, true) : null}
        degisim={tahsilat && <Degisim deger={tahsilat.degisim_yuzde} dil={dil} t={t} />}
        alt={tahsilat ? t('genelBakis.kpi.gecenAyaGore') : veriYok}
        seri={tahsilat?.seri}
        renk={RENK.yesil}
      />
      <KpiKart
        kimlik="acik"
        etiket={t('genelBakis.kpi.acikIsler')}
        kisaEtiket={t('genelBakis.kpi.acikIsler')}
        deger={acik ? sayiYaz(acik.toplam, dil) : null}
        degisim={acik && <Degisim deger={acik.degisim_yuzde} dil={dil} ters t={t} />}
        alt={acik ? dokum(acik, 'genelBakis.kpi.acikDokum') : veriYok}
        seri={acik?.seri}
        renk={RENK.turuncu}
      />
      <KpiKart
        kimlik="tamamlanan"
        etiket={t('genelBakis.kpi.tamamlanan')}
        kisaEtiket={t('genelBakis.kpi.tamamlanan')}
        deger={tamam ? sayiYaz(tamam.toplam, dil) : null}
        degisim={tamam && <Degisim deger={tamam.degisim_yuzde} dil={dil} t={t} />}
        alt={tamam ? dokum(tamam, 'genelBakis.kpi.tamamDokum') : veriYok}
        seri={tamam?.seri}
        renk={RENK.cyan}
      />
      <KpiKart
        kimlik="sla"
        etiket={t('genelBakis.kpi.sla')}
        kisaEtiket={t('genelBakis.kpi.slaKisa')}
        deger={sla ? yuzdeYaz(sla.uyum_yuzde, dil) : null}
        degisim={sla && <Degisim deger={sla.degisim_puan} dil={dil} puan t={t} />}
        alt={
          sla
            ? sla.ilk_yanit_ort_dk !== null
              ? t('genelBakis.kpi.ilkYanitOrt', { dk: sayiYaz(sla.ilk_yanit_ort_dk, dil) })
              : t('genelBakis.kpi.oncekiOtuzGune')
            : veriYok
        }
        cubuk={sla ? sla.uyum_yuzde : null}
        renk={RENK.mor}
      />
    </div>
  );
}

// ---------------------------------------------------------------- Hizmet hattı
const HAT: { anahtar: keyof Omit<HizmetHatti, 'donusum'>; ad: string; ikon: LucideIcon; renk: string }[] = [
  { anahtar: 'yeni_talep', ad: 'yeniTalep', ikon: Inbox, renk: RENK.kirmizi },
  { anahtar: 'teklif', ad: 'teklif', ikon: FileText, renk: RENK.cyan },
  { anahtar: 'sozlesme', ad: 'sozlesme', ikon: Lock, renk: RENK.cyan },
  { anahtar: 'proje', ad: 'proje', ikon: Folder, renk: RENK.cyan },
  { anahtar: 'teslim', ad: 'teslim', ikon: CircleCheck, renk: RENK.yesil },
  { anahtar: 'fatura', ad: 'fatura', ikon: ReceiptText, renk: RENK.mor },
];

function hatAlt(h: HizmetHatti, anahtar: (typeof HAT)[number]['anahtar'], dil: string, t: TFunction): string {
  switch (anahtar) {
    case 'yeni_talep':
      return t('genelBakis.hat.yeniTalepAlt');
    case 'teklif':
      return ilkPara(h.teklif.toplamlar, dil) ?? t('genelBakis.hat.teklifAlt');
    case 'sozlesme':
      return t('genelBakis.hat.sozlesmeAlt');
    case 'proje':
      return h.proje.ort_ilerleme !== null
        ? t('genelBakis.hat.projeAlt', { yuzde: sayiYaz(h.proje.ort_ilerleme, dil) })
        : t('genelBakis.hat.projeAltYok');
    case 'teslim':
      return t('genelBakis.hat.teslimAlt');
    case 'fatura': {
      const p = ilkPara(h.fatura.kalanlar, dil);
      return p ? t('genelBakis.hat.faturaAlt', { tutar: p }) : t('genelBakis.hat.faturaAltYok');
    }
  }
}

function HizmetHattiKart({ hat, dil, t, onSekmeGit }: { hat: HizmetHatti | null; dil: string; t: TFunction; onSekmeGit: (s: string) => void }) {
  const d = hat?.donusum;
  const donusumler = d
    ? [
        d.talep_teklif !== null ? t('genelBakis.hat.talepTeklif', { yuzde: sayiYaz(d.talep_teklif, dil, 1) }) : null,
        d.teklif_kabul !== null ? t('genelBakis.hat.teklifKabul', { yuzde: sayiYaz(d.teklif_kabul, dil, 1) }) : null,
        d.tahsilat_gun !== null ? t('genelBakis.hat.tahsilatGun', { gun: sayiYaz(d.tahsilat_gun, dil, 1) }) : null,
      ].filter((x): x is string => !!x)
    : [];
  return (
    <Kart
      sinif="gb-hat"
      isik={RENK.cyan}
      baslik={
        <>
          {t('genelBakis.hat.baslik')}
          <span className="gb-kart-aciklama">{t('genelBakis.hat.aciklama')}</span>
        </>
      }
      sag={
        <span className="gb-kaydir" aria-hidden="true">
          {t('genelBakis.hat.kaydir')} <ArrowRight className="gb-yon" />
        </span>
      }
    >
      {!hat ? (
        <VeriYok t={t} />
      ) : (
        <>
          <ol className="gb-hat-sira" data-hizmet-hatti="">
            {HAT.map((n, i) => {
              const dugum = hat[n.anahtar];
              const vurgu = n.anahtar === 'yeni_talep' && dugum.sayi > 0;
              const renk = n.anahtar === 'yeni_talep' && !vurgu ? RENK.cyan : n.renk;
              const sonraki = HAT[i + 1];
              return (
                <li key={n.anahtar} className="gb-hat-oge">
                  <button
                    type="button"
                    className="gb-dugum"
                    data-hat-dugumu={n.anahtar}
                    data-vurgu={vurgu ? 'evet' : undefined}
                    style={{ '--gb-renk': renk } as CSSProperties}
                    onClick={() => onSekmeGit(dugum.bolum)}
                    aria-label={`${t(`genelBakis.hat.${n.ad}`)}: ${dugum.sayi} — ${hatAlt(hat, n.anahtar, dil, t)}. ${t('genelBakis.hat.git', {
                      ad: t(`genelBakis.hat.${n.ad}`),
                    })}`}
                  >
                    {vurgu && (
                      <span className="gb-dugum-uyari" aria-hidden="true">
                        !
                      </span>
                    )}
                    <n.ikon className="gb-dugum-ikon" aria-hidden="true" />
                    <span className="gb-dugum-ad">{t(`genelBakis.hat.${n.ad}`)}</span>
                    <span className="gb-dugum-sayi gb-mono">{sayiYaz(dugum.sayi, dil)}</span>
                    <span className="gb-dugum-alt">{hatAlt(hat, n.anahtar, dil, t)}</span>
                  </button>
                  {sonraki && (
                    <span
                      className="gb-baglac"
                      aria-hidden="true"
                      style={{ '--gb-r1': renk, '--gb-r2': sonraki.renk } as CSSProperties}
                    />
                  )}
                </li>
              );
            })}
          </ol>
          <div className="gb-hat-alt">
            {donusumler.length > 0 && (
              <p className="gb-donusum">
                <b>{t('genelBakis.hat.donusum')}</b>
                {donusumler.map((x) => (
                  <span key={x}>{x}</span>
                ))}
              </p>
            )}
            <button type="button" className="gb-bag" onClick={() => onSekmeGit('crm')}>
              {t('genelBakis.hat.huniyeGit')} <ArrowRight className="gb-yon" aria-hidden="true" />
            </button>
          </div>
        </>
      )}
    </Kart>
  );
}

// ---------------------------------------------------------------- Aktivite, kategori
function AktiviteKart({ veri, dil, t }: { veri: YonetimOzeti; dil: string; t: TFunction }) {
  const a = veri.aktivite;
  return (
    <Kart
      sinif="gb-aktivite"
      isik={RENK.cyan}
      baslik={t('genelBakis.aktivite.baslik')}
      sag={
        <span className="gb-gosterge">
          <span>
            <i style={{ background: RENK.cyan }} />
            {t('genelBakis.aktivite.bugun')}
          </span>
          <span>
            <i style={{ background: RENK.mor }} />
            {t('genelBakis.aktivite.dun')}
          </span>
        </span>
      }
    >
      {!a ? (
        <VeriYok t={t} />
      ) : (
        <>
          <AlanGrafik
            bugun={a.bugun}
            dun={a.dun}
            renk1={RENK.cyan}
            renk2={RENK.mor}
            etiket={t('genelBakis.aktivite.ozet', { bugun: sayiYaz(a.toplam_bugun, dil), dun: sayiYaz(a.toplam_dun, dil) })}
          />
          <p className="gb-kucuk">
            {t('genelBakis.aktivite.ozet', { bugun: sayiYaz(a.toplam_bugun, dil), dun: sayiYaz(a.toplam_dun, dil) })} ·{' '}
            {t('genelBakis.aktivite.aciklama')}
          </p>
        </>
      )}
    </Kart>
  );
}

function KategoriKart({ k, dil, t }: { k: Kategori | null; dil: string; t: TFunction }) {
  const bos = !k || k.toplam === 0;
  const ilk = k ? k.dagilim.slice(0, 5) : [];
  const kalan = k ? k.dagilim.slice(5).reduce((a, d) => a + d.sayi, 0) : 0;
  const dilimler = [...ilk.map((d) => d.sayi), ...(kalan ? [kalan] : [])].map((deger, i) => ({ deger, renk: HALKA_RENKLERI[i % HALKA_RENKLERI.length] }));
  const adlar = [...ilk.map((d) => d.ad), ...(kalan ? ['…'] : [])];
  return (
    <Kart sinif="gb-kategori" isik={RENK.mor} baslik={t('genelBakis.kategori.baslik')}>
      {bos ? (
        <VeriYok t={t} />
      ) : (
        <>
          <div className="gb-kategori-ust">
            <Halka dilimler={dilimler} ust={sayiYaz(k!.toplam, dil)} alt={t('genelBakis.kategori.toplamIs')} />
            <ul className="gb-lejant">
              {dilimler.map((d, i) => (
                <li key={adlar[i]}>
                  <i style={{ background: d.renk, color: d.renk }} />
                  <span className="gb-lejant-ad">{adlar[i]}</span>
                  <span className="gb-mono">{yuzdeYaz((d.deger / k!.toplam) * 100, dil)}</span>
                </li>
              ))}
            </ul>
          </div>
          <p className="gb-gizli">{t('genelBakis.kategori.aciklama')}</p>
        </>
      )}
      {k && (
        <div className="gb-mini-izgara">
          <div className="gb-mini">
            <p className="gb-etiket">{t('genelBakis.kategori.buAyYeni')}</p>
            <p className="gb-mini-deger gb-mono">{sayiYaz(k.bu_ay_yeni, dil)}</p>
          </div>
          <div className="gb-mini">
            <p className="gb-etiket">{t('genelBakis.kategori.ortSure')}</p>
            <p className="gb-mini-deger gb-mono">
              {k.ort_sure_gun !== null ? t('genelBakis.kategori.gun', { sayi: sayiYaz(k.ort_sure_gun, dil, 1) }) : '—'}
            </p>
          </div>
          <div className="gb-mini" data-vurgu={k.en_hizli ? 'evet' : undefined}>
            <p className="gb-etiket">{t('genelBakis.kategori.enHizli')}</p>
            <p className="gb-mini-deger">
              {k.en_hizli ? (
                <>
                  {k.en_hizli.ad} <span aria-hidden="true">▲</span>
                  {yuzdeYaz(k.en_hizli.artis_yuzde, dil)}
                </>
              ) : (
                '—'
              )}
            </p>
          </div>
        </div>
      )}
    </Kart>
  );
}

// ---------------------------------------------------------------- Saha
const SAHA_RENGI: Record<string, string> = { iste: RENK.yesil, yolda: RENK.cyan, planlandi: RENK.mor };

function basHarf(ad: string): string {
  const p = ad.trim().split(/\s+/);
  return ((p[0]?.[0] || '') + (p.length > 1 ? p[p.length - 1][0] : '')).toLocaleUpperCase('tr');
}

function SahaKart({ saha, dil, t, onSekmeGit }: { saha: Saha; dil: string; t: TFunction; onSekmeGit: (s: string) => void }) {
  const durumAdi = (d: string) => t(`genelBakis.durum.is_emri.${d}`, { defaultValue: d });
  return (
    <Kart
      sinif="gb-saha"
      isik={RENK.yesil}
      data-saha-karti=""
      baslik={t('genelBakis.saha.baslik')}
      sag={
        <span className="gb-hap" style={{ '--gb-renk': RENK.yesil } as CSSProperties}>
          <i aria-hidden="true" />
          {t('genelBakis.saha.aktif', { sayi: saha.aktif })}
        </span>
      }
    >
      <ul className="gb-ekip">
        {saha.teknisyenler.map((tk) => {
          const renk = SAHA_RENGI[tk.durum] || RENK.cyan;
          return (
            <li key={tk.id} style={{ '--gb-renk': renk } as CSSProperties}>
              <span className="gb-avatar" aria-hidden="true">
                {basHarf(tk.ad)}
              </span>
              <div className="gb-ekip-govde">
                <p className="gb-ekip-ust">
                  <b>{tk.ad}</b>
                  <span className="gb-ekip-durum">{durumAdi(tk.durum)}</span>
                </p>
                <p className="gb-kucuk">
                  {tk.is_no} · {tk.is_baslik}
                </p>
                <div className="gb-cubuk gb-ince" aria-hidden="true">
                  <span style={{ width: `${tk.ilerleme}%` }} />
                </div>
              </div>
            </li>
          );
        })}
      </ul>
      <ul className="gb-saha-isler">
        {saha.isler.slice(0, 4).map((is) => (
          <li key={is.id}>
            <span className="gb-mono gb-saha-no">{is.no}</span>
            <span className="gb-saha-baslik">
              {is.baslik}
              {is.musteri ? ` · ${is.musteri}` : ''}
            </span>
            <span className="gb-durum" style={{ '--gb-renk': SAHA_RENGI[is.durum] || RENK.cyan } as CSSProperties}>
              {durumAdi(is.durum)}
            </span>
            {!is.teknisyenler.length && <span className="gb-kucuk">{t('genelBakis.saha.teknisyenYok')}</span>}
          </li>
        ))}
      </ul>
      <p className="gb-kucuk gb-saha-ozet">{t('genelBakis.saha.isler', { sayi: sayiYaz(saha.is_sayisi, dil) })}</p>
      <button type="button" className="gb-bag gb-ortala" onClick={() => onSekmeGit(saha.bolum)}>
        {t('genelBakis.saha.panoyaGit')} <ArrowRight className="gb-yon" aria-hidden="true" />
      </button>
    </Kart>
  );
}

// ---------------------------------------------------------------- Son işler
function durumBilgisi(is: SonIs, t: TFunction): { metin: string; renk: string } {
  const d = is.durum || '';
  if (is.tur === 'destek') {
    if (d !== 'closed' && d !== 'answered' && is.oncelik === 'acil') return { metin: t('genelBakis.durum.destek.acil'), renk: RENK.kirmizi };
    const renk = d === 'answered' ? RENK.yesil : d === 'closed' ? '#8ea2d6' : RENK.cyan;
    return { metin: t(`genelBakis.durum.destek.${d}`, { defaultValue: d }), renk };
  }
  const renkler: Record<string, Record<string, string>> = {
    proje: { planning: RENK.sari, in_progress: RENK.cyan, completed: RENK.yesil },
    is_emri: { yeni: RENK.sari, planlandi: RENK.cyan, yolda: RENK.mor, iste: RENK.yesil, tamamlandi: RENK.yesil, iptal: '#8ea2d6', ertelendi: RENK.turuncu },
    teklif: { taslak: '#8ea2d6', gonderildi: RENK.sari, goruntulendi: RENK.sari, kabul: RENK.yesil, ret: RENK.kirmizi, suresi_doldu: '#8ea2d6', revize: RENK.mor },
  };
  return { metin: d ? t(`genelBakis.durum.${is.tur}.${d}`, { defaultValue: d }) : '—', renk: renkler[is.tur]?.[d] || RENK.cyan };
}

function SonIslerKart({ isler, dil, t, onSekmeGit, onTalepAc }: { isler: SonIs[] | null; dil: string; t: TFunction; onSekmeGit: (s: string) => void; onTalepAc: (id: number) => void }) {
  const ac = (is: SonIs) => (is.tur === 'destek' ? onTalepAc(is.id) : onSekmeGit(is.bolum));
  return (
    <Kart
      sinif="gb-son"
      isik={RENK.cyan}
      baslik={t('genelBakis.son.baslik')}
      sag={
        <button type="button" className="gb-bag" onClick={() => onSekmeGit('projects')}>
          {t('genelBakis.son.tumu')} <ArrowRight className="gb-yon" aria-hidden="true" />
        </button>
      }
    >
      {!isler || isler.length === 0 ? (
        <VeriYok t={t} />
      ) : (
        <table className="gb-tablo" data-son-isler="">
          <thead>
            <tr>
              <th scope="col">{t('genelBakis.son.kod')}</th>
              <th scope="col">{t('genelBakis.son.musteri')}</th>
              <th scope="col">{t('genelBakis.son.hizmet')}</th>
              <th scope="col">{t('genelBakis.son.durum')}</th>
              <th scope="col">{t('genelBakis.son.sorumlu')}</th>
              <th scope="col" className="gb-sag">
                {t('genelBakis.son.tutar')}
              </th>
            </tr>
          </thead>
          <tbody>
            {isler.map((is) => {
              const d = durumBilgisi(is, t);
              return (
                <tr key={`${is.tur}-${is.id}`} style={{ '--gb-renk': d.renk } as CSSProperties} data-son-is={is.tur}>
                  <td className="gb-kod">
                    <button type="button" className="gb-satir-dugme gb-mono" onClick={() => ac(is)} title={t(`genelBakis.son.tur.${is.tur}`)}>
                      {is.kod}
                    </button>
                  </td>
                  <td className="gb-musteri">{is.musteri || '—'}</td>
                  <td className="gb-hizmet">{is.hizmet || '—'}</td>
                  <td>
                    <span className="gb-durum">{d.metin}</span>
                  </td>
                  <td className="gb-sorumlu">{is.sorumlu || '—'}</td>
                  <td className="gb-sag gb-mono gb-tutar">{is.tutar !== null && is.para_birimi ? paraYaz(is.tutar, is.para_birimi, dil) : '—'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </Kart>
  );
}

// ---------------------------------------------------------------- Bildirimler
function bildirimIkonu(tur: string): { ikon: LucideIcon; renk: string } {
  const x = tur.toLowerCase();
  if (/(sla|acil|escal|eskal)/.test(x)) return { ikon: TriangleAlert, renk: RENK.turuncu };
  if (/(inquiry|talep|aday|crm|ticket|destek|mesaj)/.test(x)) return { ikon: Inbox, renk: RENK.kirmizi };
  if (/(teslim|delivery|onay|imza|sozlesme|kabul)/.test(x)) return { ikon: CircleCheck, renk: RENK.yesil };
  if (/(odeme|payment|fatura|invoice|cuzdan|tahsil)/.test(x)) return { ikon: Wallet, renk: RENK.cyan };
  if (/(toplanti|randevu|meeting)/.test(x)) return { ikon: CalendarClock, renk: RENK.mor };
  if (/(saha|is_emri)/.test(x)) return { ikon: Wrench, renk: RENK.yesil };
  if (/(guvenlik|oturum)/.test(x)) return { ikon: ShieldCheck, renk: RENK.mavi };
  return { ikon: Bell, renk: RENK.mavi };
}

function BildirimKart({ liste, t }: { liste: OzetBildirimi[] | null; t: TFunction }) {
  const zilAc = () => {
    window.scrollTo({ top: 0, behavior: 'auto' });
    document.querySelector<HTMLButtonElement>('[data-pk-zil] button')?.click();
  };
  return (
    <Kart
      sinif="gb-bildirim"
      isik={RENK.mor}
      baslik={t('genelBakis.bildirim.baslik')}
      sag={
        <button type="button" className="gb-bag" onClick={zilAc}>
          {t('genelBakis.bildirim.tumu')}
        </button>
      }
    >
      {!liste || liste.length === 0 ? (
        <p className="gb-veri-yok">{t('genelBakis.bildirim.yok')}</p>
      ) : (
        <ul className="gb-bildirimler">
          {liste.map((b) => {
            const { ikon: Ikon, renk } = bildirimIkonu(b.tur || '');
            const govde = (
              <>
                <span className="gb-bildirim-ikon" style={{ '--gb-renk': renk } as CSSProperties} aria-hidden="true">
                  <Ikon />
                </span>
                <span className="gb-bildirim-metin">
                  <b>{b.baslik}</b>
                  {b.govde && <span className="gb-kucuk">{b.govde}</span>}
                </span>
                <span className="gb-kucuk gb-bildirim-zaman">
                  {!b.okundu && <span className="gb-gizli">{t('genelBakis.bildirim.okunmamis')} · </span>}
                  {goreli(b.zaman, t)}
                </span>
              </>
            );
            return (
              <li key={b.id} data-okundu={b.okundu ? 'evet' : 'hayir'}>
                {b.baglanti && b.baglanti.startsWith('/') ? (
                  <Link to={b.baglanti} className="gb-bildirim-satir">
                    {govde}
                  </Link>
                ) : (
                  <div className="gb-bildirim-satir">{govde}</div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </Kart>
  );
}

// ---------------------------------------------------------------- Ana bileşen
export default function GenelBakis({ onSekmeGit, onTalepAc }: Props) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [ozet, setOzet] = useState<AlinanOzet | null>(() => bellektekiOzet());
  const [hata, setHata] = useState(false);
  const yoklama = useYoklama(
    async () => {
      try {
        setOzet(await ozetGetir());
        setHata(false);
      } catch (e) {
        setHata(true);
        throw e;
      }
    },
    { aralik: YOKLAMA_ARALIGI },
  );

  if (!ozet) {
    return (
      <section className="gb gb-durum-ekrani" aria-busy={!hata} data-genel-bakis="">
        {hata ? (
          <div className="gb-kart gb-hata">
            <p>{t('genelBakis.hata')}</p>
            <button type="button" className="gb-acil-dugme gb-ikincil" onClick={yoklama.simdi}>
              {t('genelBakis.yenidenDene')}
            </button>
          </div>
        ) : (
          <p className="gb-yukleniyor">
            <Loader2 className="gb-don" aria-hidden="true" /> {t('genelBakis.yukleniyor')}
          </p>
        )}
      </section>
    );
  }

  const { veri, alindi } = ozet;
  const saatFarki = Date.parse(veri.olusturma) - alindi;
  const guncel = new Date(alindi).toLocaleTimeString(dil, { hour: '2-digit', minute: '2-digit' });
  return (
    <section className="gb" aria-label={t('genelBakis.bolgeEtiketi')} data-genel-bakis="" data-sahasiz={veri.saha ? undefined : ''}>
      <div className="gb-izgara">
        <AcilKart acil={veri.acil} saatFarki={Number.isFinite(saatFarki) ? saatFarki : 0} t={t} onTalepAc={onTalepAc} onSekmeGit={onSekmeGit} />
        <Kpiler veri={veri} dil={dil} t={t} />
        <HizmetHattiKart hat={veri.hizmetHatti} dil={dil} t={t} onSekmeGit={onSekmeGit} />
        {veri.saha && <SahaKart saha={veri.saha} dil={dil} t={t} onSekmeGit={onSekmeGit} />}
        <SonIslerKart isler={veri.sonIsler} dil={dil} t={t} onSekmeGit={onSekmeGit} onTalepAc={onTalepAc} />
        <AktiviteKart veri={veri} dil={dil} t={t} />
        <KategoriKart k={veri.kategori} dil={dil} t={t} />
        <BildirimKart liste={veri.bildirimler} t={t} />
      </div>
      <p className="gb-guncel" aria-live="polite">
        {hata ? t('genelBakis.hata') : t('genelBakis.guncellendi', { saat: guncel })}
      </p>
    </section>
  );
}
