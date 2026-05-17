"use client";

import { usePathname } from "next/navigation";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { ThemeToggle } from "@/components/theme-toggle";

const ROUTES: Record<string, string> = {
  agents:     "Role",
  knowledge:  "RAG",
  dictionary: "發音字典",
  sessions:   "對話日誌",
  monitor:    "即時監控",
  new:        "新增",
};

function useBreadcrumbs() {
  const pathname = usePathname();
  const segments = pathname.split("/").filter(Boolean);
  return segments.map((seg, i) => ({
    label: ROUTES[seg] ?? seg,
    href: "/" + segments.slice(0, i + 1).join("/"),
    isLast: i === segments.length - 1,
  }));
}

export function AppHeader() {
  const crumbs = useBreadcrumbs();

  return (
    <header className="flex h-14 shrink-0 items-center gap-2 border-b px-4">
<Breadcrumb className="flex-1">
        <BreadcrumbList>
          {crumbs.map((crumb, i) => (
            <span key={crumb.href} className="flex items-center gap-1.5">
              {i > 0 && <BreadcrumbSeparator />}
              <BreadcrumbItem>
                {crumb.isLast ? (
                  <BreadcrumbPage>{crumb.label}</BreadcrumbPage>
                ) : (
                  <BreadcrumbLink href={crumb.href}>{crumb.label}</BreadcrumbLink>
                )}
              </BreadcrumbItem>
            </span>
          ))}
        </BreadcrumbList>
      </Breadcrumb>
      <div className="ml-auto">
        <ThemeToggle />
      </div>
    </header>
  );
}
