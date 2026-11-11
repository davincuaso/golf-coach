import type { SVGProps } from "react";
export type IconName =
  | "flag"
  | "grid"
  | "settings"
  | "arrow"
  | "upload"
  | "camera"
  | "check"
  | "close"
  | "eye"
  | "lock"
  | "spark"
  | "play"
  | "download"
  | "info";
const paths: Record<IconName, string> = {
  flag: "M5 21V3m0 1c5-4 9 4 14 0v10c-5 4-9-4-14 0",
  grid: "M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z",
  settings: "M4 6h16M4 12h16M4 18h16M8 3v6m8 0v6M9 15v6",
  arrow: "M5 12h14m-6-6 6 6-6 6",
  upload: "M12 16V3m-5 5 5-5 5 5M4 16v5h16v-5",
  camera: "M4 6h4l2-3h4l2 3h4v14H4zM16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0",
  check: "m5 12 4 4L19 6",
  close: "m6 6 12 12M18 6 6 18",
  eye: "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12m13 0a3 3 0 1 1-6 0 3 3 0 0 1 6 0",
  lock: "M5 10h14v11H5zM8 10V6a4 4 0 0 1 8 0v4m-4 5v2",
  spark: "m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z",
  play: "m8 4 12 8-12 8z",
  download: "M12 3v13m-5-5 5 5 5-5M4 18v3h16v-3",
  info: "M12 11v6m0-10v.1M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0",
};
export function Icon({
  name,
  ...props
}: SVGProps<SVGSVGElement> & { name: IconName }) {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.65"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      <path d={paths[name]} />
    </svg>
  );
}
