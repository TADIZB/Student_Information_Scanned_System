import React from "react";

interface Props {
  onLoginClick: () => void;
  onRegisterClick: () => void;
  onQrClick: () => void;
  onOcrClick: () => void;
}

export default function Homepage({ onLoginClick, onRegisterClick, onQrClick, onOcrClick }: Props) {
  return (
    <div className="home-page">
      {/* Topbar */}
      <header className="home-topbar">
        <div className="brand">
          <span className="brand-mark" />
          <div>
            <h1>TADIZB</h1>
          </div>
        </div>
        <div className="home-auth-actions">
          <button className="ghost" onClick={onLoginClick}>
            Đăng nhập
          </button>
          <button className="primary" onClick={onRegisterClick}>
            Đăng ký
          </button>
        </div>
      </header>

      {/* Hero */}
      <section className="home-hero">
        <div className="home-hero-badge">Hệ thống quét thẻ thông minh</div>
        <h2 className="home-hero-title">
          Quét &amp; nhận dạng thẻ<br />
          <span className="home-hero-accent">nhanh chóng, chính xác</span>
        </h2>
        <p className="home-hero-desc">
          Tự động phát hiện thẻ qua camera, trích xuất thông tin bằng OCR và QR,
          lưu lịch sử toàn bộ phiên làm việc — tất cả trong một nền tảng.
        </p>
        <div className="home-hero-cta">
          <button className="primary home-cta-btn" onClick={onRegisterClick}>
            Bắt đầu miễn phí
          </button>
          <button className="ghost home-cta-btn" onClick={onLoginClick}>
            Đã có tài khoản
          </button>
        </div>
      </section>

      {/* Features */}
      <section className="home-features">
        <button className="feature-card feature-card-btn" onClick={onQrClick}>
          <div className="feature-icon" style={{ background: "rgba(255,111,60,0.12)", color: "var(--accent)" }}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
              <circle cx="12" cy="13" r="4"/>
            </svg>
          </div>
          <h3>QR Thẻ Sinh Viên</h3>
          <p>Quét mã QR trên thẻ sinh viên qua camera, nhận diện tức thời và lưu thông tin tự động.</p>
          <span className="feature-cta">Bắt đầu quét →</span>
        </button>

        <button className="feature-card feature-card-btn" onClick={onOcrClick}>
          <div className="feature-icon" style={{ background: "rgba(54,210,165,0.12)", color: "#0d9b73" }}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="3" width="18" height="18" rx="2"/>
              <path d="M3 9h18M9 21V9"/>
            </svg>
          </div>
          <h3>OCR</h3>
          <p>Nhận dạng văn bản trên thẻ bằng Tesseract OCR, tự động bóc tách MSSV, họ tên, ngành học.</p>
          <span className="feature-cta">Bắt đầu quét →</span>
        </button>
      </section>
    </div>
  );
}
