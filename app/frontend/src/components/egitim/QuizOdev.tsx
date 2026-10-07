import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { BarChart3, ClipboardCheck, FileText, Loader2, Pencil, Plus, Save, Sparkles, Trash2, X } from 'lucide-react';
import { toast } from 'sonner';

import { Alan, Anahtar, DIS_DUGME, KART, METIN_ALANI, Rozet, SECIM, Yukleniyor } from '@/components/randevu/ortak';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  blobIndir,
  hataMetni,
  tarihSaat,
  yerelGirdi,
  yerelIso,
  type Ders,
  type EgitimApi,
  type Kurs,
  type Meta,
  type Quiz,
  type Soru,
  type SoruTuru,
} from '@/lib/egitim';

/**
 * Faz 6K — quiz ve ödev. Quiz: çoktan seçmeli / doğru-yanlış / kısa cevap (otomatik puan; kısa cevapta büyük-küçük
 * harf, i/ı ve noktalama farkı yok sayılır), isteğe bağlı süre, deneme hakkı, geçme puanı. "AI ile soru üret":
 * seçilen dersin metninden ÖNERİ; kullanıcı işaretleyip ekler (kayıt kullanıcının onayıyla). Ödev: dosya + metin
 * teslimi, eğitmen notu ve geri bildirimi (öğrenciye e-posta). Eğitmen sonuçları görür ve not verir.
 */

const bosSoru = (tur: SoruTuru = 'coktan'): Soru =>
  tur === 'coktan' ? { tur, metin: '', secenekler: ['', ''], dogru: 0, puan: 1 } : tur === 'dogru_yanlis' ? { tur, metin: '', dogru: true, puan: 1 } : { tur, metin: '', dogru: [''], puan: 1 };

type Taslak = {
  tur: 'quiz' | 'odev';
  baslik: string;
  aciklama: string;
  ders_id: string;
  sure_dk: string;
  gecme_puani: string;
  deneme_hakki: string;
  son_tarih: string;
  yayinda: boolean;
  sorular: Soru[];
  ai_uretildi: boolean;
};

function SoruDuzenleyici({ s, i, onDegis, onSil }: { s: Soru; i: number; onDegis: (s: Soru) => void; onSil: () => void }) {
  const { t } = useTranslation();
  return (
    <div className="grid gap-2 rounded-xl border border-white/10 bg-black/20 p-3" data-soru={i}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-muted-foreground">{t('egitim.quiz.soruNo', { sayi: i + 1 })}</span>
        <select value={s.tur} onChange={(e) => onDegis({ ...bosSoru(e.target.value as SoruTuru), metin: s.metin, puan: s.puan })} className={`${SECIM} h-8 w-auto text-xs`} aria-label={t('egitim.quiz.soruTuru')}>
          {(['coktan', 'dogru_yanlis', 'kisa'] as const).map((x) => (
            <option key={x} value={x}>
              {t(`egitim.soruTuru.${x}`)}
            </option>
          ))}
        </select>
        <label className="flex items-center gap-1 text-xs text-muted-foreground">
          {t('egitim.quiz.puan')}
          <Input type="number" min={1} max={10} value={s.puan ?? 1} onChange={(e) => onDegis({ ...s, puan: Number(e.target.value) || 1 })} className="h-8 w-16" />
        </label>
        <span className="flex-1" />
        <Button size="icon" variant="ghost" className="h-7 w-7 text-red-300" aria-label={t('egitim.sil')} onClick={onSil}>
          <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
        </Button>
      </div>
      <textarea value={s.metin} onChange={(e) => onDegis({ ...s, metin: e.target.value })} rows={2} maxLength={1000} className={METIN_ALANI} placeholder={t('egitim.quiz.soruMetni')} aria-label={t('egitim.quiz.soruMetni')} />
      {s.tur === 'coktan' && (
        <div className="grid gap-1">
          {(s.secenekler || []).map((x, j) => (
            <div key={j} className="flex items-center gap-2">
              <input type="radio" name={`dogru-${i}`} checked={s.dogru === j} onChange={() => onDegis({ ...s, dogru: j })} className="h-4 w-4 accent-emerald-500" aria-label={t('egitim.quiz.dogruSecenek')} />
              <Input value={x} onChange={(e) => onDegis({ ...s, secenekler: (s.secenekler || []).map((y, k) => (k === j ? e.target.value : y)) })} maxLength={200} className="h-8" placeholder={t('egitim.quiz.secenek', { sayi: j + 1 })} />
              {(s.secenekler || []).length > 2 && (
                <Button
                  size="icon"
                  variant="ghost"
                  className="h-7 w-7"
                  aria-label={t('egitim.sil')}
                  onClick={() => onDegis({ ...s, secenekler: (s.secenekler || []).filter((_, k) => k !== j), dogru: typeof s.dogru === 'number' && s.dogru >= j && s.dogru > 0 ? s.dogru - 1 : s.dogru })}
                >
                  <X className="h-3.5 w-3.5" aria-hidden="true" />
                </Button>
              )}
            </div>
          ))}
          {(s.secenekler || []).length < 6 && (
            <Button size="sm" variant="ghost" className="w-fit gap-1 text-xs" onClick={() => onDegis({ ...s, secenekler: [...(s.secenekler || []), ''] })}>
              <Plus className="h-3.5 w-3.5" aria-hidden="true" />
              {t('egitim.quiz.secenekEkle')}
            </Button>
          )}
        </div>
      )}
      {s.tur === 'dogru_yanlis' && (
        <div className="flex gap-3 text-sm">
          {[true, false].map((v) => (
            <label key={String(v)} className="flex items-center gap-1.5">
              <input type="radio" name={`dy-${i}`} checked={s.dogru === v} onChange={() => onDegis({ ...s, dogru: v })} className="h-4 w-4 accent-emerald-500" />
              {v ? t('egitim.quiz.dogru') : t('egitim.quiz.yanlis')}
            </label>
          ))}
        </div>
      )}
      {s.tur === 'kisa' && (
        <Alan etiket={t('egitim.quiz.kabulEdilen')} ipucu={t('egitim.quiz.kabulIpucu')}>
          <Input value={Array.isArray(s.dogru) ? s.dogru.join(' | ') : ''} onChange={(e) => onDegis({ ...s, dogru: e.target.value.split('|').map((x) => x.trim()) })} />
        </Alan>
      )}
    </div>
  );
}

function AiUretici({ api, kurs, dersler, meta, onEkle }: { api: EgitimApi; kurs: Kurs; dersler: Ders[]; meta: Meta; onEkle: (s: Soru[]) => void }) {
  const { t } = useTranslation();
  const [dersId, setDersId] = useState<number | ''>(dersler[0]?.id ?? '');
  const [sayi, setSayi] = useState(5);
  const [turler, setTurler] = useState<SoruTuru[]>(['coktan', 'dogru_yanlis', 'kisa']);
  const [oneriler, setOneriler] = useState<Soru[] | null>(null);
  const [secili, setSecili] = useState<Set<number>>(new Set());
  const [mesgul, setMesgul] = useState(false);
  const [ai, setAi] = useState(meta.ai);
  if (!ai?.hazir) {
    return <p className="rounded-xl border border-white/10 bg-black/20 p-3 text-sm text-muted-foreground" data-testid="egitim-ai-kapali">{t('egitim.ai.kapali')}</p>;
  }
  const uret = async () => {
    if (dersId === '') return;
    setMesgul(true);
    try {
      const g = await api.aiSoru(kurs.id, { ders_id: dersId, sayi, turler });
      setOneriler(g.sorular);
      setSecili(new Set(g.sorular.map((_, i) => i)));
      setAi(g.ai);
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };
  return (
    <div className="grid gap-3 rounded-xl border border-blue-400/20 bg-blue-500/5 p-3" data-testid="egitim-ai">
      <div className="flex flex-wrap items-center gap-2">
        <Sparkles className="h-4 w-4 text-blue-300" aria-hidden="true" />
        <span className="text-sm font-medium">{t('egitim.ai.baslik')}</span>
        <span className="text-xs text-muted-foreground">
          {ai.hak != null ? t('egitim.ai.hak', { kullanilan: ai.kullanilan, hak: ai.hak }) : t('egitim.ai.sinirsiz', { kullanilan: ai.kullanilan })}
          {ai.kredi_ile_asim ? ` · ${t('egitim.ai.krediIle', { kredi: ai.uretim_kredisi })}` : ''}
        </span>
      </div>
      <div className="flex flex-wrap items-end gap-2">
        <Alan etiket={t('egitim.ai.ders')}>
          <select value={dersId} onChange={(e) => setDersId(e.target.value ? Number(e.target.value) : '')} className={`${SECIM} w-auto min-w-[10rem]`} data-testid="egitim-ai-ders">
            {dersler.map((d) => (
              <option key={d.id} value={d.id}>
                {d.baslik}
              </option>
            ))}
          </select>
        </Alan>
        <Alan etiket={t('egitim.ai.sayi')}>
          <Input type="number" min={1} max={10} value={sayi} onChange={(e) => setSayi(Math.max(1, Math.min(10, Number(e.target.value) || 1)))} className="w-20" />
        </Alan>
        <div className="flex flex-wrap gap-2 pb-2 text-xs">
          {(['coktan', 'dogru_yanlis', 'kisa'] as const).map((x) => (
            <label key={x} className="flex items-center gap-1">
              <input type="checkbox" checked={turler.includes(x)} onChange={(e) => setTurler(e.target.checked ? [...turler, x] : turler.filter((y) => y !== x))} className="h-3.5 w-3.5 accent-blue-500" />
              {t(`egitim.soruTuru.${x}`)}
            </label>
          ))}
        </div>
        <Button size="sm" onClick={() => void uret()} disabled={mesgul || dersId === '' || !turler.length} className="gap-1.5" data-testid="egitim-ai-uret">
          {mesgul ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Sparkles className="h-4 w-4" aria-hidden="true" />}
          {t('egitim.ai.uret')}
        </Button>
      </div>
      {oneriler && (
        <div className="grid gap-2" data-testid="egitim-ai-oneriler">
          <p className="text-xs text-muted-foreground">{t('egitim.ai.onayIpucu')}</p>
          {oneriler.map((s, i) => (
            <label key={i} className="flex items-start gap-2 rounded-lg bg-black/20 p-2 text-sm">
              <input
                type="checkbox"
                checked={secili.has(i)}
                onChange={(e) => {
                  const y = new Set(secili);
                  if (e.target.checked) y.add(i);
                  else y.delete(i);
                  setSecili(y);
                }}
                className="mt-1 h-4 w-4 accent-blue-500"
              />
              <span>
                <span className="me-1 text-xs text-muted-foreground">[{t(`egitim.soruTuru.${s.tur}`)}]</span>
                {s.metin}
              </span>
            </label>
          ))}
          <Button
            size="sm"
            variant="outline"
            className={`${DIS_DUGME} w-fit`}
            disabled={!secili.size}
            onClick={() => {
              onEkle(oneriler.filter((_, i) => secili.has(i)));
              setOneriler(null);
            }}
            data-testid="egitim-ai-ekle"
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
            {t('egitim.ai.ekle', { sayi: secili.size })}
          </Button>
        </div>
      )}
    </div>
  );
}

function Sonuclar({ api, kurs, quiz, onKapat }: { api: EgitimApi; kurs: Kurs; quiz: Quiz; onKapat: () => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [v, setV] = useState<{ tur: 'quiz' | 'odev'; items: Record<string, unknown>[] } | null>(null);
  const [notlar, setNotlar] = useState<Record<number, { puan: string; geri_bildirim: string }>>({});
  const yukle = useCallback(async () => {
    try {
      setV(await api.sonuclar(kurs.id, quiz.id));
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  }, [api, kurs.id, quiz.id, t]);
  useEffect(() => {
    void yukle();
  }, [yukle]);
  const notla = async (id: number) => {
    const n = notlar[id];
    try {
      await api.notla(kurs.id, id, { puan: n?.puan?.trim() ? Number(n.puan) : null, geri_bildirim: n?.geri_bildirim || '' });
      toast.success(t('egitim.quiz.notVerildi'));
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };
  return (
    <div className={`${KART} grid gap-3 p-4 sm:p-6`} data-testid="egitim-sonuclar">
      <div className="flex items-center gap-2">
        <BarChart3 className="h-4 w-4 text-blue-300" aria-hidden="true" />
        <h4 className="text-base font-semibold">{t('egitim.quiz.sonuclar', { ad: quiz.baslik })}</h4>
        <span className="flex-1" />
        <Button size="sm" variant="ghost" onClick={onKapat}>
          <X className="h-4 w-4" aria-hidden="true" />
          {t('egitim.kapat')}
        </Button>
      </div>
      {!v ? (
        <Yukleniyor />
      ) : v.items.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted-foreground">{t('egitim.quiz.sonucYok')}</p>
      ) : v.tur === 'quiz' ? (
        <ul className="divide-y divide-white/5">
          {v.items.map((x) => (
            <li key={String(x.ogrenci_id)} className="flex flex-wrap items-center gap-2 py-2 text-sm">
              <span className="min-w-0 flex-1 truncate">{String(x.ad)}</span>
              <Rozet renk={x.gecti ? 'border-emerald-400/40 bg-emerald-500/15 text-emerald-200' : 'border-red-400/40 bg-red-500/15 text-red-200'}>%{String(x.puan)}</Rozet>
              <span className="text-xs text-muted-foreground">{t('egitim.quiz.dogruSayisi', { dogru: x.dogru as number, toplam: x.toplam as number })}</span>
              <span className="text-xs text-muted-foreground">{t('egitim.quiz.denemeSayisi', { sayi: x.deneme as number })}</span>
              {x.durum === 'suresi_doldu' && <Rozet>{t('egitim.quiz.sureDoldu')}</Rozet>}
            </li>
          ))}
        </ul>
      ) : (
        <ul className="grid gap-3">
          {v.items.map((x) => {
            const id = x.id as number;
            const n = notlar[id] || { puan: x.puan == null ? '' : String(x.puan), geri_bildirim: String(x.geri_bildirim || '') };
            return (
              <li key={id} className="grid gap-2 rounded-xl border border-white/10 bg-black/20 p-3 text-sm" data-teslim-id={id}>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{String(x.ad)}</span>
                  <span className="text-xs text-muted-foreground">{tarihSaat(x.teslim_at as string, kurs.saat_dilimi, dil)}</span>
                  {Boolean(x.gec) && <Rozet renk="border-amber-400/40 bg-amber-500/15 text-amber-200">{t('egitim.quiz.gecTeslim')}</Rozet>}
                  {x.notlandi_at ? <Rozet renk="border-emerald-400/40 bg-emerald-500/15 text-emerald-200">{t('egitim.quiz.notlandi')}</Rozet> : <Rozet>{t('egitim.quiz.notBekliyor')}</Rozet>}
                </div>
                {Boolean(x.metin) && <p className="whitespace-pre-wrap text-muted-foreground">{String(x.metin)}</p>}
                {(x.dosyalar as { id: number; ad: string }[]).map((f) => (
                  <button
                    key={f.id}
                    type="button"
                    className="flex w-fit items-center gap-1 text-xs text-blue-200 hover:underline"
                    onClick={async () => {
                      try {
                        blobIndir(await api.dosyaBlob(kurs.id, f.id), f.ad);
                      } catch (e) {
                        toast.error(hataMetni(t, e));
                      }
                    }}
                  >
                    <FileText className="h-3.5 w-3.5" aria-hidden="true" />
                    {f.ad}
                  </button>
                ))}
                <div className="grid gap-2 sm:grid-cols-[6rem_minmax(0,1fr)_auto] sm:items-start">
                  <Input type="number" min={0} max={100} value={n.puan} onChange={(e) => setNotlar({ ...notlar, [id]: { ...n, puan: e.target.value } })} placeholder={t('egitim.quiz.puan100')} aria-label={t('egitim.quiz.puan100')} />
                  <textarea value={n.geri_bildirim} onChange={(e) => setNotlar({ ...notlar, [id]: { ...n, geri_bildirim: e.target.value } })} rows={2} className={METIN_ALANI} placeholder={t('egitim.quiz.geriBildirim')} aria-label={t('egitim.quiz.geriBildirim')} />
                  <Button size="sm" onClick={() => void notla(id)} data-testid="egitim-notla">
                    {t('egitim.quiz.notla')}
                  </Button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

export default function QuizOdev({ api, kurs, yonetim, meta }: { api: EgitimApi; kurs: Kurs; yonetim: boolean; meta: Meta }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [liste, setListe] = useState<Quiz[] | null>(null);
  const [dersler, setDersler] = useState<Ders[]>([]);
  const [duzenlenen, setDuzenlenen] = useState<number | 'yeni' | null>(null);
  const [sonuc, setSonuc] = useState<Quiz | null>(null);
  const [d, setD] = useState<Taslak | null>(null);
  const [mesgul, setMesgul] = useState(false);

  const yukle = useCallback(async () => {
    try {
      const [q, ds] = await Promise.all([api.quizler(kurs.id), api.dersler(kurs.id)]);
      setListe(q.items);
      setDersler(ds.items);
    } catch (e) {
      toast.error(hataMetni(t, e));
      setListe([]);
    }
  }, [api, kurs.id, t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const duzenle = (q: Quiz | null, tur: 'quiz' | 'odev' = 'quiz') => {
    setSonuc(null);
    setDuzenlenen(q ? q.id : 'yeni');
    setD(
      q
        ? {
            tur: q.tur, baslik: q.baslik, aciklama: q.aciklama, ders_id: q.ders_id ? String(q.ders_id) : '', sure_dk: q.sure_dk ? String(q.sure_dk) : '',
            gecme_puani: String(q.gecme_puani), deneme_hakki: String(q.deneme_hakki), son_tarih: yerelGirdi(q.son_tarih, kurs.saat_dilimi),
            yayinda: q.yayinda, sorular: q.sorular.map((s) => ({ ...s })), ai_uretildi: q.ai_uretildi,
          }
        : { tur, baslik: '', aciklama: '', ders_id: '', sure_dk: '', gecme_puani: '60', deneme_hakki: '1', son_tarih: '', yayinda: false, sorular: tur === 'quiz' ? [bosSoru()] : [], ai_uretildi: false }
    );
  };

  const kaydet = async () => {
    if (!d) return;
    setMesgul(true);
    const g: Record<string, unknown> = {
      tur: d.tur, baslik: d.baslik, aciklama: d.aciklama, ders_id: d.ders_id ? Number(d.ders_id) : null,
      sure_dk: d.sure_dk.trim() ? Number(d.sure_dk) : null, gecme_puani: Number(d.gecme_puani || 0), deneme_hakki: Number(d.deneme_hakki || 1),
      son_tarih: d.son_tarih ? yerelIso(d.son_tarih, kurs.saat_dilimi) : null, yayinda: d.yayinda, ai_uretildi: d.ai_uretildi,
    };
    if (d.tur === 'quiz') g.sorular = d.sorular.map(({ id, ...s }) => ({ ...(id ? { id } : {}), ...s }));
    try {
      if (duzenlenen === 'yeni') await api.quizEkle(kurs.id, g);
      else if (duzenlenen != null) await api.quizGuncelle(kurs.id, duzenlenen, g);
      toast.success(t('egitim.kaydedildi'));
      setDuzenlenen(null);
      setD(null);
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  const sil = async (q: Quiz) => {
    if (!window.confirm(t('egitim.quiz.silOnay', { ad: q.baslik }))) return;
    try {
      await api.quizSil(kurs.id, q.id);
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  return (
    <div className="grid gap-4" data-testid="egitim-quiz">
      {yonetim && duzenlenen === null && (
        <div className={`${KART} flex flex-wrap items-center gap-2 p-4`}>
          <Button size="sm" className="gap-1.5" onClick={() => duzenle(null, 'quiz')} data-testid="egitim-quiz-ekle">
            <ClipboardCheck className="h-4 w-4" aria-hidden="true" />
            {t('egitim.quiz.yeniQuiz')}
          </Button>
          <Button size="sm" variant="outline" className={DIS_DUGME} onClick={() => duzenle(null, 'odev')} data-testid="egitim-odev-ekle">
            <FileText className="h-4 w-4" aria-hidden="true" />
            {t('egitim.quiz.yeniOdev')}
          </Button>
        </div>
      )}
      {yonetim && d && duzenlenen !== null && (
        <div className={`${KART} grid gap-3 p-4 sm:p-6 md:grid-cols-2`} data-testid="egitim-quiz-editor">
          <h4 className="text-base font-semibold md:col-span-2">{d.tur === 'quiz' ? t('egitim.quiz.quizDuzenle') : t('egitim.quiz.odevDuzenle')}</h4>
          <Alan etiket={t('egitim.quiz.baslik')}>
            <Input value={d.baslik} onChange={(e) => setD({ ...d, baslik: e.target.value })} maxLength={160} data-testid="egitim-quiz-baslik" />
          </Alan>
          <Alan etiket={t('egitim.quiz.ders')}>
            <select value={d.ders_id} onChange={(e) => setD({ ...d, ders_id: e.target.value })} className={SECIM}>
              <option value="">{t('egitim.quiz.dersYok')}</option>
              {dersler.map((x) => (
                <option key={x.id} value={x.id}>
                  {x.baslik}
                </option>
              ))}
            </select>
          </Alan>
          <Alan etiket={t('egitim.quiz.aciklama')} className="md:col-span-2">
            <textarea value={d.aciklama} onChange={(e) => setD({ ...d, aciklama: e.target.value })} rows={2} maxLength={5000} className={METIN_ALANI} />
          </Alan>
          {d.tur === 'quiz' ? (
            <>
              <Alan etiket={t('egitim.quiz.sure')} ipucu={t('egitim.quiz.sureIpucu')}>
                <Input type="number" min={1} max={600} value={d.sure_dk} onChange={(e) => setD({ ...d, sure_dk: e.target.value })} />
              </Alan>
              <div className="grid grid-cols-2 gap-3">
                <Alan etiket={t('egitim.quiz.gecmePuani')}>
                  <Input type="number" min={0} max={100} value={d.gecme_puani} onChange={(e) => setD({ ...d, gecme_puani: e.target.value })} />
                </Alan>
                <Alan etiket={t('egitim.quiz.denemeHakki')}>
                  <Input type="number" min={1} max={20} value={d.deneme_hakki} onChange={(e) => setD({ ...d, deneme_hakki: e.target.value })} />
                </Alan>
              </div>
            </>
          ) : (
            <Alan etiket={t('egitim.quiz.sonTarih')}>
              <Input type="datetime-local" value={d.son_tarih} onChange={(e) => setD({ ...d, son_tarih: e.target.value })} />
            </Alan>
          )}
          {d.tur === 'quiz' && (
            <div className="grid gap-3 md:col-span-2">
              <AiUretici api={api} kurs={kurs} dersler={dersler} meta={meta} onEkle={(s) => setD({ ...d, sorular: [...d.sorular.filter((x) => x.metin.trim()), ...s.map(({ id: _id, ...x }) => x)], ai_uretildi: true })} />
              {d.sorular.map((s, i) => (
                <SoruDuzenleyici
                  key={i}
                  s={s}
                  i={i}
                  onDegis={(y) => setD({ ...d, sorular: d.sorular.map((x, j) => (j === i ? y : x)) })}
                  onSil={() => setD({ ...d, sorular: d.sorular.filter((_, j) => j !== i) })}
                />
              ))}
              {d.sorular.length < 50 && (
                <Button size="sm" variant="outline" className={`${DIS_DUGME} w-fit`} onClick={() => setD({ ...d, sorular: [...d.sorular, bosSoru()] })} data-testid="egitim-soru-ekle">
                  <Plus className="h-4 w-4" aria-hidden="true" />
                  {t('egitim.quiz.soruEkle')}
                </Button>
              )}
            </div>
          )}
          <div className="flex flex-wrap items-center gap-3 md:col-span-2">
            <Anahtar acik={d.yayinda} onDegis={(v) => setD({ ...d, yayinda: v })} etiket={t('egitim.quiz.yayinda')} testid="egitim-quiz-yayinda" />
            <span className="flex-1" />
            <Button
              variant="ghost"
              onClick={() => {
                setDuzenlenen(null);
                setD(null);
              }}
            >
              {t('egitim.vazgec')}
            </Button>
            <Button onClick={() => void kaydet()} disabled={mesgul || !d.baslik.trim()} className="gap-1.5" data-testid="egitim-quiz-kaydet">
              {mesgul ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Save className="h-4 w-4" aria-hidden="true" />}
              {t('egitim.kaydet')}
            </Button>
          </div>
        </div>
      )}
      {sonuc && <Sonuclar api={api} kurs={kurs} quiz={sonuc} onKapat={() => setSonuc(null)} />}
      <div className={`${KART} p-4 sm:p-6`}>
        <h4 className="mb-3 text-base font-semibold">{t('egitim.quiz.liste')}</h4>
        {liste === null ? (
          <Yukleniyor />
        ) : liste.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">{t('egitim.quiz.bos')}</p>
        ) : (
          <ul className="divide-y divide-white/5" data-testid="egitim-quiz-liste">
            {liste.map((q) => (
              <li key={q.id} className="flex flex-wrap items-center gap-2 py-2" data-quiz-id={q.id}>
                {q.tur === 'quiz' ? <ClipboardCheck className="h-4 w-4 text-blue-300" aria-hidden="true" /> : <FileText className="h-4 w-4 text-amber-300" aria-hidden="true" />}
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium">{q.baslik}</span>
                  <span className="block text-xs text-muted-foreground">
                    {q.tur === 'quiz'
                      ? t('egitim.quiz.ozet', { sayi: q.soru_sayisi, puan: q.gecme_puani }) + (q.sure_dk ? ` · ${t('egitim.quiz.dakika', { sayi: q.sure_dk })}` : '')
                      : q.son_tarih
                        ? t('egitim.quiz.sonTarihMetni', { zaman: tarihSaat(q.son_tarih, kurs.saat_dilimi, dil) })
                        : t('egitim.quiz.odev')}
                  </span>
                </span>
                {!q.yayinda && <Rozet>{t('egitim.ders.taslak')}</Rozet>}
                {q.ai_uretildi && <Rozet renk="border-blue-400/40 bg-blue-500/15 text-blue-200">AI</Rozet>}
                {!!q.notlanmayan && <Rozet renk="border-amber-400/40 bg-amber-500/15 text-amber-200">{t('egitim.quiz.notlanmayan', { sayi: q.notlanmayan })}</Rozet>}
                <Button size="sm" variant="outline" className={DIS_DUGME} onClick={() => setSonuc(q)} data-testid="egitim-sonuc-ac">
                  <BarChart3 className="h-4 w-4" aria-hidden="true" />
                  {t('egitim.quiz.sonuclarDugme')}
                </Button>
                {yonetim && (
                  <>
                    <Button size="icon" variant="ghost" className="h-8 w-8" aria-label={t('egitim.ders.duzenle')} onClick={() => duzenle(q)}>
                      <Pencil className="h-4 w-4" aria-hidden="true" />
                    </Button>
                    <Button size="icon" variant="ghost" className="h-8 w-8 text-red-300" aria-label={t('egitim.sil')} onClick={() => void sil(q)}>
                      <Trash2 className="h-4 w-4" aria-hidden="true" />
                    </Button>
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
