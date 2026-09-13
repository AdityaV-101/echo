const DECOR_SETS = {
  login: [
    { emoji: "⭐", top: "8%", left: "8%", size: 30, duration: 6 },
    { emoji: "🎵", top: "14%", left: "86%", size: 34, duration: 7 },
    { emoji: "☁️", top: "42%", left: "4%", size: 42, duration: 8 },
    { emoji: "🎈", top: "72%", left: "90%", size: 36, duration: 6.5 },
    { emoji: "✨", top: "88%", left: "14%", size: 24, duration: 5.5 },
    { emoji: "🌈", top: "4%", left: "46%", size: 38, duration: 9 },
    { emoji: "💫", top: "62%", left: "6%", size: 22, duration: 7.5 },
    { emoji: "🎶", top: "24%", left: "70%", size: 26, duration: 6 },
  ],
  home: [
    { emoji: "☁️", top: "4%", left: "82%", size: 40, duration: 8 },
    { emoji: "⭐", top: "20%", left: "4%", size: 22, duration: 6 },
    { emoji: "🎵", top: "50%", left: "90%", size: 26, duration: 7 },
    { emoji: "✨", top: "80%", left: "6%", size: 22, duration: 5.5 },
    { emoji: "🦋", top: "65%", left: "88%", size: 28, duration: 9 },
  ],
  practice: [
    { emoji: "🎵", top: "6%", left: "4%", size: 24, duration: 7 },
    { emoji: "⭐", top: "88%", left: "8%", size: 22, duration: 6 },
    { emoji: "✨", top: "10%", left: "92%", size: 22, duration: 5.5 },
  ],
  celebration: [
    { emoji: "🎉", top: "10%", left: "10%", size: 40, duration: 4 },
    { emoji: "🎊", top: "15%", left: "80%", size: 40, duration: 4.5 },
    { emoji: "⭐", top: "70%", left: "12%", size: 30, duration: 5 },
    { emoji: "🌟", top: "75%", left: "82%", size: 32, duration: 5.5 },
    { emoji: "🎈", top: "40%", left: "6%", size: 34, duration: 6 },
    { emoji: "🎈", top: "45%", left: "88%", size: 34, duration: 6.5 },
  ],
};

export default function FloatingDecor({ variant = "home" }) {
  const items = DECOR_SETS[variant] || [];
  return (
    <div className="decor-layer" aria-hidden="true">
      {items.map((item, i) => (
        <span
          key={i}
          className="decor-item"
          style={{
            top: item.top,
            left: item.left,
            fontSize: item.size,
            animationDuration: `${item.duration}s`,
            animationDelay: `${i * 0.3}s`,
          }}
        >
          {item.emoji}
        </span>
      ))}
    </div>
  );
}
