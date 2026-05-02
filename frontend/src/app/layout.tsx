import type { Metadata } from "next";
import { Inter_Tight, JetBrains_Mono } from "next/font/google";
import { Toaster } from "@/components/ui/sonner";
import { DesktopSidebar, MobileSidebar } from "@/components/sidebar";
import { ErrorBoundary } from "@/components/error-boundary";
import { AuthProvider } from "@/lib/auth-context";
import { ThemeProvider } from "@/components/theme-provider";
import "./globals.css";

const interTight = Inter_Tight({
  variable: "--font-sans",
  subsets: ["latin"],
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "quantsense — editorial trading terminal",
  description: "Personal quantitative research and paper trading terminal",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${interTight.variable} ${jetbrainsMono.variable} h-full`}
      suppressHydrationWarning
    >
      <body className="min-h-full bg-background font-sans text-foreground antialiased">
        <ThemeProvider>
          <AuthProvider>
            <DesktopSidebar />

            {/* Main content area, offset by sidebar width on desktop */}
            <div className="flex min-h-screen flex-col md:pl-56">
              {/* Mobile header */}
              <header className="sticky top-0 z-20 flex h-12 items-center gap-3 border-b border-border bg-background/85 px-4 backdrop-blur md:hidden">
                <MobileSidebar />
                <span className="flex items-center gap-1.5 text-sm font-medium tracking-tight text-foreground">
                  quantsense
                  <span className="size-1.5 rounded-full bg-primary" aria-hidden />
                </span>
              </header>

              <main className="flex-1 px-4 py-5 md:px-8 md:py-7">
                <ErrorBoundary>{children}</ErrorBoundary>
              </main>
            </div>

            <Toaster position="bottom-right" />
          </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
