import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, ChevronLeft, ChevronRight, Copy, Download, FileText, Layers, Loader2, Plus, Send, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Alan, Anahtar, Bos, DIS_DUGME, GIRDI, KART, Pencere, Rozet, SECIM, Uyarilar, YasalNot, Yukleniyor, uyariMetni } from '@/components/ik/ortak';
import {
  gunAdlari,
  gunEkle,
  gunYaz,
  haftaBasi,
  hataMetni,
  saatYaz,
  type HaftaPlani,
  type IkApi,
  type Meta,
  type Sablon,
  type Uyari,
  type Vardiya,
} from '@/lib/ik';

type Duzenleme = { personel_id: number; tarih: string; vardiya?: Vardiya };

function SablonPenceresi({ api, sablonlar, onKapat, onDegisti, salt }: { api: IkApi; sablonlar: Sablon[]; onKapat: () => void; onDegisti: () => void; salt: boolean }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [form, setForm] = useState({ ad: '', baslangic: '09:00', bitis: '18:00', mola_dk: '60', renk: '#7c3aed' });
  const [mesgul, setMesgul] = useState(false);
  const ekle = async () => {
    setMesgul(true);
    try {
      await api.sablonEkle({ ad: form.ad.trim(), baslangic: form.baslangic, bitis: form.bitis, mola_dk: Number(form.mola_dk || 0), renk: form.renk });
      setForm({ ...form, ad: '' });
      toast.success(t('ik.vardiya.sablonEklendi'));
      onDegisti();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };
  return (
    <Pencere baslik={t('ik.vardiya.sablonlar')} onKapat={onKapat} testid="ik-sablon-penceresi">
      {sablonlar.length === 0 ? (
        <p className="mb-3 text-sm text-muted-foreground">{t('ik.vardiya.sablonYok')}</p>
      ) : (
        <ul className="mb-4 space-y-1.5">
          {sablonlar.map((s) => (
            <li key={s.id} className="flex items-center gap-2 rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-sm">
              <span className="h-3 w-3 flex-none rounded-full" style={{ background: s.renk }} aria-hidden="true" />
              <span className="min-w-0 flex-1 truncate font-medium">{s.ad}</span>
              <span className="text-xs text-muted-foreground" dir="ltr">
                {s.baslangic}–{s.bitis}
              </span>
              <span className="text-xs text-muted-foreground">{t('ik.vardiya.netSaat', { saat: saatYaz(s.net_dk, dil) })}</span>
              {!salt && (
                <Button
                  size="icon"
                  variant="ghost"
                  className="h-7 w-7"
                  aria-label={t('ik.sil')}
                  onClick={() =>
                    void api
                      .sablonSil(s.id)
                      .then(onDegisti)
                      .catch((e) => toast.error(hataMetni(t, e)))
                  }
                >
                  <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
      {!salt && (
        <div className="grid gap-2 sm:grid-cols-2">
          <Alan etiket={t('ik.vardiya.sablonAdi')} className="sm:col-span-2">
            <input className={GIRDI} value={form.ad} onChange={(e) => setForm({ ...form, ad: e.target.value })} maxLength={60} placeholder={t('ik.vardiya.sablonAdiOrnek')} data-testid="ik-sablon-ad" />
          </Alan>
          <Alan etiket={t('ik.vardiya.baslangic')}>
            <input className={GIRDI} type="time" value={form.baslangic} onChange={(e) => setForm({ ...form, baslangic: e.target.value })} data-testid="ik-sablon-bas" />
          </Alan>
          <Alan etiket={t('ik.vardiya.bitis')} ipucu={t('ik.vardiya.geceIpucu')}>
            <input className={GIRDI} type="time" value={form.bitis} onChange={(e) => setForm({ ...form, bitis: e.target.value })} data-testid="ik-sablon-bit" />
          </Alan>
          <Alan etiket={t('ik.vardiya.mola')}>
            <input className={GIRDI} inputMode="numeric" value={form.mola_dk} onChange={(e) => setForm({ ...form, mola_dk: e.target.value.replace(/\D/g, '') })} />
          </Alan>
          <Alan etiket={t('ik.vardiya.renk')}>
            <input className={`${GIRDI} p-1`} type="color" value={form.renk} onChange={(e) => setForm({ ...form, renk: e.target.value })} />
          </Alan>
          <div className="flex justify-end sm:col-span-2">
            <Button onClick={() => void ekle()} disabled={mesgul || !form.ad.trim()} data-testid="ik-sablon-ekle">
              {mesgul ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Plus className="h-4 w-4" aria-hidden="true" />}
              {t('ik.vardiya.sablonEkle')}
            </Button>
          </div>
        </div>
      )}
    </Pencere>
  );
}

function VardiyaPenceresi({
  api,
  duzen,
  sablonlar,
  adi,
  onKapat,
  onKaydedildi,
}: {
  api: IkApi;
  duzen: Duzenleme;
  sablonlar: Sablon[];
  adi: string;
  onKapat: () => void;
  onKaydedildi: (u: Uyari[]) => void;
}) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const v = duzen.vardiya;
  const [sablon, setSablon] = useState<string>(v?.sablon_id ? String(v.sablon_id) : '');
  const [bas, setBas] = useState(v?.baslangic || '09:00');
  const [bit, setBit] = useState(v?.bitis || '17:00');
  const [mola, setMola] = useState(String(v?.mola_dk ?? 0));
  const [not, setNot] = useState(v?.notlar || '');
  const [mesgul, setMesgul] = useState(false);

  const sablonSec = (id: string) => {
    setSablon(id);
    const s = sablonlar.find((x) => String(x.id) === id);
    if (s) {
      setBas(s.baslangic);
      setBit(s.bitis);
      setMola(String(s.mola_dk));
    }
  };

  const kaydet = async () => {
    setMesgul(true);
    const govde = { personel_id: duzen.personel_id, tarih: duzen.tarih, sablon_id: sablon ? Number(sablon) : null, baslangic: bas, bitis: bit, mola_dk: Number(mola || 0), notlar: not };
    try {
      const r = v ? await api.vardiyaGuncelle(v.id, govde) : await api.vardiyaEkle(govde);
      onKaydedildi(r.uyarilar);
      onKapat();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  const sil = async () => {
    if (!v) return;
    setMesgul(true);
    try {
      await api.vardiyaSil(v.id);
      onKaydedildi([]);
      onKapat();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  return (
    <Pencere baslik={`${adi} — ${gunYaz(duzen.tarih, dil, { weekday: 'long', day: 'numeric', month: 'long' })}`} onKapat={onKapat} testid="ik-vardiya-penceresi">
      <div className="grid gap-3 sm:grid-cols-2">
        {sablonlar.length > 0 && (
          <Alan etiket={t('ik.vardiya.sablon')} className="sm:col-span-2">
            <select className={SECIM} value={sablon} onChange={(e) => sablonSec(e.target.value)} data-testid="ik-vardiya-sablon">
              <option value="">{t('ik.vardiya.ozelSaat')}</option>
              {sablonlar.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.ad} ({s.baslangic}–{s.bitis})
                </option>
              ))}
            </select>
          </Alan>
        )}
        <Alan etiket={t('ik.vardiya.baslangic')}>
          <input className={GIRDI} type="time" value={bas} onChange={(e) => setBas(e.target.value)} data-testid="ik-vardiya-bas" />
        </Alan>
        <Alan etiket={t('ik.vardiya.bitis')} ipucu={t('ik.vardiya.geceIpucu')}>
          <input className={GIRDI} type="time" value={bit} onChange={(e) => setBit(e.target.value)} data-testid="ik-vardiya-bit" />
        </Alan>
        <Alan etiket={t('ik.vardiya.mola')}>
          <input className={GIRDI} inputMode="numeric" value={mola} onChange={(e) => setMola(e.target.value.replace(/\D/g, ''))} />
        </Alan>
        <Alan etiket={t('ik.vardiya.not')}>
          <input className={GIRDI} value={not} onChange={(e) => setNot(e.target.value)} maxLength={200} />
        </Alan>
        {v?.durum === 'yayinda' && <p className="text-xs text-amber-200 sm:col-span-2">{t('ik.vardiya.yayindaDegisiklik')}</p>}
        <div className="flex justify-between gap-2 sm:col-span-2">
          {v ? (
            <Button variant="outline" className={`${DIS_DUGME} text-rose-200`} onClick={() => void sil()} disabled={mesgul} data-testid="ik-vardiya-sil">
              <Trash2 className="h-4 w-4" aria-hidden="true" />
              {t('ik.sil')}
            </Button>
          ) : (
            <span />
          )}
          <Button onClick={() => void kaydet()} disabled={mesgul} data-testid="ik-vardiya-kaydet">
            {mesgul && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
            {t('ik.kaydet')}
          </Button>
        </div>
      </div>
    </Pencere>
  );
}

/** Faz 6I — haftalık vardiya ızgarası (personel × gün), şablonlar, kopyala, taslak → yayınla, uyarılar, PDF/CSV. */
export default function VardiyaBolumu({ api, meta }: { api: IkApi; meta: Meta }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [hafta, setHafta] = useState(haftaBasi(meta.bugun));
  const [plan, setPlan] = useState<HaftaPlani | null>(null);
  const [sablonlar, setSablonlar] = useState<Sablon[]>([]);
  const [boya, setBoya] = useState<number | null>(null);
  const [duzen, setDuzen] = useState<Duzenleme | null>(null);
  const [sablonAcik, setSablonAcik] = useState(false);
  const [mesgul, setMesgul] = useState(false);
  const [bildir, setBildir] = useState(true);
  const salt = meta.salt_okunur;

  const yukle = useCallback(async () => {
    try {
      setPlan(await api.hafta(hafta));
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  }, [api, hafta, t]);

  const sablonYukle = useCallback(async () => {
    try {
      setSablonlar((await api.sablonlar()).items.filter((s) => s.aktif));
    } catch {
      setSablonlar([]);
    }
  }, [api]);

  useEffect(() => {
    setPlan(null);
    void yukle();
  }, [yukle]);
  useEffect(() => {
    void sablonYukle();
  }, [sablonYukle]);

  const adlar = useMemo(() => Object.fromEntries((plan?.personel || []).map((p) => [p.id, p.ad])), [plan]);
  const uyariHaritasi = useMemo(() => {
    const h: Record<number, Uyari[]> = {};
    for (const u of plan?.uyarilar || []) {
      if (typeof u.vardiya_id === 'number') (h[u.vardiya_id] ||= []).push(u);
    }
    return h;
  }, [plan]);
  const gunler = gunAdlari(dil, 'short');

  const hucreTik = async (pid: number, tarih: string) => {
    if (salt) return;
    if (boya) {
      try {
        const r = await api.vardiyaEkle({ personel_id: pid, tarih, sablon_id: boya });
        if (r.uyarilar.length) toast.warning(r.uyarilar.map((u) => uyariMetni(t, u, dil, adlar)).join(' · '));
        await yukle();
      } catch (e) {
        toast.error(hataMetni(t, e));
      }
      return;
    }
    setDuzen({ personel_id: pid, tarih });
  };

  const kopyala = async () => {
    const uzerine = (plan?.sayilar.taslak || 0) > 0 && window.confirm(t('ik.vardiya.kopyalaUzerine'));
    setMesgul(true);
    try {
      const r = await api.kopyala(hafta, uzerine);
      toast.success(t('ik.vardiya.kopyalandi', { eklenen: r.eklenen, atlanan: r.atlanan }));
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  const yayinla = async () => {
    setMesgul(true);
    try {
      const r = await api.yayinla(hafta, bildir);
      toast.success(t('ik.vardiya.yayinlandi', { sayi: r.yayinlanan, bildirilen: r.bildirilen }));
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  const yayinBekleyen = (plan?.sayilar.taslak || 0) + (plan?.sayilar.degisti || 0);
  const sablonKapat = useCallback(() => setSablonAcik(false), []);
  const duzenKapat = useCallback(() => setDuzen(null), []);
  return (
    <div className="space-y-4">
      <div className={`${KART} flex flex-wrap items-center gap-2 p-3`}>
        <Button size="icon" variant="ghost" aria-label={t('ik.vardiya.oncekiHafta')} onClick={() => setHafta(gunEkle(hafta, -7))}>
          <ChevronLeft className="h-4 w-4 rtl:rotate-180" aria-hidden="true" />
        </Button>
        <span className="min-w-[11rem] text-center text-sm font-semibold" data-testid="ik-vardiya-hafta">
          {gunYaz(hafta, dil, { day: 'numeric', month: 'short' })} – {gunYaz(gunEkle(hafta, 6), dil, { day: 'numeric', month: 'short', year: 'numeric' })}
        </span>
        <Button size="icon" variant="ghost" aria-label={t('ik.vardiya.sonrakiHafta')} onClick={() => setHafta(gunEkle(hafta, 7))}>
          <ChevronRight className="h-4 w-4 rtl:rotate-180" aria-hidden="true" />
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setHafta(haftaBasi(meta.bugun))}>
          {t('ik.vardiya.buHafta')}
        </Button>
        {plan && (
          <span className="flex flex-wrap gap-1">
            <Rozet renk="border-white/20 bg-white/[0.05] text-white/80">{t('ik.vardiya.taslakSayisi', { sayi: plan.sayilar.taslak })}</Rozet>
            <Rozet renk="border-emerald-400/40 bg-emerald-500/15 text-emerald-200">{t('ik.vardiya.yayindaSayisi', { sayi: plan.sayilar.yayinda })}</Rozet>
          </span>
        )}
        <div className="ms-auto flex flex-wrap gap-2">
          <Button variant="outline" className={DIS_DUGME} onClick={() => setSablonAcik(true)} data-testid="ik-sablonlar">
            <Layers className="h-4 w-4" aria-hidden="true" />
            {t('ik.vardiya.sablonlar')}
          </Button>
          {!salt && (
            <Button variant="outline" className={DIS_DUGME} onClick={() => void kopyala()} disabled={mesgul} data-testid="ik-vardiya-kopyala">
              <Copy className="h-4 w-4" aria-hidden="true" />
              {t('ik.vardiya.kopyala')}
            </Button>
          )}
          <Button variant="outline" className={DIS_DUGME} onClick={() => void api.planCsv(hafta).catch((e) => toast.error(hataMetni(t, e)))}>
            <Download className="h-4 w-4" aria-hidden="true" />
            CSV
          </Button>
          <Button variant="outline" className={DIS_DUGME} onClick={() => void api.planPdf(hafta, dil).catch((e) => toast.error(hataMetni(t, e)))} data-testid="ik-vardiya-pdf">
            <FileText className="h-4 w-4" aria-hidden="true" />
            PDF
          </Button>
        </div>
      </div>
      {!salt && sablonlar.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 text-xs" role="group" aria-label={t('ik.vardiya.boyaModu')}>
          <span className="text-muted-foreground">{t('ik.vardiya.boyaModu')}:</span>
          <button
            type="button"
            onClick={() => setBoya(null)}
            aria-pressed={boya === null}
            className={`rounded-full border px-2.5 py-1 ${boya === null ? 'border-purple-400/60 bg-purple-500/20 text-white' : 'border-white/10 text-muted-foreground'}`}
          >
            {t('ik.vardiya.elle')}
          </button>
          {sablonlar.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => setBoya(boya === s.id ? null : s.id)}
              aria-pressed={boya === s.id}
              className={`flex items-center gap-1 rounded-full border px-2.5 py-1 ${boya === s.id ? 'border-white/60 bg-white/10 text-white' : 'border-white/10 text-muted-foreground'}`}
              data-ik-boya={s.id}
            >
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: s.renk }} aria-hidden="true" />
              {s.ad}
            </button>
          ))}
        </div>
      )}
      <div className={`${KART} p-2 sm:p-3`}>
        {!plan ? (
          <Yukleniyor />
        ) : plan.personel.length === 0 ? (
          <Bos>{t('ik.vardiya.personelYok')}</Bos>
        ) : (
          <div className="overflow-x-auto" data-testid="ik-vardiya-izgara">
            <table className="w-full min-w-[760px] table-fixed border-separate border-spacing-1 text-xs">
              {/* Gün sütunları eşit genişlikte: vardiyalı gün öbürlerini daraltmasın. */}
              <colgroup>
                <col className="w-36" />
                {plan.gunler.map((g) => (
                  <col key={g} />
                ))}
                <col className="w-14" />
              </colgroup>
              <thead>
                <tr>
                  <th className="sticky start-0 z-10 bg-[#140d22]/90 p-1 text-start font-medium text-muted-foreground">{t('ik.vardiya.personel')}</th>
                  {plan.gunler.map((g, i) => {
                    const tatil = plan.tatiller[g];
                    return (
                      <th key={g} className={`p-1 text-center font-medium ${tatil ? 'text-rose-200' : 'text-muted-foreground'}`}>
                        <span className="block">{gunler[i]}</span>
                        <span className="block text-[10px]">
                          {gunYaz(g, dil, { day: 'numeric', month: 'numeric' })}
                          {tatil ? ` · ${tatil < 1 ? '½' : ''}${t('ik.vardiya.tatil')}` : ''}
                        </span>
                      </th>
                    );
                  })}
                  <th className="p-1 text-end font-medium text-muted-foreground">{t('ik.vardiya.toplam')}</th>
                </tr>
              </thead>
              <tbody>
                {plan.personel.map((p) => {
                  const dk = plan.toplam_dk[String(p.id)] || 0;
                  const fazla = dk > plan.sinirlar.haftalik_en_cok_saat * 60;
                  return (
                    <tr key={p.id} data-personel-id={p.id}>
                      <th scope="row" className="sticky start-0 z-10 max-w-[9rem] truncate bg-[#140d22]/90 p-1 text-start font-medium">
                        {p.ad}
                        {p.departman && <span className="block truncate text-[10px] font-normal text-muted-foreground">{p.departman}</span>}
                      </th>
                      {plan.gunler.map((g) => {
                        const izin = plan.izinli[String(p.id)]?.[g];
                        const bekleyen = plan.bekleyen_izin[String(p.id)]?.includes(g);
                        const vardiyalar = plan.vardiyalar.filter((v) => v.personel_id === p.id && v.tarih === g);
                        return (
                          <td key={g} className="align-top">
                            <div
                              className={`flex min-h-[3.25rem] flex-col gap-1 rounded-lg border p-1 ${izin ? 'border-sky-400/30 bg-sky-500/10' : 'border-white/10 bg-black/20'} ${
                                !salt ? 'cursor-pointer hover:border-purple-400/40' : ''
                              }`}
                              onClick={(e) => {
                                if (e.target === e.currentTarget) void hucreTik(p.id, g);
                              }}
                              data-hucre={`${p.id}-${g}`}
                            >
                              {izin && <span className="rounded bg-sky-500/25 px-1 text-[10px] text-sky-100">{t(`ik.tur.${izin}`)}</span>}
                              {bekleyen && !izin && <span className="rounded border border-dashed border-amber-300/50 px-1 text-[10px] text-amber-200">{t('ik.vardiya.izinTalebi')}</span>}
                              {vardiyalar.map((v) => {
                                const s = sablonlar.find((x) => x.id === v.sablon_id);
                                const uy = uyariHaritasi[v.id];
                                return (
                                  <button
                                    key={v.id}
                                    type="button"
                                    onClick={() => !salt && setDuzen({ personel_id: p.id, tarih: g, vardiya: v })}
                                    className={`flex items-center gap-1 rounded px-1 py-0.5 text-start text-[11px] text-white ${v.durum === 'taslak' ? 'border border-dashed border-white/50' : ''}`}
                                    style={{ background: `${s?.renk || '#7c3aed'}${v.durum === 'taslak' ? '55' : 'cc'}` }}
                                    title={uy ? uy.map((u) => uyariMetni(t, u, dil, adlar)).join('\n') : undefined}
                                    data-vardiya-id={v.id}
                                    data-durum={v.durum}
                                  >
                                    {uy && <AlertTriangle className="h-3 w-3 flex-none text-amber-200" aria-label={t('ik.uyari.var')} />}
                                    <span dir="ltr">
                                      {v.baslangic}–{v.bitis}
                                    </span>
                                  </button>
                                );
                              })}
                              {!salt && vardiyalar.length === 0 && !izin && (
                                <button type="button" onClick={() => void hucreTik(p.id, g)} className="mt-auto self-center text-muted-foreground/60 hover:text-white" aria-label={t('ik.vardiya.ekle')}>
                                  <Plus className="h-3.5 w-3.5" aria-hidden="true" />
                                </button>
                              )}
                            </div>
                          </td>
                        );
                      })}
                      <td className={`p-1 text-end font-semibold ${fazla ? 'text-amber-300' : ''}`}>{t('ik.vardiya.saat', { saat: saatYaz(dk, dil) })}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
      {plan && plan.uyarilar.length > 0 && (
        <div className={`${KART} p-3`}>
          <h4 className="mb-2 text-sm font-semibold">{t('ik.vardiya.uyarilar')}</h4>
          <Uyarilar uyarilar={plan.uyarilar} dil={dil} adlar={adlar} />
          <p className="mt-2 text-[11px] text-muted-foreground">{t('ik.vardiya.uyariNotu')}</p>
        </div>
      )}
      {!salt && plan && (
        <div className={`${KART} flex flex-wrap items-center justify-between gap-3 p-3`}>
          <Anahtar acik={bildir} onDegis={setBildir} etiket={t('ik.vardiya.bildir')} />
          <Button onClick={() => void yayinla()} disabled={mesgul || yayinBekleyen === 0} data-testid="ik-vardiya-yayinla">
            {mesgul ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Send className="h-4 w-4" aria-hidden="true" />}
            {t('ik.vardiya.yayinla', { sayi: yayinBekleyen })}
          </Button>
        </div>
      )}
      <YasalNot>{t('ik.vardiya.yasalNot')}</YasalNot>
      {sablonAcik && (
        <SablonPenceresi
          api={api}
          sablonlar={sablonlar}
          salt={salt}
          onKapat={sablonKapat}
          onDegisti={() => {
            void sablonYukle();
            void yukle();
          }}
        />
      )}
      {duzen && (
        <VardiyaPenceresi
          api={api}
          duzen={duzen}
          sablonlar={sablonlar}
          adi={adlar[duzen.personel_id] || ''}
          onKapat={duzenKapat}
          onKaydedildi={(u) => {
            if (u.length) toast.warning(u.map((x) => uyariMetni(t, x, dil, adlar)).join(' · '));
            void yukle();
          }}
        />
      )}
    </div>
  );
}
