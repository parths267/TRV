import type { Metadata } from "next";
import { Plus_Jakarta_Sans } from "next/font/google";
import { Shell } from "@/components/Shell";
import "./globals.css";

const sans = Plus_Jakarta_Sans({
  subsets: ["latin"],
  display: "swap",
});

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
      <body className={sans.className} suppressHydrationWarning>
        <script
          dangerouslySetInnerHTML={{
            __html: "try{var t=localStorage.getItem('bazaar_theme');if(t)document.documentElement.dataset.theme=t}catch(e){}",
          }}
        />
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
