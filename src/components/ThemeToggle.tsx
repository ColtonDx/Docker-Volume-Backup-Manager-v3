import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { Button } from "@/components/ui/button";
import { useColorTheme, DARK_ONLY_THEMES } from "@/contexts/ColorThemeContext";

export function ThemeToggle() {
  const { setTheme, theme } = useTheme();
  const { colorTheme } = useColorTheme();

  // Hide toggle for dark-only themes (cyberpunk, synthwave)
  if (DARK_ONLY_THEMES.includes(colorTheme)) return null;

  const toggleTheme = () => {
    setTheme(theme === "dark" ? "light" : "dark");
  };

  return (
    <Button variant="ghost" size="icon" className="h-9 w-9" onClick={toggleTheme}>
      <Sun className="h-4 w-4 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
      <Moon className="absolute h-4 w-4 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
      <span className="sr-only">Toggle theme</span>
    </Button>
  );
}
