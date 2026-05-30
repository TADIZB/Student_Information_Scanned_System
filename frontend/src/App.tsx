import React, { useCallback, useEffect, useState } from "react";
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router-dom";
import { getMe, logout } from "./api";
import type { ScanResult } from "./api";
import Homepage from "./pages/Homepage";
import Login from "./pages/Login";
import Profile from "./pages/Profile";
import Scanner from "./pages/Scanner";

type Tab = "qr" | "ocr";

// ─── Context để chia sẻ trạng thái auth giữa các route ─────────────────────
interface AuthState {
  username: string | null;
  refresh: () => Promise<void>;
  setUsername: (u: string | null) => void;
}

const AuthContext = React.createContext<AuthState>({
  username: null,
  refresh: async () => {},
  setUsername: () => {},
});

const useAuth = () => React.useContext(AuthContext);

const displayName = (u: { username: string | null; full_name: string | null; email: string }) =>
  u.full_name || u.email || u.username;

// ─── Topbar dùng chung cho các route có chrome ─────────────────────────────
function Topbar({ tab }: { tab?: Tab }) {
  const navigate = useNavigate();
  const { username } = useAuth();

  const handleLogout = async () => {
    try {
      await logout();
    } finally {
      // Reload lại trang để xoá toàn bộ state, cache hình ảnh, lịch sử... của user vừa đăng xuất
      window.location.reload();
    }
  };

  return (
    <header className="topbar">
      <div className="brand" style={{ cursor: "pointer" }} onClick={() => navigate("/")}>
        <span className="brand-mark" />
        <div><h1>TADIZB</h1></div>
      </div>

      {tab && (
        <nav className="tab-nav">
          <button
            className={`tab${tab === "qr" ? " active" : ""}`}
            onClick={() => navigate("/scan/qr")}
          >
            QR Thẻ Sinh Viên
          </button>
          <button
            className={`tab${tab === "ocr" ? " active" : ""}`}
            onClick={() => navigate("/scan/ocr")}
          >
            OCR CCCD
          </button>
        </nav>
      )}

      <div className="actions">
        {username ? (
          <>
            <span
              className="username-label clickable"
              onClick={() => navigate("/profile")}
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
            <button className="ghost" onClick={() => navigate("/login")}>
              Đăng nhập
            </button>
            <button className="primary" onClick={() => navigate("/register")}>
              Đăng ký
            </button>
          </>
        )}
      </div>
    </header>
  );
}

// ─── Route components ──────────────────────────────────────────────────────

function HomeRoute() {
  const navigate = useNavigate();
  const { username } = useAuth();

  const handleLogout = async () => {
    try {
      await logout();
    } finally {
      window.location.reload();
    }
  };

  return (
    <Homepage
      username={username}
      onLoginClick={() => navigate("/login")}
      onRegisterClick={() => navigate("/register")}
      onQrClick={() => navigate("/scan/qr")}
      onOcrClick={() => navigate("/scan/ocr")}
      onProfileClick={() => navigate("/profile")}
      onLogoutClick={handleLogout}
    />
  );
}

function ScanRoute({ mode }: { mode: Tab }) {
  const navigate = useNavigate();
  const { username } = useAuth();
  const handleScanSuccess = (_result: ScanResult) => {};
  return (
    <div className="app">
      <Topbar tab={mode} />
      <main className="main-content">
        <Scanner
          scanMode={mode}
          isLoggedIn={!!username}
          onScanSuccess={handleScanSuccess}
          onLoginClick={() => navigate("/login")}
        />
      </main>
    </div>
  );
}

function ProfileRoute() {
  const navigate = useNavigate();
  const { username } = useAuth();
  if (!username) {
    return <Navigate to="/login" state={{ from: { pathname: "/profile" } }} replace />;
  }
  return (
    <div className="app">
      <Topbar />
      <main className="main-content">
        <Profile onBack={() => navigate("/scan/qr")} />
      </main>
    </div>
  );
}

function AuthRoute({ initialMode }: { initialMode: "login" | "register" }) {
  const navigate = useNavigate();
  const location = useLocation();
  const { refresh } = useAuth();

  const handleLogin = async () => {
    await refresh();
    // Nếu user bị redirect từ trang khác → quay lại trang đó. Mặc định: /scan/qr.
    const from = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname;
    navigate(from || "/scan/qr", { replace: true });
  };

  return (
    <Login
      onLogin={handleLogin}
      initialMode={initialMode}
      onBack={() => navigate("/")}
    />
  );
}

// ─── App root ──────────────────────────────────────────────────────────────

function AppRoutes() {
  const [username, setUsername] = useState<string | null>(null);
  const [checking, setChecking] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const data = await getMe();
      setUsername(displayName(data));
    } catch {
      setUsername(null);
    }
  }, []);

  useEffect(() => {
    refresh().finally(() => setChecking(false));
  }, [refresh]);

  if (checking) {
    return (
      <div className="full-center">
        <span className="brand-mark" style={{ width: 48, height: 48 }} />
      </div>
    );
  }

  return (
    <AuthContext.Provider value={{ username, refresh, setUsername }}>
      <Routes>
        <Route path="/" element={<HomeRoute />} />
        <Route path="/login" element={<AuthRoute initialMode="login" />} />
        <Route path="/register" element={<AuthRoute initialMode="register" />} />
        <Route path="/scan/qr" element={<ScanRoute mode="qr" />} />
        <Route path="/scan/ocr" element={<ScanRoute mode="ocr" />} />
        <Route path="/profile" element={<ProfileRoute />} />
        {/* Route không tồn tại → quay về trang chủ */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthContext.Provider>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  );
}
