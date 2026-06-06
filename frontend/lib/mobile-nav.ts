export type MobileTabKey = "home" | "discover" | "create" | "me";

export interface MobileBottomTabDef {
  key: MobileTabKey;
  href: string;
  authRequired?: boolean;
}

export const MOBILE_BOTTOM_TABS: MobileBottomTabDef[] = [
  { key: "home", href: "/" },
  { key: "discover", href: "/discover" },
  { key: "create", href: "/workshop", authRequired: true },
  { key: "me", href: "/me", authRequired: true },
];

export function getActiveMobileTab(pathname: string): MobileTabKey | null {
  if (pathname === "/") return "home";
  if (pathname === "/discover" || pathname.startsWith("/discover/") || pathname.startsWith("/worlds/")) {
    return "discover";
  }
  if (pathname === "/workshop" || pathname.startsWith("/workshop/")) {
    return "create";
  }
  if (pathname === "/me" || pathname.startsWith("/me/")) {
    return "me";
  }
  return null;
}
