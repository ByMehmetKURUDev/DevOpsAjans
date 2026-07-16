import { FormEvent, useState } from 'react';
import { toast } from 'sonner';
import { Mail, MapPin, MessageCircle, Send, Github, Linkedin, Twitter, Instagram, Loader2 } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { createClient } from '@metagptx/web-sdk';
import { useTranslation } from 'react-i18next';

const client = createClient();

const WHATSAPP_NUMBER = '905555555555';

const SOCIALS = [
  { icon: Github, label: 'GitHub', href: '#' },
  { icon: Linkedin, label: 'LinkedIn', href: '#' },
  { icon: Twitter, label: 'Twitter / X', href: '#' },
  { icon: Instagram, label: 'Instagram', href: '#' },
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
              <a href="mailto:hello@mehmetkuru.dev" className="flex items-center gap-4 p-4 rounded-xl glass hover:border-purple-500/40 transition-colors group">
                <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-purple-600 to-pink-600 flex items-center justify-center">
                  <Mail className="h-5 w-5 text-white" />
                </div>
                <div>
                  <p className="text-xs uppercase tracking-widest text-muted-foreground">{t('contact.email')}</p>
                  <p className="font-medium group-hover:gradient-text transition-all">hello@mehmetkuru.dev</p>
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
              <div className="flex flex-wrap gap-2">
                {SOCIALS.map((s) => (
                  <a
                    key={s.label}
                    href={s.href}
                    className="inline-flex items-center gap-2 px-4 py-2 rounded-full glass text-sm hover:border-purple-500/40 transition-colors"
                  >
                    <s.icon className="h-4 w-4" /> {s.label}
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
    </div>
  );
}