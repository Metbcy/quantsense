"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  FlaskConical,
  Brain,
  Settings,
  Menu,
  BarChart3,
  LineChart,
  LogIn,
  LogOut,
  User,
  Sun,
  Moon,
  Briefcase,
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

type NavItem = {
  href: string;
  label: string;
  icon: typeof LayoutDashboard;
};

const navSections: { label: string; items: NavItem[] }[] = [
  {
    label: "Overview",
    items: [{ href: "/", label: "Dashboard", icon: LayoutDashboard }],
  },
  {
    label: "Research",
    items: [
      { href: "/backtest", label: "Backtest", icon: FlaskConical },
      { href: "/portfolio", label: "Portfolio", icon: Briefcase },
      { href: "/compare", label: "Compare", icon: BarChart3 },
      { href: "/charts", label: "Charts", icon: LineChart },
      { href: "/sentiment", label: "Sentiment", icon: Brain },
    ],
  },
  {
    label: "System",
    items: [{ href: "/settings", label: "Settings", icon: Settings }],
  },
];

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();

  return (
    <nav className="flex flex-col gap-5 px-3">
      {navSections.map((section) => (
        <div key={section.label} className="flex flex-col gap-0.5">
          <span className="px-2 pb-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground/70">
            {section.label}
          </span>
          {section.items.map(({ href, label, icon: Icon }) => {
            const isActive =
              href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                onClick={onNavigate}
                className={cn(
                  "group relative flex items-center gap-2.5 rounded-md py-1.5 pl-3 pr-2 text-[13px] transition-colors duration-150",
                  isActive
                    ? "text-foreground"
                    : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
                )}
              >
                {/* 2px ochre indicator bar on active */}
                <span
                  aria-hidden
                  className={cn(
                    "absolute left-0 top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-full bg-primary transition-opacity duration-150",
                    isActive ? "opacity-100" : "opacity-0",
                  )}
                />
                <Icon className="size-4 shrink-0" strokeWidth={1.75} />
                <span className="truncate">{label}</span>
              </Link>
            );
          })}
        </div>
      ))}
    </nav>
  );
}

function Brand() {
  return (
    <div className="flex items-center gap-1.5 px-5 py-5">
      <span className="text-[15px] font-medium tracking-tight text-sidebar-foreground">
        quantsense
      </span>
      <span
        className="size-1.5 rounded-full bg-primary"
        aria-hidden
        title="quantsense"
      />
    </div>
  );
}

function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const mounted = useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );
  const isDark = resolvedTheme === "dark";

  return (
    <button
      onClick={() => setTheme(isDark ? "light" : "dark")}
      className="flex w-full items-center gap-2.5 rounded-md px-3 py-1.5 text-[13px] text-muted-foreground transition-colors duration-150 hover:bg-accent/60 hover:text-foreground"
      title={
        mounted ? (isDark ? "Switch to light mode" : "Switch to dark mode") : "Toggle theme"
      }
    >
      {mounted ? (
        isDark ? (
          <Sun className="size-4" strokeWidth={1.75} />
        ) : (
          <Moon className="size-4" strokeWidth={1.75} />
        )
      ) : (
        <Sun className="size-4" strokeWidth={1.75} />
      )}
      {mounted ? (isDark ? "Light mode" : "Dark mode") : "Toggle theme"}
    </button>
  );
}

function UserSection() {
  const { user, logout } = useAuth();
  if (!user) {
    return (
      <div className="px-3 pb-2">
        <Link
          href="/login"
          className="flex items-center gap-2.5 rounded-md px-3 py-1.5 text-[13px] text-muted-foreground transition-colors duration-150 hover:bg-accent/60 hover:text-foreground"
        >
          <LogIn className="size-4" strokeWidth={1.75} />
          Sign in
        </Link>
      </div>
    );
  }
  return (
    <div className="border-t border-sidebar-border px-3 py-3">
      <div className="flex items-center gap-2 px-1">
        <User className="size-4 text-muted-foreground" strokeWidth={1.75} />
        <span className="flex-1 truncate text-[13px] text-foreground">
          {user.username}
        </span>
        <button
          onClick={logout}
          className="text-muted-foreground transition-colors duration-150 hover:text-foreground"
          title="Sign out"
        >
          <LogOut className="size-4" strokeWidth={1.75} />
        </button>
      </div>
    </div>
  );
}

/** Desktop sidebar — always visible on md+ screens */
export function DesktopSidebar() {
  return (
    <aside className="z-30 hidden border-r border-sidebar-border bg-sidebar md:fixed md:inset-y-0 md:flex md:w-56 md:flex-col">
      <Brand />
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
          <Button variant="ghost" size="icon-sm" className="text-muted-foreground">
            <Menu className="size-5" strokeWidth={1.75} />
            <span className="sr-only">Toggle menu</span>
          </Button>
        </SheetTrigger>
        <SheetContent
          side="left"
          className="flex w-56 flex-col border-sidebar-border bg-sidebar p-0"
        >
          <SheetTitle className="sr-only">Navigation</SheetTitle>
          <Brand />
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
