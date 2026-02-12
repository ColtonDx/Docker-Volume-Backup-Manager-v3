import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

export type ColorTheme = "cyan" | "purple" | "red" | "green";

interface ColorThemeContextValue {
  colorTheme: ColorTheme;
  setColorTheme: (theme: ColorTheme) => void;
}

const ColorThemeContext = createContext<ColorThemeContextValue>({
  colorTheme: "cyan",
  setColorTheme: () => {},
});

const STORAGE_KEY = "backup-buddy-color-theme";

export function ColorThemeProvider({ children }: { children: ReactNode }) {
  const [colorTheme, setColorThemeState] = useState<ColorTheme>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved && ["cyan", "purple", "red", "green"].includes(saved)) {
        return saved as ColorTheme;
      }
    } catch {}
    return "cyan";
  });

  useEffect(() => {
    const root = document.documentElement;
    if (colorTheme === "cyan") {
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
