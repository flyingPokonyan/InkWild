export type DrawerMode = "docked" | "modal";

const DOCKED_DRAWER_BREAKPOINT = 1200;

export function getDrawerMode(width: number): DrawerMode {
  return width >= DOCKED_DRAWER_BREAKPOINT ? "docked" : "modal";
}

export function shouldOffsetTimelineForDrawer(): boolean {
  return false;
}
