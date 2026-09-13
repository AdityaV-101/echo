import { useState } from "react";

export default function Tooltip({ text }) {
  const [open, setOpen] = useState(false);
  return (
    <span className="tooltip-wrap">
      <button
        type="button"
        className="tooltip-trigger"
        onClick={() => setOpen((o) => !o)}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        aria-label="More info"
      >
        i
      </button>
      {open && <div className="tooltip-bubble">{text}</div>}
    </span>
  );
}
