import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Bot, CheckCircle2, Eye, EyeOff, Link2, Plus, RefreshCw, Share2, Target } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { CheckinFormu, HedefFormu, KrFormu } from '@/components/hedefler/Formlar';
import { Bos, DIS_DUGME, HataSatiri, IlerlemeCubugu, KART, Rozet, Yukleniyor } from '@/components/hedefler/ortak';
import {
  degerYaz,
  donemAdi,
  DURUM_METIN_RENGI,
  gunYaz,
  GUVEN_RENGI,
  hataMetni,
  yuzde,
  type Donem,
  type DonemOzeti,
  type Hedef,
  type Kr,
  type Meta,
  type OkrApi,
} from '@/lib/okr';

export interface BolumProps {
  api: OkrApi;
  meta: Meta;
  donem: Donem;
  surum: number;
  yenile: () => void;
  ac: (hedefId: number) => void;
}

/** KR satırı (liste ve ayrıntı): başlık, değer → hedef, ilerleme çubuğu, güven ve kaynak rozetleri, hızlı eylemler. */
export function KrSatiri({ kr, beklenen, yazabilir, onCheckin, onYenile }: {
  kr: Kr;
  beklenen: number;
  yazabilir: boolean;
  onCheckin?: () => void;
  onYenile?: () => void;
}) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const durum = kr.ilerleme >= 1 ? 'tamam' : kr.ilerleme >= beklenen - 0.1 ? 'yolunda' : kr.ilerleme >= beklenen - 0.25 ? 'riskli' : 'geride';
  const deger =
    kr.tur === 'kilometre'
      ? t('hedefler.kr.kilometreSayisi', { tamam: kr.kilometre_tamam, toplam: kr.kilometre_toplam })
      : `${degerYaz(kr, kr.mevcut, dil, t)} / ${degerYaz(kr, kr.hedef, dil, t)}`;
  return (
    <li className="grid gap-1.5 py-2" data-testid="okr-kr" data-kr={kr.id} data-ilerleme={Math.round(kr.ilerleme * 100)}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <span className="min-w-0 flex-1 break-words text-sm">{kr.baslik}</span>
        <span className="flex flex-wrap items-center gap-1">
          {kr.kaynak && (
            <Rozet renk="border-sky-400/30 bg-sky-500/10 text-sky-100" testid="okr-kr-otomatik">
              <Bot className="h-3 w-3" aria-hidden="true" />
              {t('hedefler.kr.otomatik')}
            </Rozet>
          )}
          {kr.guven && <Rozet renk={GUVEN_RENGI[kr.guven]}>{t(`hedefler.guven.${kr.guven}`)}</Rozet>}
          {kr.kapanis_puani !== null && <Rozet>{t('hedefler.kapanis.puanKisa', { puan: kr.kapanis_puani })}</Rozet>}
        </span>
      </div>
      <div className="flex items-center gap-2">
        <div className="min-w-0 flex-1">
          <IlerlemeCubugu ilerleme={kr.ilerleme} beklenen={beklenen} durum={durum} etiket={kr.baslik} kucuk testid="okr-kr-cubuk" />
        </div>
        <span className={`w-12 flex-none text-end text-xs tabular-nums ${DURUM_METIN_RENGI[durum]}`}>{yuzde(kr.ilerleme, dil)}</span>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
        <span className="min-w-0 break-words" data-testid="okr-kr-deger">
          {deger}
          {kr.kaynak_hata ? ` · ${t(`hedefler.hata.${kr.kaynak_hata}`, { defaultValue: t('hedefler.hata.genel') })}` : ''}
        </span>
        {yazabilir && (
          <span className="flex gap-1">
            {kr.kaynak && onYenile && (
              <Button type="button" size="sm" variant="ghost" className="h-7 gap-1 px-2 text-xs" onClick={onYenile} data-testid="okr-kr-yenile">
                <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
                {t('hedefler.kr.simdiYenile')}
              </Button>
            )}
            {onCheckin && (
              <Button type="button" size="sm" variant="ghost" className="h-7 gap-1 px-2 text-xs" onClick={onCheckin} data-testid="okr-kr-checkin">
                <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
                {t('hedefler.checkin.dugme')}
              </Button>
            )}
          </span>
        )}
      </div>
    </li>
  );
}

/**
 * Faz 6O — dönem listesi: dönemin genel ilerlemesi (beklenen ilerleme çizgisiyle), hedefler (ilerleme çubuğu, sahibi,
 * taslak / özel / paylaşılan rozetleri) ve KR'leri; hedef ekle, KR ekle, check-in, otomatik KR "şimdi yenile".
 */
export default function Liste({ api, meta, donem, surum, yenile, ac }: BolumProps) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [oz, setOz] = useState<DonemOzeti | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [hedefFormu, setHedefFormu] = useState<Hedef | 'yeni' | null>(null);
  const [krFormu, setKrFormu] = useState<Hedef | null>(null);
  const [checkin, setCheckin] = useState<Kr | null>(null);
  const [ic, setIc] = useState(0);
  const acik = donem.durum === 'acik';
  const yazabilir = !meta.okur && acik;

  const yukle = useCallback(async () => {
    setHata(null);
    try {
      setOz(await api.donemOzeti(donem.id));
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  }, [api, donem.id, t]);

  useEffect(() => {
    void yukle();
  }, [yukle, surum, ic]);

  const krYenile = async (kr: Kr) => {
    try {
      await api.krYenile(kr.id);
      setIc((x) => x + 1);
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  };

  if (!oz) return hata ? <HataSatiri hata={hata} /> : <Yukleniyor />;
  const beklenen = oz.donem.beklenen;
  return (
    <div className="grid gap-4" data-testid="okr-liste">
      <div className={`${KART} grid gap-2 p-4`}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="min-w-0">
            <p className="font-semibold">{donemAdi(t, oz.donem, dil)}</p>
            <p className="text-xs text-muted-foreground">
              {gunYaz(oz.donem.baslangic, dil)} – {gunYaz(oz.donem.bitis, dil)}
              {oz.donem.durum === 'kapandi' ? ` · ${t('hedefler.donem.kapandi')}` : ''}
            </p>
          </div>
          <div className="text-end">
            <p className={`text-2xl font-bold tabular-nums ${oz.durum_rengi ? DURUM_METIN_RENGI[oz.durum_rengi] : ''}`} data-testid="okr-genel-ilerleme">
              {yuzde(oz.ilerleme, dil)}
            </p>
            <p className="text-xs text-muted-foreground">{t('hedefler.liste.beklenen', { oran: yuzde(beklenen, dil) })}</p>
          </div>
        </div>
        <IlerlemeCubugu ilerleme={oz.ilerleme} beklenen={beklenen} durum={oz.durum_rengi} etiket={t('hedefler.liste.genel')} testid="okr-genel-cubuk" />
        {oz.durum_rengi && <p className={`text-xs ${DURUM_METIN_RENGI[oz.durum_rengi]}`}>{t(`hedefler.durumRengi.${oz.durum_rengi}`)}</p>}
      </div>
      <HataSatiri hata={hata} />
      {yazabilir && (
        <div>
          <Button type="button" onClick={() => setHedefFormu('yeni')} className="gap-1.5 bg-gradient-to-r from-purple-600 to-pink-600 text-white" data-testid="okr-hedef-yeni">
            <Plus className="h-4 w-4" aria-hidden="true" />
            {t('hedefler.hedef.yeni')}
          </Button>
        </div>
      )}
      {oz.hedefler.length === 0 ? (
        <Bos testid="okr-hedef-bos">{t('hedefler.liste.bos')}</Bos>
      ) : (
        oz.hedefler.map((h) => (
          <article key={h.id} className={`${KART} p-4`} data-testid="okr-hedef" data-hedef={h.id} data-ilerleme={h.ilerleme === null ? '' : Math.round(h.ilerleme * 100)}>
            <div className="flex flex-wrap items-start justify-between gap-2">
              <button type="button" onClick={() => ac(h.id)} className="min-w-0 flex-1 text-start" data-testid="okr-hedef-ac">
                <span className="flex items-start gap-2">
                  <Target className="mt-0.5 h-4 w-4 flex-none text-purple-300" aria-hidden="true" />
                  <span className="min-w-0 break-words font-semibold hover:underline">{h.baslik}</span>
                </span>
                {h.sahip && <span className="ms-6 block truncate text-xs text-muted-foreground">{h.sahip}</span>}
              </button>
              <span className="flex flex-wrap items-center gap-1">
                {h.durum !== 'etkin' && <Rozet>{t(`hedefler.hedef.durumlar.${h.durum}`)}</Rozet>}
                {h.gorunurluk === 'ozel' ? (
                  <Rozet>
                    <EyeOff className="h-3 w-3" aria-hidden="true" />
                    {t('hedefler.hedef.gorunurlukler.ozel')}
                  </Rozet>
                ) : null}
                {h.ust_id && (
                  <Rozet>
                    <Link2 className="h-3 w-3" aria-hidden="true" />
                    {t('hedefler.hedef.hizali')}
                  </Rozet>
                )}
                {h.musteri_paylasim && (
                  <Rozet renk="border-emerald-400/30 bg-emerald-500/10 text-emerald-100" testid="okr-paylasildi">
                    <Share2 className="h-3 w-3" aria-hidden="true" />
                    {t('hedefler.hedef.paylasildi')}
                  </Rozet>
                )}
                {meta.ajans && h.musteri_email && !h.musteri_paylasim && (
                  <Rozet>
                    <Eye className="h-3 w-3" aria-hidden="true" />
                    {h.musteri_email}
                  </Rozet>
                )}
              </span>
            </div>
            <div className="mt-3 flex items-center gap-2">
              <div className="min-w-0 flex-1">
                <IlerlemeCubugu ilerleme={h.ilerleme} beklenen={beklenen} durum={h.durum_rengi} etiket={h.baslik} testid="okr-hedef-cubuk" />
              </div>
              <span className={`w-12 flex-none text-end text-sm font-semibold tabular-nums ${h.durum_rengi ? DURUM_METIN_RENGI[h.durum_rengi] : ''}`}>
                {yuzde(h.ilerleme, dil)}
              </span>
            </div>
            {h.krler.length > 0 ? (
              <ul className="mt-2 divide-y divide-white/5">
                {h.krler.map((kr) => (
                  <KrSatiri
                    key={kr.id}
                    kr={kr}
                    beklenen={beklenen}
                    yazabilir={yazabilir && h.durum !== 'kapandi'}
                    onCheckin={() => setCheckin(kr)}
                    onYenile={() => void krYenile(kr)}
                  />
                ))}
              </ul>
            ) : (
              <p className="mt-2 text-xs text-muted-foreground">{t('hedefler.kr.yok')}</p>
            )}
            {yazabilir && h.durum !== 'kapandi' && h.krler.length < meta.sabitler.en_cok_kr && (
              <Button type="button" size="sm" variant="outline" className={`${DIS_DUGME} mt-2`} onClick={() => setKrFormu(h)} data-testid="okr-kr-yeni">
                <Plus className="h-4 w-4" aria-hidden="true" />
                {t('hedefler.kr.yeni')}
              </Button>
            )}
          </article>
        ))
      )}
      {hedefFormu && (
        <HedefFormu
          api={api}
          meta={meta}
          donem={donem}
          hedef={hedefFormu === 'yeni' ? null : hedefFormu}
          onKapat={() => setHedefFormu(null)}
          onKaydet={() => {
            setHedefFormu(null);
            yenile();
          }}
        />
      )}
      {krFormu && (
        <KrFormu
          api={api}
          meta={meta}
          hedef={krFormu}
          kr={null}
          onKapat={() => setKrFormu(null)}
          onKaydet={() => {
            setKrFormu(null);
            setIc((x) => x + 1);
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
            setIc((x) => x + 1);
          }}
        />
      )}
    </div>
  );
}
