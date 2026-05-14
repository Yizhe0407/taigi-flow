/** Mean of nullable numbers, rounded to nearest integer. Returns null when no non-null values. */
export function avg(values: (number | null)[]): number | null {
  const nums = values.filter((v): v is number => v !== null);
  return nums.length > 0 ? Math.round(nums.reduce((s, v) => s + v, 0) / nums.length) : null;
}
