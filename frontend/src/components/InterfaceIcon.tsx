import type { CSSProperties } from "react";

export type IconName = "pulse" | "dashboard" | "book" | "info" | "refresh" | "plus" | "trash" | "user" | "heart" | "layers" | "queue" | "chevron";
const paths: Record<IconName, string[]> = {
  pulse: ["M3 12h4l3-7 4 14 3-7h4"],
  dashboard: ["M3 3h7v7H3z", "M14 3h7v7h-7z", "M3 14h7v7H3z", "M14 14h7v7h-7z"],
  book: ["M12 5v16", "M3 4h5a4 4 0 0 1 4 2 4 4 0 0 1 4-2h5v15h-5a4 4 0 0 0-4 2 4 4 0 0 0-4-2H3z"],
  info: ["M12 8h.01", "M12 11v5", "M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0"],
  refresh: ["M20 7v5h-5", "M4 17v-5h5", "M6 6a8 8 0 0 1 13 2l1 4", "M18 18a8 8 0 0 1-13-2l-1-4"],
  plus: ["M12 5v14", "M5 12h14"],
  trash: ["M3 6h18", "M9 6V3h6v3", "M5 6l1 15h12l1-15", "M10 10v7", "M14 10v7"],
  user: ["M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0", "M4 21v-2a8 8 0 0 1 16 0v2"],
  heart: ["M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8"],
  layers: ["m12 3 10 5-10 5L2 8z", "m2 12 10 5 10-5", "m2 16 10 5 10-5"],
  queue: ["M8 6h13", "M8 12h13", "M8 18h13", "M3 6h.01", "M3 12h.01", "M3 18h.01"],
  chevron: ["m9 5 7 7-7 7"],
};

/** Small code-native icons are decorative; visible labels carry every meaning. */
export default function InterfaceIcon({ name, className = "", style }: { name: IconName; className?: string; style?: CSSProperties }) {
  return <svg className={`interface-icon ${className}`} style={style} width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
    {paths[name].map((path, index) => <path d={path} key={index} />)}
  </svg>;
}
