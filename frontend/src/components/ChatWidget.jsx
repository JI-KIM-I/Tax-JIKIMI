import { useState, useRef, useEffect } from "react";
import { sendChatMessage } from "../api/client";
import ShieldIcon from "./ShieldIcon";

// 현재 진단 결과에서 챗봇 프롬프트에 넣을 핵심 수치만 골라 요약합니다.
// (전체 result를 그대로 보내면 너무 길어져서 응답 속도·비용 면에서 불리해요)
function summarizeResultForContext(result) {
  if (!result) return null;
  const { financial_income_tax, pension_compare, limit_usage, report_summary } = result;
  return {
    요약: report_summary,
    금융소득: financial_income_tax.financial_income,
    금융소득_예상추가세액: financial_income_tax.additional_total_tax,
    연금_일시금세금: pension_compare.lump_total_tax,
    연금_분할수령세금: pension_compare.split_total_tax,
    연금_분할수령절세액: pension_compare.saving_by_split,
    ISA_연간한도활용률: limit_usage.isa_annual_usage_rate,
    예상세액공제액: limit_usage.estimated_tax_credit,
  };
}

const SUGGESTED_QUESTIONS = [
  "ISA 비과세 한도가 얼마야?",
  "연금저축이랑 IRP 세액공제 한도가 어떻게 돼?",
  "연금을 나눠 받으면 왜 세금이 줄어들어?",
];

export default function ChatWidget({ result }) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      text: "안녕하세요! 세금·절세 관련 궁금한 점을 물어보세요. 국세청 자료를 근거로 답변해드려요.",
      sources: [],
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const scrollRef = useRef(null);

  useEffect(() => {
    if (open) {
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
    }
  }, [messages, loading, open]);

  const handleSend = async (text) => {
    const question = (text ?? input).trim();
    if (!question || loading) return;

    setMessages((prev) => [...prev, { role: "user", text: question }]);
    setInput("");
    setLoading(true);
    setError(null);

    try {
      const context = summarizeResultForContext(result);
      const data = await sendChatMessage(question, context);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: data.answer, sources: data.sources || [] },
      ]);
    } catch (err) {
      const detail = err.response?.data?.detail || err.message;
      setError(detail);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <>
      {open && (
        <div className="chat-widget-panel">
          <div className="chat-widget-header">
            <div className="chat-widget-title">
              <ShieldIcon size={18} />
              <span>세금지킴이 AI 챗봇</span>
            </div>
            <button
              type="button"
              className="chat-widget-close"
              onClick={() => setOpen(false)}
              aria-label="챗봇 닫기"
            >
              ✕
            </button>
          </div>

          <p className="chat-widget-subtitle">
            {result
              ? "지금 진단 결과를 참고해서 답변해드려요."
              : "진단을 먼저 실행하면 결과를 참고한 답변도 받을 수 있어요."}
          </p>

          <div className="chat-window chat-window--widget" ref={scrollRef}>
            {messages.map((m, i) => (
              <div key={i} className={`chat-bubble-row chat-bubble-row--${m.role}`}>
                {m.role === "assistant" && (
                  <div className="chat-avatar">
                    <ShieldIcon size={14} />
                  </div>
                )}
                <div className={`chat-bubble chat-bubble--${m.role}`}>
                  <p>{m.text}</p>
                  {m.sources && m.sources.length > 0 && (
                    <details className="chat-sources">
                      <summary>참고 자료 {m.sources.length}건</summary>
                      <ul>
                        {m.sources.map((s, j) => (
                          <li key={j}>
                            <strong>{s.source}</strong>: {s.text.slice(0, 60)}
                            {s.text.length > 60 ? "..." : ""}
                          </li>
                        ))}
                      </ul>
                    </details>
                  )}
                </div>
              </div>
            ))}

            {loading && (
              <div className="chat-bubble-row chat-bubble-row--assistant">
                <div className="chat-avatar">
                  <ShieldIcon size={14} />
                </div>
                <div className="chat-bubble chat-bubble--assistant chat-bubble--loading">
                  답변 생각하는 중...
                </div>
              </div>
            )}
          </div>

          {error && <div className="error-banner chat-error">{error}</div>}

          <div className="suggested-questions">
            {SUGGESTED_QUESTIONS.map((q) => (
              <button
                key={q}
                type="button"
                className="suggested-question-btn"
                onClick={() => handleSend(q)}
                disabled={loading}
              >
                {q}
              </button>
            ))}
          </div>

          <form
            className="chat-input-row"
            onSubmit={(e) => {
              e.preventDefault();
              handleSend();
            }}
          >
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="궁금한 점을 입력하세요 (Enter로 전송)"
              rows={2}
            />
            <button type="submit" className="btn-primary chat-send-btn" disabled={loading || !input.trim()}>
              전송
            </button>
          </form>
        </div>
      )}

      <button
        type="button"
        className="chat-fab"
        onClick={() => setOpen((v) => !v)}
        aria-label="AI 챗봇 열기"
      >
        {open ? "✕" : <ShieldIcon size={24} color="white" />}
      </button>
    </>
  );
}
