import React, { FormEvent, useState } from "react";
import { login, register } from "../api";

type Mode = "login" | "register";

interface Props {
  onLogin: () => void;
  initialMode?: Mode;
  onBack?: () => void;
}

export default function Login({ onLogin, initialMode = "login", onBack }: Props) {
  const [mode, setMode] = useState<Mode>(initialMode);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(false);

  const switchMode = (m: Mode) => {
    setMode(m);
    setError("");
    setSuccess("");
    setPassword("");
    setConfirm("");
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
        await login(username, password);
        onLogin();
      } else {
        await register(username, password);
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

        {/* Tab chuyển đổi */}
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

        <form onSubmit={handleSubmit} className="login-form">
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
      </div>
    </div>
  );
}
