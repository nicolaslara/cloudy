import type { NormalsPeriod } from "./api/climatology";

// The backend emits a recurring slot as a bare integer string: month is "1".."12",
// day is day-of-year "1".."366", year is the calendar year. Rendering is the
// frontend's job — turn those raw slot indices into something a person reads.
const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

/** Human label for one climatology slot, e.g. month "7" → "Jul", day "200" → "Day 200". */
export function normalsPeriodLabel(period: string, grain: NormalsPeriod): string {
  if (grain === "month") {
    const index = Number(period) - 1; // slots are 1-based months
    return MONTHS[index] ?? period;
  }
  if (grain === "day") return `Day ${period}`;
  return period; // year is already a readable "YYYY"
}

/** Full month name from the 1-based month number the current-month callout carries. */
export function monthName(month: number): string {
  const FULL = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
  ];
  return FULL[month - 1] ?? `Month ${month}`;
}
