import React, { FormEvent, useEffect, useRef, useState } from "react";
import { DayPicker } from "react-day-picker";
import "react-day-picker/dist/style.css";
import { login, registerLocal, requestHustOtp, verifyHustOtp } from "../api";

type Mode = "login" | "register";
type RegisterKind = "hust" | "local";
type ToastKind = "success" | "error";

interface Props {
  onLogin: () => void;
  initialMode?: Mode;
  onBack?: () => void;
}

const HUST_DOMAIN = "@sis.hust.edu.vn";
const HUST_EMAIL_RE = /^[A-Za-z0-9._%+-]+@sis\.hust\.edu\.vn$/i;
const USERNAME_RE = /^[A-Za-z0-9._-]{3,50}$/;

const COMMON_PASSWORDS = new Set([
  "123456", "password", "12345678", "qwerty", "abc123", "111111", "123123",
  "admin", "letmein", "welcome", "password1", "iloveyou", "000000", "matkhau",
  "123456789", "1234567890", "12345", "1q2w3e4r", "p@ssw0rd",
]);

// ─── Icons (inline SVG) ──────────────────────────────────────────────────
const IconEye = ({ off }: { off?: boolean }) => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    {off ? (
      <>
        <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
        <line x1="1" y1="1" x2="23" y2="23" />
      </>
    ) : (
      <>
        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8S1 12 1 12z" />
        <circle cx="12" cy="12" r="3" />
      </>
    )}
  </svg>
);
const IconCheck = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <polyline points="20 6 9 17 4 12" />
  </svg>
);
const IconAlert = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <circle cx="12" cy="12" r="10" />
    <line x1="12" y1="8" x2="12" y2="12" />
    <line x1="12" y1="16" x2="12.01" y2="16" />
  </svg>
);
const IconCalendar = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <rect x="3" y="4" width="18" height="18" rx="3" />
    <line x1="16" y1="2" x2="16" y2="6" />
    <line x1="8" y1="2" x2="8" y2="6" />
    <line x1="3" y1="10" x2="21" y2="10" />
  </svg>
);

export default function Login({ onLogin, initialMode = "login", onBack }: Props) {
  const [mode, setMode] = useState<Mode>(initialMode);
  const [registerKind, setRegisterKind] = useState<RegisterKind>("hust");

  // Form fields
  const [identifier, setIdentifier] = useState("");
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [fullName, setFullName] = useState("");
  const [birthDate, setBirthDate] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");

  // OTP đăng ký tài khoản trường (2 bước)
  const RESEND_COOLDOWN = 30; // giây tối thiểu giữa 2 lần gửi mã
  const [otpStep, setOtpStep] = useState<"request" | "verify">("request");
  const [code, setCode] = useState("");
  const [otpExpiresAt, setOtpExpiresAt] = useState<number | null>(null); // ms
  const [resendAt, setResendAt] = useState<number | null>(null);         // ms cho phép gửi lại
  const [nowTs, setNowTs] = useState(Date.now());

  // UX state
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [showPw, setShowPw] = useState(false);
  const [showConfirmPw, setShowConfirmPw] = useState(false);
  const [capsLock, setCapsLock] = useState(false);
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState<{ kind: ToastKind; msg: string } | null>(null);

  // Popup lịch
  const [showCalendar, setShowCalendar] = useState(false);

  // Auto focus đúng input khi switch tab/kind
  const firstFieldRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    firstFieldRef.current?.focus();
  }, [mode, registerKind]);

  // Toast auto-dismiss
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 3500);
    return () => clearTimeout(t);
  }, [toast]);

  // Tick mỗi giây khi đang ở bước nhập mã (để đếm ngược hạn + cooldown gửi lại)
  const inOtpVerify = mode === "register" && registerKind === "hust" && otpStep === "verify";
  useEffect(() => {
    if (!inOtpVerify) return;
    setNowTs(Date.now());
    const id = setInterval(() => setNowTs(Date.now()), 1000);
    return () => clearInterval(id);
  }, [inOtpVerify]);

  const secondsLeft = otpExpiresAt ? Math.max(0, Math.ceil((otpExpiresAt - nowTs) / 1000)) : 0;
  const resendCooldown = resendAt ? Math.max(0, Math.ceil((resendAt - nowTs) / 1000)) : 0;
  const fmtMMSS = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

  const startOtpTimers = (expiresIn: number) => {
    const now = Date.now();
    setOtpExpiresAt(now + expiresIn * 1000);
    setResendAt(now + RESEND_COOLDOWN * 1000);
    setNowTs(now);
  };

  // Khi popup lịch mở: chặn scroll body + Esc đóng
  useEffect(() => {
    if (!showCalendar) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setShowCalendar(false);
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prev;
      document.removeEventListener("keydown", onKey);
    };
  }, [showCalendar]);

  // ─── Validation realtime ─────────────────────────────────────────────────
  const v = {
    identifier: identifier.trim().length > 0,
    email: HUST_EMAIL_RE.test(email.trim()),
    username: USERNAME_RE.test(username.trim()),
    password: password.length >= 6 && !COMMON_PASSWORDS.has(password.toLowerCase()),
    confirm: confirm.length > 0 && confirm === password,
    birthDate: birthDate.trim() === "" || !!parseBirthDate(birthDate),
    code: /^\d{6}$/.test(code.trim()),
  };

  // ─── Password strength ───────────────────────────────────────────────────
  const passwordStrength = (pw: string) => {
    let score = 0;
    if (pw.length >= 8) score++;
    if (pw.length >= 12) score++;
    if (/[A-Z]/.test(pw) && /[a-z]/.test(pw)) score++;
    if (/\d/.test(pw) && /[^A-Za-z0-9]/.test(pw)) score++;
    const labels = ["Rất yếu", "Yếu", "Trung bình", "Mạnh", "Rất mạnh"] as const;
    const colors = ["#ef4444", "#f97316", "#eab308", "#22c55e", "#16a34a"];
    return { score, label: labels[score], color: colors[score] };
  };

  function parseBirthDate(s: string): string | null {
    const m = s.trim().match(/^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})$/);
    if (!m) return null;
    const d = +m[1], mo = +m[2], y = +m[3];
    if (mo < 1 || mo > 12 || d < 1 || d > 31) return null;
    const dt = new Date(y, mo - 1, d);
    if (dt.getFullYear() !== y || dt.getMonth() !== mo - 1 || dt.getDate() !== d) return null;
    return `${y}-${String(mo).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
  }

  // Ngày đang chọn — parse từ ô text để DayPicker highlight
  const selectedDate: Date | undefined = (() => {
    const iso = parseBirthDate(birthDate);
    if (!iso) return undefined;
    const [y, m, d] = iso.split("-").map(Number);
    return new Date(y, m - 1, d);
  })();

  const handleDaySelect = (d: Date | undefined) => {
    if (!d) return;
    const dd = String(d.getDate()).padStart(2, "0");
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    setBirthDate(`${dd}/${mm}/${d.getFullYear()}`);
    setTouched((t) => ({ ...t, birthDate: true }));
    setShowCalendar(false);
  };

  // ─── Switchers ───────────────────────────────────────────────────────────
  const resetOtp = () => {
    setOtpStep("request");
    setCode("");
    setOtpExpiresAt(null);
    setResendAt(null);
  };
  const switchMode = (m: Mode) => {
    setMode(m);
    setPassword("");
    setConfirm("");
    setTouched({});
    setToast(null);
    resetOtp();
  };
  const switchKind = (k: RegisterKind) => {
    setRegisterKind(k);
    setTouched({});
    setToast(null);
    resetOtp();
  };

  const touch = (name: string) => setTouched((t) => ({ ...t, [name]: true }));

  // Caps lock detect
  const handleCapsCheck = (e: React.KeyboardEvent<HTMLInputElement>) => {
    setCapsLock(e.getModifierState && e.getModifierState("CapsLock"));
  };

  // ─── Submit ──────────────────────────────────────────────────────────────
  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setToast(null);

    if (mode === "login") {
      if (!v.identifier) {
        setToast({ kind: "error", msg: "Vui lòng nhập tài khoản." });
        touch("identifier");
        return;
      }
      setLoading(true);
      try {
        await login(identifier.trim(), password);
        setToast({ kind: "success", msg: "Đăng nhập thành công." });
        onLogin();
      } catch (err: any) {
        setToast({ kind: "error", msg: err?.response?.data?.detail || "Sai tài khoản hoặc mật khẩu." });
      } finally {
        setLoading(false);
      }
      return;
    }

    // ── Đăng ký tài khoản trường — Bước 1: xin mã OTP ──
    if (registerKind === "hust" && otpStep === "request") {
      if (!v.email) {
        setToast({ kind: "error", msg: `Email phải có đuôi ${HUST_DOMAIN}.` });
        touch("email");
        return;
      }
      setLoading(true);
      try {
        const res = await requestHustOtp(email.trim());
        startOtpTimers(res.expires_in);
        setOtpStep("verify");
        setCode("");
        setToast({ kind: "success", msg: "Đã gửi mã xác nhận tới email của bạn." });
      } catch (err: any) {
        setToast({ kind: "error", msg: err?.response?.data?.detail || "Không gửi được mã xác nhận." });
      } finally {
        setLoading(false);
      }
      return;
    }

    // Từ đây cần mật khẩu (đăng ký thường, hoặc bước 2 đăng ký trường)
    if (!v.password) {
      setToast({ kind: "error", msg: "Mật khẩu chưa đạt yêu cầu (≥6 ký tự, không phổ biến)." });
      touch("password");
      return;
    }
    if (!v.confirm) {
      setToast({ kind: "error", msg: "Mật khẩu xác nhận không khớp." });
      touch("confirm");
      return;
    }

    // ── Đăng ký tài khoản trường — Bước 2: xác minh mã + tạo tài khoản ──
    if (registerKind === "hust") {
      if (!v.code) {
        setToast({ kind: "error", msg: "Mã xác nhận gồm 6 chữ số." });
        touch("code");
        return;
      }
      setLoading(true);
      try {
        await verifyHustOtp({
          email: email.trim(),
          code: code.trim(),
          password,
          full_name: fullName.trim() || undefined,
        });
        setToast({ kind: "success", msg: "Đăng ký thành công." });
        onLogin();
      } catch (err: any) {
        setToast({ kind: "error", msg: err?.response?.data?.detail || "Xác minh thất bại." });
      } finally {
        setLoading(false);
      }
      return;
    }

    // ── Đăng ký tài khoản thường ──
    if (!v.username) {
      setToast({ kind: "error", msg: "Tên đăng nhập 3-50 ký tự, chỉ chữ/số/._-" });
      touch("username");
      return;
    }
    if (!v.birthDate) {
      setToast({ kind: "error", msg: "Ngày sinh không hợp lệ. Format: dd/mm/yyyy." });
      touch("birthDate");
      return;
    }
    setLoading(true);
    try {
      let bdate: string | undefined;
      if (birthDate.trim()) {
        bdate = parseBirthDate(birthDate) || undefined;
      }
      await registerLocal({
        username: username.trim(),
        password,
        full_name: fullName.trim() || undefined,
        birth_date: bdate,
      });
      setToast({ kind: "success", msg: "Đăng ký thành công." });
      onLogin();
    } catch (err: any) {
      setToast({ kind: "error", msg: err?.response?.data?.detail || "Đăng ký thất bại." });
    } finally {
      setLoading(false);
    }
  };

  // Gửi lại mã OTP (bước 2)
  const handleResend = async () => {
    if (loading || resendCooldown > 0) return;
    setLoading(true);
    try {
      const res = await requestHustOtp(email.trim());
      startOtpTimers(res.expires_in);
      setCode("");
      setToast({ kind: "success", msg: "Đã gửi lại mã mới." });
    } catch (err: any) {
      setToast({ kind: "error", msg: err?.response?.data?.detail || "Không gửi lại được mã." });
    } finally {
      setLoading(false);
    }
  };

  // ─── Helpers UI ──────────────────────────────────────────────────────────
  const fieldClass = (name: keyof typeof v, value: string) => {
    const valid = v[name];
    const isTouched = touched[name];
    let cls = "field-floating";
    if (value) cls += " has-value";
    if (isTouched && !valid) cls += " is-invalid";
    if (isTouched && valid && value) cls += " is-valid";
    return cls;
  };
  const renderStatusIcon = (name: keyof typeof v, value: string) => {
    if (!value) return null;
    const valid = v[name];
    if (!touched[name]) return null;
    return (
      <span className={`field-icon ${valid ? "field-icon-valid" : "field-icon-invalid"}`} style={{ right: 12 }}>
        {valid ? <IconCheck /> : <IconAlert />}
      </span>
    );
  };

  const s = passwordStrength(password);

  // Bước xin mã (đăng ký trường): chỉ hiện email + nút "Gửi mã".
  const hustRequestStep = mode === "register" && registerKind === "hust" && otpStep === "request";
  const showFullName = mode === "register" && !hustRequestStep;
  const showPasswordFields = !hustRequestStep;          // login + local + hust verify
  const showConfirm = mode === "register" && !hustRequestStep;

  const submitLabel = loading
    ? mode === "login"
      ? "Đang đăng nhập..."
      : hustRequestStep
        ? "Đang gửi mã..."
        : "Đang xử lý..."
    : mode === "login"
      ? "Đăng nhập"
      : hustRequestStep
        ? "Gửi mã xác nhận"
        : registerKind === "hust"
          ? "Xác nhận & đăng ký"
          : "Đăng ký";

  return (
    <div className="login-page">
      <div className="login-shell">
        {/* Hero panel */}
        <aside className="login-hero" aria-hidden="true">
          <div className="login-hero-scanline" />
          <div className="login-hero-top">
            <span className="login-hero-badge">
              <span className="login-hero-badge-dot" />
              TADIZB Scanner · HUST
            </span>
          </div>
          <div className="login-hero-bottom">
            <h2>Quét &amp; nhận dạng<br/>thẻ sinh viên</h2>
            <p>Hệ thống nhận dạng thẻ sinh viên thông minh.</p>
            <ul className="login-hero-features">
              <li><span className="login-hero-tick">✓</span> Quét mã QR tức thì qua camera</li>
              <li><span className="login-hero-tick">✓</span> OCR trích xuất văn bản 7 bước</li>
              <li><span className="login-hero-tick">✓</span> Đối chiếu CSDL &amp; lưu lịch sử</li>
            </ul>
          </div>
        </aside>

        {/* Form panel */}
        <div className="login-card">
          <div className="brand login-brand">
            <span className="brand-mark" />
            <h1>TADIZB</h1>
          </div>
          <p className="login-subtitle">Hệ thống nhận dạng thẻ sinh viên</p>

          <div className="auth-tabs">
            <button type="button" className={`auth-tab${mode === "login" ? " active" : ""}`} onClick={() => switchMode("login")}>
              Đăng nhập
            </button>
            <button type="button" className={`auth-tab${mode === "register" ? " active" : ""}`} onClick={() => switchMode("register")}>
              Đăng ký
            </button>
          </div>

          {mode === "register" && (
            <div className="auth-tabs auth-subtabs">
              <button type="button" className={`auth-tab${registerKind === "hust" ? " active" : ""}`} onClick={() => switchKind("hust")}>
                Tài khoản trường
              </button>
              <button type="button" className={`auth-tab${registerKind === "local" ? " active" : ""}`} onClick={() => switchKind("local")}>
                Tài khoản thường
              </button>
            </div>
          )}

          <form
            onSubmit={handleSubmit}
            className="login-form auth-pane"
            key={`${mode}-${registerKind}`} /* trigger re-mount → animation chạy lại */
          >
            {/* ── Identity field ── */}
            {mode === "login" ? (
              <div className={fieldClass("identifier", identifier)}>
                <input
                  ref={firstFieldRef}
                  id="identifier"
                  type="text"
                  value={identifier}
                  onChange={(e) => setIdentifier(e.target.value)}
                  onBlur={() => touch("identifier")}
                  placeholder=" "
                  required
                  autoComplete="username"
                />
                <label htmlFor="identifier">Tài khoản (email {HUST_DOMAIN} hoặc tên đăng nhập)</label>
                {renderStatusIcon("identifier", identifier)}
              </div>
            ) : registerKind === "hust" ? (
              <>
                <div className={fieldClass("email", email)}>
                  <input
                    ref={firstFieldRef}
                    id="email"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    onBlur={() => touch("email")}
                    placeholder=" "
                    required
                    autoComplete="email"
                    disabled={inOtpVerify}
                  />
                  <label htmlFor="email">Email trường ({HUST_DOMAIN})</label>
                  {!inOtpVerify && renderStatusIcon("email", email)}
                  {touched.email && email && !v.email && (
                    <div className="field-hint err">Email phải có đuôi {HUST_DOMAIN}.</div>
                  )}
                </div>

                {inOtpVerify && (
                  <>
                    <div className={fieldClass("code", code)}>
                      <input
                        id="code"
                        type="text"
                        value={code}
                        onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                        onBlur={() => touch("code")}
                        placeholder=" "
                        inputMode="numeric"
                        autoComplete="one-time-code"
                        maxLength={6}
                      />
                      <label htmlFor="code">Mã xác nhận (6 chữ số)</label>
                      {renderStatusIcon("code", code)}
                      <div className="field-hint" style={{ color: secondsLeft > 0 ? "#64748b" : "#ef4444" }}>
                        {secondsLeft > 0
                          ? `Mã hết hạn sau ${fmtMMSS(secondsLeft)}.`
                          : "Mã đã hết hạn — vui lòng gửi lại."}
                      </div>
                    </div>

                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: -4, marginBottom: 4 }}>
                      <button
                        type="button"
                        className="ghost"
                        onClick={() => { resetOtp(); setToast(null); }}
                        style={{ fontSize: 13, padding: "4px 0" }}
                      >
                        ← Đổi email
                      </button>
                      <button
                        type="button"
                        className="ghost"
                        onClick={handleResend}
                        disabled={loading || resendCooldown > 0}
                        style={{ fontSize: 13, padding: "4px 0" }}
                      >
                        {resendCooldown > 0 ? `Gửi lại mã (${resendCooldown}s)` : "Gửi lại mã"}
                      </button>
                    </div>
                  </>
                )}
              </>
            ) : (
              <div className={fieldClass("username", username)}>
                <input
                  ref={firstFieldRef}
                  id="username"
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  onBlur={() => touch("username")}
                  placeholder=" "
                  required
                  autoComplete="username"
                />
                <label htmlFor="username">Tên đăng nhập</label>
                {renderStatusIcon("username", username)}
                {touched.username && username && !v.username && (
                  <div className="field-hint err">3-50 ký tự, chỉ chữ/số/._-</div>
                )}
              </div>
            )}

            {/* ── Họ và tên + Ngày sinh (register; tài khoản trường: chỉ ở bước 2) ── */}
            {showFullName && (
              <>
                <div className={`field-floating${fullName ? " has-value" : ""}`}>
                  <input
                    id="fullName"
                    type="text"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    placeholder=" "
                    autoComplete="name"
                  />
                  <label htmlFor="fullName">Họ và tên</label>
                </div>

                {registerKind === "local" && (
                  <div className={fieldClass("birthDate", birthDate)}>
                    <input
                      id="birthDate"
                      type="text"
                      value={birthDate}
                      onChange={(e) => setBirthDate(e.target.value)}
                      onBlur={() => touch("birthDate")}
                      placeholder=" "
                      inputMode="numeric"
                      style={{ paddingRight: 42 }}
                    />
                    <label htmlFor="birthDate">Ngày sinh (dd/mm/yyyy)</label>
                    <span className="field-icon">
                      <button
                        type="button"
                        className="field-icon-btn"
                        onClick={() => setShowCalendar(true)}
                        title="Chọn từ lịch"
                        aria-label="Mở lịch chọn ngày"
                      >
                        <IconCalendar />
                      </button>
                    </span>
                    {touched.birthDate && birthDate && !v.birthDate && (
                      <div className="field-hint err">Định dạng đúng: dd/mm/yyyy.</div>
                    )}
                  </div>
                )}
              </>
            )}

            {/* ── Password ── */}
            {showPasswordFields && (
            <div className={fieldClass("password", password)}>
              <input
                id="password"
                type={showPw ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onBlur={() => touch("password")}
                onKeyDown={handleCapsCheck}
                onKeyUp={handleCapsCheck}
                placeholder=" "
                required
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                style={{ paddingRight: 42 }}
              />
              <label htmlFor="password">Mật khẩu</label>
              <span className="field-icon">
                <button
                  type="button"
                  className="field-icon-btn"
                  onClick={() => setShowPw((s) => !s)}
                  title={showPw ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
                  aria-label={showPw ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
                >
                  <IconEye off={showPw} />
                </button>
              </span>
              {capsLock && (
                <div className="field-hint warn">
                  <IconAlert /> Caps Lock đang bật.
                </div>
              )}
              {mode === "register" && password && (
                <div style={{ marginTop: 8 }}>
                  <div style={{ height: 4, background: "#e5e7eb", borderRadius: 999, overflow: "hidden" }}>
                    <div style={{
                      width: `${(s.score / 4) * 100}%`,
                      height: "100%",
                      background: s.color,
                      transition: "width 0.25s, background 0.25s",
                    }} />
                  </div>
                  <div style={{ fontSize: 11, color: s.color, marginTop: 4, fontWeight: 600 }}>
                    Độ mạnh: {s.label}
                  </div>
                </div>
              )}
              {touched.password && password && !v.password && (
                <div className="field-hint err">≥ 6 ký tự và không nằm trong danh sách phổ biến.</div>
              )}
            </div>
            )}

            {/* ── Confirm password ── */}
            {showConfirm && (
              <div className={fieldClass("confirm", confirm)}>
                <input
                  id="confirm"
                  type={showConfirmPw ? "text" : "password"}
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  onBlur={() => touch("confirm")}
                  placeholder=" "
                  required
                  autoComplete="new-password"
                  style={{ paddingRight: 42 }}
                />
                <label htmlFor="confirm">Xác nhận mật khẩu</label>
                <span className="field-icon">
                  <button
                    type="button"
                    className="field-icon-btn"
                    onClick={() => setShowConfirmPw((s) => !s)}
                    title={showConfirmPw ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
                    aria-label={showConfirmPw ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
                  >
                    <IconEye off={showConfirmPw} />
                  </button>
                </span>
                {touched.confirm && confirm && !v.confirm && (
                  <div className="field-hint err">Mật khẩu xác nhận không khớp.</div>
                )}
              </div>
            )}

            <button type="submit" className="primary full-width" disabled={loading} style={{ marginTop: 6 }}>
              {loading && <span className="btn-spinner" />}
              {submitLabel}
            </button>
          </form>

          {onBack && (
            <button
              type="button"
              className="login-back ghost"
              onClick={onBack}
              style={{ marginTop: 12, alignSelf: "center" }}
            >
              ← Về trang chủ
            </button>
          )}
        </div>
      </div>

      {/* Toast */}
      {toast && (
        <div className={`toast ${toast.kind}`} role="status" onClick={() => setToast(null)}>
          {toast.kind === "success" ? <IconCheck /> : <IconAlert />}
          <span>{toast.msg}</span>
        </div>
      )}

      {/* Modal lịch */}
      {showCalendar && (
        <>
          <div
            className="modal-backdrop"
            onClick={() => setShowCalendar(false)}
            style={{ position: "fixed", inset: 0, background: "rgba(15,20,44,0.4)", zIndex: 999 }}
          />
          <div
            role="dialog"
            aria-modal="true"
            className="modal-pop"
            style={{
              position: "fixed",
              top: "50%",
              left: "50%",
              transform: "translate(-50%, -50%)",
              zIndex: 1000,
              background: "#fff",
              border: "1px solid #e5e7eb",
              borderRadius: 18,
              boxShadow: "0 24px 60px rgba(15,20,44,0.32)",
              padding: 14,
              maxHeight: "90vh",
              maxWidth: "calc(100vw - 24px)",
              overflow: "auto",
            }}
          >
            <DayPicker
              mode="single"
              selected={selectedDate}
              onSelect={handleDaySelect}
              defaultMonth={selectedDate}
              captionLayout="dropdown"
              startMonth={new Date(1900, 0)}
              endMonth={new Date(new Date().getFullYear(), 11)}
              showOutsideDays
            />
          </div>
        </>
      )}
    </div>
  );
}
