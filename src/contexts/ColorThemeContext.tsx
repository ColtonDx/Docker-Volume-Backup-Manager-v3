import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

/**
 * Theme ID format: "<family>-<variant>"
 * This keeps the door open for entirely new theme families
 * (e.g. "minimal-blue", "neon-pink") later.
 */
export type ThemeId = "default-blue" | "default-purple" | "default-red" | "default-green" | "cyberpunk" | "synthwave";

export interface ThemeOption {
  id: ThemeId;
  label: string;
  /** Tailwind-safe swatch colour for the picker */
  swatch: string;
  /** Preview dark-mode bg colour for the picker card */
  previewBg: string;
}

export const THEMES: ThemeOption[] = [
  { id: "default-blue",   label: "Blue",       swatch: "bg-[hsl(192,91%,36%)]",  previewBg: "bg-[hsl(222,47%,6%)]" },
  { id: "default-purple", label: "Purple",     swatch: "bg-[hsl(270,65%,50%)]",  previewBg: "bg-[hsl(270,40%,6%)]" },
  { id: "default-red",    label: "Red",        swatch: "bg-[hsl(0,72%,51%)]",    previewBg: "bg-[hsl(0,35%,6%)]" },
  { id: "default-green",  label: "Green",      swatch: "bg-[hsl(152,69%,36%)]",  previewBg: "bg-[hsl(152,35%,5%)]" },
  { id: "cyberpunk",      label: "Cyberpunk",  swatch: "bg-[hsl(54,96%,60%)]" ,  previewBg: "bg-[hsl(230,25%,4%)]" },
  { id: "synthwave",      label: "Synthwave",  swatch: "bg-[hsl(320,100%,60%)]" , previewBg: "bg-[hsl(265,35%,5%)]" },
];

const VALID_IDS = THEMES.map((t) => t.id) as string[];

interface ColorThemeContextValue {
  colorTheme: ThemeId;
  setColorTheme: (theme: ThemeId) => void;
}

const ColorThemeContext = createContext<ColorThemeContextValue>({
  colorTheme: "default-blue",
  setColorTheme: () => {},
});

const STORAGE_KEY = "backup-buddy-color-theme";

/** Migrate legacy values stored before the rename */
function migrateLegacy(raw: string | null): ThemeId | null {
  if (!raw) return null;
  const map: Record<string, ThemeId> = {
    cyan: "default-blue",
    purple: "default-purple",
    red: "default-red",
    green: "default-green",
  };
  if (map[raw]) return map[raw];
  if (VALID_IDS.includes(raw)) return raw as ThemeId;
  return null;
}

export function ColorThemeProvider({ children }: { children: ReactNode }) {
  const [colorTheme, setColorThemeState] = useState<ThemeId>(() => {
    try {
      return migrateLegacy(localStorage.getItem(STORAGE_KEY)) ?? "default-blue";
    } catch {}
    return "default-blue";
  });

  useEffect(() => {
    const root = document.documentElement;
    if (colorTheme === "default-blue") {
      root.removeAttribute("data-theme");
    } else {
      root.setAttribute("data-theme", colorTheme);
    }
    try {
      localStorage.setItem(STORAGE_KEY, colorTheme);
    } catch {}
  }, [colorTheme]);

  return (
    <ColorThemeContext.Provider value={{ colorTheme, setColorTheme: setColorThemeState }}>
      {children}
    </ColorThemeContext.Provider>
  );
}

export function useColorTheme() {
  return useContext(ColorThemeContext);
}
