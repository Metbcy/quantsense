"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  FlaskConical,
  Brain,
  Settings,
  Menu,
  TrendingUp,
  BarChart3,
  LineChart,
  LogIn,
  LogOut,
  User,
  Sun,
  Moon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetTrigger,
  SheetContent,
  SheetTitle,
} from "@/components/ui/sheet";
import { cn } from "@/lib/utils";
import { useState, useSyncExternalStore } from "react";
import { HealthIndicator } from "@/components/health-indicator";
import { useAuth } from "@/lib/auth-context";
import { useTheme } from "next-themes";

const navItems = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/backtest", label: "Backtest", icon: FlaskConical },
  { href: "/compare", label: "Compare", icon: BarChart3 },
  { href: "/charts", label: "Charts", icon: LineChart },
  { href: "/sentiment", label: "Sentiment", icon: Brain },
  { href: "/settings", label: "Settings", icon: Settings },
] as const;

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();

  return (
    <nav className="flex flex-col gap-1 px-3">
      {navItems.map(({ href, label, icon: Icon }) => {
        const isActive = href === "/" ? pathname === "/" : pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            onClick={onNavigate}
            className={cn(
              "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
              isActive
                ? "bg-blue-600/15 text-blue-400"
                : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
            )}
          >
            <Icon className="size-4 shrink-0" />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}

function Logo() {
  return (
    <div className="flex items-center gap-2.5 px-6 py-5">
      <div className="flex size-8 items-center justify-center rounded-lg bg-blue-600 font-bold text-white text-sm">
        <TrendingUp className="size-4" />
      </div>
      <span className="text-base font-semibold tracking-tight text-sidebar-foreground">
        QuantSense
      </span>
    </div>
  );
}

function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  // Use useSyncExternalStore to safely detect client-side mounting without hydration mismatch
  const mounted = useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );

  const isDark = resolvedTheme === "dark";

  return (
    <button
      onClick={() => setTheme(isDark ? "light" : "dark")}
      className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors w-full"
      title={mounted ? (isDark ? "Switch to light mode" : "Switch to dark mode") : "Toggle theme"}
    >
      {mounted ? (
        isDark ? <Sun className="size-4" /> : <Moon className="size-4" />
      ) : (
        <Sun className="size-4" />
      )}
      {mounted ? (isDark ? "Light Mode" : "Dark Mode") : "Toggle Theme"}
    </button>
  );
}

function UserSection() {
  const { user, logout } = useAuth();
  if (!user) {
    return (
      <div className="px-3 pb-3">
        <Link
          href="/login"
          className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
        >
          <LogIn className="size-4" />
          Sign In
        </Link>
      </div>
    );
  }
  return (
    <div className="border-t border-border px-3 py-3">
      <div className="flex items-center gap-2 px-3 py-1">
        <User className="size-4 text-muted-foreground" />
        <span className="text-sm font-medium text-foreground truncate flex-1">
          {user.username}
        </span>
        <button
          onClick={logout}
          className="text-muted-foreground hover:text-foreground transition-colors"
          title="Sign out"
        >
          <LogOut className="size-4" />
        </button>
      </div>
    </div>
  );
}

/** Desktop sidebar — always visible on md+ screens */
export function DesktopSidebar() {
  return (
    <aside className="hidden md:flex md:w-56 md:flex-col md:fixed md:inset-y-0 z-30 border-r border-sidebar-border bg-sidebar">
      <Logo />
      <NavLinks />
      <div className="mt-auto">
        <div className="px-3 pb-1">
          <ThemeToggle />
        </div>
        <UserSection />
        <HealthIndicator />
      </div>
    </aside>
  );
}

/** Mobile sidebar — sheet overlay triggered by hamburger menu */
export function MobileSidebar() {
  const [open, setOpen] = useState(false);

  return (
    <div className="md:hidden">
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetTrigger asChild>
          <Button variant="ghost" size="icon" className="text-muted-foreground">
            <Menu className="size-5" />
            <span className="sr-only">Toggle menu</span>
          </Button>
        </SheetTrigger>
        <SheetContent side="left" className="w-56 bg-sidebar p-0 border-sidebar-border flex flex-col">
          <SheetTitle className="sr-only">Navigation</SheetTitle>
          <Logo />
          <div className="flex-1">
            <NavLinks onNavigate={() => setOpen(false)} />
          </div>
          <div className="px-3 pb-1">
            <ThemeToggle />
          </div>
          <UserSection />
          <HealthIndicator />
        </SheetContent>
      </Sheet>
    </div>
  );
}
