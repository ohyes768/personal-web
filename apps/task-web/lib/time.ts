/** 供表格扫视用的短时间：今天只显示 HH:MM:SS，往年/往日显示 MM-DD HH:MM */
export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  const hms = `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  if (d.toDateString() === now.toDateString()) return hms;
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${hms.slice(0, 5)}`;
}
