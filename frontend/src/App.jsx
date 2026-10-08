import { useEffect, useRef, useState } from "react";
import jsPDF from "jspdf";
import { getHistory, isLoggedIn, login, logout, register, verifyAudio, verifyText } from "./api";

const VERDICT_COLORS = {
  Real: "var(--verdict-real)",
  "Likely Real": "var(--verdict-likely-real)",
  Unverified: "var(--verdict-unverified)",
  "Likely Fake": "var(--verdict-likely-fake)",
  Fake: "var(--verdict-fake)",
};

const AGENT_STEPS = [
  { key: "parse", label: "Parsing input" },
  { key: "search", label: "Searching sources" },
  { key: "scrape", label: "Scraping matched articles" },
  { key: "score", label: "Cross-checking & scoring trust" },
  { key: "summarize", label: "Generating AI summary" },
];

function verdictClass(verdict) {
  return `verdict-${(verdict || "unverified").toLowerCase().replace(/\s+/g, "-")}`;
}

// jsPDF's built-in standard fonts (Helvetica etc.) only support the Latin-1
// character set. Smart quotes, em/en dashes, ellipses, the ₹ sign and other
// characters LLM-generated text often contains aren't in that set — and
// crucially, the font's width table has no entry for them, so jsPDF
// *miscalculates* how wide a line is and lets it run off the page instead
// of wrapping it. Replace the common offenders with safe ASCII equivalents
// before anything is measured or drawn.
function sanitizePdfText(value) {
  if (value === null || value === undefined) return "";
  return String(value)
    .replace(/[\u2018\u2019\u201A\u2032]/g, "'")
    .replace(/[\u201C\u201D\u201E\u2033]/g, '"')
    .replace(/[\u2013\u2014]/g, "-")
    .replace(/\u2026/g, "...")
    .replace(/[\u2022\u25CF\u25AA]/g, "-")
    .replace(/\u20B9/g, "Rs. ")
    .replace(/\u00A0/g, " ")
    .replace(/[^\x00-\xFF]/g, "?"); // any other non-Latin-1 char: safe fallback so width calc never breaks
}

function AgentSteps({ active }) {
  const [stepIndex, setStepIndex] = useState(0);

  useEffect(() => {
    if (!active) {
      setStepIndex(0);
      return;
    }
    const interval = setInterval(() => {
      setStepIndex((i) => (i < AGENT_STEPS.length - 1 ? i + 1 : i));
    }, 1100);
    return () => clearInterval(interval);
  }, [active]);

  if (!active) return null;

  return (
    <div className="glass-card agent-steps-card">
      <div className="agent-steps-title">Agent pipeline</div>
      <ul className="agent-steps">
        {AGENT_STEPS.map((step, i) => {
          const status = i < stepIndex ? "done" : i === stepIndex ? "running" : "pending";
          return (
            <li key={step.key} className={`agent-step ${status}`}>
              <span className="agent-step-icon">
                {status === "done" && "✓"}
                {status === "running" && <span className="spinner-dot" />}
              </span>
              <span className="agent-step-label">{step.label}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function downloadReportPdf(query, result) {
  const doc = new jsPDF({ unit: "pt", format: "a4" });
  const pageWidth = doc.internal.pageSize.getWidth();
  const margin = 48;
  const maxWidth = pageWidth - margin * 2;
  let y = 56;

  const ensureSpace = (needed) => {
    if (y + needed > doc.internal.pageSize.getHeight() - margin) {
      doc.addPage();
      y = 56;
    }
  };

  doc.setFont("helvetica", "bold");
  doc.setFontSize(17);
  doc.text("Fake News Verifier - Report", margin, y);
  y += 20;

  doc.setFont("helvetica", "normal");
  doc.setFontSize(9.5);
  doc.setTextColor(120);
  doc.text(`Generated ${new Date().toLocaleString()}`, margin, y);
  doc.setTextColor(20);
  y += 26;

  doc.setFont("helvetica", "bold");
  doc.setFontSize(11);
  doc.text("Claim checked", margin, y);
  y += 15;
  doc.setFont("helvetica", "normal");
  doc.setFontSize(10.5);
  const claimLines = doc.splitTextToSize(sanitizePdfText(query) || "(no claim text)", maxWidth);
  ensureSpace(claimLines.length * 13);
  doc.text(claimLines, margin, y);
  y += claimLines.length * 13 + 16;

  doc.setFont("helvetica", "bold");
  doc.setFontSize(11);
  doc.text(`Verdict: ${sanitizePdfText(result.verdict)}`, margin, y);
  doc.text(`Trust score: ${result.trust_score}/100`, margin + 260, y);
  y += 22;

  doc.setFont("helvetica", "bold");
  doc.setFontSize(11);
  doc.text("AI summary", margin, y);
  y += 15;
  doc.setFont("helvetica", "normal");
  doc.setFontSize(10.5);
  const summaryLines = doc.splitTextToSize(
    sanitizePdfText(result.ai_summary) || "(no summary available)",
    maxWidth
  );
  ensureSpace(summaryLines.length * 13);
  doc.text(summaryLines, margin, y);
  y += summaryLines.length * 13 + 18;

  doc.setFont("helvetica", "bold");
  doc.setFontSize(11);
  ensureSpace(20);
  doc.text(`Sources (${result.scraped_sources_used} scraped)`, margin, y);
  y += 16;

  result.sources.forEach((s, i) => {
    const titleLines = doc.splitTextToSize(
      `${i + 1}. ${sanitizePdfText(s.title) || sanitizePdfText(s.url)}`,
      maxWidth
    );
    const urlLines = doc.splitTextToSize(sanitizePdfText(s.url), maxWidth);
    const excerptLines = s.excerpt
      ? doc.splitTextToSize(`"${sanitizePdfText(s.excerpt)}..."`, maxWidth)
      : [];
    const blockHeight = (titleLines.length + urlLines.length + excerptLines.length) * 12.5 + 10;
    ensureSpace(blockHeight);

    doc.setFont("helvetica", "bold");
    doc.setFontSize(10);
    doc.text(titleLines, margin, y);
    y += titleLines.length * 12.5;

    doc.setFont("helvetica", "normal");
    doc.setFontSize(9);
    doc.setTextColor(80, 110, 220);
    doc.text(urlLines, margin, y);
    doc.setTextColor(20);
    y += urlLines.length * 12.5;

    if (excerptLines.length) {
      doc.setFontSize(9.5);
      doc.setTextColor(100);
      doc.text(excerptLines, margin, y);
      doc.setTextColor(20);
      y += excerptLines.length * 12.5;
    }
    y += 8;
  });

  const slug = (query || "report").trim().slice(0, 40).replace(/[^a-z0-9]+/gi, "-").toLowerCase();
  doc.save(`fact-check-${slug || "report"}.pdf`);
}

function Sidebar({ loggedIn, username, history, onNewCheck, onLogout }) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">FN</div>
        <div className="brand-word">
          Verifier
          <span>Fake News Agent</span>
        </div>
      </div>

      <button className="new-check-btn" onClick={onNewCheck}>
        + New check
      </button>

      <div className="sidebar-label">History</div>
      <div className="history-scroll">
        {!loggedIn && (
          <div className="history-empty">
            Log in to save your check history across sessions.
          </div>
        )}
        {loggedIn && history.length === 0 && (
          <div className="history-empty">No checks yet — your first one will show up here.</div>
        )}
        {loggedIn &&
          history.map((h) => (
            <div className="history-item" key={h.id} title={h.query_text}>
              <span
                className="history-dot"
                style={{ background: VERDICT_COLORS[h.verdict] || "var(--text-faint)" }}
              />
              <span className="history-text">
                <strong style={{ color: VERDICT_COLORS[h.verdict] || "var(--text-faint)" }}>
                  {h.trust_score}
                </strong>{" "}
                {h.query_text}
              </span>
            </div>
          ))}
      </div>

      <div className="sidebar-footer">
        {loggedIn ? (
          <div className="sidebar-user">
            <span className="sidebar-user-name">{username}</span>
            <button className="logout-link" onClick={onLogout}>
              Log out
            </button>
          </div>
        ) : (
          <div className="sidebar-guest">Browsing as guest</div>
        )}
      </div>
    </aside>
  );
}

export default function App() {
  const [inputMode, setInputMode] = useState("text"); // "text" | "url" | "voice"
  const [query, setQuery] = useState("");
  const [urlInput, setUrlInput] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [loggedIn, setLoggedIn] = useState(isLoggedIn());
  const [currentUsername, setCurrentUsername] = useState(localStorage.getItem("username") || "");
  const [authMode, setAuthMode] = useState("login"); // "login" | "register"
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [history, setHistory] = useState([]);

  // Voice recording state
  const [isRecording, setIsRecording] = useState(false);
  const [recordedBlob, setRecordedBlob] = useState(null);
  const [recordSeconds, setRecordSeconds] = useState(0);
  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);
  const timerRef = useRef(null);

  useEffect(() => {
    if (loggedIn) getHistory().then(setHistory);
  }, [loggedIn]);

  async function startRecording() {
    setError("");
    setRecordedBlob(null);
    if (!navigator.mediaDevices || !window.MediaRecorder) {
      setError(
        "Microphone recording isn't available here — it needs HTTPS (or localhost) and a browser with MediaRecorder support."
      );
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = MediaRecorder.isTypeSupported("audio/webm")
        ? "audio/webm"
        : MediaRecorder.isTypeSupported("audio/mp4")
        ? "audio/mp4"
        : "";
      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: mimeType || "audio/webm" });
        setRecordedBlob(blob);
        stream.getTracks().forEach((t) => t.stop());
      };
      recorder.start();
      mediaRecorderRef.current = recorder;
      setIsRecording(true);
      setRecordSeconds(0);
      timerRef.current = setInterval(() => setRecordSeconds((s) => s + 1), 1000);
    } catch (err) {
      setError(
        "Couldn't access the microphone (permission denied or none found): " + err.message
      );
    }
  }

  function stopRecording() {
    mediaRecorderRef.current?.stop();
    setIsRecording(false);
    clearInterval(timerRef.current);
  }

  function resetAll() {
    setResult(null);
    setError("");
    setQuery("");
    setUrlInput("");
    setRecordedBlob(null);
    setIsRecording(false);
  }

  async function handleVerify(e) {
    e.preventDefault();
    setError("");
    setResult(null);

    if (inputMode === "voice") {
      if (!recordedBlob) {
        setError("Record something first.");
        return;
      }
      setLoading(true);
      try {
        const data = await verifyAudio(recordedBlob);
        setResult(data);
        if (loggedIn) getHistory().then(setHistory);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
      return;
    }

    const value = inputMode === "url" ? urlInput : query;
    if (!value.trim()) return;
    setLoading(true);
    try {
      const data = await verifyText(value);
      setResult(data);
      if (loggedIn) getHistory().then(setHistory);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleAuth(e) {
    e.preventDefault();
    setError("");
    try {
      if (authMode === "login") {
        await login(username, password);
      } else {
        await register(username, password);
        await login(username, password);
      }
      localStorage.setItem("username", username);
      setCurrentUsername(username);
      setLoggedIn(true);
      setUsername("");
      setPassword("");
    } catch (err) {
      setError(err.message);
    }
  }

  function handleLogout() {
    logout();
    localStorage.removeItem("username");
    setLoggedIn(false);
    setHistory([]);
  }

  return (
    <div className="app-shell">
      <Sidebar
        loggedIn={loggedIn}
        username={currentUsername}
        history={history}
        onNewCheck={resetAll}
        onLogout={handleLogout}
      />

      <div className="main-col">
        <div className="main-inner">
          <div className="hero">
            <h1>Check a claim before you share it</h1>
            <p>Paste text, a link, or record a clip — get a trust score backed by real sources.</p>
          </div>

          {!loggedIn && (
            <div className="glass-card auth-box">
              <div className="tabs">
                <button
                  className={authMode === "login" ? "active" : ""}
                  onClick={() => setAuthMode("login")}
                  type="button"
                >
                  Log in
                </button>
                <button
                  className={authMode === "register" ? "active" : ""}
                  onClick={() => setAuthMode("register")}
                  type="button"
                >
                  Register
                </button>
              </div>
              <form onSubmit={handleAuth}>
                <input
                  placeholder="Username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                />
                <input
                  placeholder="Password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
                <button type="submit">{authMode === "login" ? "Log in" : "Create account"}</button>
              </form>
              <p className="hint">Or skip this and verify a claim below as a guest.</p>
            </div>
          )}

          <form className="glass-card verify-box" onSubmit={handleVerify}>
            <div className="input-mode-tabs">
              <button
                type="button"
                className={inputMode === "text" ? "active" : ""}
                onClick={() => setInputMode("text")}
              >
                Text
              </button>
              <button
                type="button"
                className={inputMode === "url" ? "active" : ""}
                onClick={() => setInputMode("url")}
              >
                URL
              </button>
              <button
                type="button"
                className={inputMode === "voice" ? "active" : ""}
                onClick={() => setInputMode("voice")}
              >
                Voice
              </button>
            </div>

            {inputMode === "text" && (
              <textarea
                placeholder="Paste a claim or headline to fact-check..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                rows={4}
              />
            )}

            {inputMode === "url" && (
              <input
                type="url"
                placeholder="https://example.com/news-article"
                value={urlInput}
                onChange={(e) => setUrlInput(e.target.value)}
              />
            )}

            {inputMode === "voice" && (
              <div className="voice-box">
                {!isRecording && !recordedBlob && (
                  <button type="button" className="mic-btn" onClick={startRecording}>
                    Start recording
                  </button>
                )}
                {isRecording && (
                  <button type="button" className="mic-btn recording" onClick={stopRecording}>
                    Stop ({recordSeconds}s)
                  </button>
                )}
                {!isRecording && recordedBlob && (
                  <div className="recorded-preview">
                    <audio controls src={URL.createObjectURL(recordedBlob)} />
                    <button type="button" onClick={() => setRecordedBlob(null)}>
                      Re-record
                    </button>
                  </div>
                )}
              </div>
            )}

            <button type="submit" disabled={loading}>
              {loading ? "Running agents..." : "Verify"}
            </button>
          </form>

          {error && <div className="error">{error}</div>}

          <AgentSteps active={loading} />

          {result && (
            <div className="glass-card result-card">
              <div className="result-top">
                <span className={`verdict-badge ${verdictClass(result.verdict)}`}>
                  {result.verdict}
                </span>
                <span className="score-readout">
                  <span className="score-num">{result.trust_score}</span>
                  <span className="score-denom">/100</span>
                </span>
              </div>
              <p className="summary">{result.ai_summary}</p>
              <div className="sources">
                <div className="sources-head">
                  <h3>Sources ({result.scraped_sources_used} scraped)</h3>
                  <button
                    type="button"
                    className="download-btn"
                    onClick={() => downloadReportPdf(result.query, result)}
                  >
                    Download report (PDF)
                  </button>
                </div>
                <ul>
                  {result.sources.map((s, i) => (
                    <li className="source-item" key={i}>
                      <a href={s.url} target="_blank" rel="noreferrer">
                        {s.title || s.url}
                      </a>
                      {s.excerpt && <p className="excerpt">{s.excerpt}...</p>}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
