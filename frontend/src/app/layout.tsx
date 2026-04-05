import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { Toaster } from "@/components/ui/sonner";
import { DesktopSidebar, MobileSidebar } from "@/components/sidebar";
import { ErrorBoundary } from "@/components/error-boundary";
import { AuthProvider } from "@/lib/auth-context";
import { ThemeProvider } from "@/components/theme-provider";
import "./globals.css";

const inter = Inter({
  variable: "--font-sans",
  subsets: ["latin"],
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "QuantSense – Trading Dashboard",
  description: "AI-powered quantitative trading dashboard",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${jetbrainsMono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <body className="min-h-full bg-background text-foreground">
        <ThemeProvider>
        <AuthProvider>
        <DesktopSidebar />

        {/* Main content area, offset by sidebar width on desktop */}
        <div className="md:pl-56 min-h-screen flex flex-col">
          {/* Mobile header */}
          <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-border bg-background/80 px-4 backdrop-blur-md md:hidden">
            <MobileSidebar />
            <span className="text-sm font-semibold tracking-tight text-foreground">
              QuantSense
            </span>
          </header>

          <main className="flex-1 p-4 md:p-6">
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
