import React from "react";

interface Props {
  onLoginClick: () => void;
  onRegisterClick: () => void;
  onQrClick: () => void;
  onOcrClick: () => void;
  // Auth state — Homepage cần biết để hiển thị topbar đúng
  username: string | null;
  onProfileClick?: () => void;
  onLogoutClick?: () => void;
}

export default function Homepage({
  onLoginClick,
  onRegisterClick,
  onQrClick,
  onOcrClick,
  username,
  onProfileClick,
  onLogoutClick,
}: Props) {
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
          {username ? (
            <>
              <span
                className="username-label clickable"
                onClick={onProfileClick}
                title="Hồ sơ"
              >
                {username}
              </span>
              <button className="ghost" onClick={onLogoutClick}>
                Đăng xuất
              </button>
            </>
          ) : (
            <>
              <button className="ghost" onClick={onLoginClick}>
                Đăng nhập
              </button>
              <button className="primary" onClick={onRegisterClick}>
                Đăng ký
              </button>
            </>
          )}
        </div>
      </header>

      {/* Hero */}
      <section className="home-hero">
        <div className="home-hero-text">
          <div className="home-hero-badge">
            <span className="home-hero-badge-dot" />
            Hệ thống nhận dạng thẻ sinh viên · HUST
          </div>
          <h2 className="home-hero-title">
            Quét &amp; nhận dạng thẻ<br />
            <span className="home-hero-accent">nhanh chóng, chính xác</span>
          </h2>
          <p className="home-hero-desc">
            Tự động phát hiện thẻ qua camera, trích xuất thông tin bằng OCR và QR.
          </p>
          <div className="home-hero-cta">
            <button className="primary home-cta-btn" onClick={onQrClick}>
              QR Code
            </button>
            <button className="secondary home-cta-btn" onClick={onOcrClick}>
              Phân tích ảnh
            </button>
          </div>
          <div className="home-hero-stats">
            <div className="home-stat">
              <strong>2</strong>
              <span>Chế độ quét</span>
            </div>
            <div className="home-stat-divider" />
            <div className="home-stat">
              <strong>7</strong>
              <span>Bước xử lý ảnh</span>
            </div>
            <div className="home-stat-divider" />
            <div className="home-stat">
              <strong>100%</strong>
              <span>Lưu lịch sử</span>
            </div>
          </div>
        </div>

        {/* Hero visual — mô phỏng thẻ sinh viên đang được quét */}
        <div className="home-hero-visual" aria-hidden="true">
          <div className="hero-card">
            <div className="hero-card-glow" />
            <div className="hero-card-top">
              <span className="hero-card-logo" />
              <span className="hero-card-univ">ĐẠI HỌC BÁCH KHOA HÀ NỘI</span>
            </div>
            <div className="hero-card-body">
              <div className="hero-card-photo" />
              <div className="hero-card-lines">
                <span className="hero-line w-70" />
                <span className="hero-line w-50" />
                <span className="hero-line w-60" />
                <span className="hero-line w-40" />
              </div>
            </div>
            <div className="hero-card-qr">
              <svg width="100%" height="100%" viewBox="0 0 24 24" fill="currentColor">
                <path d="M3 3h8v8H3V3zm2 2v4h4V5H5zm8-2h8v8h-8V3zm2 2v4h4V5h-4zM3 13h8v8H3v-8zm2 2v4h4v-4H5zm10-2h2v2h-2v-2zm4 0h2v2h-2v-2zm-4 4h2v2h-2v-2zm2 2h2v2h-2v-2zm2-2h2v2h-2v-2z" />
              </svg>
            </div>
            <div className="hero-scanline" />
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="home-features">
        <div className="home-section-head">
          <h3 className="home-section-title">Chọn chế độ Scan</h3>

        </div>
        <div className="home-features-grid">
          <button className="feature-card feature-card-btn" onClick={onQrClick}>
            <div className="feature-icon feature-icon-qr">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
                <circle cx="12" cy="13" r="4" />
              </svg>
            </div>
            <h3>QR Thẻ Sinh Viên</h3>
            <p>Quét mã QR trên thẻ sinh viên qua camera, đối chiếu MSSV tức thì.</p>
            <span className="feature-cta">Bắt đầu quét →</span>
          </button>

          <button className="feature-card feature-card-btn" onClick={onOcrClick}>
            <div className="feature-icon feature-icon-ocr">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="3" width="18" height="18" rx="2" />
                <path d="M3 9h18M9 21V9" />
              </svg>
            </div>
            <h3>OCR Nhận Dạng</h3>
            <p>Trích xuất văn bản trên thẻ qua quy trình xử lý ảnh.</p>
            <span className="feature-cta">Bắt đầu quét →</span>
          </button>
        </div>
      </section>

      {/* Quy trình */}
      <section className="home-steps">
        <div className="home-section-head">
          <h3 className="home-section-title">Hoạt động thế nào?</h3>
          <p className="home-section-sub">Ba bước đơn giản từ thẻ đến dữ liệu.</p>
        </div>
        <div className="home-steps-grid">
          <div className="step-card">
            <span className="step-num">1</span>
            <h4>Đưa thẻ vào camera</h4>
            <p>Hệ thống tự động phát hiện và căn chỉnh thẻ trong khung hình.</p>
          </div>
          <div className="step-card">
            <span className="step-num">2</span>
            <h4>Quét QR hoặc OCR</h4>
            <p>Giải mã QR hoặc nhận dạng văn bản, trích xuất thông tin sinh viên.</p>
          </div>
          <div className="step-card">
            <span className="step-num">3</span>
            <h4>Đối chiếu &amp; lưu</h4>
            <p>So khớp với cơ sở dữ liệu và lưu toàn bộ phiên vào lịch sử.</p>
          </div>
        </div>
      </section>

      <footer className="home-footer">
        <span className="brand-mark home-footer-mark" />
        <p>TADIZB Scanner — Đồ án tốt nghiệp · Đại học Bách khoa Hà Nội</p>
      </footer>
    </div>
  );
}
