import React, { FormEvent, useEffect, useRef, useState } from "react";
import { googleLogin, googleRegister, login, register } from "../api";

type Mode = "login" | "register";

interface Props {
  onLogin: () => void;
  initialMode?: Mode;
  onBack?: () => void;
}

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID as string | undefined;

declare global {
  interface Window {
    google?: any;
  }
}

export default function Login({ onLogin, initialMode = "login", onBack }: Props) {
  const [mode, setMode] = useState<Mode>(initialMode);
  const [identifier, setIdentifier] = useState("");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(false);

  // Google OAuth token client (khởi tạo 1 lần)
  const tokenClientRef = useRef<any>(null);
  // Lưu mode đang yêu cầu Google: callback sẽ đọc giá trị này
  const pendingModeRef = useRef<Mode>(initialMode);

  const switchMode = (m: Mode) => {
    setMode(m);
    setError("");
    setSuccess("");
    setPassword("");
    setConfirm("");
  };

  // ─── Khởi tạo Google Identity Services (1 lần) ────────────────────────────
  useEffect(() => {
    if (!GOOGLE_CLIENT_ID || !window.google?.accounts?.oauth2) return;

    tokenClientRef.current = window.google.accounts.oauth2.initTokenClient({
      client_id: GOOGLE_CLIENT_ID,
      scope: "openid email profile",
      callback: async (resp: { access_token?: string; error?: string }) => {
        if (!resp.access_token) {
          setError("Không lấy được access token từ Google.");
          return;
        }
        setError("");
        setSuccess("");
        setLoading(true);
        try {
          if (pendingModeRef.current === "register") {
            const data = await googleRegister(resp.access_token);
            if (data.already_existed) {
              setSuccess("Tài khoản Google đã tồn tại, đang đăng nhập...");
            }
          } else {
            await googleLogin(resp.access_token);
          }
          onLogin();
        } catch (err: any) {
          setError(err?.response?.data?.detail || "Xác thực Google thất bại.");
        } finally {
          setLoading(false);
        }
      },
    });
  }, [onLogin]);

  const handleGoogleClick = (target: Mode) => {
    if (!tokenClientRef.current) {
      setError("Google chưa sẵn sàng. Vui lòng tải lại trang.");
      return;
    }
    pendingModeRef.current = target;
    setError("");
    tokenClientRef.current.requestAccessToken({ prompt: "consent" });
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setSuccess("");

    if (mode === "register") {
      if (password !== confirm) {
        setError("Mật khẩu xác nhận không khớp.");
        return;
      }
      if (password.length < 6) {
        setError("Mật khẩu phải có ít nhất 6 ký tự.");
        return;
      }
    }

    setLoading(true);
    try {
      if (mode === "login") {
        await login(identifier, password);
        onLogin();
      } else {
        await register({
          username,
          password,
          email: email.trim() || undefined,
          full_name: fullName.trim() || undefined,
        });
        setSuccess("Đăng ký thành công! Hãy đăng nhập.");
        switchMode("login");
      }
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      if (mode === "login") {
        setError(detail || "Sai tên đăng nhập hoặc mật khẩu.");
      } else {
        setError(detail || "Đăng ký thất bại. Vui lòng thử lại.");
      }
    } finally {
      setLoading(false);
    }
  };

  // Icon Google (SVG inline)
  const GoogleIcon = () => (
    <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true">
      <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3c-1.6 4.6-6 8-11.3 8-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.9 1.2 8 3l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z"/>
      <path fill="#FF3D00" d="m6.3 14.7 6.6 4.8C14.7 16 19 13 24 13c3.1 0 5.9 1.2 8 3l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z"/>
      <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2c-2 1.5-4.5 2.4-7.2 2.4-5.2 0-9.6-3.3-11.3-8l-6.5 5C9.6 39.6 16.3 44 24 44z"/>
      <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.3-2.3 4.2-4.2 5.6l6.2 5.2C40.6 36 44 30.5 44 24c0-1.3-.1-2.4-.4-3.5z"/>
    </svg>
  );

  return (
    <div className="login-page">
      <div className="login-card">
        {onBack && (
          <button type="button" className="login-back ghost" onClick={onBack}>
            ← Trang chủ
          </button>
        )}
        <div className="brand login-brand">
          <span className="brand-mark" />
          <h1>TADIZB</h1>
        </div>
        <p className="login-subtitle">Hệ thống quét thẻ thông minh</p>

        <div className="auth-tabs">
          <button
            type="button"
            className={`auth-tab${mode === "login" ? " active" : ""}`}
            onClick={() => switchMode("login")}
          >
            Đăng nhập
          </button>
          <button
            type="button"
            className={`auth-tab${mode === "register" ? " active" : ""}`}
            onClick={() => switchMode("register")}
          >
            Đăng ký
          </button>
        </div>

        {/* ─── LUỒNG 1: Username / Password ─── */}
        <form onSubmit={handleSubmit} className="login-form">
          {mode === "login" ? (
            <div className="field">
              <label htmlFor="identifier">Tên đăng nhập hoặc Email</label>
              <input
                id="identifier"
                type="text"
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value)}
                placeholder="username hoặc email@example.com"
                required
                autoFocus
              />
            </div>
          ) : (
            <>
              <div className="field">
                <label htmlFor="username">Tên đăng nhập</label>
                <input
                  id="username"
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="Nhập tên đăng nhập"
                  required
                  autoFocus
                />
              </div>
              <div className="field">
                <label htmlFor="email">Email (tuỳ chọn)</label>
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="email@example.com"
                />
              </div>
              <div className="field">
                <label htmlFor="fullName">Họ và tên (tuỳ chọn)</label>
                <input
                  id="fullName"
                  type="text"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="Nguyễn Văn A"
                />
              </div>
            </>
          )}

          <div className="field">
            <label htmlFor="password">Mật khẩu</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
            />
          </div>

          {mode === "register" && (
            <div className="field">
              <label htmlFor="confirm">Xác nhận mật khẩu</label>
              <input
                id="confirm"
                type="password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                placeholder="••••••••"
                required
              />
            </div>
          )}

          {error   && <p className="login-error">{error}</p>}
          {success && <p className="login-success">{success}</p>}

          <button type="submit" className="primary full-width" disabled={loading}>
            {loading
              ? mode === "login" ? "Đang đăng nhập..." : "Đang đăng ký..."
              : mode === "login" ? "Đăng nhập" : "Đăng ký"}
          </button>
        </form>

        {/* ─── LUỒNG 2: Google OAuth ─── */}
        {GOOGLE_CLIENT_ID && (
          <>
            <div className="auth-divider"><span>hoặc</span></div>
            <button
              type="button"
              className="google-btn full-width"
              onClick={() => handleGoogleClick(mode)}
              disabled={loading}
            >
              <GoogleIcon />
              <span>
                {mode === "login" ? "Đăng nhập bằng Google" : "Đăng ký bằng Google"}
              </span>
            </button>
          </>
        )}
      </div>
    </div>
  );
}
