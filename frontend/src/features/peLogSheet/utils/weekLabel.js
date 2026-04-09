/**
 * weekLabel.js
 * 요청일(YYYY-MM-DD 또는 YYYY.MM.DD) → "N월 N주차" 계산
 */

/**
 * Returns the ISO week-of-month label for a given date string.
 * Week 1 = the week containing the 1st of the month.
 * @param {string} dateStr  e.g. "2024-03-15" or "2024.03.15"
 * @returns {string}  e.g. "3월 3주차"  or "" if unparseable
 */
export function calcWeekLabel(dateStr) {
  if (!dateStr) return '';

  const normalized = String(dateStr).replace(/\./g, '-').trim();
  const d = new Date(normalized);

  if (isNaN(d.getTime())) return '';

  const month = d.getMonth() + 1;

  // Find the Monday of the week containing d
  const dayOfWeek = d.getDay() === 0 ? 7 : d.getDay(); // 1=Mon … 7=Sun
  const monday = new Date(d);
  monday.setDate(d.getDate() - (dayOfWeek - 1));

  // Find the Monday of the first week that contains the 1st of the month
  const firstOfMonth = new Date(d.getFullYear(), d.getMonth(), 1);
  const firstDow = firstOfMonth.getDay() === 0 ? 7 : firstOfMonth.getDay();
  const firstMonday = new Date(firstOfMonth);
  firstMonday.setDate(firstOfMonth.getDate() - (firstDow - 1));

  const diffMs = monday.getTime() - firstMonday.getTime();
  const weekNumber = Math.floor(diffMs / (7 * 24 * 60 * 60 * 1000)) + 1;

  return `${month}월 ${weekNumber}주차`;
}
