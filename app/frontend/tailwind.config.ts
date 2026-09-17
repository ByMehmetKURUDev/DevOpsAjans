import type { Config } from 'tailwindcss';
import tailwindcssAnimate from 'tailwindcss-animate';
import tailwindcssAspectRatio from '@tailwindcss/aspect-ratio';
import tailwindcssTypography from '@tailwindcss/typography';

export default {
  darkMode: ['class'],
  content: [
    './pages/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './app/**/*.{ts,tsx}',
    './src/**/*.{ts,tsx}',
  ],
  prefix: '',
  theme: {
    container: {
      center: true,
      padding: '2rem',
      screens: {
        '2xl': '1400px',
      },
    },
    extend: {
      fontFamily: {
        /*
         * Prototipin fontlari. `font-mono` sinifi 40+ yerde kullaniliyor
         * (etiketler, sayaclar, kod parcalari) ve Tailwind'in varsayilani
         * isletim sistemine gore degisiyordu — ayni sayfa Mac'te Menlo,
         * Windows'ta Consolas cikiyordu. Artik her yerde JetBrains Mono.
         */
        sans: ['Plus Jakarta Sans', 'Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      colors: {
        /*
         * Vurgu paletleri CSS değişkenine bağlı.
         *
         * Sitede 296 yerde sabit `purple-*` / `pink-*` sınıfı var. Bu
         * sınıfların karşılığı burada sabit bir renk olsaydı tema yalnızca
         * derleme sırasında değişirdi — ziyaretçi tuşla değiştiremezdi.
         * Değerler `index.css` içinde `:root` (mor) ve
         * `:root[data-tema="yesil"]` (yeşil) altında tanımlı.
         *
         * `<alpha-value>` yer tutucusu Tailwind'in `/20`, `/40` gibi
         * saydamlık eklerini korumak için gerekli; olmazsa `bg-purple-500/10`
         * sessizce tam opak çıkar.
         */
        purple: {
          50: 'rgb(var(--vurgu-50) / <alpha-value>)',
          100: 'rgb(var(--vurgu-100) / <alpha-value>)',
          200: 'rgb(var(--vurgu-200) / <alpha-value>)',
          300: 'rgb(var(--vurgu-300) / <alpha-value>)',
          400: 'rgb(var(--vurgu-400) / <alpha-value>)',
          500: 'rgb(var(--vurgu-500) / <alpha-value>)',
          600: 'rgb(var(--vurgu-600) / <alpha-value>)',
          700: 'rgb(var(--vurgu-700) / <alpha-value>)',
          800: 'rgb(var(--vurgu-800) / <alpha-value>)',
          900: 'rgb(var(--vurgu-900) / <alpha-value>)',
          950: 'rgb(var(--vurgu-950) / <alpha-value>)',
        },
        pink: {
          50: 'rgb(var(--yan-50) / <alpha-value>)',
          100: 'rgb(var(--yan-100) / <alpha-value>)',
          200: 'rgb(var(--yan-200) / <alpha-value>)',
          300: 'rgb(var(--yan-300) / <alpha-value>)',
          400: 'rgb(var(--yan-400) / <alpha-value>)',
          500: 'rgb(var(--yan-500) / <alpha-value>)',
          600: 'rgb(var(--yan-600) / <alpha-value>)',
          700: 'rgb(var(--yan-700) / <alpha-value>)',
          800: 'rgb(var(--yan-800) / <alpha-value>)',
          900: 'rgb(var(--yan-900) / <alpha-value>)',
          950: 'rgb(var(--yan-950) / <alpha-value>)',
        },
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        primary: {
          DEFAULT: 'hsl(var(--primary))',
          foreground: 'hsl(var(--primary-foreground))',
        },
        secondary: {
          DEFAULT: 'hsl(var(--secondary))',
          foreground: 'hsl(var(--secondary-foreground))',
        },
        destructive: {
          DEFAULT: 'hsl(var(--destructive))',
          foreground: 'hsl(var(--destructive-foreground))',
        },
        muted: {
          DEFAULT: 'hsl(var(--muted))',
          foreground: 'hsl(var(--muted-foreground))',
        },
        accent: {
          DEFAULT: 'hsl(var(--accent))',
          foreground: 'hsl(var(--accent-foreground))',
        },
        popover: {
          DEFAULT: 'hsl(var(--popover))',
          foreground: 'hsl(var(--popover-foreground))',
        },
        card: {
          DEFAULT: 'hsl(var(--card))',
          foreground: 'hsl(var(--card-foreground))',
        },
        sidebar: {
          DEFAULT: 'hsl(var(--sidebar-background))',
          foreground: 'hsl(var(--sidebar-foreground))',
          primary: 'hsl(var(--sidebar-primary))',
          'primary-foreground': 'hsl(var(--sidebar-primary-foreground))',
          accent: 'hsl(var(--sidebar-accent))',
          'accent-foreground': 'hsl(var(--sidebar-accent-foreground))',
          border: 'hsl(var(--sidebar-border))',
          ring: 'hsl(var(--sidebar-ring))',
        },
      },
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)',
      },
      keyframes: {
        'accordion-down': {
          from: {
            height: '0',
          },
          to: {
            height: 'var(--radix-accordion-content-height)',
          },
        },
        'accordion-up': {
          from: {
            height: 'var(--radix-accordion-content-height)',
          },
          to: {
            height: '0',
          },
        },
      },
      animation: {
        'accordion-down': 'accordion-down 0.2s ease-out',
        'accordion-up': 'accordion-up 0.2s ease-out',
      },
    },
  },
  plugins: [tailwindcssAnimate, tailwindcssAspectRatio, tailwindcssTypography],
} satisfies Config;
