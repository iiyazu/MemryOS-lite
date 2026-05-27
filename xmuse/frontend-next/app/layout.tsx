import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "xmuse Observability",
  description: "Anthropic-inspired local observability frontend for xmuse God collaboration"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
