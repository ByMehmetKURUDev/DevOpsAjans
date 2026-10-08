import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { ArrowLeft, CalendarClock, CalendarPlus, FileDown, Loader2, Plus, RefreshCcw, Rss, X } from 'lucide-react';

import {
  AbonelikTarifi,
  AdresKutusu,
  DUGME_ANA,
  DUGME_IKINCIL,
  DurumRozeti,
  GIRDI,
  KART,
  Rozet,
  SECIM,
  Yer,
  YanitRozeti,
  Zaman,
} from '@/components/toplantilar/ortak';
import ToplantiIste from '@/components/toplantilar/ToplantiIste';
import { PDF_DILLERI } from '@/lib/belge';
import {
  hataKodu,
  mAksiyon,
  mAyrinti,
  mIcs,
  mListe,
  mMd,
  mPdf,
  mTakvim,
  mTakvimIptal,
  mTakvimUret,
  mTalepler,
  mYanit,
  YANITLAR,
  type Abonelik,
  type MusteriAyrinti,
  type MusteriOzet,
  type Talep,
  type Yanit,
} from '@/lib/toplantilar';

function YanitFormu({ id, yanit, not: ilkNot, onKaydedildi }: { id: number; yanit: Yanit | null; not: string | null; onKaydedildi: () => void }) {
  const { t } = useTranslation();
  const [not, setNot] = useState(ilkNot || '');
  const [calisan, setCalisan] = useState<Yanit | null>(null);
  async function ver(y: Yanit) {
    setCalisan(y);
    try {
      await mYanit(id, y, not.trim());
      toast.success(t('toplantilar.musteri.yanitKaydedildi'));
      onKaydedildi();
    } catch (h) {
      toast.error(t(`toplantilar.hata.${hataKodu(h)}`, { defaultValue: t('toplantilar.hata.genel') }));
    } finally {
      setCalisan(null);
    }
  }
  return (
    <div className="mt-3 rounded-xl border border-white/10 bg-black/20 p-3" data-yanit-formu={id}>
      <p className="mb-2 text-sm font-medium">{t('toplantilar.musteri.yanitim')}</p>
      <div className="flex flex-wrap gap-2">
        {YANITLAR.map((y) => (
          <button
            key={y}
            type="button"
            onClick={() => void ver(y)}
            disabled={!!calisan}
            aria-pressed={yanit === y}
            className={`min-h-[36px] rounded-lg border px-3 py-1.5 text-sm ${yanit === y ? 'border-purple-400/70 bg-purple-500/20 text-white' : 'border-white/15 text-muted-foreground hover:text-white'}`}
            data-yanit={y}
          >
            {calisan === y && <Loader2 className="me-1 inline h-3.5 w-3.5 animate-spin" aria-hidden="true" />}
            {t(`toplantilar.yanit.${y}`)}
          </button>
        ))}
      </div>
      <input
        className={`${GIRDI} mt-2`}
        value={not}
        maxLength={500}
        placeholder={t('toplantilar.musteri.yanitNot')}
        aria-label={t('toplantilar.musteri.yanitNot')}
        onChange={(e) => setNot(e.target.value)}
        data-yanit-not
      />
    </div>
  );
}

function Ayrinti({ id, onGeri }: { id: number; onGeri: () => void }) {
  const { t, i18n } = useTranslation();
  const [v, setV] = useState<MusteriAyrinti | null>(null);
  const [hata, setHata] = useState(false);
  const [dil, setDil] = useState<string>(PDF_DILLERI.includes(i18n.language as never) ? i18n.language : 'tr');
  const yukle = useCallback(() => {
    mAyrinti(id)
      .then((g) => {
        setV(g);
        setHata(false);
      })
      .catch(() => setHata(true));
  }, [id]);
  useEffect(() => {
    yukle();
  }, [yukle]);
  const mesaj = (h: unknown) => t(`toplantilar.hata.${hataKodu(h)}`, { defaultValue: t('toplantilar.hata.genel') });

  if (hata) return <p className={`${KART} p-6 text-sm text-red-200`}>{t('toplantilar.hata.genel')}</p>;
  if (!v) {
    return (
      <div className="flex items-center justify-center py-16 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" />
      </div>
    );
  }
  return (
    <div className="space-y-4" data-testid="musteri-toplanti-ayrinti" data-toplanti-id={v.id}>
      <button type="button" className={DUGME_IKINCIL} onClick={onGeri}>
        <ArrowLeft className="h-4 w-4 rtl:rotate-180" aria-hidden="true" />
        {t('toplantilar.ayrinti.listeyeDon')}
      </button>
      <section className={`${KART} p-4 sm:p-6`}>
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="min-w-0 break-words text-xl font-semibold">{v.baslik}</h3>
          <DurumRozeti durum={v.durum} />
        </div>
        <p className="mt-2 text-sm text-muted-foreground">
          <Zaman iso={v.baslangic} /> · {t('toplantilar.zaman.dk', { sayi: v.sure_dk })}
        </p>
        {v.durum !== 'iptal' && (
          <div className="mt-2">
            <Yer yer_turu={v.yer_turu} baglanti={v.baglanti} adres={v.adres} telefon={v.telefon} katil={v.kategori === 'yaklasan'} />
          </div>
        )}
        {v.durum === 'iptal' && v.iptal_nedeni && (
          <p className="mt-2 whitespace-pre-line break-words text-sm text-white/80">
            {t('toplantilar.ayrinti.iptalNedeni')}: {v.iptal_nedeni}
          </p>
        )}
        <div className="mt-3 flex flex-wrap gap-2">
          {v.durum !== 'iptal' && (
            <button type="button" className={DUGME_IKINCIL} onClick={() => void mIcs(v.id).catch((h) => toast.error(mesaj(h)))} data-musteri-ics>
              <CalendarPlus className="h-4 w-4" aria-hidden="true" />
              {t('toplantilar.musteri.ics')}
            </button>
          )}
        </div>
        {v.katilimci_miyim && v.kategori === 'yaklasan' && <YanitFormu id={v.id} yanit={v.yanitim} not={v.yanit_notum} onKaydedildi={yukle} />}
        {!v.katilimci_miyim && v.kategori === 'yaklasan' && <p className="mt-3 text-xs text-muted-foreground">{t('toplantilar.musteri.katilimciDegil')}</p>}
      </section>

      <section className={`${KART} p-4 sm:p-6`}>
        {v.gundem.length > 0 && (
          <>
            <h4 className="mb-2 font-semibold">{t('toplantilar.form.gundem')}</h4>
            <ol className="mb-4 list-decimal space-y-1 ps-6 text-sm">
              {v.gundem.map((g, i) => (
                <li key={i} className="break-words">{g}</li>
              ))}
            </ol>
          </>
        )}
        <h4 className="mb-2 font-semibold">{t('toplantilar.ayrinti.katilimcilar')}</h4>
        <ul className="space-y-1 text-sm">
          {v.katilimcilar.map((k, i) => (
            <li key={`${k.tur}-${i}`} className="flex flex-wrap items-center justify-between gap-2" data-musteri-katilimci={k.tur}>
              <span className="min-w-0 break-all">
                {k.ad || k.eposta}
                {k.tur === 'ekip' && <span className="ms-1 text-xs text-muted-foreground">({t('toplantilar.katilimciTuru.ekip')})</span>}
              </span>
              {k.yanit && <YanitRozeti yanit={k.yanit} />}
            </li>
          ))}
        </ul>
        {!v.katilimci_miyim && v.dis_sayisi > 0 && (
          <p className="mt-1 text-xs text-muted-foreground" data-dis-sayisi>
            {t('toplantilar.musteri.disKatilimci', { sayi: v.dis_sayisi })}
          </p>
        )}
      </section>

      <section className={`${KART} p-4 sm:p-6`} data-testid="musteri-tutanak">
        <h4 className="mb-2 font-semibold">{t('toplantilar.musteri.notlar')}</h4>
        {v.notlar_paylasildi ? (
          <>
            {/* Sunucu güvenli HTML'i (services/guvenli_html.py). */}
            <div className="prose prose-invert max-w-none break-words text-sm" data-paylasilan-not dangerouslySetInnerHTML={{ __html: v.notlar_html || '' }} />
            {v.kararlar.length > 0 && (
              <>
                <h4 className="mb-2 mt-4 font-semibold">{t('toplantilar.musteri.kararlar')}</h4>
                <ul className="list-disc space-y-1 ps-6 text-sm" data-kararlar>
                  {v.kararlar.map((k, i) => (
                    <li key={i} className="break-words">{k}</li>
                  ))}
                </ul>
              </>
            )}
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <select className={`${SECIM} w-auto`} value={dil} onChange={(e) => setDil(e.target.value)} aria-label={t('toplantilar.tutanak.dil')}>
                {PDF_DILLERI.map((d) => (
                  <option key={d} value={d}>
                    {d.toUpperCase()}
                  </option>
                ))}
              </select>
              <button type="button" className={DUGME_IKINCIL} onClick={() => void mPdf(v.id, dil).catch((h) => toast.error(mesaj(h)))}>
                <FileDown className="h-4 w-4" aria-hidden="true" />
                {t('toplantilar.tutanak.pdf')}
              </button>
              <button type="button" className={DUGME_IKINCIL} onClick={() => void mMd(v.id, dil).catch((h) => toast.error(mesaj(h)))}>
                <FileDown className="h-4 w-4" aria-hidden="true" />
                {t('toplantilar.tutanak.md')}
              </button>
            </div>
          </>
        ) : (
          <p className="text-sm text-muted-foreground" data-paylasilmadi>
            {t('toplantilar.musteri.paylasilmadi')}
          </p>
        )}
        {v.aksiyonlar.length > 0 && (
          <>
            <h4 className="mb-2 mt-4 font-semibold">{t('toplantilar.musteri.aksiyonlar')}</h4>
            <ul className="space-y-2 text-sm">
              {v.aksiyonlar.map((a) => (
                <li key={a.id} className="flex items-start gap-2" data-musteri-aksiyon={a.id}>
                  {a.isaretleyebilir ? (
                    <input
                      type="checkbox"
                      className="mt-1 h-4 w-4 accent-purple-500"
                      checked={a.durum === 'tamamlandi'}
                      aria-label={t('toplantilar.musteri.tamamla')}
                      onChange={(e) =>
                        void mAksiyon(a.id, e.target.checked)
                          .then(() => {
                            toast.success(t('toplantilar.musteri.aksiyonKaydedildi'));
                            yukle();
                          })
                          .catch((h) => toast.error(mesaj(h)))
                      }
                    />
                  ) : (
                    <span className="mt-1 inline-block h-4 w-4 flex-none rounded border border-white/20" aria-hidden="true" />
                  )}
                  <span className="min-w-0 flex-1">
                    <span className={`break-words ${a.durum === 'tamamlandi' ? 'text-muted-foreground line-through' : ''}`}>{a.metin}</span>
                    <span className="block text-xs text-muted-foreground">
                      {a.sorumlu_tur === 'musteri' ? t('toplantilar.musteri.benim') : t('toplantilar.aksiyon.ekip')}
                      {a.son_tarih && ` · ${t('toplantilar.aksiyon.sonTarih')}: ${a.son_tarih}`}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
    </div>
  );
}

function TakvimAboneligi() {
  const { t } = useTranslation();
  const [a, setA] = useState<Abonelik | null>(null);
  const [adres, setAdres] = useState<string | null>(null);
  const [calisan, setCalisan] = useState(false);
  useEffect(() => {
    mTakvim()
      .then(setA)
      .catch(() => setA({ var: false }));
  }, []);
  async function uret() {
    setCalisan(true);
    try {
      const g = await mTakvimUret();
      setA(g);
      setAdres(g.adres || null);
    } catch (h) {
      toast.error(t(`toplantilar.hata.${hataKodu(h)}`, { defaultValue: t('toplantilar.hata.genel') }));
    } finally {
      setCalisan(false);
    }
  }
  async function iptal() {
    setCalisan(true);
    try {
      await mTakvimIptal();
      setA({ var: false });
      setAdres(null);
      toast.success(t('toplantilar.abonelik.iptalEdildi'));
    } catch (h) {
      toast.error(t(`toplantilar.hata.${hataKodu(h)}`, { defaultValue: t('toplantilar.hata.genel') }));
    } finally {
      setCalisan(false);
    }
  }
  return (
    <section className={`${KART} p-4 sm:p-6`} data-testid="musteri-takvim-aboneligi">
      <h3 className="flex items-center gap-2 font-semibold">
        <Rss className="h-4 w-4 text-purple-300" aria-hidden="true" />
        {t('toplantilar.abonelik.baslik')}
      </h3>
      <p className="mt-1 text-sm text-muted-foreground">{t('toplantilar.abonelik.aciklama')}</p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {a?.var && <Rozet tur="katilacak">{t('toplantilar.abonelik.var')}</Rozet>}
        <button type="button" className={DUGME_IKINCIL} onClick={() => void uret()} disabled={calisan || !a} data-musteri-abonelik-uret>
          {calisan ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <RefreshCcw className="h-4 w-4" aria-hidden="true" />}
          {a?.var ? t('toplantilar.abonelik.yenidenUret') : t('toplantilar.abonelik.uret')}
        </button>
        {a?.var && (
          <button type="button" className={DUGME_IKINCIL} onClick={() => void iptal()} disabled={calisan}>
            <X className="h-4 w-4" aria-hidden="true" />
            {t('toplantilar.abonelik.iptal')}
          </button>
        )}
      </div>
      {adres && <AdresKutusu adres={adres} />}
      <AbonelikTarifi />
    </section>
  );
}

/**
 * Faz 6T — müşteri paneli › Toplantılar: yaklaşan / geçmiş toplantılar (etkin hesabın), katıl bağlantısı, ICS,
 * katılım yanıtı, paylaşılmış notlar / kararlar, kendisine atanmış aksiyonu tamamlama, "Toplantı iste", talepler
 * ve kişiye özel takvim aboneliği. Paylaşılmamış ekip notları sunucudan hiç gelmez.
 */
export default function MusteriToplantilari() {
  const { t } = useTranslation();
  const [liste, setListe] = useState<MusteriOzet[] | null>(null);
  const [talepler, setTalepler] = useState<Talep[]>([]);
  const [hata, setHata] = useState(false);
  const [secili, setSecili] = useState<number | null>(null);
  const [iste, setIste] = useState(false);

  const yukle = useCallback(() => {
    mListe()
      .then((g) => {
        setListe(g.items);
        setHata(false);
      })
      .catch(() => setHata(true));
    mTalepler()
      .then((g) => setTalepler(g.items))
      .catch(() => setTalepler([]));
  }, []);

  useEffect(() => {
    yukle();
  }, [yukle]);

  if (secili) return <Ayrinti id={secili} onGeri={() => { setSecili(null); yukle(); }} />;

  const yaklasan = (liste ?? []).filter((x) => x.kategori === 'yaklasan').sort((a, b) => a.baslangic.localeCompare(b.baslangic));
  const gecmis = (liste ?? []).filter((x) => x.kategori !== 'yaklasan');

  const kart = (x: MusteriOzet) => (
    <li key={x.id} className={`${KART} p-4`} data-musteri-toplanti={x.id}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1 basis-56">
          <p className="break-words font-medium">{x.baslik}</p>
          <p className="text-xs text-muted-foreground">
            <Zaman iso={x.baslangic} /> · {t('toplantilar.zaman.dk', { sayi: x.sure_dk })}
          </p>
          {x.durum !== 'iptal' && (
            <div className="mt-1">
              <Yer yer_turu={x.yer_turu} baglanti={x.baglanti} adres={x.adres} telefon={x.telefon} katil={x.kategori === 'yaklasan'} />
            </div>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <DurumRozeti durum={x.durum} />
          {x.yanitim && <YanitRozeti yanit={x.yanitim} />}
          {x.notlar_paylasildi && <Rozet tur="bilgi">{t('toplantilar.rozet.paylasildi')}</Rozet>}
          {!!x.acik_aksiyon && <Rozet tur="uyari">{t('toplantilar.musteri.acikAksiyon', { sayi: x.acik_aksiyon })}</Rozet>}
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" className={DUGME_IKINCIL} onClick={() => setSecili(x.id)} data-musteri-ac={x.id}>
          {t('toplantilar.musteri.ayrinti')}
        </button>
        {x.durum !== 'iptal' && (
          <button
            type="button"
            className={DUGME_IKINCIL}
            onClick={() => void mIcs(x.id).catch((h) => toast.error(t(`toplantilar.hata.${hataKodu(h)}`, { defaultValue: t('toplantilar.hata.genel') })))}
          >
            <CalendarPlus className="h-4 w-4" aria-hidden="true" />
            {t('toplantilar.musteri.ics')}
          </button>
        )}
      </div>
      {x.katilimci_miyim && x.kategori === 'yaklasan' && <YanitFormu id={x.id} yanit={x.yanitim} not={x.yanit_notum} onKaydedildi={yukle} />}
    </li>
  );

  return (
    <section aria-labelledby="musteri-toplantilar-baslik" data-testid="musteri-toplantilar">
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 id="musteri-toplantilar-baslik" className="flex items-center gap-2 text-2xl font-bold">
            <CalendarClock className="h-6 w-6 text-purple-300" aria-hidden="true" />
            {t('toplantilar.musteri.baslik')}
          </h2>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{t('toplantilar.musteri.aciklama')}</p>
        </div>
        {!iste && (
          <button type="button" className={DUGME_ANA} onClick={() => setIste(true)} data-toplanti-iste>
            <Plus className="h-4 w-4" aria-hidden="true" />
            {t('toplantilar.musteri.iste')}
          </button>
        )}
      </div>

      {iste && (
        <div className="mb-5">
          <ToplantiIste
            onKapat={() => setIste(false)}
            onGonderildi={() => {
              setIste(false);
              yukle();
            }}
          />
        </div>
      )}

      {hata ? (
        <p className={`${KART} p-6 text-sm text-red-200`}>{t('toplantilar.hata.genel')}</p>
      ) : !liste ? (
        <div className="flex items-center justify-center py-16 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
        </div>
      ) : (
        <div className="space-y-6">
          <div>
            <h3 className="mb-2 text-sm font-semibold uppercase tracking-wider text-muted-foreground">{t('toplantilar.musteri.yaklasan')}</h3>
            {yaklasan.length ? <ul className="space-y-3">{yaklasan.map(kart)}</ul> : <p className="text-sm text-muted-foreground">{t('toplantilar.musteri.bos')}</p>}
          </div>
          {gecmis.length > 0 && (
            <div>
              <h3 className="mb-2 text-sm font-semibold uppercase tracking-wider text-muted-foreground">{t('toplantilar.musteri.gecmis')}</h3>
              <ul className="space-y-3">{gecmis.map(kart)}</ul>
            </div>
          )}
          {talepler.length > 0 && (
            <div className={`${KART} p-4`} data-musteri-talepler>
              <h3 className="mb-2 font-semibold">{t('toplantilar.musteri.talepler')}</h3>
              <ul className="space-y-2 text-sm">
                {talepler.map((x) => (
                  <li key={x.id} className="flex flex-wrap items-center justify-between gap-2" data-musteri-talep={x.id}>
                    <span className="min-w-0 break-words">{x.konu}</span>
                    <Rozet tur={x.durum === 'bekliyor' ? 'uyari' : x.durum === 'planlandi' ? 'katilacak' : 'bekliyor'}>
                      {t(`toplantilar.talep.durum.${x.durum}`)}
                    </Rozet>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <TakvimAboneligi />
        </div>
      )}
    </section>
  );
}
