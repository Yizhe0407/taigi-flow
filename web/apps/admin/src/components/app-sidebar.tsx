"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BookOpen,
  Bot,
  History,
  LayoutDashboard,
  MessageSquare,
  Radio,
} from "lucide-react";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  SidebarTrigger,
} from "@/components/ui/sidebar";

const NAV = [
  { href: "/agents",     label: "Role", icon: Bot },
  { href: "/knowledge",  label: "RAG",     icon: BookOpen },
  { href: "/dictionary", label: "發音字典",   icon: MessageSquare },
  { href: "/sessions",   label: "對話日誌",   icon: History },
  { href: "/monitor",    label: "即時監控",   icon: Radio },
];

export function AppSidebar() {
  const pathname = usePathname();

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        {/* Expanded: logo + collapse trigger */}
        <div className="flex items-center gap-1 group-data-[collapsible=icon]:hidden">
          <SidebarMenu className="flex-1">
            <SidebarMenuItem>
              <SidebarMenuButton size="lg" render={<Link href="/agents" />}>
                <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                  <LayoutDashboard className="size-4" />
                </div>
                <div className="flex flex-col gap-0.5 leading-none">
                  <span className="font-bold">Taigi Flow</span>
                  <span className="text-xs text-muted-foreground">管理後台</span>
                </div>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
          <SidebarTrigger size="icon" className="shrink-0" />
        </div>
        {/* Collapsed: only expand trigger */}
        <div className="hidden group-data-[collapsible=icon]:flex justify-center py-1">
          <SidebarTrigger size="icon" />
        </div>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>功能</SidebarGroupLabel>
          <SidebarMenu>
            {NAV.map(({ href, label, icon: Icon }) => {
              const active =
                href === "/agents"
                  ? pathname === "/agents" || pathname.startsWith("/agents/")
                  : pathname.startsWith(href);
              return (
                <SidebarMenuItem key={href}>
                  <SidebarMenuButton
                    render={<Link href={href} />}
                    isActive={active}
                    tooltip={label}
                  >
                    <Icon />
                    <span>{label}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              );
            })}
          </SidebarMenu>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter />
      <SidebarRail />
    </Sidebar>
  );
}
