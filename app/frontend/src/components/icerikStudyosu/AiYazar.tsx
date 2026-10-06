import { useEffect, useMemo, useState } from 'react';
import { CalendarPlus, ChevronDown, ChevronUp, Copy, History, Languages, Loader2, Mail, Minimize2, Settings2, Smile, SmilePlus, Sparkles, Heart } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Alan, Bos, DIS_DUGME, GIRDI, KART, METIN_ALANI, Rozet, SECIM, SayacRozeti, Uyarilar } from '@/components/icerikStudyosu/ortak';
import type { PlanTaslagi } from '@/components/IcerikStudyosu';
import {
  hataMetni,
  kampanyayaAktar,
  panoyaKopyala,
  tarihSaatYaz,
  type GenelAyarlar,
  type InceAyar,
  type Kullanim,
  type Marka,
  type Meta,
  type Sablon,
  type StudyoApi,
  type Uretim,
  type Varyasyon,
} from '@/lib/icerikStudyosu';

/**
 * Faz 5I — AI yazar: marka sesi + şablon + girdi → 1–3 varyasyon. Her varyasyonda kanal/alan
 * karakter sınırı ölçümü (sunucunun tek sınır tablosu) ve uyarı rozeti (sağlık/finans/hukuk
 * vaadi, kaynaksız sayı, yasaklı kelime). İnce ayar: daha kısa / daha samimi / emoji ekle /
 * emoji çıkar (ücretsiz, yerel) / çevir. "Planlayıcıya ekle" ve bülten şablonunda "E-posta
 * kampanyasına aktar" (Faz 5M). Maliyet: aylık dahil üretim, aşımda kredi bloğu.
 */

const DILLER = ['tr', 'en', 'de', 'ru', 'zh', 'hi', 'ar'];
const INCE_AYAR_IKONU: Record<string, typeof Smile> = { kisalt: Minimize2, samimi: Heart, emoji_ekle: SmilePlus, emoji_cikar: Smile, cevir: Languages };

export default function AiYazar({
  api,
  meta,
  onPlanla,
  metaYenile,
}: {
  api: StudyoApi;
  meta: Meta;
  onPlanla: (t: PlanTaslagi) => void;
  metaYenile: () => Promise<void>;
}) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [sablonlar, setSablonlar] = useState<Sablon[]>(meta.hazir_sablonlar);
  const [markalar, setMarkalar] = useState<Marka[]>([]);
  const [kod, setKod] = useState(meta.hazir_sablonlar[0]?.kod ?? 'instagram_gonderi');
  const [markaId, setMarkaId] = useState<number | null>(null);
  const [kanal, setKanal] = useState<string>('');
  const [icerikDili, setIcerikDili] = useState(DILLER.includes(dil) ? dil : 'tr');
  const [varyasyon, setVaryasyon] = useState(2);
  const [girdi, setGirdi] = useState<Record<string, string>>({});
  const [calisiyor, setCalisiyor] = useState<string | null>(null);
  const [sonuclar, setSonuclar] = useState<Uretim[]>([]);
  const [kullanim, setKullanim] = useState<Kullanim>(meta.kullanim);
  const [gecmis, setGecmis] = useState<Uretim[] | null>(null);
  const [cevirDili, setCevirDili] = useState('en');

  useEffect(() => {
    api.markalar().then((r) => {
      setMarkalar(r.items);
      if (r.items.length === 1) setMarkaId(r.items[0].id);
    }).catch(() => setMarkalar([]));
    api.sablonlar().then((r) => setSablonlar([...r.hazir, ...r.ozel])).catch(() => undefined);
  }, [api]);

  const sablon = useMemo(() => sablonlar.find((s) => s.kod === kod) ?? sablonlar[0], [sablonlar, kod]);
  const kanallar = sablon?.kanallar?.length ? sablon.kanallar : meta.kanallar;
  const etkinKanal = kanal && kanallar.includes(kanal) ? kanal : sablon?.kanal ?? kanallar[0] ?? null;
  const sablonAdi = (s: Sablon) => (s.hazir ? t(`icerikStudyosu.sablon.${s.kod}.ad`) : s.ad || s.kod);
  /** Üretim kaydındaki şablon kodunun adı: hazır şablon çevirisi ya da kendi şablonunun adı (`ozel:<id>`). */
  const uretimSablonu = (kodu: string) => {
    const s = sablonlar.find((x) => x.kod === kodu);
    if (s) return sablonAdi(s);
    return kodu.startsWith('ozel:') ? t('icerikStudyosu.yazar.ozelSablonlar') : t(`icerikStudyosu.sablon.${kodu}.ad`, { defaultValue: kodu });
  };
  const aiKapaliIpucu = meta.ai_hazir ? undefined : t('icerikStudyosu.uyariAiKapali');
  const girdiEtiketi = (g: { anahtar: string; etiket?: string }) => (sablon?.hazir ? t(`icerikStudyosu.girdi.${g.anahtar}`) : g.etiket || g.anahtar);

  const uret = async () => {
    if (!sablon) return;
    const eksik = sablon.girdiler.find((g) => g.zorunlu && !(girdi[g.anahtar] || '').trim());
    if (eksik) {
      toast.error(t('icerikStudyosu.yazar.zorunlu', { alan: girdiEtiketi(eksik) }));
      return;
    }
    setCalisiyor('uret');
    try {
      const y = await api.uret({
        sablon: sablon.kod,
        girdi: Object.fromEntries(sablon.girdiler.map((g) => [g.anahtar, girdi[g.anahtar] || ''])),
        marka_id: markaId,
        kanal: etkinKanal,
        varyasyon,
        dil: icerikDili,
      });
      setSonuclar((s) => [y.uretim, ...s].slice(0, 6));
      setKullanim(y.kullanim);
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setCalisiyor(null);
    }
  };

  const inceAyar = async (u: Uretim, v: Varyasyon, islem: InceAyar) => {
    setCalisiyor(`ince-${u.id}-${islem}`);
    try {
      const y = await api.inceAyar({ islem, metin: v.metin, kanal: u.kanal, marka_id: u.marka_id, hedef_dil: islem === 'cevir' ? cevirDili : undefined, kaynak_id: u.id });
      setSonuclar((s) => [y.uretim, ...s].slice(0, 6));
      setKullanim(y.kullanim);
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setCalisiyor(null);
    }
  };

  const planla = (u: Uretim, v: Varyasyon) => {
    const konu = (u.girdi.konu || u.girdi.urun_adi || u.girdi.etkinlik_adi || '').split('\n')[0];
    onPlanla({
      baslik: (konu || (u.sablon === 'ince_ayar' ? t('icerikStudyosu.yazar.yeniIcerik') : uretimSablonu(u.sablon))).slice(0, 120),
      metin: v.metin,
      kanallar: u.kanal && meta.kanallar.includes(u.kanal) ? [u.kanal] : ['instagram'],
      marka_id: u.marka_id,
      uretim_id: u.id,
    });
  };

  const aktar = async (u: Uretim, v: Varyasyon) => {
    setCalisiyor(`aktar-${u.id}`);
    try {
      await kampanyayaAktar(meta.yonetici ? 'yonetici' : 'musteri', v.alanlar, String(v.alanlar.konu || u.girdi.konu || ''));
      toast.success(t('icerikStudyosu.yazar.aktarildi'), {
        action: { label: t('icerikStudyosu.yazar.kampanyayaGit'), onClick: () => window.location.assign(meta.yonetici ? '/admin?sekme=epostaPazarlama&alt=kampanyalar' : '/client?sekme=epostaPazarlama') },
      });
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setCalisiyor(null);
    }
  };

  const gecmisiAc = async () => {
    if (gecmis) {
      setGecmis(null);
      return;
    }
    try {
      setGecmis((await api.uretimler(20)).items);
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const s = kullanim.sinirlar;
  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]" data-testid="is-yazar">
      <div className={`${KART} space-y-3 p-4`}>
        <Alan etiket={t('icerikStudyosu.yazar.sablon')}>
          <select className={SECIM} value={sablon?.kod ?? ''} onChange={(e) => { setKod(e.target.value); setKanal(''); }} data-testid="is-yazar-sablon">
            <optgroup label={t('icerikStudyosu.yazar.hazirSablonlar')}>
              {sablonlar.filter((x) => x.hazir).map((x) => (
                <option key={x.kod} value={x.kod}>{sablonAdi(x)}</option>
              ))}
            </optgroup>
            {sablonlar.some((x) => !x.hazir) && (
              <optgroup label={t('icerikStudyosu.yazar.ozelSablonlar')}>
                {sablonlar.filter((x) => !x.hazir).map((x) => (
                  <option key={x.kod} value={x.kod}>{sablonAdi(x)}</option>
                ))}
              </optgroup>
            )}
          </select>
        </Alan>
        {sablon && <p className="text-xs text-muted-foreground">{sablon.hazir ? t(`icerikStudyosu.sablon.${sablon.kod}.aciklama`) : sablon.aciklama}</p>}
        <div className="grid grid-cols-2 gap-2">
          <Alan etiket={t('icerikStudyosu.yazar.marka')}>
            <select className={SECIM} value={markaId ?? ''} onChange={(e) => setMarkaId(e.target.value ? Number(e.target.value) : null)} data-testid="is-yazar-marka">
              <option value="">{t('icerikStudyosu.form.markaYok')}</option>
              {markalar.map((m) => (
                <option key={m.id} value={m.id}>{m.ad}</option>
              ))}
            </select>
          </Alan>
          <Alan etiket={t('icerikStudyosu.yazar.kanal')}>
            <select className={SECIM} value={etkinKanal ?? ''} onChange={(e) => setKanal(e.target.value)} data-testid="is-yazar-kanal">
              {kanallar.map((k) => (
                <option key={k} value={k}>{t(`icerikOnay.kanal.${k}`)}</option>
              ))}
            </select>
          </Alan>
          <Alan etiket={t('icerikStudyosu.yazar.dil')}>
            <select className={SECIM} value={icerikDili} onChange={(e) => setIcerikDili(e.target.value)}>
              {DILLER.map((d) => (
                <option key={d} value={d}>{t(`icerikStudyosu.dil.${d}`)}</option>
              ))}
            </select>
          </Alan>
          <Alan etiket={t('icerikStudyosu.yazar.varyasyon')}>
            <select className={SECIM} value={varyasyon} onChange={(e) => setVaryasyon(Number(e.target.value))} data-testid="is-yazar-varyasyon">
              {Array.from({ length: meta.en_cok_varyasyon }, (_, i) => i + 1).map((n) => (
                <option key={n} value={n}>{n}</option>
              ))}
            </select>
          </Alan>
        </div>
        {sablon?.girdiler.map((g) => (
          <Alan key={g.anahtar} etiket={`${girdiEtiketi(g)}${g.zorunlu ? ' *' : ''}`}>
            {g.tur === 'uzun' ? (
              <textarea className={METIN_ALANI} value={girdi[g.anahtar] || ''} onChange={(e) => setGirdi((x) => ({ ...x, [g.anahtar]: e.target.value }))} dir="auto" data-girdi={g.anahtar} maxLength={4000} />
            ) : (
              <input className={GIRDI} value={girdi[g.anahtar] || ''} onChange={(e) => setGirdi((x) => ({ ...x, [g.anahtar]: e.target.value }))} dir="auto" data-girdi={g.anahtar} maxLength={4000} />
            )}
          </Alan>
        ))}
        <p className="text-[11px] text-muted-foreground">{t('icerikStudyosu.yazar.kural')}</p>
        <Button type="button" className="w-full gap-1.5" onClick={uret} disabled={!meta.ai_hazir || !!calisiyor} title={aiKapaliIpucu} data-testid="is-yazar-uret">
          {calisiyor === 'uret' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" aria-hidden="true" />}
          {t('icerikStudyosu.yazar.uret')}
        </Button>
        <p className="text-[11px] text-muted-foreground" data-testid="is-kullanim">
          {kullanim.ajans
            ? t('icerikStudyosu.kullanim.ajans', { sayi: kullanim.ay.uretim, bugun: kullanim.bugun, gunluk: s.gunluk_uretim ?? '∞' })
            : t('icerikStudyosu.kullanim.musteri', { sayi: kullanim.ay.uretim, dahil: s.aylik_uretim ?? '∞', kredi: kullanim.ay.kredi, bakiye: kullanim.kredi_bakiyesi ?? '—', blok: kullanim.blok_uretim, blokKredi: kullanim.blok_kredi })}
        </p>
        <button type="button" className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-white" onClick={gecmisiAc} data-testid="is-gecmis">
          <History className="h-3.5 w-3.5" aria-hidden="true" />
          {t('icerikStudyosu.yazar.gecmis')}
          {gecmis ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
        </button>
        {gecmis && (
          <ul className="max-h-60 space-y-1 overflow-y-auto text-xs">
            {gecmis.length === 0 && <li className="text-muted-foreground">{t('icerikStudyosu.yazar.gecmisBos')}</li>}
            {gecmis.map((u) => (
              <li key={u.id}>
                <button type="button" className="w-full truncate rounded px-1.5 py-1 text-start hover:bg-white/5" onClick={() => setSonuclar((x) => [u, ...x.filter((y) => y.id !== u.id)].slice(0, 6))}>
                  <span className="text-muted-foreground">{tarihSaatYaz(u.created_at, dil)} · {t(`icerikStudyosu.islem.${u.islem}`, { defaultValue: u.islem })} ·</span>{' '}
                  {(u.varyasyonlar[0]?.metin || '').slice(0, 60)}
                </button>
              </li>
            ))}
          </ul>
        )}
        {meta.yonetici && <GenelAyarlarKarti api={api} onKaydet={metaYenile} />}
      </div>

      <div className="min-w-0 space-y-4" data-testid="is-yazar-sonuclar">
        {sonuclar.length === 0 && <Bos>{meta.ai_hazir ? t('icerikStudyosu.yazar.bos') : t('icerikStudyosu.uyariAiKapali')}</Bos>}
        {sonuclar.map((u) => (
          <section key={u.id} className="space-y-2" data-uretim={u.id}>
            <p className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <Rozet>{t(`icerikStudyosu.islem.${u.islem}`, { defaultValue: u.islem })}</Rozet>
              {u.sablon !== 'ince_ayar' && <span>{uretimSablonu(u.sablon)}</span>}
              {u.kanal && <span>· {t(`icerikOnay.kanal.${u.kanal}`, { defaultValue: u.kanal })}</span>}
              {u.kredi > 0 && <Rozet renk="border-amber-400/30 bg-amber-400/10 text-amber-100">{t('icerikStudyosu.yazar.krediDustu', { kredi: u.kredi })}</Rozet>}
              {u.sahte && <Rozet renk="border-sky-400/30 bg-sky-400/10 text-sky-100">{t('icerikStudyosu.yazar.sahte')}</Rozet>}
            </p>
            {u.varyasyonlar.map((v, i) => (
              <article key={i} className={`${KART} p-3`} data-varyasyon={i}>
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <span className="text-xs font-semibold">{t('icerikStudyosu.yazar.varyasyonNo', { sayi: i + 1 })}</span>
                  <SayacRozeti olcum={v.kanal_olcumu} dil={dil} />
                  <Uyarilar uyarilar={v.uyarilar} />
                </div>
                <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-relaxed" dir="auto" data-testid="is-varyasyon-metin">{v.metin}</pre>
                {v.olcum.some((o) => o.asim) && (
                  <ul className="mt-2 space-y-0.5 text-[11px] text-rose-300" data-testid="is-olcum-asim">
                    {v.olcum.filter((o) => o.asim).map((o, k) => (
                      <li key={k}>
                        {t(`icerikStudyosu.cikti.${o.alan}`, { defaultValue: o.alan })}
                        {o.indeks !== undefined ? ` #${o.indeks + 1}` : ''}:{' '}
                        {o.uzunluk !== undefined ? `${o.uzunluk}/${o.sinir}` : t('icerikStudyosu.yazar.adet', { adet: o.adet, en_az: o.en_az ?? 0, en_cok: o.en_cok ?? o.sinir ?? '∞' })}
                      </li>
                    ))}
                  </ul>
                )}
                <div className="mt-3 flex flex-wrap gap-1.5">
                  <Button type="button" size="sm" variant="outline" className={DIS_DUGME}
                    onClick={async () => toast[(await panoyaKopyala(v.metin)) ? 'success' : 'error'](t('icerikStudyosu.kopyalandi'))}>
                    <Copy className="h-3.5 w-3.5" aria-hidden="true" />
                    {t('icerikStudyosu.kopyala')}
                  </Button>
                  <Button type="button" size="sm" className="gap-1.5" onClick={() => planla(u, v)} data-testid="is-planlayiciya-ekle">
                    <CalendarPlus className="h-3.5 w-3.5" aria-hidden="true" />
                    {t('icerikStudyosu.yazar.planla')}
                  </Button>
                  {u.sablon === 'eposta_bulten' && (
                    <Button type="button" size="sm" variant="outline" className={DIS_DUGME} onClick={() => aktar(u, v)} disabled={!!calisiyor} data-testid="is-kampanyaya-aktar">
                      <Mail className="h-3.5 w-3.5" aria-hidden="true" />
                      {t('icerikStudyosu.yazar.kampanyayaAktar')}
                    </Button>
                  )}
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-1.5 border-t border-white/5 pt-2">
                  <span className="text-[11px] text-muted-foreground">{t('icerikStudyosu.yazar.inceAyar')}:</span>
                  {(['kisalt', 'samimi', 'emoji_ekle', 'emoji_cikar'] as InceAyar[]).map((islem) => {
                    const Ikon = INCE_AYAR_IKONU[islem];
                    return (
                      <button key={islem} type="button" disabled={!!calisiyor || (islem !== 'emoji_cikar' && !meta.ai_hazir)} title={islem !== 'emoji_cikar' ? aiKapaliIpucu : undefined}
                        onClick={() => inceAyar(u, v, islem)} data-ince-ayar={islem}
                        className="inline-flex items-center gap-1 rounded-md border border-white/10 px-2 py-1 text-[11px] hover:bg-white/5 disabled:opacity-50">
                        {calisiyor === `ince-${u.id}-${islem}` ? <Loader2 className="h-3 w-3 animate-spin" /> : <Ikon className="h-3 w-3" aria-hidden="true" />}
                        {t(`icerikStudyosu.islem.${islem}`)}
                      </button>
                    );
                  })}
                  <span className="inline-flex items-center gap-1">
                    <select className="h-7 rounded-md border border-white/10 bg-black/40 px-1 text-[11px]" value={cevirDili} onChange={(e) => setCevirDili(e.target.value)} aria-label={t('icerikStudyosu.yazar.cevirDili')}>
                      {DILLER.map((d) => (
                        <option key={d} value={d}>{t(`icerikStudyosu.dil.${d}`)}</option>
                      ))}
                    </select>
                    <button type="button" disabled={!!calisiyor || !meta.ai_hazir} title={aiKapaliIpucu} onClick={() => inceAyar(u, v, 'cevir')} data-ince-ayar="cevir"
                      className="inline-flex items-center gap-1 rounded-md border border-white/10 px-2 py-1 text-[11px] hover:bg-white/5 disabled:opacity-50">
                      {calisiyor === `ince-${u.id}-cevir` ? <Loader2 className="h-3 w-3 animate-spin" /> : <Languages className="h-3 w-3" aria-hidden="true" />}
                      {t('icerikStudyosu.islem.cevir')}
                    </button>
                  </span>
                </div>
              </article>
            ))}
          </section>
        ))}
      </div>
    </div>
  );
}

function GenelAyarlarKarti({ api, onKaydet }: { api: StudyoApi; onKaydet: () => Promise<void> }) {
  const { t } = useTranslation();
  const [acik, setAcik] = useState(false);
  const [a, setA] = useState<GenelAyarlar | null>(null);
  const [kaydediliyor, setKaydediliyor] = useState(false);

  useEffect(() => {
    if (acik && !a) api.ayarlar().then(setA).catch((e) => toast.error(hataMetni(t, e)));
  }, [acik, a, api, t]);

  const kaydet = async () => {
    if (!a) return;
    setKaydediliyor(true);
    try {
      setA(await api.ayarlarYaz({ model: a.model_ayari, gunluk_butce: a.gunluk_butce, blok_uretim: a.blok_uretim, blok_kredi: a.blok_kredi, ajans_gunluk: a.ajans_gunluk }));
      toast.success(t('icerikStudyosu.form.kaydedildi'));
      await onKaydet();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setKaydediliyor(false);
    }
  };

  return (
    <div className="border-t border-white/10 pt-3">
      <button type="button" className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-white" onClick={() => setAcik(!acik)} aria-expanded={acik}>
        <Settings2 className="h-3.5 w-3.5" aria-hidden="true" />
        {t('icerikStudyosu.ayarlar.baslik')}
      </button>
      {acik && a && (
        <div className="mt-2 space-y-2">
          <Alan etiket={t('icerikStudyosu.ayarlar.model')} ipucu={t('icerikStudyosu.ayarlar.modelIpucu', { model: a.model })}>
            <input className={GIRDI} value={a.model_ayari} onChange={(e) => setA({ ...a, model_ayari: e.target.value })} dir="ltr" />
          </Alan>
          <div className="grid grid-cols-2 gap-2">
            {(['blok_uretim', 'blok_kredi', 'gunluk_butce', 'ajans_gunluk'] as const).map((k) => (
              <Alan key={k} etiket={t(`icerikStudyosu.ayarlar.${k}`)}>
                <input className={GIRDI} type="number" min={0} step={k === 'blok_kredi' ? 0.25 : 1} value={a[k]}
                  onChange={(e) => setA({ ...a, [k]: k === 'blok_kredi' ? Number(e.target.value) : Math.round(Number(e.target.value)) })} />
              </Alan>
            ))}
          </div>
          <Button type="button" size="sm" onClick={kaydet} disabled={kaydediliyor}>
            {kaydediliyor && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            {t('icerikStudyosu.kaydet')}
          </Button>
        </div>
      )}
    </div>
  );
}
