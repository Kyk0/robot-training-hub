export default function RobotIllustration({
  compact = false,
}: {
  compact?: boolean;
}) {
  return (
    <svg
      className={"robot-art " + (compact ? "compact" : "")}
      viewBox="0 0 480 460"
      fill="none"
      aria-hidden="true"
    >
      <defs>
        <linearGradient
          id="robot-metal"
          x1="170"
          y1="80"
          x2="310"
          y2="400"
          gradientUnits="userSpaceOnUse"
        >
          <stop stopColor="#fff" />
          <stop offset="1" stopColor="#aab8df" />
        </linearGradient>
        <linearGradient
          id="robot-core"
          x1="210"
          y1="155"
          x2="282"
          y2="260"
          gradientUnits="userSpaceOnUse"
        >
          <stop stopColor="#b7a2ff" />
          <stop offset="1" stopColor="#6753db" />
        </linearGradient>
        <radialGradient id="robot-glow">
          <stop stopColor="#a899ff" stopOpacity=".3" />
          <stop offset="1" stopColor="#8b80e9" stopOpacity="0" />
        </radialGradient>
        <filter id="robot-shadow">
          <feGaussianBlur stdDeviation="10" />
        </filter>
      </defs>
      <circle cx="240" cy="230" r="215" fill="url(#robot-glow)" />
      <g stroke="#c4c6f5" strokeOpacity=".2">
        <ellipse
          cx="240"
          cy="250"
          rx="207"
          ry="66"
          transform="rotate(-22 240 250)"
        />
        <ellipse
          cx="240"
          cy="250"
          rx="207"
          ry="66"
          transform="rotate(36 240 250)"
        />
        <circle cx="240" cy="230" r="175" strokeDasharray="3 12" />
      </g>
      <ellipse
        cx="249"
        cy="414"
        rx="90"
        ry="12"
        fill="#060b24"
        opacity=".45"
        filter="url(#robot-shadow)"
      />
      <g stroke="#6b779d" strokeWidth="2" strokeLinejoin="round">
        <path
          d="m207 267-12 62 8 56 27 2 4-60 11-54"
          fill="url(#robot-metal)"
        />
        <path
          d="m252 274 18 56-3 54 28 5 15-61-16-64"
          fill="url(#robot-metal)"
        />
        <path d="m201 378-10 23 3 10 44-1 1-19-10-13" fill="#dce4fb" />
        <path d="m270 378-2 28 9 7 44-4-5-13-23-14" fill="#dce4fb" />
        <path
          d="m198 166-22 14-10 53 15 12 19-10 15-56"
          fill="url(#robot-metal)"
        />
        <path d="m171 232-21 49 12 12 16-8 16-47" fill="url(#robot-metal)" />
        <path d="m151 280-5 21 9 10 16-7 6-21" fill="#c5cfee" />
        <path
          d="m292 165 25 12 18 47-13 19-19-10-22-52"
          fill="url(#robot-metal)"
        />
        <path d="m321 224 20-45 20 4-1 20-18 37" fill="url(#robot-metal)" />
        <path d="m340 182-1-21 10-13 19 7-6 27" fill="#d6dff6" />
        <path
          d="m204 161 38-10 44 12 13 56-16 45-60 3-27-46"
          fill="url(#robot-metal)"
        />
        <path
          d="m217 177 28-7 27 9 5 37-14 17-38-1-15-19"
          fill="url(#robot-core)"
          stroke="#a99cea"
        />
        <path d="m224 244 46-2 13 20-13 17-44-1-13-16" fill="#344263" />
        <path d="m236 139-2 18 21 1 6-20" fill="#485779" />
        <path
          d="m218 90 33-7 30 16-2 35-18 15-35-5-16-21"
          fill="url(#robot-metal)"
        />
        <path d="m219 107 45 2 2 17-42 1" fill="#202e50" />
      </g>
      <g fill="#b8b0ff">
        <circle cx="235" cy="117" r="3" />
        <circle cx="252" cy="117" r="3" />
        <rect x="231" y="191" width="28" height="4" rx="2" />
        <rect x="231" y="201" width="19" height="3" rx="1.5" />
      </g>
      <g fill="#273758" stroke="#8b98be" strokeWidth="3">
        <circle cx="186" cy="180" r="12" />
        <circle cx="308" cy="180" r="12" />
        <circle cx="211" cy="327" r="11" />
        <circle cx="288" cy="328" r="11" />
      </g>
      <g fill="#c4c2ff">
        <circle cx="79" cy="240" r="5" />
        <circle cx="369" cy="102" r="4" />
        <circle cx="386" cy="321" r="3" />
      </g>
    </svg>
  );
}
