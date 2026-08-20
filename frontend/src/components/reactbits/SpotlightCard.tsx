/**
 * SpotlightCard — React Bits (reactbits.dev/components/spotlight-card), adapted.
 *
 * Adaptations: TypeScript props; the hard-coded #111/#222/1.5rem card styling
 * from the docs is dropped so the card inherits Aegis's own `aegis-surface`
 * tokens (the spotlight is an overlay effect, not a replacement skin).
 *
 * Used on EXACTLY ONE surface in this app: the Decision Summary card.
 */

import { useRef, type ReactNode } from "react";

import "./SpotlightCard.css";

export default function SpotlightCard({
  children,
  className = "",
  spotlightColor = "rgba(51, 51, 204, 0.07)",
}: {
  children: ReactNode;
  className?: string;
  spotlightColor?: string;
}) {
  const divRef = useRef<HTMLDivElement>(null);

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const el = divRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    el.style.setProperty("--mouse-x", `${e.clientX - rect.left}px`);
    el.style.setProperty("--mouse-y", `${e.clientY - rect.top}px`);
    el.style.setProperty("--spotlight-color", spotlightColor);
  };

  return (
    <div ref={divRef} onMouseMove={handleMouseMove} className={`card-spotlight ${className}`}>
      {children}
    </div>
  );
}
