import type { KeyboardEvent, MouseEvent } from 'react';
import {
  CalendarPlus,
  ChevronDown,
  ChevronsLeft,
  ChevronsRight,
  Cog,
  Ellipsis,
  FileCheck2,
  FolderKanban,
  FolderPlus,
  Globe,
  Handshake,
  House,
  Inbox,
  LifeBuoy,
  Megaphone,
  Puzzle,
  Receipt,
  Wallet,
  Workflow,
  X,
  type LucideIcon,
} from 'lucide-react';
import MarkaLogosu from '@/components/MarkaLogosu';
import type { GrupluMenuDurumu } from '@/components/GrupluMenu';
import { GENEL_BAKIS, type GrupAnahtari } from '@/lib/yonetimMenusu';

/**
 * Faz 11A — yönetici paneli sol kenar çubuğu (`<nav data-yonetim-menusu>`).
 *
 * Tek kaynak yine `lib/yonetimMenusu.ts` GRUPLAR; durum/arama/rozet mantığı ortak
 * `useGrupluMenu`'de (müşteri paneli aynı kancayı Faz 11B'de kendi üst çubuğuyla kullanıyor —
 * `components/MusteriKabugu.tsx`). Kabuk (`YonetimKabugu.tsx`) bu menüyü beş kipte gösterir:
 *   genis    ≥1024 px: logo, Genel bakış, Gelen kutusu, 9 grup akordeon, hızlı işlemler;
 *   ray      768–1023 px ya da kullanıcı daralttıysa: yalnız ikonlar (etiketler ekran okuyucuda);
 *   ray-acik ray'de bir gruba tıklanınca / arama yapılırken içeriğin üstüne açılan geniş hâli;
 *   serit    <768 px: grup çipleri yatay şerit, açık grubun bölümleri altında (aramada sonuçlar);
 *   cekmece  <768 px "Menü" sekmesiyle açılan tam liste (aynı akordeon).
 *
 * Seçici sözleşmesi (paylaşılan e2e testleri): her bölüm düğmesinde `data-sekme` (+ seçiliyken
 * `data-secili="evet"`), her grup başlığında `data-grup` + `data-grup-sekmeler`; gizli bölümün
 * grubuna tıklayınca bölüm görünür. Grupların ÜSTÜNDEKİ bağlantılar (`data-ust-sekme`) ve hızlı
 * işlemler bilerek `data-sekme` taşımaz ve düğme değil bağlantıdır: bölüm sayımı GRUPLAR'la aynı kalsın.
 */

export const GRUP_IKONU: Record<GrupAnahtari, LucideIcon> = {
  site: Globe,
  pazarlama: Megaphone,
  satis: Handshake,
  projeler: FolderKanban,
  finans: Wallet,
  destek: LifeBuoy,
  araclar: Puzzle,
  otomasyon: Workflow,
  sistem: Cog,
  diger: Ellipsis,
};

export type HizliIslem = 'teklif' | 'proje' | 'fatura' | 'toplanti';

/** Hızlı işlemler: hedef sekme + (varsa) açılacak form. */
export const HIZLI_ISLEMLER: readonly { tur: HizliIslem; sekme: string; ikon: LucideIcon; etiket: string }[] = [
  { tur: 'teklif', sekme: 'teklifler', ikon: FileCheck2, etiket: 'yeniTeklif' },
  { tur: 'proje', sekme: 'projects', ikon: FolderPlus, etiket: 'projeAc' },
  { tur: 'fatura', sekme: 'invoices', ikon: Receipt, etiket: 'faturaKes' },
  { tur: 'toplanti', sekme: 'toplantilar', ikon: CalendarPlus, etiket: 'toplantiPlanla' },
];

export type KenarKipi = 'genis' | 'ray' | 'ray-acik' | 'serit' | 'cekmece';
export type UstSekme = typeof GENEL_BAKIS | 'gelenKutusu';

interface Props<K extends string> {
  menu: GrupluMenuDurumu<K, GrupAnahtari>;
  aktif: string;
  acikGrup: string | null;
  kip: KenarKipi;
  /** Ekran sınıfı: geniş (≥1024) | orta (768–1023) | dar (<768). Daraltma düğmesi yalnız genişte. */
  ekran: 'genis' | 'orta' | 'dar';
  dar: boolean;
  gelenSayisi: number;
  onGrup: (g: GrupAnahtari | 'diger') => void;
  onBolum: (k: K) => void;
  onUst: (k: UstSekme) => void;
  onHizli: (tur: HizliIslem) => void;
  onDarDegistir: () => void;
  onKapat: () => void;
}

function Rozet({ sayi, ust = false }: { sayi: number; ust?: boolean }) {
  if (sayi <= 0) return null;
  const metin = sayi > 99 ? '99+' : String(sayi);
  // Grup/bölüm rozetinde `data-rozet` (e2e sözleşmesi); üst bağlantıda ayrı ad (sayımlara karışmasın).
  return ust ? (
    <span className="pk-rozet" data-ust-rozet={sayi}>
      {metin}
    </span>
  ) : (
    <span className="pk-rozet" data-rozet={sayi}>
      {metin}
    </span>
  );
}

/** Ok tuşlarıyla menüde gezinme (Tab sırası bozulmadan). */
function okTusu(e: KeyboardEvent<HTMLElement>) {
  if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(e.key)) return;
  const hedef = e.target as HTMLElement;
  const odaklar = Array.from(e.currentTarget.querySelectorAll<HTMLElement>('a[href], button')).filter(
    (el) => el.getClientRects().length > 0 && !el.hasAttribute('disabled'),
  );
  if (!odaklar.length) return;
  const i = odaklar.indexOf(hedef);
  let sonraki = 0;
  if (e.key === 'Home') sonraki = 0;
  else if (e.key === 'End') sonraki = odaklar.length - 1;
  else if (e.key === 'ArrowDown') sonraki = i < 0 ? 0 : Math.min(odaklar.length - 1, i + 1);
  else sonraki = i <= 0 ? 0 : i - 1;
  e.preventDefault();
  odaklar[sonraki]?.focus();
}

/** Yeni sekmede/pencerede açma isteğine dokunma; düz tıklamada panel içinde geç. */
function duzTik(e: MouseEvent<HTMLAnchorElement>): boolean {
  if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return false;
  e.preventDefault();
  return true;
}

export default function YonetimMenusu<K extends string>({
  menu,
  aktif,
  acikGrup,
  kip,
  ekran,
  dar,
  gelenSayisi,
  onGrup,
  onBolum,
  onUst,
  onHizli,
  onDarDegistir,
  onKapat,
}: Props<K>) {
  const { t, gruplar, grupAdi, bulunanGrup, arama, sonuclar, sonucAnahtarlari, grubunRozeti, rozetler } = menu;
  const k = (ad: string) => t(`yonetimMenusu.kabuk.${ad}`);
  const ray = kip === 'ray';
  const bolumAcik = arama ? sonuclar.length > 0 : gruplar.some((g) => g.anahtar === acikGrup);

  return (
    <nav
      aria-label={t('yonetimMenusu.menu')}
      className="pk-kenar"
      data-yonetim-menusu
      data-kip={kip}
      data-ekran={ekran}
      data-arama={arama ? '' : undefined}
      data-bolum-acik={bolumAcik ? '' : undefined}
      id="pk-kenar"
      onKeyDown={okTusu}
    >
      <div className="pk-marka">
        <MarkaLogosu yazi={false} />
        <span className="pk-marka-yazi">
          <span className="pk-marka-ad">
            {t('ui.brandPrefix')}
            <span className="pk-marka-vurgu">{t('ui.brandHighlight')}</span> {t('ui.brandSuffix')}
          </span>
          <span className="pk-marka-alt">{k('komutaMerkezi')}</span>
        </span>
        <button type="button" className="pk-cekmece-kapat" onClick={onKapat} aria-label={k('menuKapat')}>
          <X aria-hidden="true" />
        </button>
      </div>

      <div className="pk-ust-baglantilar">
        <a
          href={`/admin?sekme=${GENEL_BAKIS}`}
          className="pk-oge pk-ust-oge"
          data-ust-sekme={GENEL_BAKIS}
          data-secili={aktif === GENEL_BAKIS ? 'evet' : undefined}
          aria-current={aktif === GENEL_BAKIS ? 'page' : undefined}
          title={ray ? k('genelBakis') : undefined}
          onClick={(e) => duzTik(e) && onUst(GENEL_BAKIS)}
        >
          <House className="pk-ikon" aria-hidden="true" />
          <span className="pk-etiket">{k('genelBakis')}</span>
        </a>
        <a
          href="/admin?sekme=gelenKutusu"
          className="pk-oge pk-ust-oge"
          data-ust-sekme="gelenKutusu"
          data-secili={aktif === 'gelenKutusu' ? 'evet' : undefined}
          title={ray ? k('gelenKutusu') : undefined}
          onClick={(e) => duzTik(e) && onUst('gelenKutusu')}
        >
          <Inbox className="pk-ikon" aria-hidden="true" />
          <span className="pk-etiket">{k('gelenKutusu')}</span>
          <Rozet sayi={gelenSayisi} ust />
        </a>
      </div>

      <div className="pk-gruplar">
        {gruplar.map((g) => {
          const Ikon = GRUP_IKONU[g.anahtar];
          const eslesen = arama ? g.sekmeler.filter((s) => sonucAnahtarlari.has(s.key)) : null;
          const grupGorunur = !eslesen || eslesen.length > 0;
          const acik = arama ? grupGorunur : acikGrup === g.anahtar;
          const rozet = grubunRozeti(g.anahtar);
          const kimlik = `pk-grup-${g.anahtar}`;
          return (
            <div className="pk-grup" key={g.anahtar} data-acik={acik ? '' : undefined} hidden={!grupGorunur}>
              <button
                type="button"
                className="pk-oge pk-grup-baslik"
                data-grup={g.anahtar}
                data-grup-sekmeler={g.sekmeler.map((s) => s.key).join(' ')}
                aria-expanded={acik}
                aria-controls={kimlik}
                aria-current={!arama && g.anahtar === bulunanGrup ? 'true' : undefined}
                title={ray ? grupAdi(g.anahtar) : undefined}
                onClick={() => onGrup(g.anahtar)}
              >
                <Ikon className="pk-ikon" aria-hidden="true" />
                <span className="pk-etiket">{grupAdi(g.anahtar)}</span>
                <Rozet sayi={rozet} />
                <ChevronDown className="pk-ok" aria-hidden="true" />
              </button>
              <div className="pk-bolumler" id={kimlik} hidden={!acik}>
                {g.sekmeler.map((s) => {
                  const gorunur = eslesen ? eslesen.includes(s) : acik;
                  const secili = s.key === aktif;
                  return (
                    <button
                      key={s.key}
                      type="button"
                      hidden={!gorunur}
                      className="pk-oge pk-bolum"
                      data-sekme={s.key}
                      data-secili={secili ? 'evet' : 'hayir'}
                      aria-current={secili ? 'page' : undefined}
                      onClick={() => onBolum(s.key)}
                    >
                      <s.icon className="pk-ikon" aria-hidden="true" />
                      <span className="pk-etiket">{s.label}</span>
                      {arama && <span className="pk-bolum-grup">· {grupAdi(g.anahtar)}</span>}
                      <Rozet sayi={rozetler[s.key] || 0} />
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}
        {arama && sonuclar.length === 0 && (
          <p className="pk-arama-bos" data-arama-bos>
            {t('yonetimMenusu.sonucYok')}
          </p>
        )}
      </div>

      <div className="pk-hizli">
        <p className="pk-hizli-baslik">{k('hizliIslemler')}</p>
        {HIZLI_ISLEMLER.map((h) => (
          <a
            key={h.tur}
            href={`/admin?sekme=${h.sekme}`}
            className="pk-oge pk-hizli-oge"
            data-hizli={h.tur}
            title={ray ? k(h.etiket) : undefined}
            onClick={(e) => duzTik(e) && onHizli(h.tur)}
          >
            <h.ikon className="pk-ikon" aria-hidden="true" />
            <span className="pk-etiket">{k(h.etiket)}</span>
            <ChevronsRight className="pk-hizli-ok pk-yon" aria-hidden="true" />
          </a>
        ))}
      </div>

      <button
        type="button"
        className="pk-daralt"
        onClick={onDarDegistir}
        aria-expanded={!dar}
        aria-controls="pk-kenar"
        aria-label={dar ? k('genislet') : k('daralt')}
        title={dar ? k('genislet') : k('daralt')}
        data-kenar-daralt
      >
        {dar ? <ChevronsRight className="pk-yon" aria-hidden="true" /> : <ChevronsLeft className="pk-yon" aria-hidden="true" />}
        <span className="pk-etiket">{dar ? k('genislet') : k('daralt')}</span>
      </button>
    </nav>
  );
}
