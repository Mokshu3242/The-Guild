"use client";

import { useState } from "react";

// Round photo, or initials when there is no photo or it fails to load.
export function Avatar({
  name,
  url,
  size = 36,
  className = "",
}: {
  name: string;
  url?: string | null;
  size?: number;
  className?: string;
}) {
  const [broken, setBroken] = useState<string | null>(null);
  const showPhoto = !!url && broken !== url;
  const letters =
    name
      .trim()
      .split(/\s+/)
      .filter(Boolean)
      .map((p) => p[0])
      .slice(0, 2)
      .join("")
      .toUpperCase() || "?";

  return (
    <span
      className={`relative inline-grid shrink-0 place-items-center overflow-hidden rounded-full bg-guild-deep font-semibold text-seal-bright ${className}`}
      style={{ width: size, height: size, fontSize: Math.round(size * 0.38) }}
      aria-hidden="true"
    >
      {showPhoto ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={url!}
          alt=""
          className="h-full w-full object-cover"
          onError={() => setBroken(url!)}
          referrerPolicy="no-referrer"
        />
      ) : (
        letters
      )}
    </span>
  );
}
