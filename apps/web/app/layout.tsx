import type { Metadata } from "next";
import { Shell } from "@/components/Shell";
import "./globals.css";

export const metadata: Metadata = {
  title: "Stoxs8 — Indian market intelligence",
  description: "Research terminal for Indian indices, scanners, and paper trading.",
  icons: {
    icon: [{ url: "/stoxs8-mark.png", type: "image/png" }],
    apple: "/stoxs8-mark.png",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body suppressHydrationWarning>
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
