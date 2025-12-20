"use client";

import * as React from "react";

export type Theme = "light" | "dark";

const STORAGE_KEY = "aurora-theme";

type ThemeContextValue = {
  theme: Theme;
  setTheme: (theme: Theme) => void;
};

const ThemeContext = React.createContext<ThemeContextValue | undefined>(
  undefined
);

const getPreferredTheme = (): Theme => {
  if (typeof window === "undefined") return "light";

  const stored = window.localStorage.getItem(STORAGE_KEY) as Theme | null;
  if (stored === "light" || stored === "dark") return stored;

  const prefersDark = window.matchMedia?.("(prefers-color-scheme: dark)")
    .matches;
  return prefersDark ? "dark" : "light";
};

export function ThemeProvider({
  children
}: {
  children: React.ReactNode;
}) {
  const [theme, setThemeState] = React.useState<Theme>("light");

  React.useEffect(() => {
    setThemeState(getPreferredTheme());
  }, []);

  React.useEffect(() => {
    if (typeof document === "undefined") return;
    document.documentElement.setAttribute("data-theme", theme);
    window.localStorage.setItem(STORAGE_KEY, theme);
  }, [theme]);

  const setTheme = React.useCallback((nextTheme: Theme) => {
    setThemeState(nextTheme);
  }, []);

  const value = React.useMemo(
    () => ({
      theme,
      setTheme
    }),
    [theme, setTheme]
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const context = React.useContext(ThemeContext);
  if (!context) {
    throw new Error("useTheme must be used within a ThemeProvider");
  }
  return context;
}
