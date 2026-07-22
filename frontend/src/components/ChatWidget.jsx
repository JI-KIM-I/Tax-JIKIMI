import { useState, useRef, useEffect, useMemo } from "react";
import { sendChatMessage } from "../api/client";
import ShieldIcon from "./ShieldIcon";
import { won, pct } from "../utils/format";
import { friendlyDiagnosisError } from "../utils/errors";
import { initialForm as diagnosisDefaults } from "./DiagnosisForm";
import {
  extractProfileFromText,
  hasEnoughForDiagnosis,
  describeProfile,
} from "../utils/chatEntityExtract";

// DiagnosisForm의 기본값(퍼센트 단위 등)을 실제 진단 API가 기대하는 payload 모양으로 변환합니다.
function toDefaultDiagnosisPayload() {
  const { annual_yield_rate_pct, ...rest } = diagnosisDefaults;
  return { ...rest, annual_yield_rate: annual_yield_rate_pct / 100 };
}

const STORAGE_KEY = "taxjikimi_chat_history_v1";
const INTRO_BUBBLE_KEY = "taxjikimi_chat_intro_seen_v1";

// "⤢"/"⤡" 같은 유니코드 화살표는 서로 방향이 잘 구분되지 않고, 확장/축소 어느 쪽이 어느 아이콘인지
// 헷갈린다는 피드백이 있어서 SVG로 직접 그렸습니다. 화살표가 네 모서리 바깥으로 뻗으면 "확장",
// 안쪽으로 모이면 "축소"라는 의미가 아이콘만 봐도 분명합니다.
function FullscreenIcon({ active }) {
  return active ? (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M5 16h3v3h2v-5H5v2zm3-8H5v2h5V5H8v3zm6 11h2v-3h3v-2h-5v5zm2-11V5h-2v5h5V8h-3z" />
    </svg>
  ) : (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M7 14H5v5h5v-2H7v-3zm-2-4h2V7h3V5H5v5zm12 7h-3v2h5v-5h-2v3zM14 5v2h3v3h2V5h-5z" />
    </svg>
  );
}

const GREETING = {
  role: "assistant",
  text: "안녕하세요! 세금·절세 관련 궁금한 점을 물어보세요. 국세청 자료를 근거로 답변해드려요.",
  sources: [],
};

// 현재 진단 결과에서 챗봇 프롬프트에 넣을 핵심 수치만 골라 요약합니다.
// (전체 result를 그대로 보내면 너무 길어져서 응답 속도·비용 면에서 불리해요)
function summarizeResultForContext(result) {
  if (!result) return null;
  const { financial_income_tax, pension_compare, limit_usage, report_summary, pension_start_recommendation } = result;
  const summary = {
    요약: report_summary,
    금융소득: financial_income_tax.financial_income,
    금융소득_예상추가세액: financial_income_tax.additional_total_tax,
    연금_일시금세금: pension_compare.lump_total_tax,
    연금_분할수령세금: pension_compare.split_total_tax,
    연금_분할수령절세액: pension_compare.saving_by_split,
    ISA_연간한도활용률: limit_usage.isa_annual_usage_rate,
    예상세액공제액: limit_usage.estimated_tax_credit,
  };

  // 연금 시작 시점 추천은 더 이상 별도 탭으로 보여주지 않고, 챗봇 컨텍스트로만 전달합니다.
  // 세율만 비교한 단순 계산이라 생활비·건강·투자수익률은 반영 안 됐다는 걸 답변에 꼭 함께 안내해야 해서,
  // 그 주의사항을 데이터 자체에 명시해 LLM이 참고하게 합니다.
  if (pension_start_recommendation) {
    summary.연금_시작나이_참고값 = {
      단순세율기준_추천나이: pension_start_recommendation.recommended_start_age,
      해당나이_예상분할수령세금: pension_start_recommendation.expected_split_total_tax,
      주의: "세율만 비교한 단순 계산이라 생활비, 건강, 투자수익률 등은 반영하지 않음. 답변할 때 이 한계를 함께 설명할 것.",
    };
  }

  return summary;
}

// 채팅창 상단에 접어둘 수 있는 "참고 수치 카드"용 데이터.
// 새로 계산하지 않고, 이미 백엔드가 계산해준 결과값만 보여줍니다 (숫자를 임의로 추정/가공하지 않음).
function buildReferenceFacts(result) {
  if (!result) return [];
  const { financial_income_tax, pension_compare, limit_usage } = result;
  const facts = [
    ["금융소득", won(financial_income_tax?.financial_income)],
    ["금융소득 예상 추가세액", won(financial_income_tax?.additional_total_tax)],
    ["연금 일시금 세금", won(pension_compare?.lump_total_tax)],
    ["연금 분할수령 세금", won(pension_compare?.split_total_tax)],
    ["분할수령 절세액", won(pension_compare?.saving_by_split)],
    ["ISA 연간한도 활용률", pct(limit_usage?.isa_annual_usage_rate)],
  ];
  return facts
    .filter(([, value]) => value && value !== "-" && value !== "-원")
    .map(([label, value]) => ({ label, value }));
}

const DEFAULT_QUESTIONS = [
  "ISA 비과세 한도가 얼마야?",
  "연금저축이랑 IRP 세액공제 한도가 어떻게 돼?",
  "연금을 나눠 받으면 왜 세금이 줄어들어?",
];

// 진단 결과가 있으면, 실제로 계산된 숫자를 활용해 훨씬 구체적인 추천 질문을 만듭니다.
function buildSuggestedQuestions(result) {
  if (!result) return DEFAULT_QUESTIONS;
  const questions = [];
  const saving = result.pension_compare?.saving_by_split;
  if (saving) questions.push(`연금을 나눠 받으면 왜 ${won(saving)} 절세되나요?`);

  const addTax = result.financial_income_tax?.additional_total_tax;
  if (addTax) questions.push(`제 금융소득 기준 예상 추가세액 ${won(addTax)}은 어떻게 계산된 거예요?`);

  const isaRate = result.limit_usage?.isa_annual_usage_rate;
  if (isaRate !== undefined && isaRate !== null) {
    questions.push("ISA 한도를 올해 더 채우면 어떤 효과가 있을까요?");
  }

  if (result.pension_start_recommendation) {
    questions.push("연금은 몇 살부터 받는 게 좋을까요? 세금 말고 다른 것도 같이 알려주세요");
  }

  questions.push("지금 제 상황에서 가장 먼저 확인해야 할 건 뭔가요?");
  return questions; // 슬라이싱은 이미 물어본 질문을 걸러낸 뒤 호출 쪽에서 처리합니다.
}

function loadStoredMessages() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (!saved) return [GREETING];
    const parsed = JSON.parse(saved);
    return Array.isArray(parsed) && parsed.length ? parsed : [GREETING];
  } catch {
    return [GREETING];
  }
}

// 출처를 접어둔 <details> 대신, 칩을 눌러 필요한 자료만 펼쳐볼 수 있게 합니다.
function SourceList({ sources }) {
  const [expanded, setExpanded] = useState(null);
  if (!sources || sources.length === 0) return null;

  // 같은 문서(title)에서 문단 여러 개가 뽑히면 라벨이 그대로 겹쳐 보이므로,
  // 겹치는 라벨에는 "1/3" 식으로 순번을 붙여 구분합니다.
  const totalByLabel = {};
  sources.forEach((s, i) => {
    const label = s.title || s.source || `참고자료 ${i + 1}`;
    totalByLabel[label] = (totalByLabel[label] || 0) + 1;
  });
  const seenByLabel = {};

  return (
    <div className="chat-source-list">
      {/* 칩만 덜렁 있으면 뭔지 안 와닿아서, 이게 뭔지 짧게 라벨을 붙였습니다 */}
      <span className="chat-source-list-label">참고한 자료</span>
      <div className="chat-source-chips">
        {sources.map((s, i) => {
          const label = s.title || s.source || `참고자료 ${i + 1}`;
          seenByLabel[label] = (seenByLabel[label] || 0) + 1;
          const displayLabel =
            totalByLabel[label] > 1 ? `${label} ${seenByLabel[label]}/${totalByLabel[label]}` : label;
          return (
            <button
              key={i}
              type="button"
              className={`chat-source-chip${expanded === i ? " chat-source-chip--active" : ""}`}
              onClick={() => setExpanded((prev) => (prev === i ? null : i))}
            >
              {displayLabel}
            </button>
          );
        })}
      </div>
      {expanded !== null && sources[expanded] && (
        <div className="chat-source-detail">
          <strong>{sources[expanded].title || sources[expanded].source}</strong>
          <p>{sources[expanded].text}</p>
        </div>
      )}
    </div>
  );
}

function ReferenceFactsCard({ facts }) {
  const [collapsed, setCollapsed] = useState(false);
  if (!facts || facts.length === 0) return null;

  return (
    <div className="chat-reference-card">
      <button type="button" className="chat-reference-toggle" onClick={() => setCollapsed((v) => !v)}>
        <span>🧾 현재 진단 결과</span>
        <span className="chat-reference-toggle-caret">{collapsed ? "▾" : "▴"}</span>
      </button>
      {!collapsed && (
        <ul>
          {facts.map((f) => (
            <li key={f.label}>
              <span>{f.label}</span>
              <strong>{f.value}</strong>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function ChatWidget({ result, requestPayload, onRunDiagnosis, onOpenDiagnosisForm }) {
  const [open, setOpen] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [messages, setMessages] = useState(loadStoredMessages);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [showNudge, setShowNudge] = useState(false);
  const [pendingProfile, setPendingProfile] = useState(null);
  const [pendingQuestion, setPendingQuestion] = useState(null);
  const [justAddedIndex, setJustAddedIndex] = useState(null);
  const [showIntroBubble, setShowIntroBubble] = useState(false);
  const scrollRef = useRef(null);
  const inputRef = useRef(null);
  const composingRef = useRef(false);
  const enterTimerRef = useRef(null);
  const introTimerRef = useRef(null);

  const referenceFacts = useMemo(() => buildReferenceFacts(result), [result]);

  // 이미 물어본 질문(직접 타이핑했든 추천 버튼을 눌렀든)은 추천 목록에서 빼줍니다.
  const askedQuestions = useMemo(
    () => new Set(messages.filter((m) => m.role === "user").map((m) => m.text)),
    [messages]
  );
  const suggestedQuestions = useMemo(() => {
    const candidates = buildSuggestedQuestions(result);
    return candidates.filter((q) => !askedQuestions.has(q)).slice(0, 3);
  }, [result, askedQuestions]);

  useEffect(() => {
    if (result) setShowNudge(false);
  }, [result]);

  useEffect(() => {
    if (open) {
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
    }
  }, [messages, loading, open, pendingProfile]);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(messages));
    } catch {
      // 저장 실패(예: 프라이빗 모드)는 무시하고 대화만 이어갑니다.
    }
  }, [messages]);

  // 처음 방문한 사람에게 챗봇 존재를 알려주는 말풍선을 한 번만 띄웁니다.
  useEffect(() => {
    try {
      if (!localStorage.getItem(INTRO_BUBBLE_KEY)) {
        setShowIntroBubble(true);
      }
    } catch {
      // 저장소 접근이 안 되면 그냥 안 띄웁니다.
    }
  }, []);

  const dismissIntroBubble = () => {
    setShowIntroBubble(false);
    clearTimeout(introTimerRef.current);
    try {
      localStorage.setItem(INTRO_BUBBLE_KEY, "1");
    } catch {
      // 무시
    }
  };

  useEffect(() => {
    if (!showIntroBubble) return undefined;
    introTimerRef.current = setTimeout(dismissIntroBubble, 6000);
    return () => clearTimeout(introTimerRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showIntroBubble]);

  useEffect(() => () => clearTimeout(enterTimerRef.current), []);

  // 답변이 한 글자씩 타이핑되는 연출은 오히려 산만하다는 피드백이 있어서,
  // 로딩이 끝나면 완성된 답변이 한 번에 스르륵(fade-in) 나타나는 방식으로 바꿨습니다.
  const proceedWithChat = async (question, overrideResult) => {
    setLoading(true);
    setError(null);
    try {
      const context = summarizeResultForContext(overrideResult !== undefined ? overrideResult : result);
      const data = await sendChatMessage(question, context);
      setMessages((prev) => {
        const next = [...prev, { role: "assistant", text: data.answer, sources: data.sources || [] }];
        setJustAddedIndex(next.length - 1);
        clearTimeout(enterTimerRef.current);
        enterTimerRef.current = setTimeout(() => setJustAddedIndex(null), 400);
        return next;
      });
    } catch (err) {
      const detail = err.response?.data?.detail || err.message;
      setError(detail);
    } finally {
      setLoading(false);
    }
  };

  const handleSend = async (text) => {
    const question = (text ?? inputRef.current?.value ?? input).trim();
    if (!question || loading) return;

    // 이전에 확인 대기 중이던 추출 결과가 있으면, 새 질문을 우선하고 취소합니다.
    if (pendingProfile) {
      setPendingProfile(null);
      setPendingQuestion(null);
    }

    setMessages((prev) => [...prev, { role: "user", text: question }]);
    setInput("");
    setError(null);

    // 아직 진단 결과가 없을 때만, 지호님이 만든 규칙 기반 추출기로 나이·금액 등을 뽑아봅니다.
    // (100% 정확하지 않기 때문에 절대 바로 계산에 쓰지 않고, 항상 사용자 확인을 먼저 거칩니다)
    if (!result && onRunDiagnosis) {
      const profile = extractProfileFromText(question);
      if (hasEnoughForDiagnosis(profile)) {
        setPendingProfile(profile);
        setPendingQuestion(question);
        return;
      }
      if (profile && Object.keys(profile).length > 0) {
        setShowNudge(true);
      }
    }

    await proceedWithChat(question);
  };

  const handleConfirmProfile = async () => {
    const profile = pendingProfile;
    const question = pendingQuestion;
    setPendingProfile(null);
    setPendingQuestion(null);
    setLoading(true);
    setError(null);
    try {
      const basePayload = requestPayload || toDefaultDiagnosisPayload();
      const mergedPayload = { ...basePayload, ...profile };
      const diagnosisData = await onRunDiagnosis(mergedPayload);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: "말씀해주신 내용으로 간단 진단을 완료했어요. 왼쪽 화면에서 자세한 탭도 확인할 수 있어요. 이어서 질문에 답변드릴게요.",
          sources: [],
        },
      ]);
      await proceedWithChat(question, diagnosisData);
    } catch (err) {
      // 백엔드 원본 에러(영어 필드명 등)를 그대로 보여주지 않고 자연스러운 안내로 바꿉니다.
      const rawDetail = err.response?.data?.detail;
      const detail = rawDetail ? friendlyDiagnosisError(rawDetail) : "진단 계산 중 문제가 발생했어요.";
      setError(detail);
      setLoading(false);
    }
  };

  const handleDeclineProfile = () => {
    const question = pendingQuestion;
    setPendingProfile(null);
    setPendingQuestion(null);
    proceedWithChat(question);
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      // Korean/Japanese IME composition also uses Enter to confirm the current syllable.
      // Sending before composition ends can re-apply the final character after setInput("").
      if (composingRef.current || e.nativeEvent.isComposing || e.keyCode === 229) return;
      e.preventDefault();
      handleSend(e.currentTarget.value);
    }
  };

  const handleReset = () => {
    clearTimeout(enterTimerRef.current);
    setJustAddedIndex(null);
    setShowNudge(false);
    setPendingProfile(null);
    setPendingQuestion(null);
    setMessages([GREETING]);
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      // 무시
    }
  };

  const handleClose = () => {
    setOpen(false);
    setFullscreen(false);
  };

  return (
    <>
      {open && (
        <div className={`chat-widget-panel${fullscreen ? " chat-widget-panel--fullscreen" : ""}`}>
          <div className="chat-widget-header">
            <div className="chat-widget-title">
              <ShieldIcon size={18} />
              <span>세금지킴이 AI 챗봇</span>
            </div>
            <div className="chat-widget-header-actions">
              <button
                type="button"
                className="chat-widget-icon-btn"
                onClick={handleReset}
                title="대화 초기화"
                aria-label="대화 초기화"
              >
                ⟲
              </button>
              <button
                type="button"
                className="chat-widget-icon-btn"
                onClick={() => setFullscreen((v) => !v)}
                title={fullscreen ? "작게 보기" : "전체화면으로 보기"}
                aria-label="전체화면 전환"
              >
                <FullscreenIcon active={fullscreen} />
              </button>
              {/* 평소엔 우측 하단 FAB가 닫기 역할을 하지만, 전체화면일 땐 그 FAB 자체를 숨겨서
                  닫을 방법이 없어졌었습니다. 전체화면일 때만 닫기 버튼을 여기 둡니다. */}
              {fullscreen && (
                <button
                  type="button"
                  className="chat-widget-icon-btn"
                  onClick={handleClose}
                  title="닫기"
                  aria-label="챗봇 닫기"
                >
                  ✕
                </button>
              )}
            </div>
          </div>

          <p className="chat-widget-subtitle">
            {result
              ? "진단 결과를 참고해서 답변해드려요."
              : "진단을 먼저 실행하면 결과를 참고한 답변도 받을 수 있어요."}
          </p>

          <ReferenceFactsCard facts={referenceFacts} />

          <div className="chat-window chat-window--widget" ref={scrollRef}>
            {messages.map((m, i) => (
              <div key={i} className={`chat-bubble-row chat-bubble-row--${m.role}`}>
                {m.role === "assistant" && (
                  <div className="chat-avatar">
                    <ShieldIcon size={14} />
                  </div>
                )}
                <div
                  className={`chat-bubble chat-bubble--${m.role}${
                    i === justAddedIndex ? " chat-bubble--enter" : ""
                  }`}
                >
                  <p>{m.text}</p>
                  <SourceList sources={m.sources} />
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

          {pendingProfile && (
            <div className="chat-confirm-profile">
              <p className="chat-confirm-profile__title">말씀하신 내용을 이렇게 이해했어요</p>
              <ul>
                {describeProfile(pendingProfile).map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
              <p className="chat-confirm-profile__note">
                나머지 값은 일반적인 값으로 채워 간단 진단할게요. 정확도를 높이려면 왼쪽 진단 폼을 직접 채워주세요.
              </p>
              <div className="chat-confirm-profile__actions">
                <button
                  type="button"
                  className="chat-confirm-btn chat-confirm-btn--primary"
                  onClick={handleConfirmProfile}
                  disabled={loading}
                >
                  이 내용으로 진단하기
                </button>
                <button
                  type="button"
                  className="chat-confirm-btn"
                  onClick={handleDeclineProfile}
                  disabled={loading}
                >
                  그냥 질문만 답해줘
                </button>
              </div>
            </div>
          )}

          {showNudge && !result && !pendingProfile && (
            <div className="chat-nudge">
              <p>더 정확한 숫자로 답변받으시려면 왼쪽 진단 폼에 정보를 입력해보세요.</p>
              <button
                type="button"
                className="chat-nudge-btn"
                onClick={() => {
                  onOpenDiagnosisForm?.();
                  setShowNudge(false);
                }}
              >
                진단 폼으로 이동
              </button>
            </div>
          )}

          {!pendingProfile && suggestedQuestions.length > 0 && (
            <div className="suggested-questions">
              {suggestedQuestions.map((q) => (
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
          )}

          <form
            className="chat-input-row"
            onSubmit={(e) => {
              e.preventDefault();
              handleSend();
            }}
          >
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onCompositionStart={() => {
                composingRef.current = true;
              }}
              onCompositionEnd={(e) => {
                composingRef.current = false;
                setInput(e.currentTarget.value);
              }}
              onKeyDown={handleKeyDown}
              placeholder="궁금한 점을 입력해주세요."
              rows={2}
            />
            <button type="submit" className="btn-primary chat-send-btn" disabled={loading || !input.trim()}>
              전송
            </button>
          </form>
          <p className="chat-input-hint">Enter로 전송 · Shift+Enter로 줄바꿈</p>
        </div>
      )}

      {!open && showIntroBubble && (
        <div
          className="chat-intro-bubble"
          role="button"
          tabIndex={0}
          onClick={() => {
            setOpen(true);
            dismissIntroBubble();
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              setOpen(true);
              dismissIntroBubble();
            }
          }}
        >
          <button
            type="button"
            className="chat-intro-bubble__close"
            onClick={(e) => {
              e.stopPropagation();
              dismissIntroBubble();
            }}
            aria-label="말풍선 닫기"
          >
            ✕
          </button>
          <p>궁금한 거 물어보세요!</p>
        </div>
      )}

      {!(open && fullscreen) && (
        <button
          type="button"
          className={`chat-fab${open ? "" : " chat-fab--labeled"}`}
          onClick={() => {
            if (open) {
              handleClose();
            } else {
              setOpen(true);
              dismissIntroBubble();
            }
          }}
          aria-label="AI 챗봇 열기"
        >
          {open ? (
            "✕"
          ) : (
            <>
              <ShieldIcon size={20} color="white" />
              {/* 처음 뜨는 말풍선이 사라진 뒤에도 챗봇이 있다는 걸 계속 알 수 있도록,
                  아이콘만 있던 버튼에 상시 라벨을 붙였습니다 */}
              <span className="chat-fab-label">AI 챗봇</span>
            </>
          )}
        </button>
      )}
    </>
  );
}
