import React from "react";

interface Props {
  children: React.ReactNode;
}

interface State {
  hasError: boolean;
  message: string;
}

/**
 * Bắt lỗi render React không lường trước được — hiển thị fallback UI tiếng Việt
 * thay vì màn trắng. Chỉ catch lỗi RENDER (không catch lỗi async/event handler).
 */
export default class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, message: "" };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, message: error.message || "Lỗi không xác định" };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    // Log ra console để dev/QA debug; production có thể đẩy sang Sentry/Datadog
    console.error("ErrorBoundary đã bắt lỗi:", error, info);
  }

  handleReload = () => {
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="full-center" style={{ flexDirection: "column", padding: 24, textAlign: "center" }}>
          <h2 style={{ marginBottom: 8 }}>Đã xảy ra lỗi</h2>
          <p style={{ marginBottom: 16, color: "#6b7280", maxWidth: 480 }}>
            Ứng dụng gặp sự cố không mong muốn. Hãy thử tải lại trang. Nếu lỗi
            vẫn xuất hiện, vui lòng liên hệ quản trị viên.
          </p>
          {this.state.message && (
            <pre style={{
              background: "#1f2937", color: "#f3f4f6", padding: 12, borderRadius: 6,
              maxWidth: 600, overflow: "auto", fontSize: 12, marginBottom: 16,
            }}>
              {this.state.message}
            </pre>
          )}
          <button className="primary" onClick={this.handleReload}>
            Tải lại trang
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
