export function won(value) {
  if (value === null || value === undefined) return "-";
  return `${Math.round(value).toLocaleString("ko-KR")}원`;
}

export function pct(ratio) {
  if (ratio === null || ratio === undefined) return "-";
  return `${(ratio * 100).toFixed(1)}%`;
}
