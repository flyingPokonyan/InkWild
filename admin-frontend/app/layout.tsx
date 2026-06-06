import type { Metadata } from "next";

import { AdminShell } from "@/components/AdminShell";
import { AuthGate } from "@/components/AuthGate";
import { Providers } from "@/app/providers";

import "./globals.css";

export const metadata: Metadata = {
  title: "InkWild · Admin Console",
  description: "InkWild 运营控制台",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body>
        <Providers>
          <AuthGate>
            <AdminShell>{children}</AdminShell>
          </AuthGate>
        </Providers>
      </body>
    </html>
  );
}
