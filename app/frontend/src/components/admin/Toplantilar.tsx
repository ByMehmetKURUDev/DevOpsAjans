import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { CalendarClock, Inbox, Loader2, Plus, RefreshCcw, Rss, Users } from 'lucide-react';

import {
  AltDugme,
  DUGME_ANA,
  DUGME_IKINCIL,
  DurumRozeti,
  GIRDI,
  KART,
  Rozet,
  SECIM,
  Yer,
  Zaman,
} from '@/components/toplantilar/ortak';
import {
  haftaBasi,
  liste as listeGetir,
  meta as metaGetir,
  talepGetir,
  yerelAd,
  type Ayrinti,
  type Kategori,
  type Meta,
  type Ozet,
  type Talep,
} from '@/lib/toplantilar';

const ToplantiFormu = lazy(() => import('@/components/admin/toplantilar/ToplantiFormu'));
const ToplantiAyrinti = lazy(() => import('@/components/admin/toplantilar/ToplantiAyrinti'));
const Talepler = lazy(() => import('@/components/admin/toplantilar/Talepler'));
const Abonelikler = lazy(() => import('@/components/admin/toplantilar/Abonelikler'));

type Alt = 'liste' | 'talepler' | 'abonelik';
type Gorunum = Kategori | 'hepsi';
const GORUNUMLER: Gorunum[] = ['yaklasan', 'gecmis', 'iptal', 'hepsi'];

function param(ad: string): string | null {
  try {
    return new URLSearchParams(window.location.search).get(ad);
  } catch {
    return null;
  }
}

const Bekle = () => (
  <div className="flex items-center justify-center py-16 text-muted-foreground">
    <Loader2 className="h-5 w-5 animate-spin" />
  </div>
);

/**
 * Faz 6T — Yönetici › Projeler › Toplantılar (menüde TEK sekme; bölümler burada alt gezinme):
 * hafta gruplu liste (yaklaşan / geçmiş / iptal; müşteri, proje, durum, tarih süzgeci), oluştur/düzenle,
 * ayrıntı (davet, ertele, iptal, tutanak, aksiyon → görev), müşteri talepleri, ekip takvim abonelikleri.
 * `?talep=<id>` (gelen kutusundaki "Toplantı planla") talepten ön doldurulmuş formu, `?toplanti=<id>` ayrıntıyı açar.
 * Metinler `toplantilar` ek paketinde.
 */
/** `yeniIstek`: Faz 11A hızlı işlem ("Toplantı planla") — her artışta yeni toplantı formu (meta gelince çizilir). */
export default function Toplantilar({ yeniIstek = 0 }: { yeniIstek?: number } = {}) {
  const { t, i18n } = useTranslation();
  const [alt, setAlt] = useState<Alt>('liste');
  const [meta, setMeta] = useState<Meta | null>(null);
  const [gorunum, setGorunum] = useState<Gorunum>('yaklasan');
  const [suzgec, setSuzgec] = useState({ hesap: '', proje_id: '', durum: '', bas: '', bit: '', q: '' });
  const [liste, setListe] = useState<Ozet[] | null>(null);
  const [bekleyenTalep, setBekleyenTalep] = useState(0);
  const [hata, setHata] = useState(false);
  const [secili, setSecili] = useState<number | null>(() => Number(param('toplanti')) || null);
  const [form, setForm] = useState<{ mevcut?: Ayrinti | null; talep?: Talep | null } | null>(null);
  useEffect(() => {
    if (yeniIstek) setForm({});
  }, [yeniIstek]);

  useEffect(() => {
    metaGetir()
      .then(setMeta)
      .catch(() => setHata(true));
    const talepId = Number(param('talep'));
    if (talepId) {
      talepGetir(talepId)
        .then((tl) => {
          if (tl.durum === 'bekliyor') setForm({ talep: tl });
          else if (tl.toplanti_id) setSecili(tl.toplanti_id);
        })
        .catch(() => undefined);
    }
  }, []);

  const yukle = useCallback(() => {
    listeGetir({ gorunum, ...suzgec })
      .then((g) => {
        setListe(g.items);
        setBekleyenTalep(g.bekleyen_talep);
        setHata(false);
      })
      .catch(() => setHata(true));
  }, [gorunum, suzgec]);

  useEffect(() => {
    if (alt === 'liste') yukle();
  }, [yukle, alt]);

  const gruplar = useMemo(() => {
    const g: { anahtar: string; pazartesi: string; ogeler: Ozet[] }[] = [];
    for (const o of liste ?? []) {
      const anahtar = o.hafta || haftaBasi(o.baslangic);
      let grup = g.find((x) => x.anahtar === anahtar);
      if (!grup) {
        grup = { anahtar, pazartesi: haftaBasi(o.baslangic), ogeler: [] };
        g.push(grup);
      }
      grup.ogeler.push(o);
    }
    return g;
  }, [liste]);

  const haftaEtiketi = (pazartesi: string) => {
    try {
      const bas = new Date(`${pazartesi}T00:00:00Z`);
      const son = new Date(bas.getTime() + 6 * 86400000);
      const f = new Intl.DateTimeFormat(yerelAd(i18n.language), { day: 'numeric', month: 'short', timeZone: 'UTC' });
      return t('toplantilar.hafta', { aralik: `${f.format(bas)} – ${f.format(son)}` });
    } catch {
      return pazartesi;
    }
  };

  const projeler = (meta?.projeler ?? []).filter((p) => !suzgec.hesap || p.hesap_email === suzgec.hesap);

  if (form && meta) {
    return (
      <Suspense fallback={<Bekle />}>
        <ToplantiFormu
          meta={meta}
          mevcut={form.mevcut}
          talep={form.talep}
          onVazgec={() => setForm(null)}
          onKaydedildi={(s) => {
            setForm(null);
            setAlt('liste');
            setSecili(s.id);
            yukle();
          }}
        />
      </Suspense>
    );
  }

  return (
    <section aria-labelledby="toplantilar-baslik" data-testid="toplantilar-yonetim">
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="flex items-center gap-2 text-2xl font-bold" id="toplantilar-baslik">
            <CalendarClock className="h-6 w-6 text-purple-300" aria-hidden="true" />
            {t('toplantilar.baslik')}
          </h2>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{t('toplantilar.aciklama')}</p>
        </div>
        <button type="button" className={DUGME_ANA} disabled={!meta} onClick={() => setForm({})} data-yeni-toplanti>
          <Plus className="h-4 w-4" aria-hidden="true" />
          {t('toplantilar.yeni')}
        </button>
      </div>

      <div className="mb-4 flex gap-1 overflow-x-auto pb-1" role="tablist" aria-label={t('toplantilar.baslik')}>
        <AltDugme anahtar="liste" secili={alt === 'liste'} onClick={() => { setAlt('liste'); setSecili(null); }}>
          <Users className="h-4 w-4" aria-hidden="true" />
          {t('toplantilar.alt.liste')}
        </AltDugme>
        <AltDugme anahtar="talepler" secili={alt === 'talepler'} onClick={() => setAlt('talepler')}>
          <Inbox className="h-4 w-4" aria-hidden="true" />
          {t('toplantilar.alt.talepler')}
          {bekleyenTalep > 0 && (
            <span className="rounded-full bg-amber-500/80 px-1.5 text-[10px] font-semibold text-zinc-950" data-talep-rozet>
              {bekleyenTalep}
            </span>
          )}
        </AltDugme>
        <AltDugme anahtar="abonelik" secili={alt === 'abonelik'} onClick={() => setAlt('abonelik')}>
          <Rss className="h-4 w-4" aria-hidden="true" />
          {t('toplantilar.alt.abonelik')}
        </AltDugme>
      </div>

      <Suspense fallback={<Bekle />}>
        {alt === 'talepler' ? (
          <Talepler onPlanla={(tl) => setForm({ talep: tl })} onDegisti={yukle} />
        ) : alt === 'abonelik' ? (
          <Abonelikler />
        ) : secili && meta ? (
          <ToplantiAyrinti
            id={secili}
            meta={meta}
            onGeri={() => setSecili(null)}
            onDuzenle={(m) => setForm({ mevcut: m })}
            onDegisti={yukle}
          />
        ) : (
          <>
            <div className={`${KART} mb-4 p-3`}>
              <div className="flex flex-wrap gap-1" role="tablist" aria-label={t('toplantilar.alt.liste')}>
                {GORUNUMLER.map((g) => (
                  <button
                    key={g}
                    type="button"
                    role="tab"
                    aria-selected={gorunum === g}
                    onClick={() => setGorunum(g)}
                    className={`min-h-[36px] rounded-lg px-3 py-1.5 text-sm ${gorunum === g ? 'bg-purple-500/20 text-white' : 'text-muted-foreground hover:text-white'}`}
                    data-gorunum={g}
                  >
                    {t(`toplantilar.gorunum.${g}`)}
                  </button>
                ))}
                <button type="button" className={`${DUGME_IKINCIL} ms-auto`} onClick={yukle} aria-label={t('toplantilar.yenile')}>
                  <RefreshCcw className="h-4 w-4" aria-hidden="true" />
                </button>
              </div>
              <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-6">
                <input
                  className={GIRDI}
                  value={suzgec.q}
                  placeholder={t('toplantilar.suzgec.ara')}
                  aria-label={t('toplantilar.suzgec.ara')}
                  onChange={(e) => setSuzgec((s) => ({ ...s, q: e.target.value }))}
                />
                <select
                  className={SECIM}
                  value={suzgec.hesap}
                  aria-label={t('toplantilar.suzgec.musteri')}
                  onChange={(e) => setSuzgec((s) => ({ ...s, hesap: e.target.value, proje_id: '' }))}
                  data-suzgec="hesap"
                >
                  <option value="">{t('toplantilar.suzgec.tumMusteriler')}</option>
                  {(meta?.musteriler ?? []).map((m) => (
                    <option key={m.eposta} value={m.eposta}>
                      {m.ad || m.eposta}
                    </option>
                  ))}
                </select>
                <select
                  className={SECIM}
                  value={suzgec.proje_id}
                  aria-label={t('toplantilar.suzgec.proje')}
                  onChange={(e) => setSuzgec((s) => ({ ...s, proje_id: e.target.value }))}
                >
                  <option value="">{t('toplantilar.suzgec.tumProjeler')}</option>
                  {projeler.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.baslik}
                    </option>
                  ))}
                </select>
                <select
                  className={SECIM}
                  value={suzgec.durum}
                  aria-label={t('toplantilar.suzgec.durum')}
                  onChange={(e) => setSuzgec((s) => ({ ...s, durum: e.target.value }))}
                >
                  <option value="">{t('toplantilar.suzgec.tumDurumlar')}</option>
                  {(['planlandi', 'ertelendi', 'yapildi', 'iptal'] as const).map((d) => (
                    <option key={d} value={d}>
                      {t(`toplantilar.durum.${d}`)}
                    </option>
                  ))}
                </select>
                <input
                  type="date"
                  className={GIRDI}
                  value={suzgec.bas}
                  aria-label={t('toplantilar.suzgec.bas')}
                  onChange={(e) => setSuzgec((s) => ({ ...s, bas: e.target.value }))}
                  dir="ltr"
                />
                <input
                  type="date"
                  className={GIRDI}
                  value={suzgec.bit}
                  aria-label={t('toplantilar.suzgec.bit')}
                  onChange={(e) => setSuzgec((s) => ({ ...s, bit: e.target.value }))}
                  dir="ltr"
                />
              </div>
            </div>

            {hata ? (
              <p className={`${KART} p-6 text-sm text-red-200`}>{t('toplantilar.hata.genel')}</p>
            ) : !liste ? (
              <Bekle />
            ) : liste.length === 0 ? (
              <p className={`${KART} p-8 text-center text-sm text-muted-foreground`} data-bos>
                {t('toplantilar.bos')}
              </p>
            ) : (
              <div className="space-y-5" data-toplanti-listesi>
                {gruplar.map((g) => (
                  <section key={g.anahtar} aria-label={haftaEtiketi(g.pazartesi)} data-hafta={g.anahtar}>
                    <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{haftaEtiketi(g.pazartesi)}</h3>
                    <ul className="space-y-2">
                      {g.ogeler.map((o) => (
                        <li key={o.id}>
                          <button
                            type="button"
                            onClick={() => setSecili(o.id)}
                            className={`${KART} block w-full p-3 text-start transition-colors hover:border-purple-400/40`}
                            data-toplanti={o.id}
                          >
                            <div className="flex flex-wrap items-start justify-between gap-2">
                              <div className="min-w-0 flex-1 basis-56">
                                <p className="break-words font-medium">{o.baslik}</p>
                                <p className="text-xs text-muted-foreground">
                                  <Zaman iso={o.baslangic} /> · {t('toplantilar.zaman.dk', { sayi: o.sure_dk })}
                                  {o.hesap_email && <span className="break-all"> · {o.hesap_adi || o.hesap_email}</span>}
                                </p>
                                <div className="mt-1">
                                  <Yer yer_turu={o.yer_turu} baglanti={null} adres={o.adres} telefon={o.telefon} />
                                </div>
                              </div>
                              <div className="flex flex-wrap items-center gap-1.5">
                                <DurumRozeti durum={o.durum} />
                                {o.guncelleme_bekliyor && <Rozet tur="uyari">{t('toplantilar.rozet.guncelleme')}</Rozet>}
                                {o.kategori === 'gecmis' && !o.notlar_var && <Rozet tur="uyari">{t('toplantilar.rozet.notYok')}</Rozet>}
                                {o.notlar_paylasildi && <Rozet tur="bilgi">{t('toplantilar.rozet.paylasildi')}</Rozet>}
                                <Rozet tur="bekliyor">
                                  {t('toplantilar.katilimciOzet', { sayi: o.katilimci_sayisi })}
                                  {o.yanitlar.katilacak > 0 && ` · ✓${o.yanitlar.katilacak}`}
                                  {o.yanitlar.katilamayacak > 0 && ` · ✗${o.yanitlar.katilamayacak}`}
                                  {o.yanitlar.belki > 0 && ` · ?${o.yanitlar.belki}`}
                                </Rozet>
                              </div>
                            </div>
                          </button>
                        </li>
                      ))}
                    </ul>
                  </section>
                ))}
              </div>
            )}
          </>
        )}
      </Suspense>
    </section>
  );
}
