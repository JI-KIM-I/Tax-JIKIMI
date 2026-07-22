import { useState } from "react";
import { exportReport } from "../api/client";

// 예전엔 "종합 추천 & 시나리오" 탭 맨 아래에만 있어서, 그 탭까지 가지 않으면
// 다운로드 기능이 있는지조차 몰랐어요. 진단 결과가 나오자마자 보이는 SummaryCards 옆에 두어
// 어떤 탭을 보고 있든 항상 접근할 수 있게 했습니다.
export default function ReportDownload({ requestPayload }) {
  const [downloading, setDownloading] = useState(false);

  const handleDownload = async (format) => {
    setDownloading(true);
    try {
      const blob = await exportReport({ ...requestPayload, format });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = format === "pdf" ? "세금지킴이_report.pdf" : "세금지킴이_report.txt";
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      alert("리포트 다운로드에 실패했습니다: " + err.message);
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="report-download">
      <button type="button" className="btn-secondary" onClick={() => handleDownload("text")} disabled={downloading}>
        📄 텍스트 리포트 다운로드 (.txt)
      </button>
      <button type="button" className="btn-secondary" onClick={() => handleDownload("pdf")} disabled={downloading}>
        📑 PDF 리포트 다운로드 (.pdf)
      </button>
    </div>
  );
}
