/** Inline SVG icons. No icon-font dependency, and each carries a title for
 *  assistive technology where it conveys meaning rather than decoration. */
const base = { width: 18, height: 18, viewBox: "0 0 24 24", fill: "none",
  stroke: "currentColor", strokeWidth: 1.9, strokeLinecap: "round",
  strokeLinejoin: "round", "aria-hidden": true };

export const IconHome = (p) => (<svg {...base} {...p}><path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/></svg>);
export const IconMap = (p) => (<svg {...base} {...p}><path d="M9 3 3 5.5v16L9 19l6 2.5 6-2.5v-16L15 5.5 9 3Z"/><path d="M9 3v16M15 5.5v16"/></svg>);
export const IconChart = (p) => (<svg {...base} {...p}><path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/></svg>);
export const IconBell = (p) => (<svg {...base} {...p}><path d="M18 9a6 6 0 1 0-12 0c0 6-2 7-2 7h16s-2-1-2-7Z"/><path d="M10.5 20a2 2 0 0 0 3 0"/></svg>);
export const IconDoc = (p) => (<svg {...base} {...p}><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Z"/><path d="M14 3v5h5M9 13h6M9 17h6"/></svg>);
export const IconInfo = (p) => (<svg {...base} {...p}><circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/></svg>);
export const IconDrop = (p) => (<svg {...base} {...p}><path d="M12 3s6 6.2 6 10a6 6 0 0 1-12 0c0-3.8 6-10 6-10Z"/></svg>);
export const IconRain = (p) => (<svg {...base} {...p}><path d="M7 15a4.5 4.5 0 0 1 .6-8.96A5.5 5.5 0 0 1 18 7.5a3.75 3.75 0 0 1 0 7.5"/><path d="M9 19l-.7 1.6M13 19l-.7 1.6M17 19l-.7 1.6"/></svg>);
export const IconWarn = (p) => (<svg {...base} {...p}><path d="M10.3 3.6 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.6a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4M12 17h.01"/></svg>);
export const IconPin = (p) => (<svg {...base} {...p}><path d="M12 21s7-5.5 7-11a7 7 0 1 0-14 0c0 5.5 7 11 7 11Z"/><circle cx="12" cy="10" r="2.5"/></svg>);
export const IconSpark = (p) => (<svg {...base} {...p}><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1"/></svg>);
export const IconLogo = (p) => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden {...p}>
    <path d="M12 2.5S18.5 9 18.5 13.5a6.5 6.5 0 0 1-13 0C5.5 9 12 2.5 12 2.5Z" fill="#fff" opacity=".95"/>
    <path d="M8.6 13.8c1.4.9 2.6-.7 4-.7s2.3 1.4 3.4.4" stroke="#0e7490" strokeWidth="1.6" strokeLinecap="round"/>
  </svg>
);
