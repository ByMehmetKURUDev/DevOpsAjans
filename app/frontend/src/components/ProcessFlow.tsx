import { useTranslation } from 'react-i18next';

/**
 * Süreç akış şeması.
 *
 * Fotoğraf yerine çizim: dört aşamanın sırasını ve İnşa Et aşamasındaki
 * haftalık sürüm döngüsünü gösteriyor — süslemeden çok bilgi taşıyor.
 * SVG olduğu için ekran boyutundan bağımsız keskin ve birkaç yüz bayt.
 *
 * `role="img"` + `aria-label`: ekran okuyucu şemanın ne anlattığını
 * tek cümlede alıyor, içindeki metinler ayrıca okunmuyor.
 */
export default function ProcessFlow({ className = '' }: { className?: string }) {
  const { t } = useTranslation();

  const steps = [
    t('process.step1Title'),
    t('process.step2Title'),
    t('process.step3Title'),
    t('process.step4Title'),
  ];

  const boxWidth = 118;
  const gap = 28;
  const x = (index: number) => 10 + index * (boxWidth + gap);

  return (
    <svg
      viewBox="0 0 594 140"
      className={`w-full max-w-xl ${className}`}
      role="img"
      aria-label={t('process.flowAlt')}
    >
      <defs>
        <linearGradient id="akis" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#8b3dff" />
          <stop offset="100%" stopColor="#ec4899" />
        </linearGradient>
        <marker id="ok" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto">
          <path d="M0 0 L8 4 L0 8 z" fill="url(#akis)" />
        </marker>
      </defs>

      {steps.map((label, index) => (
        <g key={label}>
          <rect
            x={x(index)}
            y="28"
            width={boxWidth}
            height="46"
            rx="12"
            fill="rgba(255,255,255,0.04)"
            stroke="rgba(255,255,255,0.14)"
          />
          <text
            x={x(index) + boxWidth / 2}
            y="47"
            textAnchor="middle"
            fill="#9d8cbf"
            fontSize="10"
            fontFamily="ui-monospace, monospace"
            letterSpacing="1.4"
          >
            0{index + 1}
          </text>
          <text
            x={x(index) + boxWidth / 2}
            y="64"
            textAnchor="middle"
            fill="#ece6ff"
            fontSize="14"
            fontWeight="600"
          >
            {label}
          </text>

          {index < steps.length - 1 ? (
            <line
              x1={x(index) + boxWidth + 4}
              y1="51"
              x2={x(index + 1) - 6}
              y2="51"
              stroke="url(#akis)"
              strokeWidth="2"
              markerEnd="url(#ok)"
            />
          ) : null}
        </g>
      ))}

      {/* İnşa Et aşamasından geri dönen haftalık sürüm döngüsü */}
      <path
        d={`M ${x(2) + boxWidth / 2} 78 L ${x(2) + boxWidth / 2} 104 L ${x(1) + boxWidth / 2} 104 L ${x(1) + boxWidth / 2} 82`}
        fill="none"
        stroke="url(#akis)"
        strokeWidth="1.5"
        strokeDasharray="4 4"
        markerEnd="url(#ok)"
        opacity="0.75"
      />
      <text
        x={(x(1) + x(2) + boxWidth) / 2}
        y="122"
        textAnchor="middle"
        fill="#9d8cbf"
        fontSize="11"
        fontFamily="ui-monospace, monospace"
      >
        {t('process.flowLoop')}
      </text>
    </svg>
  );
}
