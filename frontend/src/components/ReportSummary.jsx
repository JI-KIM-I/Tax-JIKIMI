// 진단 요약 문장 안의 금액(원)·비율(%) 부분만 굵게 강조해서 눈에 잘 들어오게 합니다.
// (문장 단위 줄바꿈도 해봤는데, 그건 원하는 방향이 아니어서 한 문단으로 되돌렸습니다)
// 텍스트 자체(백엔드가 만든 문장)는 그대로 두고 화면에 표시할 때만 강조 처리를 합니다.
const FIGURE_RE = /([0-9][0-9,]*(?:\.[0-9]+)?\s?(?:원|%))/g;

export default function ReportSummary({ text }) {
  if (!text) return null;

  // 캡처 그룹이 있는 정규식으로 split하면 [일반텍스트, 매칭된 숫자, 일반텍스트, ...] 순서로 나뉩니다.
  // 홀수 인덱스가 항상 숫자(금액/비율) 부분입니다.
  const parts = text.split(FIGURE_RE);

  return (
    <p className="report-summary">
      {parts.map((part, i) =>
        i % 2 === 1 ? (
          <strong key={i} className="report-summary-figure">
            {part}
          </strong>
        ) : (
          part
        )
      )}
    </p>
  );
}
