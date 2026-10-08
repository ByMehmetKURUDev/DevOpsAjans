import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowUpRight, History, Pencil, Timer, Trash2 } from 'lucide-react';
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

import { Button } from '@/components/ui/button';
import { CheckinFormu, HedefFormu, KrFormu } from '@/components/hedefler/Formlar';
import { KrSatiri } from '@/components/hedefler/Liste';
import OdakSayaci from '@/components/hedefler/OdakSayaci';
import { DIS_DUGME, HataSatiri, IlerlemeCubugu, KART, Pencere, Rozet, Yukleniyor } from '@/components/hedefler/ortak';
import {
  degerYaz,
  donemAdi,
  gunYaz,
  GUVEN_RENGI,
  hataMetni,
  yuzde,
  zamanYaz,
  type HedefAyrinti,
  type Kr,
  type Meta,
  type OkrApi,
} from '@/lib/okr';

const IPUCU = { background: '#150a2b', border: '1px solid rgba(167,139,250,0.4)', borderRadius: 12, color: '#ece6ff' };
const EKSEN = '#b9a9d6';

/** Check-in geçmişinin küçük çizgi grafiği (recharts — projede zaten var; yeni paket yok). */
function GecmisGrafigi({ kr }: { kr: Kr }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const noktalar = [...(kr.checkinler || [])]
    .filter((c) => c.tur !== 'odak')
    .reverse()
    .map((c) => ({ tarih: c.tarih, deger: kr.tur === 'para' ? c.deger / 100 : c.deger }));
  if (noktalar.length < 2) return null;
  return (
    <div className="h-28 w-full" data-testid="okr-grafik" role="img" aria-label={t('hedefler.ayrinti.grafik')}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={noktalar} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
          <XAxis dataKey="tarih" stroke={EKSEN} fontSize={10} tickLine={false} tickFormatter={(v: string) => gunYaz(v, dil).replace(/\s?\d{4}$/, '')} />
          <YAxis stroke={EKSEN} fontSize={10} tickLine={false} width={44} domain={['auto', 'auto']} />
          <Tooltip contentStyle={IPUCU} formatter={(v: number) => degerYaz(kr, kr.tur === 'para' ? v * 100 : v, dil, t)} labelFormatter={(v: string) => gunYaz(v, dil)} />
          <Line type="monotone" dataKey="deger" stroke="#a78bfa" strokeWidth={2} dot={{ r: 2.5 }} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

/**
 * Faz 6O — hedef ayrıntısı (pencere): açıklama, sahibi, üst / alt hedefler, KR'ler ve her birinin check-in geçmişi
 * (küçük çizgi grafik + liste; otomatik değişim ve odak oturumu ayrı işaretli), taşıma geçmişi (önceki dönemlerdeki
 * kopya), düzenle / sil, check-in, "şimdi yenile", odak sayacı (25/5).
 */
export default function Ayrinti({ api, meta, hedefId, onKapat, onDegisti, ac }: {
  api: OkrApi;
  meta: Meta;
  hedefId: number;
  onKapat: () => void;
  onDegisti: () => void;
  ac: (id: number) => void;
}) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [h, setH] = useState<HedefAyrinti | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [duzenle, setDuzenle] = useState(false);
  const [krFormu, setKrFormu] = useState<Kr | null>(null);
  const [checkin, setCheckin] = useState<Kr | null>(null);
  const [odak, setOdak] = useState<Kr | null>(null);

  const yukle = useCallback(async () => {
    setHata(null);
    try {
      setH(await api.hedef(hedefId));
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  }, [api, hedefId, t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const degisti = () => {
    onDegisti();
    void yukle();
  };
  const sil = async () => {
    if (!h || !window.confirm(t('hedefler.hedef.silOnay'))) return;
    try {
      await api.hedefSil(h.id);
      onDegisti();
      onKapat();
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  };
  const krSil = async (kr: Kr) => {
    if (!window.confirm(t('hedefler.kr.silOnay'))) return;
    try {
      await api.krSil(kr.id);
      degisti();
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  };
  const krYenile = async (kr: Kr) => {
    try {
      await api.krYenile(kr.id);
      degisti();
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  };

  const acik = !!h && h.donem.durum === 'acik' && h.durum !== 'kapandi';
  const yazabilir = !meta.okur && acik;
  return (
    <Pencere baslik={h?.baslik || t('hedefler.ayrinti.baslik')} onKapat={onKapat} genis testid="okr-ayrinti">
      <HataSatiri hata={hata} />
      {!h ? (
        !hata && <Yukleniyor />
      ) : (
        <div className="grid gap-4">
          <div className="grid gap-2">
            <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
              <span>{donemAdi(t, h.donem, dil)}</span>
              {h.sahip && <span>· {h.sahip}</span>}
              <Rozet>{t(`hedefler.hedef.durumlar.${h.durum}`)}</Rozet>
              <Rozet>{t(`hedefler.hedef.gorunurlukler.${h.gorunurluk}`)}</Rozet>
              {h.musteri_paylasim && <Rozet renk="border-emerald-400/30 bg-emerald-500/10 text-emerald-100">{t('hedefler.hedef.paylasildi')}</Rozet>}
            </div>
            {h.aciklama && <p className="whitespace-pre-line break-words text-sm text-white/85">{h.aciklama}</p>}
            <div className="flex items-center gap-2">
              <div className="min-w-0 flex-1">
                <IlerlemeCubugu ilerleme={h.ilerleme} beklenen={h.donem.beklenen} durum={h.durum_rengi} etiket={h.baslik} testid="okr-ayrinti-cubuk" />
              </div>
              <span className="w-12 flex-none text-end text-sm font-semibold tabular-nums">{yuzde(h.ilerleme, dil)}</span>
            </div>
            {(h.ust || h.altlar.length > 0) && (
              <div className="flex flex-wrap gap-1.5 text-xs">
                {h.ust && (
                  <button type="button" className="inline-flex items-center gap-1 rounded-full border border-white/10 px-2 py-0.5 hover:bg-white/5" onClick={() => ac(h.ust!.id)}>
                    <ArrowUpRight className="h-3 w-3" aria-hidden="true" />
                    {t('hedefler.hedef.ust')}: {h.ust.baslik}
                  </button>
                )}
                {h.altlar.map((a) => (
                  <button key={a.id} type="button" className="rounded-full border border-white/10 px-2 py-0.5 hover:bg-white/5" onClick={() => ac(a.id)}>
                    {t('hedefler.ayrinti.alt')}: {a.baslik}
                  </button>
                ))}
              </div>
            )}
            {yazabilir && (
              <div className="flex flex-wrap gap-2">
                <Button type="button" size="sm" variant="outline" className={DIS_DUGME} onClick={() => setDuzenle(true)} data-testid="okr-hedef-duzenle">
                  <Pencil className="h-4 w-4" aria-hidden="true" />
                  {t('hedefler.ortak.duzenle')}
                </Button>
                <Button type="button" size="sm" variant="ghost" className="gap-1.5 text-rose-300" onClick={() => void sil()} data-testid="okr-hedef-sil">
                  <Trash2 className="h-4 w-4" aria-hidden="true" />
                  {t('hedefler.ortak.sil')}
                </Button>
              </div>
            )}
          </div>
          {h.krler.length === 0 && <p className="text-sm text-muted-foreground">{t('hedefler.kr.yok')}</p>}
          {h.krler.map((kr) => (
            <section key={kr.id} className={`${KART} grid gap-2 p-3`} data-testid="okr-ayrinti-kr">
              <ul>
                <KrSatiri kr={kr} beklenen={h.donem.beklenen} yazabilir={yazabilir} onCheckin={() => setCheckin(kr)} onYenile={() => void krYenile(kr)} />
              </ul>
              {kr.kaynak && (
                <p className="text-xs text-muted-foreground">
                  {t(`hedefler.kaynak.${kr.kaynak}`)} · {t('hedefler.kr.sonYenileme')}: {zamanYaz(kr.kaynak_son_yenileme, dil)}
                </p>
              )}
              <GecmisGrafigi kr={kr} />
              {(kr.checkinler || []).length > 0 && (
                <details className="text-xs">
                  <summary className="cursor-pointer text-muted-foreground">
                    <History className="me-1 inline h-3.5 w-3.5" aria-hidden="true" />
                    {t('hedefler.ayrinti.gecmis', { sayi: (kr.checkinler || []).length })}
                  </summary>
                  <ul className="mt-2 grid gap-1.5" data-testid="okr-gecmis">
                    {(kr.checkinler || []).slice(0, 20).map((c) => (
                      <li key={c.id} className="rounded-lg border border-white/5 p-2">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className="tabular-nums">{gunYaz(c.tarih, dil)}</span>
                          {c.tur === 'odak' ? (
                            <Rozet>{t('hedefler.odak.kayit', { dk: c.sure_dk ?? 0 })}</Rozet>
                          ) : (
                            <span className="font-medium">{degerYaz(kr, c.deger, dil, t)}</span>
                          )}
                          {c.tur === 'otomatik' && <Rozet>{t('hedefler.kr.otomatik')}</Rozet>}
                          {c.guven && <Rozet renk={GUVEN_RENGI[c.guven]}>{t(`hedefler.guven.${c.guven}`)}</Rozet>}
                          {c.yazan && <span className="truncate text-muted-foreground">{c.yazan}</span>}
                        </div>
                        {c.notlar && <p className="mt-1 whitespace-pre-line break-words text-white/80">{c.notlar}</p>}
                      </li>
                    ))}
                  </ul>
                </details>
              )}
              {(kr.tasima_gecmisi || []).length > 0 && (
                <p className="text-xs text-muted-foreground" data-testid="okr-tasima">
                  {t('hedefler.ayrinti.tasindi')}{' '}
                  {(kr.tasima_gecmisi || []).map((g) => `${g.donem ?? ''} (${yuzde(g.ilerleme, dil)}${g.kapanis_puani !== null ? ` · ${t('hedefler.kapanis.puanKisa', { puan: g.kapanis_puani })}` : ''}, ${t('hedefler.ayrinti.checkinSayisi', { sayi: g.checkin_sayisi })})`).join(' ← ')}
                </p>
              )}
              {yazabilir && (
                <div className="flex flex-wrap gap-1">
                  <Button type="button" size="sm" variant="ghost" className="h-8 gap-1 px-2 text-xs" onClick={() => setKrFormu(kr)} data-testid="okr-kr-duzenle">
                    <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                    {t('hedefler.ortak.duzenle')}
                  </Button>
                  <Button type="button" size="sm" variant="ghost" className="h-8 gap-1 px-2 text-xs" onClick={() => setOdak(odak?.id === kr.id ? null : kr)} data-testid="okr-odak-ac">
                    <Timer className="h-3.5 w-3.5" aria-hidden="true" />
                    {t('hedefler.odak.baslik')}
                  </Button>
                  <Button type="button" size="sm" variant="ghost" className="h-8 gap-1 px-2 text-xs text-rose-300" onClick={() => void krSil(kr)}>
                    <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                    {t('hedefler.ortak.sil')}
                  </Button>
                </div>
              )}
              {odak?.id === kr.id && <OdakSayaci api={api} kr={kr} calisma={meta.sabitler.odak_dk} mola={meta.sabitler.mola_dk} onKaydedildi={() => void yukle()} />}
            </section>
          ))}
        </div>
      )}
      {h && duzenle && (
        <HedefFormu
          api={api}
          meta={meta}
          donem={h.donem}
          hedef={h}
          onKapat={() => setDuzenle(false)}
          onKaydet={() => {
            setDuzenle(false);
            degisti();
          }}
        />
      )}
      {h && krFormu && (
        <KrFormu
          api={api}
          meta={meta}
          hedef={h}
          kr={krFormu}
          onKapat={() => setKrFormu(null)}
          onKaydet={() => {
            setKrFormu(null);
            degisti();
          }}
        />
      )}
      {checkin && (
        <CheckinFormu
          api={api}
          kr={checkin}
          onKapat={() => setCheckin(null)}
          onKaydet={() => {
            setCheckin(null);
            degisti();
          }}
        />
      )}
    </Pencere>
  );
}
