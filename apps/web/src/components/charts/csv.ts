/** Tiny CSV helpers for "Export" buttons - the data is already in the browser. */

export type CsvCell = string | number | null | undefined;

function escapeCell(cell: CsvCell): string {
  if (cell === null || cell === undefined) return "";
  let text = String(cell);
  // Spreadsheet formula injection: a cell starting with = + - @ (or tab/CR) would be
  // evaluated by Excel/Sheets. Prefix with an apostrophe-equivalent. Plain negative
  // numbers are real numbers, not text, so they are left alone.
  if (typeof cell === "string" && /^[=+\-@\t\r]/.test(text) && Number.isNaN(Number(text))) text = `'${text}`;
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export function toCsv(rows: CsvCell[][]): string {
  return rows.map((row) => row.map(escapeCell).join(",")).join("\r\n");
}

export function downloadCsv(filename: string, rows: CsvCell[][]): void {
  // UTF-8 BOM so Excel opens non-ASCII text correctly.
  const blob = new Blob(["\ufeff", toCsv(rows)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
