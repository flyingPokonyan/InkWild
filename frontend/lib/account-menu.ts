export type AccountMenuItemKey = "profile" | "credits" | "settings" | "logout";

export interface AccountMenuItem {
  key: AccountMenuItemKey;
  href: string | null;
}

export function getAccountMenuItems(): AccountMenuItem[] {
  return [
    { key: "profile", href: "/me" },
    { key: "credits", href: "/me/credits" },
    { key: "settings", href: null },
    { key: "logout", href: null },
  ];
}
