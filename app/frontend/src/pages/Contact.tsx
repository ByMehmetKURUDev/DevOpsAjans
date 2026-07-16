import { FormEvent, useState } from 'react';
import { toast } from 'sonner';
import { Mail, MapPin, MessageCircle, Send, Phone, Loader2 } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { createClient } from '@metagptx/web-sdk';
import { useTranslation } from 'react-i18next';

const client = createClient();

const WHATSAPP_NUMBER = '905555555555';

const SOCIALS = [
  { label: 'Facebook', href: '#', svg: 'M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z' },
  { label: 'Instagram', href: '#', svg: 'M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zM12 0C8.741 0 8.333.014 7.053.072 2.695.272.273 2.69.073 7.052.014 8.333 0 8.741 0 12c0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98C8.333 23.986 8.741 24 12 24c3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98C15.668.014 15.259 0 12 0zm0 5.838a6.162 6.162 0 100 12.324 6.162 6.162 0 000-12.324zM12 16a4 4 0 110-8 4 4 0 010 8zm6.406-11.845a1.44 1.44 0 100 2.881 1.44 1.44 0 000-2.881z' },
  { label: 'Twitter', href: '#', svg: 'M23.953 4.57a10 10 0 01-2.825.775 4.958 4.958 0 002.163-2.723c-.951.555-2.005.959-3.127 1.184a4.92 4.92 0 00-8.384 4.482C7.69 8.095 4.067 6.13 1.64 3.162a4.822 4.822 0 00-.666 2.475c0 1.71.87 3.213 2.188 4.096a4.904 4.904 0 01-2.228-.616v.06a4.923 4.923 0 003.946 4.827 4.996 4.996 0 01-2.212.085 4.936 4.936 0 004.604 3.417 9.867 9.867 0 01-6.102 2.105c-.39 0-.779-.023-1.17-.067a13.995 13.995 0 007.557 2.209c9.053 0 13.998-7.496 13.998-13.985 0-.21 0-.42-.015-.63A9.935 9.935 0 0024 4.59z' },
  { label: 'LinkedIn', href: '#', svg: 'M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z' },
  { label: 'YouTube', href: '#', svg: 'M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z' },
  { label: 'GitHub', href: '#', svg: 'M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12' },
];

export default function Contact() {
  const { t } = useTranslation();
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
              <a href="mailto:by@mehmetkuru.dev" className="flex items-center gap-4 p-4 rounded-xl glass hover:border-purple-500/40 transition-colors group">
                <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-purple-600 to-pink-600 flex items-center justify-center">
                  <Mail className="h-5 w-5 text-white" />
                </div>
                <div>
                  <p className="text-xs uppercase tracking-widest text-muted-foreground">{t('contact.email')}</p>
                  <p className="font-medium group-hover:gradient-text transition-all">by@mehmetkuru.dev</p>
                </div>
              </a>

              <a href="tel:+905412965878" className="flex items-center gap-4 p-4 rounded-xl glass hover:border-purple-500/40 transition-colors group">
                <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-orange-500 to-pink-600 flex items-center justify-center">
                  <Phone className="h-5 w-5 text-white" />
                </div>
                <div>
                  <p className="text-xs uppercase tracking-widest text-muted-foreground">{t('contact.phone')}</p>
                  <p className="font-medium group-hover:gradient-text transition-all">{t('contact.phoneNumber')}</p>
                </div>
              </a>

              <a
                href={`https://wa.me/${WHATSAPP_NUMBER}`}
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
                  <p className="font-medium">{t('contact.location')}</p>
                </div>
              </div>
            </div>

            <div>
              <p className="text-xs uppercase tracking-[0.3em] text-muted-foreground mb-4">{t('contact.elsewhere')}</p>
              <div className="flex flex-wrap gap-3">
                {SOCIALS.map((s) => (
                  <a
                    key={s.label}
                    href={s.href}
                    aria-label={s.label}
                    className="inline-flex items-center gap-2 px-4 py-2 rounded-full glass text-sm hover:border-purple-500/40 transition-colors"
                  >
                    <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24"><path d={s.svg}/></svg>
                    {s.label}
                  </a>
                ))}
              </div>
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