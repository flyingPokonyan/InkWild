import { cookies } from "next/headers";
import { getRequestConfig } from "next-intl/server";

const SUPPORTED = ["zh", "en"] as const;
type SupportedLocale = (typeof SUPPORTED)[number];
const DEFAULT_LOCALE: SupportedLocale = "zh";

export default getRequestConfig(async () => {
  const cookieStore = await cookies();
  const raw = cookieStore.get("NEXT_LOCALE")?.value;
  const locale: SupportedLocale = (SUPPORTED as readonly string[]).includes(raw ?? "")
    ? (raw as SupportedLocale)
    : DEFAULT_LOCALE;
  return {
    locale,
    messages: (await import(`./${locale}.json`)).default,
  };
});
