/**
 * format_bytes.ts — Format a byte count as a human-readable string.
 *
 * Self-contained utility with zero internal imports and a JSDoc
 * docstring. Should be flagged as extractable by the TS path.
 */

export function formatBytes(bytes: number, decimals = 2): string {
  if (bytes === 0) return "0 B";
  if (!Number.isFinite(bytes)) return "NaN";
  if (bytes < 0) return "-" + formatBytes(-bytes, decimals);

  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB", "TB", "PB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  const value = bytes / Math.pow(k, i);
  return `${value.toFixed(decimals)} ${sizes[i]}`;
}

export function parseBytes(text: string): number | null {
  const match = text.trim().match(/^([\d.]+)\s*([a-z]+)$/i);
  if (!match) return null;
  const value = parseFloat(match[1]);
  if (!Number.isFinite(value)) return null;
  const unit = match[2].toLowerCase();
  const sizes: Record<string, number> = {
    b: 1, kb: 1024, mb: 1024 ** 2,
    gb: 1024 ** 3, tb: 1024 ** 4, pb: 1024 ** 5,
  };
  if (!(unit in sizes)) return null;
  return Math.floor(value * sizes[unit]);
}
