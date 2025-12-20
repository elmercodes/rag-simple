import type { Metadata } from "next";
import { Space_Grotesk } from "next/font/google";
import "./globals.css";
import { ThemeProvider } from "@/components/theme-provider";

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap"
});

export const metadata: Metadata = {
  title: "Doc. Chat",
  description: "A clean, streaming-ready LLM chat interface."
};

export default function RootLayout({
  children
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" data-theme="light" className={spaceGrotesk.variable}>
      <body className="h-full font-sans">
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
