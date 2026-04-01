import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";

export type RefreshInterval = 0 | 10 | 30 | 60 | 300;

export interface RefreshOption {
  value: RefreshInterval;
  label: string;
}

export const REFRESH_OPTIONS: RefreshOption[] = [
  { value: 0,   label: "Off" },
  { value: 10,  label: "10s" },
  { value: 30,  label: "30s" },
  { value: 60,  label: "1m" },
  { value: 300, label: "5m" },
];

const STORAGE_KEY = "dvbm-auto-refresh";

interface AutoRefreshContextValue {
  interval: RefreshInterval;
  setInterval: (v: RefreshInterval) => void;
}

const AutoRefreshContext = createContext<AutoRefreshContextValue>({
  interval: 0,
  setInterval: () => {},
});

export function AutoRefreshProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();

  const [interval, setIntervalState] = useState<RefreshInterval>(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      const n = Number(stored);
      if (REFRESH_OPTIONS.some((o) => o.value === n)) return n as RefreshInterval;
    }
    return 0;
  });

  const setInterval = useCallback((v: RefreshInterval) => {
    setIntervalState(v);
    localStorage.setItem(STORAGE_KEY, String(v));
  }, []);

  useEffect(() => {
    if (interval === 0) return;

    const id = window.setInterval(() => {
      queryClient.invalidateQueries();
    }, interval * 1000);

    return () => window.clearInterval(id);
  }, [interval, queryClient]);

  return (
    <AutoRefreshContext.Provider value={{ interval, setInterval }}>
      {children}
    </AutoRefreshContext.Provider>
  );
}

export const useAutoRefresh = () => useContext(AutoRefreshContext);
