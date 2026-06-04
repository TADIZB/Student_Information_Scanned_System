import React, { useEffect, useState } from "react";
import { getMe, logout } from "./api";
import type { ScanResult } from "./api";
import Login from "./pages/Login";
import MicrosoftLogin from "./pages/MicrosoftLogin";
import Scanner from "./pages/Scanner";
import Homepage from "./pages/Homepage";
import Profile from "./pages/Profile";

type Tab = "qr" | "ocr";
type View = "home" | "app" | "profile";
type AuthMode = "login" | "register";

export default function App() {
  const [username, setUsername] = useState<string | null>(null);
  const [checking, setChecking] = useState(true);
  const [view, setView] = useState<View>("home");
  const [tab, setTab] = useState<Tab>("qr");
  const [showAuth, setShowAuth] = useState(false);
  const [authMode, setAuthMode] = useState<AuthMode>("login");
  const [showMsLogin, setShowMsLogin] = useState(false);
  const [msPrefillEmail, setMsPrefillEmail] = useState<string | undefined>(undefined);

  const displayName = (u: { username: string | null; full_name: string | null; email: string | null }) =>
    u.username || u.full_name || u.email;

  useEffect(() => {
    getMe()
      .then((data) => setUsername(displayName(data)))
      .catch(() => setUsername(null))
      .finally(() => setChecking(false));
  }, []);

  const handleLogin = async () => {
    const data = await getMe();
    setUsername(displayName(data));
    setShowAuth(false);
    setShowMsLogin(false);
    setView("app");
  };

  const handleLogout = async () => {
    try {
      await logout();
    } finally {
      window.location.reload();
    }
  };

  const handleScanSuccess = (_result: ScanResult) => { };

  if (checking) {
    return (
      <div className="full-center">
        <span className="brand-mark" style={{ width: 48, height: 48 }} />
      </div>
    );
  }


  if (showMsLogin) {
    return (
      <MicrosoftLogin
        onLogin={handleLogin}
        initialEmail={msPrefillEmail}
        onBack={() => { setShowMsLogin(false); setShowAuth(true); }}
      />
    );
  }

  if (showAuth) {
    return (
      <Login
        onLogin={handleLogin}
        initialMode={authMode}
        onBack={() => setShowAuth(false)}
        onMicrosoftLogin={(prefill) => {
          setMsPrefillEmail(prefill);
          setShowAuth(false);
          setShowMsLogin(true);
        }}
      />
    );
  }

  if (view === "home") {
    return (
      <Homepage
        username={username}
        onLoginClick={() => { setAuthMode("login"); setShowAuth(true); }}
        onRegisterClick={() => { setAuthMode("register"); setShowAuth(true); }}
        onQrClick={() => { setTab("qr"); setView("app"); }}
        onOcrClick={() => { setTab("ocr"); setView("app"); }}
        onProfileClick={() => setView("profile")}
        onLogoutClick={handleLogout}
      />
    );
  }

  if (view === "profile") {
    return (
      <div className="app">
        <header className="topbar">
          <div className="brand" style={{ cursor: "pointer" }} onClick={() => setView("home")}>
            <span className="brand-mark" />
            <div>
              <h1>TADIZB</h1>
            </div>
          </div>
          <div className="actions">
            {username && <span className="username-label">{username}</span>}
            <button className="ghost" onClick={handleLogout}>
              Đăng xuất
            </button>
          </div>
        </header>
        <main className="main-content">
          <Profile onBack={() => setView("home")} />
        </main>
      </div>
    );
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand" style={{ cursor: "pointer" }} onClick={() => setView("home")}>
          <span className="brand-mark" />
          <div>
            <h1>TADIZB</h1>
          </div>
        </div>

        <nav className="tab-nav">
          <button
            className={`tab${tab === "qr" ? " active" : ""}`}
            onClick={() => setTab("qr")}
          >
            QR Thẻ Sinh Viên
          </button>
          <button
            className={`tab${tab === "ocr" ? " active" : ""}`}
            onClick={() => setTab("ocr")}
          >
            OCR
          </button>
        </nav>

        <div className="actions">
          {username ? (
            <>
              <span
                className="username-label clickable"
                onClick={() => setView("profile")}
                title="Hồ sơ"
              >
                {username}
              </span>
              <button className="ghost" onClick={handleLogout}>
                Đăng xuất
              </button>
            </>
          ) : (
            <>
              <button className="ghost" onClick={() => { setAuthMode("login"); setShowAuth(true); }}>
                Đăng nhập
              </button>
              <button className="primary" onClick={() => { setAuthMode("register"); setShowAuth(true); }}>
                Đăng ký
              </button>
            </>
          )}
        </div>
      </header>

      <main className="main-content">
        {tab === "qr" && (
          <Scanner
            scanMode="qr"
            isLoggedIn={!!username}
            onScanSuccess={handleScanSuccess}
            onLoginClick={() => { setAuthMode("login"); setShowAuth(true); }}
          />
        )}
        {tab === "ocr" && (
          <Scanner
            scanMode="ocr"
            isLoggedIn={!!username}
            onScanSuccess={handleScanSuccess}
            onLoginClick={() => { setAuthMode("login"); setShowAuth(true); }}
          />
        )}
      </main>
    </div>
  );
}
