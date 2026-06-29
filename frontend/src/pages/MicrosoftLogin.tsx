import React, { FormEvent, useEffect, useState } from "react";
import { loginMicrosoft } from "../api";

interface Props {
  onLogin: () => void;
  onBack: () => void;
  initialEmail?: string;
}

const HUST_DOMAINS = ["@sis.hust.edu.vn", "@hust.edu.vn"];
const HUST_DOMAIN_LABEL = HUST_DOMAINS.join(" hoặc ");
type ToastKind = "success" | "error";

const IconMicrosoft = () => (
  <svg width="22" height="22" viewBox="0 0 23 23" aria-hidden>
    <rect x="1" y="1" width="10" height="10" fill="#f25022" />
    <rect x="12" y="1" width="10" height="10" fill="#7fba00" />
    <rect x="1" y="12" width="10" height="10" fill="#00a4ef" />
    <rect x="12" y="12" width="10" height="10" fill="#ffb900" />
  </svg>
);
const IconAlert = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <circle cx="12" cy="12" r="10" />
    <line x1="12" y1="8" x2="12" y2="12" />
    <line x1="12" y1="16" x2="12.01" y2="16" />
  </svg>
);
const IconCheck = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <polyline points="20 6 9 17 4 12" />
  </svg>
);
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

export default function MicrosoftLogin({ onLogin, onBack, initialEmail = "" }: Props) {
  const [email, setEmail] = useState(initialEmail);
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [capsLock, setCapsLock] = useState(false);
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState<{ kind: ToastKind; msg: string } | null>(null);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 3500);
    return () => clearTimeout(t);
  }, [toast]);

  const handleCapsCheck = (e: React.KeyboardEvent<HTMLInputElement>) => {
    setCapsLock(e.getModifierState && e.getModifierState("CapsLock"));
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setToast(null);
    const mail = email.trim();
    if (!HUST_DOMAINS.some((domain) => mail.toLowerCase().endsWith(domain))) {
      setToast({ kind: "error", msg: `Vui lòng dùng email trường ${HUST_DOMAIN_LABEL}.` });
      return;
    }
    if (!password) {
      setToast({ kind: "error", msg: "Vui lòng nhập mật khẩu." });
      return;
    }
    setLoading(true);
    try {
      await loginMicrosoft(mail, password);
      setToast({ kind: "success", msg: "Đăng nhập thành công." });
      onLogin();
    } catch (err: any) {
      setToast({
        kind: "error",
        msg: err?.response?.data?.detail || "Đăng nhập tài khoản trường thất bại.",
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-shell">
        {/* Hero panel */}
        <aside className="login-hero" aria-hidden="true">
          <div className="login-hero-slides">
            <div className="login-hero-slide" style={{ backgroundImage: "url(/hero-scan.svg)" }} />
            <div className="login-hero-slide" style={{ backgroundImage: "url(/hero-scan-2.svg)" }} />
            <div className="login-hero-slide" style={{ backgroundImage: "url(/hero-scan-3.svg)" }} />
            <div className="login-hero-slide" style={{ backgroundImage: "url(/hero-scan-4.svg)" }} />
          </div>
          <div className="login-hero-overlay" />
          <div className="login-hero-top">
            <span className="login-hero-badge">
              <span className="login-hero-badge-dot" />
              TADIZB Scanner · HUST
            </span>
          </div>
          <div className="login-hero-bottom">
            <h2>Quét &amp; nhận dạng<br />thẻ sinh viên</h2>
            <p>Hệ thống nhận dạng thẻ sinh viên thông minh.</p>
          </div>
        </aside>

        {/* Form panel */}
        <div className="login-card">
          <div className="brand login-brand">
            <span className="brand-mark" />
            <h1>TADIZB</h1>
          </div>
          <p className="login-subtitle">Hệ thống nhận dạng thẻ sinh viên</p>

          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
            <IconMicrosoft />
            <h2 style={{ margin: 0, fontSize: 20 }}>Đăng nhập tài khoản trường</h2>
          </div>
          <p style={{ margin: "0 0 18px", fontSize: 13, color: "#64748b" }}>
            Dùng email trường ({HUST_DOMAIN_LABEL}) và mật khẩu đăng nhập của trường.
          </p>

          <form onSubmit={handleSubmit} className="login-form auth-pane">
            <div className={`field-floating${email ? " has-value" : ""}`}>
              <input
                id="ms-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder=" "
                required
                autoFocus
                autoComplete="username"
                disabled={loading}
              />
              <label htmlFor="ms-email">Email trường</label>
            </div>

            <div className={`field-floating${password ? " has-value" : ""}`}>
              <input
                id="ms-password"
                type={showPw ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onKeyDown={handleCapsCheck}
                onKeyUp={handleCapsCheck}
                placeholder=" "
                required
                autoComplete="current-password"
                disabled={loading}
                style={{ paddingRight: 42 }}
              />
              <label htmlFor="ms-password">Mật khẩu</label>
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
            </div>

            <button type="submit" className="primary full-width" disabled={loading} style={{ marginTop: 6 }}>
              {loading && <span className="btn-spinner" />}
              {loading ? "Đang xác thực..." : "Đăng nhập"}
            </button>

            <button
              type="button"
              className="ghost"
              onClick={onBack}
              disabled={loading}
              style={{ marginTop: 10, alignSelf: "center", fontSize: 13 }}
            >
              ← Quay lại đăng nhập
            </button>
          </form>
        </div>
      </div>

      {toast && (
        <div className={`toast ${toast.kind}`} role="status" onClick={() => setToast(null)}>
          {toast.kind === "success" ? <IconCheck /> : <IconAlert />}
          <span>{toast.msg}</span>
        </div>
      )}
    </div>
  );
}
