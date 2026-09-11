import { FormEvent, useState } from 'react';
import { toast } from 'sonner';
import { Mail, MapPin, MessageCircle, Send, Phone, Loader2 } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { client } from '@/lib/sdkClient';
import { useTranslation } from 'react-i18next';
import SocialLinks from '@/components/SocialLinks';
import StoreBadges from '@/components/StoreBadges';
import { useSiteSettings } from '@/lib/siteSettings';



export default function Contact() {
  const { t } = useTranslation();
  const { settings } = useSiteSettings();
  const whatsappNumber = (settings.whatsapp_number || '905412965878').replace(/\D/g, '');
  const [form, setForm] = useState({
    name: '',
    email: '',
    phone: '',
    subject: '',
    message: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);

  const handleChange = (field: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    setForm((f) => ({ ...f, [field]: e.target.value }));
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!form.name.trim() || !form.email.trim() || !form.message.trim()) {
      toast.error(t('contact.errorRequired'));
      return;
    }
    setSubmitting(true);
    try {
      await client.entities.inquiries.create({
        data: {
          name: form.name.trim(),
          email: form.email.trim(),
          phone: form.phone.trim(),
          subject: form.subject.trim(),
          message: form.message.trim(),
          status: 'new',
        },
      });
      setSuccess(true);
      setForm({ name: '', email: '', phone: '', subject: '', message: '' });
      toast.success(t('contact.success'));
    } catch (err) {
      const anyErr = err as { data?: { detail?: string }; message?: string };
      toast.error(anyErr?.data?.detail || anyErr?.message || 'Failed to send message. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div>
      <section className="py-24 md:py-32">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 grid gap-12 lg:grid-cols-2">
          {/* Left column */}
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-purple-400 mb-4">{t('contact.sectionTag')}</p>
            <h1 className="text-5xl md:text-7xl font-bold leading-[1.05] mb-6">
              {t('contact.title')} <span className="gradient-text">{t('contact.titleHighlight')}</span>.
            </h1>
            <p className="text-lg text-muted-foreground max-w-lg mb-10">
              {t('contact.desc')}
            </p>

            <div className="space-y-4 mb-10">
              <a href={`mailto:${settings.contact_email}`} className="flex items-center gap-4 p-4 rounded-xl glass hover:border-purple-500/40 transition-colors group">
                <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-purple-600 to-pink-600 flex items-center justify-center">
                  <Mail className="h-5 w-5 text-white" />
                </div>
                <div>
                  <p className="text-xs uppercase tracking-widest text-muted-foreground">{t('contact.email')}</p>
                  <p className="font-medium group-hover:gradient-text transition-all">{settings.contact_email}</p>
                </div>
              </a>

              <a href={`tel:${settings.contact_phone.replace(/\s/g, '')}`} className="flex items-center gap-4 p-4 rounded-xl glass hover:border-purple-500/40 transition-colors group">
                <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-orange-500 to-pink-600 flex items-center justify-center">
                  <Phone className="h-5 w-5 text-white" />
                </div>
                <div>
                  <p className="text-xs uppercase tracking-widest text-muted-foreground">{t('contact.phone')}</p>
                  <p className="font-medium group-hover:gradient-text transition-all">{settings.contact_phone}</p>
                </div>
              </a>

              <a
                href={`https://wa.me/${whatsappNumber}`}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-4 p-4 rounded-xl glass hover:border-green-500/40 transition-colors group"
              >
                <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-green-500 to-emerald-600 flex items-center justify-center">
                  <MessageCircle className="h-5 w-5 text-white" />
                </div>
                <div>
                  <p className="text-xs uppercase tracking-widest text-muted-foreground">{t('contact.whatsapp')}</p>
                  <p className="font-medium group-hover:text-green-400 transition-colors">{t('contact.whatsappLabel')}</p>
                </div>
              </a>

              <div className="flex items-center gap-4 p-4 rounded-xl glass">
                <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-cyan-500 to-purple-500 flex items-center justify-center">
                  <MapPin className="h-5 w-5 text-white" />
                </div>
                <div>
                  <p className="text-xs uppercase tracking-widest text-muted-foreground">{t('contact.basedIn')}</p>
                  <p className="font-medium">{settings.contact_address}</p>
                  {/* Mağaza rozetleri adresin hemen altında; adres panelden gelir. */}
                  <StoreBadges
                    appStoreUrl={settings.app_store_url}
                    googlePlayUrl={settings.google_play_url}
                    className="mt-3"
                  />
                </div>
              </div>
            </div>

            <div>
              <p className="text-xs uppercase tracking-[0.3em] text-muted-foreground mb-4">{t('contact.elsewhere')}</p>
              <SocialLinks variant="pill" />
            </div>
          </div>

          {/* Right column: form */}
          <div>
            <div className="relative rounded-3xl glass p-8 md:p-10">
              <div className="absolute -inset-4 bg-gradient-to-br from-purple-600/10 via-pink-600/10 to-cyan-600/10 blur-2xl -z-10 rounded-3xl" />
              {success && (
                <div className="mb-6 p-4 rounded-xl bg-green-500/10 border border-green-500/30 text-sm text-green-300">
                  {t('contact.success')}
                </div>
              )}
              <form onSubmit={handleSubmit} className="space-y-5">
                <div className="grid gap-5 sm:grid-cols-2">
                  <div>
                    <Label htmlFor="name" className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">
                      {t('contact.formName')} *
                    </Label>
                    <Input
                      id="name"
                      value={form.name}
                      onChange={handleChange('name')}
                      placeholder={t('contact.formNamePlaceholder')}
                      required
                      className="bg-white/5 border-white/10 focus:border-purple-500"
                    />
                  </div>
                  <div>
                    <Label htmlFor="email" className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">
                      {t('contact.formEmail')} *
                    </Label>
                    <Input
                      id="email"
                      type="email"
                      value={form.email}
                      onChange={handleChange('email')}
                      placeholder={t('contact.formEmailPlaceholder')}
                      required
                      className="bg-white/5 border-white/10 focus:border-purple-500"
                    />
                  </div>
                </div>
                <div className="grid gap-5 sm:grid-cols-2">
                  <div>
                    <Label htmlFor="phone" className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">
                      {t('contact.formPhone')}
                    </Label>
                    <Input
                      id="phone"
                      value={form.phone}
                      onChange={handleChange('phone')}
                      placeholder={t('contact.formPhonePlaceholder')}
                      className="bg-white/5 border-white/10 focus:border-purple-500"
                    />
                  </div>
                  <div>
                    <Label htmlFor="subject" className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">
                      {t('contact.formSubject')}
                    </Label>
                    <Input
                      id="subject"
                      value={form.subject}
                      onChange={handleChange('subject')}
                      placeholder={t('contact.formSubjectPlaceholder')}
                      className="bg-white/5 border-white/10 focus:border-purple-500"
                    />
                  </div>
                </div>
                <div>
                  <Label htmlFor="message" className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">
                    {t('contact.formMessage')} *
                  </Label>
                  <Textarea
                    id="message"
                    value={form.message}
                    onChange={handleChange('message')}
                    placeholder={t('contact.formMessagePlaceholder')}
                    rows={6}
                    required
                    className="bg-white/5 border-white/10 focus:border-purple-500 resize-none"
                  />
                </div>
                <Button
                  type="submit"
                  disabled={submitting}
                  className="w-full h-12 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-500 hover:to-pink-500 text-white border-0 gap-2 glow-primary"
                >
                  {submitting ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" /> {t('contact.sending')}
                    </>
                  ) : (
                    <>
                      {t('contact.send')} <Send className="h-4 w-4" />
                    </>
                  )}
                </Button>
              </form>
            </div>
          </div>
        </div>
      </section>

      {/* Map Section */}
      <section className="pb-24">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="rounded-3xl overflow-hidden glass border border-white/10">
            <iframe
              title="Office Location"
              src="https://www.google.com/maps/embed?pb=!1m18!1m12!1m3!1d3008.5!2d28.98!3d41.08!2m3!1f0!2f0!3f0!3m2!1i1024!2i768!4f13.1!3m3!1m2!1s0x0%3A0x0!2zNDHCsDA0JzQ4LjAiTiAyOMKwNTgnNDguMCJF!5e0!3m2!1str!2str!4v1"
              width="100%"
              height="400"
              style={{ border: 0 }}
              allowFullScreen
              loading="lazy"
              referrerPolicy="no-referrer-when-downgrade"
              className="w-full"
            />
          </div>
        </div>
      </section>
    </div>
  );
}