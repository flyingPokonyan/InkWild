import type { LucideIcon } from "lucide-react";
import {
  ClipboardList,
  Coins,
  Database,
  FileText,
  LayoutDashboard,
  Megaphone,
  MessageSquare,
  Settings,
  Sparkles,
  Users,
  Wallet,
} from "lucide-react";

export interface NavItem {
  id: string;
  label: string;
  href?: string;
  icon: LucideIcon;
  tag?: string;
  disabled?: boolean;
}

export interface NavSection {
  label: string;
  items: NavItem[];
}

// 分组依据 = 未来角色权限边界（客服/运营 · 内容审核 · 技术超管），
// 不平铺；高频在上、配置/治理在下。新增模块归入对应职能域。
export const NAV: NavSection[] = [
  {
    label: "运营与支持",
    items: [
      { id: "dashboard", label: "仪表盘", href: "/", icon: LayoutDashboard },
      { id: "users", label: "用户管理", href: "/users", icon: Users },
      { id: "content", label: "内容审核", href: "/content", icon: FileText },
      { id: "announcements", label: "系统公告", href: "/announcements", icon: Megaphone },
      { id: "feedback", label: "用户反馈", href: "/feedback", icon: MessageSquare },
    ],
  },
  {
    label: "内容 & 模型",
    items: [
      { id: "generations", label: "生成记录", href: "/generations", icon: Sparkles },
      { id: "models", label: "模型管理", href: "/models", icon: Database },
    ],
  },
  {
    label: "分析与治理",
    items: [
      { id: "cost", label: "成本分析", href: "/cost", icon: Coins },
      { id: "credits", label: "积分经济", href: "/credits", icon: Wallet },
      { id: "audit", label: "审计日志", href: "/audit", icon: ClipboardList },
      { id: "settings", label: "系统设置", href: "/settings", icon: Settings },
    ],
  },
];

export function activeIdFromPath(pathname: string): string {
  if (pathname === "/" || pathname === "") return "dashboard";
  const seg = pathname.split("/")[1];
  return seg || "dashboard";
}

export function crumbsFromPath(pathname: string): string[] {
  const id = activeIdFromPath(pathname);
  for (const sec of NAV) {
    const hit = sec.items.find((i) => i.id === id);
    if (hit) return ["InkWild", hit.label];
  }
  return ["InkWild"];
}
