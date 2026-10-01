import { useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

declare global {
  interface Window {
    MKForm?: { tara: () => void };
  }
}

/**
 * Faz 3C — gömülebilir CRM formunun doğrudan bağlantısı: `/form/<anahtar>`.
 *
 * Formu çizen kod sitedeki gömme betiğinin AYNISI (`public/crm-form.js`):
 * etiketler (7 dil), KVKK onayı, bal küpü ve süre jetonu orada; bu sayfa yalnız
 * kabı ve betiği yüklüyor. Prerender edilmiyor, noindex (kişiye özel bağlantı
 * değil ama arama sonucunda işi yok). Dil: `?dil=` ya da sitenin seçili dili.
 */
export default function CrmFormSayfasi() {
  const { anahtar } = useParams<{ anahtar: string }>();
  const { i18n } = useTranslation();
  const dil = (() => {
    try {
      const d = new URLSearchParams(window.location.search).get('dil');
      if (d) return d.slice(0, 2);
    } catch {
      /* tarayıcı dışı */
    }
    return (i18n.language || 'tr').slice(0, 2);
  })();

  useEffect(() => {
    const etiket = document.createElement('meta');
    etiket.name = 'robots';
    etiket.content = 'noindex, nofollow';
    document.head.appendChild(etiket);
    return () => etiket.remove();
  }, []);

  useEffect(() => {
    if (!anahtar) return;
    if (window.MKForm) {
      window.MKForm.tara();
      return;
    }
    if (document.querySelector('script[data-mk-crm-form]')) return;
    const betik = document.createElement('script');
    betik.src = '/crm-form.js';
    betik.async = true;
    betik.setAttribute('data-mk-crm-form', '');
    document.body.appendChild(betik);
  }, [anahtar]);

  return (
    <main className="flex min-h-screen items-start justify-center bg-background px-4 py-10 text-foreground sm:py-16" dir={dil === 'ar' ? 'rtl' : 'ltr'}>
      <div className="w-full max-w-xl space-y-6">
        <div
          key={anahtar}
          className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-6"
          data-mk-form={anahtar}
          data-mk-dil={dil}
          data-testid="crm-form-kabi"
        />
        <p className="text-center text-xs text-muted-foreground">
          <a href="/" className="hover:text-foreground">
            By Mehmet KURU Dev
          </a>
        </p>
      </div>
    </main>
  );
}
