import type { Metadata, Viewport } from "next";
import { NextIntlClientProvider } from "next-intl";
import { getLocale, getMessages } from "next-intl/server";

import { AuthBootstrap } from "@/components/AuthBootstrap";
import { BottomTabBar } from "@/components/BottomTabBar";
import { InstallPrompt } from "@/components/InstallPrompt";
import { OpeningLoadingOverlay } from "@/components/OpeningLoadingOverlay";
import { QueryProvider } from "@/components/QueryProvider";
import { ConfirmProvider } from "@/components/ui/ConfirmDialog";
import StyledJsxRegistry from "./registry";

import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "InkWild",
    template: "%s | InkWild",
  },
  description: "AI 驱动的互动叙事引擎，每一个选择塑造独一无二的故事。",
  manifest: "/manifest.webmanifest",
  applicationName: "InkWild",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "InkWild",
  },
  icons: {
    icon: [{ url: "/favicon.svg", type: "image/svg+xml" }],
    apple: [{ url: "/icon.svg", type: "image/svg+xml" }],
    shortcut: [{ url: "/favicon.svg" }],
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#0a0a0c",
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const locale = await getLocale();
  const messages = await getMessages();
  const htmlLang = locale === "en" ? "en" : "zh-CN";
  return (
    <html lang={htmlLang} className="h-full antialiased" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,500;1,300;1,400&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&family=Noto+Serif+SC:wght@300;400;500;600&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="lv-theme min-h-full flex flex-col" suppressHydrationWarning>
        <StyledJsxRegistry>
          <NextIntlClientProvider locale={locale} messages={messages}>
            <QueryProvider>
              <ConfirmProvider>
                <AuthBootstrap />
                {children}
                <BottomTabBar />
                <InstallPrompt />
                <OpeningLoadingOverlay />
              </ConfirmProvider>
            </QueryProvider>
          </NextIntlClientProvider>
        </StyledJsxRegistry>
      </body>
    </html>
  );
}
