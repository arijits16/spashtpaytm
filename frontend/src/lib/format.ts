/**
 * Display formatting for the dashboard.
 *
 * In its own module rather than beside the components: React Fast Refresh only
 * works when a file exports components alone, and a helper object living in
 * `ui.tsx` broke it for every file that imported one.
 *
 * These mirror the backend's own output (`journey/templates.format_rupees`), so
 * a figure reads identically on the phone, on the receipt and here.
 */

export const fmt = {
  /** Indian digit grouping: `55200` -> `55,200`. */
  rupees(value: number | null | undefined): string {
    if (value === null || value === undefined) return "—";
    return value.toLocaleString("en-IN");
  },
  percent(value: number | null | undefined, digits = 1): string {
    if (value === null || value === undefined) return "—";
    return `${value.toFixed(digits)}%`;
  },
  duration(seconds: number | null | undefined): string {
    if (seconds === null || seconds === undefined) return "—";
    if (seconds < 60) return `${Math.round(seconds)}s`;
    const minutes = Math.floor(seconds / 60);
    return `${minutes}m ${Math.round(seconds % 60)}s`;
  },
  /** Stored UTC, shown IST (section 6). */
  time(iso: string): string {
    return new Date(iso).toLocaleTimeString("en-IN", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      timeZone: "Asia/Kolkata",
    });
  },
  dateTime(iso: string): string {
    return new Date(iso).toLocaleString("en-IN", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
      timeZone: "Asia/Kolkata",
    });
  },
  hash(value: string, length = 12): string {
    return value.length <= length ? value : `${value.slice(0, length)}…`;
  },
  language(code: string): string {
    return { "mr-IN": "मराठी", "hi-IN": "हिंदी", "en-IN": "English" }[code] ?? code;
  },
};
