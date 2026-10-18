/** HighGround's elevation motif: nested contour rings, drawn behind a scene. */

const CONTOUR =
  'M-220 -30 C-210 -130 -100 -200 20 -195 C140 -190 225 -110 228 -5 C231 100 150 190 20 200 C-110 210 -230 130 -220 -30 Z'

/** `scales` lists [scale, opacity] pairs, outermost first. */
export default function Contours({ className, scales, stroke = '#FFFFFF' }) {
  return (
    <svg className={className} viewBox="0 0 600 600" aria-hidden="true" fill="none" stroke={stroke} strokeWidth="1.5">
      <g transform="translate(300 300)">
        {scales.map(([scale, opacity]) => (
          <path
            key={scale}
            transform={scale === 1 ? undefined : `scale(${scale})`}
            d={CONTOUR}
            opacity={opacity}
          />
        ))}
      </g>
    </svg>
  )
}

