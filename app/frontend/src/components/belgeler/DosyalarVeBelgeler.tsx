import { lazy, Suspense, useEffect, useMemo, useState } from 'react';
import { BookText, FolderOpen, LayoutGrid } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { ekliLazy } from '@/i18n/ekliLazy';
import { musteriOzeti, type BelgeMod, type Ozet } from '@/lib/belgeler';

import { Yukleniyor } from './ortak';

/**
 * Faz 5B — "Dosyalar ve belgeler": mevcut Dosyalar sekmesinin İÇİNDE alt gezinme
 * (menüde yeni düğme yok): Dosyalar (Faz 2C, aynen) · Belgeler (doküman/wiki/not) · Strateji.
 *
 * Yönetici: üçü de her zaman. Müşteri: Dosyalar yalnız `dosyalar` modülü + izniyle; Belgeler ve
 * Strateji ajansın paylaştığı belge varsa (modülden bağımsız) ya da `belgeler` modülü + izni
 * varsa. Tek alt bölüm kalıyorsa gezinme gizli (yalnız dosyası olan müşteri bugünkü ekranı görür).
 * `?alt=belgeler&belge=12` bağlantısı doğrudan o belgeyi açar (bildirim, gelen kutusu).
 */

const DosyaYonetimi = ekliLazy('dosyalar', () => import('@/components/admin/DosyaYonetimi'));
const Dosyalarim = ekliLazy('dosyalar', () => import('@/components/Dosyalarim'));
const BelgeMerkezi = lazy(() => import('./BelgeMerkezi'));

type Alt = 'dosyalar' | 'belgeler' | 'strateji';
const ALTLAR: Alt[] = ['dosyalar', 'belgeler', 'strateji'];
const IKON = { dosyalar: FolderOpen, belgeler: BookText, strateji: LayoutGrid } as const;

function adrestenOku(): { alt: Alt | null; belge: number | null } {
  try {
    const p = new URLSearchParams(window.location.search);
    const alt = p.get('alt') as Alt | null;
    const belge = Number(p.get('belge'));
    return { alt: alt && ALTLAR.includes(alt) ? alt : null, belge: Number.isInteger(belge) && belge > 0 ? belge : null };
  } catch {
    return { alt: null, belge: null };
  }
}

interface Ozellikler {
  mod: BelgeMod;
  /** Müşteri: `dosyalar` modülü açık ve izni var mı? */
  dosyalarAcik?: boolean;
  /** Müşteri: `belgeler` modülü açık ve izni var mı (kendi belgesini oluşturabilir mi)? */
  belgelerAcik?: boolean;
}

export default function DosyalarVeBelgeler({ mod, dosyalarAcik = true, belgelerAcik = true }: Ozellikler) {
  const { t } = useTranslation();
  const adres = useMemo(adrestenOku, []);
  const [ozet, setOzet] = useState<Ozet | null | undefined>(mod === 'musteri' ? undefined : null);

  useEffect(() => {
    if (mod !== 'musteri') return;
    let iptal = false;
    musteriOzeti()
      .then((o) => {
        if (!iptal) setOzet(o);
      })
      .catch(() => {
        if (!iptal) setOzet(null);
      });
    return () => {
      iptal = true;
    };
  }, [mod]);

  const altlar = useMemo<Alt[]>(() => {
    if (mod === 'yonetici') return ALTLAR;
    const l: Alt[] = [];
    if (dosyalarAcik) l.push('dosyalar');
    const kendi = belgelerAcik && (ozet ? ozet.modul_acik && ozet.izin : true);
    if (kendi || (ozet?.paylasilan_belge ?? 0) > 0) l.push('belgeler');
    if (kendi || (ozet?.paylasilan_strateji ?? 0) > 0) l.push('strateji');
    return l;
  }, [mod, dosyalarAcik, belgelerAcik, ozet]);

  const [alt, setAlt] = useState<Alt>(adres.alt ?? 'dosyalar');
  const yukleniyor = mod === 'musteri' && ozet === undefined;
  useEffect(() => {
    if (!yukleniyor && altlar.length && !altlar.includes(alt)) setAlt(altlar[0]);
  }, [altlar, alt, yukleniyor]);

  const altSec = (a: Alt) => {
    setAlt(a);
    try {
      const u = new URL(window.location.href);
      if (u.searchParams.get('sekme') === 'dosyalar' || u.searchParams.has('alt')) {
        u.searchParams.set('alt', a);
        u.searchParams.delete('belge');
        window.history.replaceState(window.history.state, '', u.toString());
      }
    } catch {
      /* tarayıcı dışı */
    }
  };

  if (yukleniyor && !dosyalarAcik) return <Yukleniyor />;
  if (!yukleniyor && altlar.length === 0) {
    return <p className="py-10 text-center text-sm text-muted-foreground">{t('belgeler.bos.musteri')}</p>;
  }
  const gorunen: Alt = altlar.includes(alt) ? alt : altlar[0] ?? 'dosyalar';

  return (
    <div className="min-w-0" data-testid="dosyalar-ve-belgeler" data-alt={gorunen}>
      {altlar.length > 1 && (
        <div className="-mx-1 mb-5 flex gap-1 overflow-x-auto pb-1" role="tablist" aria-label={t('belgeler.alt.etiket')}>
          {altlar.map((a) => {
            const Ikon = IKON[a];
            return (
              <button
                key={a}
                type="button"
                role="tab"
                aria-selected={gorunen === a}
                onClick={() => altSec(a)}
                data-alt-sekme={a}
                className={`flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-2 text-sm transition-colors ${
                  gorunen === a ? 'bg-purple-500/20 text-white ring-1 ring-purple-400/40' : 'text-muted-foreground hover:bg-white/5 hover:text-white'
                }`}
              >
                <Ikon className="h-4 w-4" aria-hidden="true" />
                {t(`belgeler.alt.${a}`)}
              </button>
            );
          })}
        </div>
      )}
      <Suspense fallback={<Yukleniyor />}>
        {gorunen === 'dosyalar' && (mod === 'yonetici' ? <DosyaYonetimi /> : <Dosyalarim />)}
        {gorunen === 'belgeler' && (
          <BelgeMerkezi key={`belge-${mod}`} mod={mod} kategori="belge" baslangicBelge={adres.alt !== 'strateji' ? adres.belge : null} />
        )}
        {gorunen === 'strateji' && (
          <BelgeMerkezi key={`strateji-${mod}`} mod={mod} kategori="strateji" baslangicBelge={adres.alt === 'strateji' ? adres.belge : null} />
        )}
      </Suspense>
    </div>
  );
}
