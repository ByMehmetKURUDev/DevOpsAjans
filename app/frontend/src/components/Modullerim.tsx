import { Link } from 'react-router-dom';
import { Blocks, CheckCircle2, Hourglass, Loader2, PackagePlus } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import type { Modullerim as ModulBilgisi, MusteriModulu } from '@/lib/moduller';
import { modulIkonu } from '@/lib/modulIkonlari';

/**
 * Müşteri paneli › Profil › Modüllerim.
 *
 * Üç grup: panelinizde açık olanlar, yakında gelecekler ve paketinize
 * eklenebilecekler. Liste müşteri panelinin zaten çektiği
 * `/api/v1/modullerim` yanıtından geliyor (ikinci istek yok). Kapalı bir
 * modül için "Teklif iste" iletişim formunu konusu dolu açıyor.
 */

const GRUPLAR = ['acik', 'yakinda', 'eklenebilir'] as const;

function DurumRozeti({ modul }: { modul: MusteriModulu }) {
  const { t } = useTranslation();
  if (modul.durum === 'yakinda') {
    return (
      <span className="rounded-full border border-sky-400/30 bg-sky-500/10 px-2 py-0.5 text-[10px] uppercase tracking-widest text-sky-300">
        {t('modul.durum.yakinda')}
      </span>
    );
  }
  if (!modul.acik) {
    return (
      <span className="rounded-full border border-white/15 bg-white/5 px-2 py-0.5 text-[10px] uppercase tracking-widest text-muted-foreground">
        {t('modul.gorunum.eklenebilir')}
      </span>
    );
  }
  return (
    <span className="rounded-full border border-emerald-400/30 bg-emerald-500/10 px-2 py-0.5 text-[10px] uppercase tracking-widest text-emerald-300">
      {modul.durum === 'beta' ? t('modul.durum.beta') : t('modul.gorunum.acik')}
    </span>
  );
}

function ModulKarti({ modul }: { modul: MusteriModulu }) {
  const { t } = useTranslation();
  const Ikon = modulIkonu(modul.ikon);
  const ad = t(modul.ad_anahtari);
  const kapali = modul.gorunum === 'eklenebilir';
  return (
    <li
      className={`cam-kart flex gap-4 rounded-2xl border border-white/10 bg-white/[0.03] p-5 ${kapali ? 'opacity-90' : ''}`}
      data-testid={`modulum-${modul.anahtar}`}
      data-gorunum={modul.gorunum}
    >
      <div
        className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl ${
          modul.gorunum === 'acik'
            ? 'bg-gradient-to-br from-purple-600 to-pink-600 text-white'
            : 'border border-white/10 bg-white/5 text-muted-foreground'
        }`}
        aria-hidden="true"
      >
        <Ikon className="h-5 w-5" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="mb-1 flex flex-wrap items-center gap-2">
          <h4 className="font-semibold">{ad}</h4>
          <DurumRozeti modul={modul} />
          {modul.cekirdek ? (
            <span className="text-[10px] uppercase tracking-widest text-muted-foreground">
              {t('modul.kategori.cekirdek')}
            </span>
          ) : null}
        </div>
        <p className="text-sm leading-relaxed text-muted-foreground">{t(modul.aciklama_anahtari)}</p>
        {modul.durum === 'yakinda' && modul.acik ? (
          <p className="mt-2 text-xs text-sky-300/90">{t('modul.musteri.paketinizde')}</p>
        ) : null}
        {kapali ? (
          <Link
            to="/contact"
            state={{ kaynak: 'modul', konu: t('modul.musteri.teklifKonusu', { ad }) }}
            className="mt-3 inline-block"
          >
            <Button
              size="sm"
              variant="outline"
              className="!bg-transparent gap-1.5 border-purple-400/40 text-foreground hover:border-pink-400/60"
            >
              <PackagePlus className="h-3.5 w-3.5" aria-hidden="true" />
              {t('modul.musteri.teklifIste')}
            </Button>
          </Link>
        ) : null}
      </div>
    </li>
  );
}

export default function Modullerim({ bilgi, hata }: { bilgi: ModulBilgisi | null; hata?: boolean }) {
  const { t } = useTranslation();

  const gruplar = GRUPLAR.map((g) => ({
    anahtar: g,
    liste: (bilgi?.moduller ?? []).filter((m) => m.gorunum === g),
  }));
  const ikon = { acik: CheckCircle2, yakinda: Hourglass, eklenebilir: PackagePlus } as const;

  return (
    <section
      className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-6"
      aria-labelledby="modullerim-baslik"
      data-testid="modullerim"
    >
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 id="modullerim-baslik" className="flex items-center gap-2 text-lg font-semibold">
            <Blocks className="h-5 w-5 text-purple-400" aria-hidden="true" />
            {t('modul.musteri.baslik')}
          </h3>
          <p className="mt-1 text-sm text-muted-foreground">{t('modul.musteri.aciklama')}</p>
        </div>
        {bilgi?.paket ? (
          <span className="rounded-full border border-purple-400/30 bg-purple-500/10 px-3 py-1 text-xs text-purple-200">
            {t('modul.musteri.paketiniz', { paket: bilgi.paket })}
          </span>
        ) : null}
      </div>

      {!bilgi ? (
        hata ? (
          <p className="text-sm text-muted-foreground">{t('modul.musteri.hata')}</p>
        ) : (
          <div className="flex items-center justify-center py-8 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
          </div>
        )
      ) : (
        <div className="space-y-6">
          {gruplar.map((g) => {
            if (g.liste.length === 0) return null;
            const GrupIkonu = ikon[g.anahtar];
            return (
              <div key={g.anahtar} data-testid={`modullerim-grup-${g.anahtar}`}>
                <h4 className="mb-3 flex items-center gap-2 text-xs uppercase tracking-widest text-muted-foreground">
                  <GrupIkonu className="h-3.5 w-3.5" aria-hidden="true" />
                  {t(`modul.musteri.grup.${g.anahtar}`)}
                  <span className="text-foreground/70">({g.liste.length})</span>
                </h4>
                <ul className="grid gap-3 md:grid-cols-2">
                  {g.liste.map((m) => (
                    <ModulKarti key={m.anahtar} modul={m} />
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
