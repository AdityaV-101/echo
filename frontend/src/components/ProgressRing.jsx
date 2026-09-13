import { useEffect, useState } from "react";

export default function ProgressRing({ percent, size = 140, stroke = 14 }) {
  const [animatedPercent, setAnimatedPercent] = useState(0);
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;

  useEffect(() => {
    const id = requestAnimationFrame(() => setAnimatedPercent(percent));
    return () => cancelAnimationFrame(id);
  }, [percent]);

  const offset = circumference - (animatedPercent / 100) * circumference;
  const tier = percent >= 80 ? "high" : percent >= 50 ? "mid" : "low";
  const gradientId = `progressRingGradient-${tier}`;
  const glow = percent >= 80 ? "rgba(62, 203, 126, 0.45)" : percent >= 50 ? "rgba(255, 184, 77, 0.45)" : "rgba(255, 107, 107, 0.4)";
  const gradientStops =
    tier === "high"
      ? ["#7ee2a8", "#3ecb7e"]
      : tier === "mid"
        ? ["#ffd082", "#ffb84d"]
        : ["#ff9d9d", "#ff6b6b"];

  return (
    <div className="progress-ring" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ filter: `drop-shadow(0 4px 14px ${glow})` }}>
        <defs>
          <linearGradient id={gradientId} x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor={gradientStops[0]} />
            <stop offset="100%" stopColor={gradientStops[1]} />
          </linearGradient>
        </defs>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--color-ring-track)"
          strokeWidth={stroke}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={`url(#${gradientId})`}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          style={{ transition: "stroke-dashoffset 1s cubic-bezier(0.34,1.2,0.4,1), stroke 0.4s" }}
        />
      </svg>
      <div className="progress-ring-label">{percent}%</div>
    </div>
  );
}
