"use client";

import { SWRConfig } from "swr";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <SWRConfig value={{ keepPreviousData: true, dedupingInterval: 10000, revalidateOnFocus: false }}>
      {children}
    </SWRConfig>
  );
}