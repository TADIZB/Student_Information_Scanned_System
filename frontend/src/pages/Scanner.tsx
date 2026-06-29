import React, { ChangeEvent, useCallback, useEffect, useRef, useState } from "react";
import Webcam from "react-webcam";
import jsQR from "jsqr";
import {
  API_BASE,
  getScanDetail,
  getScanHistory,
  FaceMatch,
  lookupStudent,
  LookupResult,
  OcrEngine,
  processScan,
  ScanDetail,
  ScanRecord,
  ScanResult,
  ScanStep,
  StudentInfo,
} from "../api";

interface Props {
  onScanSuccess: (result: ScanResult) => void;
  scanMode: "qr" | "ocr";
  isLoggedIn: boolean;
  // Chỉ tài khoản trường (@sis.hust.edu.vn hoặc @hust.edu.vn) mới được gửi thông báo qua Teams/Outlook.
  isHustAccount?: boolean;
  onLoginClick?: () => void;
}

interface QrAnalysis {
  data: string | null;
  cropBlob?: Blob;
  cropDataUrl?: string;
}

const renderMssvStyled = (mssv: string | null) => {
  if (!mssv) return <span>—</span>;
  const year = mssv.slice(0, 4);
  const rest = mssv.slice(4);
  return (
    <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontWeight: 600, letterSpacing: "0.04em" }}>
      <span style={{ color: "#dc2626" }}>{year}</span>
      <span style={{ color: "#12141f" }}>{rest}</span>
    </span>
  );
};

// Trích URL đầu tiên từ chuỗi QR (nếu có). Trả về { match, href }: match là chuỗi xuất hiện
// trong raw (để highlight đúng vị trí), href là URL có scheme (để mở/hiển thị link).
const extractUrl = (raw: string | null | undefined): { match: string; href: string } | null => {
  if (!raw) return null;
  const httpMatch = raw.match(/https?:\/\/[^\s"'<>]+/i);
  if (httpMatch) return { match: httpMatch[0], href: httpMatch[0] };
  const wwwMatch = raw.match(/www\.[^\s"'<>]+/i);
  if (wwwMatch) return { match: wwwMatch[0], href: `https://${wwwMatch[0]}` };
  return null;
};

const renderQrData = (raw: string) => {
  const url = extractUrl(raw);
  if (!url) return <pre className="raw-pre">{raw}</pre>;
  const idx = raw.indexOf(url.match);
  const before = raw.slice(0, idx);
  const after = raw.slice(idx + url.match.length);
  return (
    <pre className="raw-pre">
      {before}
      <a href={url.href} target="_blank" rel="noopener" className="qr-link">
        {url.match}
      </a>
      {after}
    </pre>
  );
};

const blobToDataUrl = (blob: Blob): Promise<string> =>
  new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });

const STEP_COLOR: Record<string, string> = {
  pending: "#9ca3af",
  success: "#22c55e",
  warning: "#f59e0b",
  fail: "#ef4444",
};

// Nội dung tin nhắn mặc định khi gửi cho sinh viên (Teams/email, người dùng có thể sửa).
const DEFAULT_MSG =
  "Chào bạn, đây là thông báo từ phòng CTSV liên quan đến thẻ sinh viên của bạn.";

export default function Scanner({ onScanSuccess, scanMode, isLoggedIn, isHustAccount = false, onLoginClick }: Props) {
  const webcamRef = useRef<Webcam>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const intervalRef = useRef<number | null>(null);
  const busyRef = useRef(false);
  const resultRef = useRef<HTMLDivElement>(null);
  const stepsRef = useRef<HTMLDivElement>(null);
  const zxingReaderRef = useRef<any>(null);

  // Link phát hiện từ QR mới nhất, hiển thị overlay trên camera
  const [qrOverlayUrl, setQrOverlayUrl] = useState<string | null>(null);

  // Danh sách camera + thiết bị đang chọn
  const [cameras, setCameras] = useState<MediaDeviceInfo[]>([]);
  const [deviceId, setDeviceId] = useState<string | undefined>(undefined);

  const refreshCameras = useCallback(async () => {
    if (!navigator.mediaDevices?.enumerateDevices) return;
    try {
      const all = await navigator.mediaDevices.enumerateDevices();
      const cams = all.filter((d) => d.kind === "videoinput");
      setCameras(cams);
      setDeviceId((cur) =>
        cur && cams.some((c) => c.deviceId === cur)
          ? cur
          : cams[0]?.deviceId
      );
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    refreshCameras();
    const md = navigator.mediaDevices;
    if (!md?.addEventListener) return;
    md.addEventListener("devicechange", refreshCameras);
    return () => md.removeEventListener("devicechange", refreshCameras);
  }, [refreshCameras]);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [ocrEngine, setOcrEngine] = useState<OcrEngine>("tesseract");
  const [lastResult, setLastResult] = useState<ScanResult | null>(null);
  const [analyzingPreview, setAnalyzingPreview] = useState<string | null>(null);

  // Nội dung soạn để gửi cho sinh viên vừa quét (dùng chung cho Teams & email).
  const [msgContent, setMsgContent] = useState(DEFAULT_MSG);

  const [manualMssv, setManualMssv] = useState("");
  const [lookupResult, setLookupResult] = useState<LookupResult | null>(null);
  const [lookupError, setLookupError] = useState("");
  const [lookupBusy, setLookupBusy] = useState(false);

  const [visibleSteps, setVisibleSteps] = useState<(ScanStep & { visible: boolean })[]>([]);

  const [records, setRecords] = useState<ScanRecord[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [selected, setSelected] = useState<ScanDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [showDetailImage, setShowDetailImage] = useState(false);

  const loadHistory = useCallback(() => {
    if (!isLoggedIn) {
      setLoadingHistory(false);
      setRecords([]);
      return;
    }
    setLoadingHistory(true);
    getScanHistory()
      .then((r) => setRecords(r.filter((x) =>
        x.scan_type === scanMode || (scanMode === "qr" && x.scan_type === "lookup")
      )))
      .catch(() => { })
      .finally(() => setLoadingHistory(false));
  }, [scanMode, isLoggedIn]);

  useEffect(() => { loadHistory(); }, [loadHistory]);

  // ── Reset state khi đổi tab ───────────────────────────────────────────────
  useEffect(() => {
    setLastResult(null);
    setError("");
    setVisibleSteps([]);
    setLookupResult(null);
    setLookupError("");
    setManualMssv("");
    setAnalyzingPreview(null);
    setQrOverlayUrl(null);
    setMsgContent(DEFAULT_MSG);
  }, [scanMode]);

  const openDetail = async (id: string) => {
    setLoadingDetail(true);
    setShowDetailImage(false);
    try { setSelected(await getScanDetail(id)); }
    catch { /* ignore */ }
    finally { setLoadingDetail(false); }
  };

  const getImageUrl = (imageUrl: string | null) => {
    if (!imageUrl) return null;
    if (imageUrl.startsWith("data:")) return imageUrl;
    return `${API_BASE}${imageUrl}`;
  };

  // Mở Teams (app/web) tới khung chat với sinh viên, điền sẵn nội dung.
  // Teams cần email/UPN hợp lệ (không nhận MSSV trơn) nên đòi student_info.email.
  const sendTeamsChat = (info: StudentInfo) => {
    if (!isHustAccount || !info.email || !msgContent.trim()) return;
    const message = encodeURIComponent(`${msgContent.trim()} (MSSV ${info.student_id ?? ""})`.trim());
    const users = encodeURIComponent(info.email);
    window.open(
      `https://teams.microsoft.com/l/chat/0/0?users=${users}&message=${message}`,
      "_blank",
      "noopener,noreferrer",
    );
  };

  // Mở trình email mặc định (mailto) với người nhận + tiêu đề + nội dung soạn sẵn.
  // Dùng thẻ <a> ẩn thay vì window.open để tránh để lại tab trắng trên Chrome.
  const sendEmail = (info: StudentInfo) => {
    if (!isHustAccount || !info.email || !msgContent.trim()) return;
    const subject = encodeURIComponent(`[HUST] Thông báo về thẻ sinh viên ${info.student_id ?? ""}`.trim());
    const greet = info.full_name || info.ho_va_ten || `bạn sinh viên có mã số ${info.student_id ?? ""}`;
    const body = encodeURIComponent(`Chào ${greet},\n\n${msgContent.trim()}\n\nTrân trọng.`);
    const a = document.createElement("a");
    a.href = `mailto:${info.email}?subject=${subject}&body=${body}`;
    a.click();
  };

  // Khối soạn + 2 nút gửi (Teams/email). Chỉ render khi sinh viên có email.
  // Chỉ tài khoản trường mới được gửi — tài khoản thường bị chặn.
  const renderMessageActions = (info: StudentInfo) => {
    if (!info.email) return null;
    return (
      <div className="raw-section teams-send">
        <p className="raw-label">Gửi tin nhắn cho sinh viên</p>
        <p className="teams-send-to">
          Người nhận: <strong>{info.email}</strong>
        </p>
        {!isHustAccount && (
          <p className="teams-locked-note">
            🔒 Cần đăng nhập bằng <strong>tài khoản trường (@sis.hust.edu.vn hoặc @hust.edu.vn)</strong> để
            gửi thông báo qua Teams/Outlook.
          </p>
        )}
        <textarea
          className="teams-msg"
          value={msgContent}
          onChange={(e) => setMsgContent(e.target.value)}
          rows={3}
          placeholder="Nội dung tin nhắn gửi tới sinh viên..."
          disabled={!isHustAccount}
        />
        <div className="teams-actions">
          <button
            type="button"
            className="teams-btn"
            disabled={!isHustAccount || !msgContent.trim()}
            title={!isHustAccount ? "Chỉ dùng được với tài khoản trường (@sis.hust.edu.vn hoặc @hust.edu.vn)" : undefined}
            onClick={() => sendTeamsChat(info)}
          >
            💬 Gửi qua Teams
          </button>
          <button
            type="button"
            className="teams-btn email-btn"
            disabled={!isHustAccount || !msgContent.trim()}
            title={!isHustAccount ? "Chỉ dùng được với tài khoản trường (@sis.hust.edu.vn hoặc @hust.edu.vn)" : undefined}
            onClick={() => sendEmail(info)}
          >
            ✉️ Gửi email
          </button>
        </div>
      </div>
    );
  };

  // Animate OCR steps 
  const animateSteps = (steps: ScanStep[]) => {
    // Khởi tạo tất cả là pending (giữ image_url + description sẵn để fade-in)
    const init = steps.map((s) => ({ ...s, status: "pending" as const, visible: false }));
    setVisibleSteps(init);
    steps.forEach((step, i) => {
      setTimeout(() => {
        setVisibleSteps((prev) =>
          prev.map((s, idx) =>
            idx === i ? { ...step, visible: true } : s
          )
        );
      }, (i + 1) * 700);
    });
  };

  // Decode QR client-side and crop/zoom around the detected QR region.
  const analyzeQrInDataUrl = useCallback((dataUrl: string): Promise<QrAnalysis> => {
    return new Promise((resolve) => {
      const img = new Image();
      img.onload = async () => {
        const MAX_W = 1200;
        const scale = img.width > MAX_W ? MAX_W / img.width : 1;
        const w = Math.round(img.width * scale);
        const h = Math.round(img.height * scale);
        const canvas = document.createElement("canvas");
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext("2d", { willReadFrequently: true });
        if (!ctx) return resolve({ data: null });
        ctx.drawImage(img, 0, 0, w, h);
        try {
          const imageData = ctx.getImageData(0, 0, w, h);
          const code = jsQR(imageData.data, imageData.width, imageData.height, {
            inversionAttempts: "attemptBoth",
          });
          if (!code?.data) {
            try {
              if (!zxingReaderRef.current) {
                const { BrowserQRCodeReader } = await import("@zxing/browser");
                zxingReaderRef.current = new BrowserQRCodeReader();
              }
              const result = await zxingReaderRef.current.decodeFromCanvas(canvas);
              const text = result?.getText?.() || String(result || "");
              return resolve({ data: text || null });
            } catch {
              return resolve({ data: null });
            }
          }

          const points = [
            code.location.topLeftCorner,
            code.location.topRightCorner,
            code.location.bottomRightCorner,
            code.location.bottomLeftCorner,
          ];
          const xs = points.map((p) => p.x / scale);
          const ys = points.map((p) => p.y / scale);
          const minX = Math.max(0, Math.min(...xs));
          const minY = Math.max(0, Math.min(...ys));
          const maxX = Math.min(img.width, Math.max(...xs));
          const maxY = Math.min(img.height, Math.max(...ys));
          const qrW = Math.max(1, maxX - minX);
          const qrH = Math.max(1, maxY - minY);
          const pad = Math.max(qrW, qrH) * 0.65;

          const cropX = Math.max(0, Math.floor(minX - pad));
          const cropY = Math.max(0, Math.floor(minY - pad));
          const cropW = Math.min(img.width - cropX, Math.ceil(qrW + pad * 2));
          const cropH = Math.min(img.height - cropY, Math.ceil(qrH + pad * 2));
          const targetLongest = 1000;
          const cropScale = Math.max(1, targetLongest / Math.max(cropW, cropH));

          const cropCanvas = document.createElement("canvas");
          cropCanvas.width = Math.round(cropW * cropScale);
          cropCanvas.height = Math.round(cropH * cropScale);
          const cropCtx = cropCanvas.getContext("2d");
          if (!cropCtx) return resolve({ data: code.data });
          cropCtx.imageSmoothingEnabled = true;
          cropCtx.imageSmoothingQuality = "high";
          cropCtx.drawImage(img, cropX, cropY, cropW, cropH, 0, 0, cropCanvas.width, cropCanvas.height);

          cropCanvas.toBlob(
            (cropBlob) => {
              resolve({
                data: code.data,
                cropBlob: cropBlob || undefined,
                cropDataUrl: cropCanvas.toDataURL("image/jpeg", 0.92),
              });
            },
            "image/jpeg",
            0.92,
          );
        } catch {
          resolve({ data: null });
        }
      };
      img.onerror = () => resolve({ data: null });
      img.src = dataUrl;
    });
  }, []);

  // Xử lý blob (dùng chung cho cả QR lẫn OCR) 
  const handleBlob = useCallback(
    async (blob: Blob, force = false, qrDataClient?: string | null) => {
      if (!force && busyRef.current) return;
      busyRef.current = true;
      setBusy(true);
      setError("");
      setVisibleSteps([]);
      if (scanMode === "qr") setQrOverlayUrl(null);
      // OCR: lưu snapshot để hiển thị thay cho cam trong lúc phân tích
      let previewObjectUrl: string | null = null;
      if (scanMode === "ocr" || (scanMode === "qr" && force)) {
        try {
          previewObjectUrl = URL.createObjectURL(blob);
          setAnalyzingPreview(previewObjectUrl);
        } catch { /* ignore */ }
      }
      try {
        let qrText = qrDataClient || null;
        let scanBlob = blob;
        if (scanMode === "qr" && !qrText) {
          const qrAnalysis = await analyzeQrInDataUrl(await blobToDataUrl(blob));
          qrText = qrAnalysis.data;
          if (qrAnalysis.cropBlob) {
            scanBlob = qrAnalysis.cropBlob;
          }
          if (qrAnalysis.cropDataUrl) {
            setAnalyzingPreview(qrAnalysis.cropDataUrl);
          }
          if (!qrText && !force) {
            setError("Khong doc duoc ma QR trong anh. Vui long chup hoac tai anh ro hon.");
            return;
          }
        }

        const result = await processScan(
          scanBlob,
          scanMode,
          scanMode === "ocr" ? ocrEngine : "tesseract",
          qrText,
        );

        // QR auto-scan: frame không có QR → bỏ qua, không cập nhật UI
        if (scanMode === "qr" && !result.qr_data) {
          setError("Backend da nhan anh nhung khong tra ve du lieu QR.");
          return;
        }

        setLastResult(result);

        if (scanMode === "ocr" && ocrEngine === "tesseract" && result.steps?.length) {
          animateSteps(result.steps);
          setTimeout(() => stepsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 0);
        } else {
          setTimeout(() => resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 0);
        }

        const recognized = scanMode === "qr" ? !!result.qr_data : result.match_result === 1;
        if (recognized) {
          if (scanMode === "qr") {
            stopAutoScan();
            const url = extractUrl(result.qr_data);
            setQrOverlayUrl(url ? url.href : null);
          }
          loadHistory();
          onScanSuccess(result);
        }
      } catch (err: any) {
        const detail = err?.response?.data?.detail;
        setError(detail || "Quét thất bại. Vui lòng thử lại hoặc điều chỉnh góc chụp.");
      } finally {
        busyRef.current = false;
        setBusy(false);
        setAnalyzingPreview(null);
        if (previewObjectUrl) URL.revokeObjectURL(previewObjectUrl);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [scanMode, ocrEngine, loadHistory, onScanSuccess, analyzeQrInDataUrl],
  );

  // Auto-scan (QR luôn bật khi mount) 
  const startAutoScan = useCallback(() => {
    if (intervalRef.current) return;
    intervalRef.current = window.setInterval(async () => {
      if (busyRef.current) return;
      const imageSrc = webcamRef.current?.getScreenshot();
      if (!imageSrc) return;
      // Chỉ gọi BE khi đã thấy QR trong frame
      const qrAnalysis = await analyzeQrInDataUrl(imageSrc);
      if (!qrAnalysis.data) return;
      if (intervalRef.current) { clearInterval(intervalRef.current); intervalRef.current = null; }
      const blob = qrAnalysis.cropBlob || await (await fetch(imageSrc)).blob();
      handleBlob(blob, false, qrAnalysis.data);
    }, 400);
  }, [analyzeQrInDataUrl, handleBlob]);

  const stopAutoScan = useCallback(() => {
    if (intervalRef.current) { clearInterval(intervalRef.current); intervalRef.current = null; }
  }, []);

  // QR: tự bật auto-scan khi mount
  useEffect(() => {
    if (scanMode === "qr") startAutoScan();
    return () => stopAutoScan();
  }, [scanMode, startAutoScan, stopAutoScan]);

  // Upload file 
  const handleFileUpload = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      if (scanMode === "qr") stopAutoScan();
      handleBlob(file, true); // force=true để bỏ qua busy check
      e.target.value = "";
    },
    [handleBlob, scanMode, stopAutoScan],
  );

  //OCR: chụp thủ công 
  const handleCapture = useCallback(() => {
    const imageSrc = webcamRef.current?.getScreenshot();
    if (!imageSrc) return;
    fetch(imageSrc).then((r) => r.blob()).then(handleBlob);
  }, [handleBlob]);

  const handleManualLookup = async () => {
    if (!manualMssv.trim()) return;
    setLookupBusy(true);
    setLookupError("");
    setLookupResult(null);
    try {
      const info = await lookupStudent(manualMssv.trim());
      setLookupResult(info);
      if (info.scan_id) loadHistory();
    } catch (err: any) {
      setLookupError(err?.response?.data?.detail || "Không tìm thấy sinh viên.");
    } finally {
      setLookupBusy(false);
    }
  };

  const renderStatus = (s?: number | null): React.ReactNode => {
    if (s === 1) return <strong style={{ color: "#16a34a" }}>Đang học</strong>;
    if (s === 0) return <strong style={{ color: "#dc2626" }}>Nghỉ học</strong>;
    return "—";
  };

  // Render thông tin sinh viên / CCCD 
  const renderStudentInfo = (info: StudentInfo) => {
    // Có dữ liệu CCCD bóc được? (chỉ ở chế độ OCR)
    const hasCccd = !!(info.so_cccd || info.dia_chi || info.ho_va_ten);
    let rows: [string, React.ReactNode][];
    if (hasCccd) {
      rows = [
        ["Họ và tên", info.ho_va_ten || info.full_name || "—"],
        ["Số CCCD", info.so_cccd || "—"],
        ["Ngày sinh", info.ngay_sinh || info.birth_date || "—"],
        ["Địa chỉ", info.dia_chi || "—"],
        ["Trường, Viện", info.school || "—"],
        ["Email", info.email || "—"],
        ["MSSV", renderMssvStyled(info.student_id)],
      ];
    } else {
      rows = [
        ["Họ tên", info.full_name || "—"],
        ["Ngày sinh", info.birth_date || "—"],
        ["MSSV", renderMssvStyled(info.student_id)],
        ["Email liên lạc", info.email || "—"],
        ["Trường, Viện", info.school || "—"],
        ["Trạng thái", renderStatus(info.study_status)],
      ];
    }
    return (
      <div className="student-info">
        {info.avatar_url && (
          <img src={getImageUrl(info.avatar_url) ?? undefined} alt="Ảnh đại diện" className="student-avatar" />
        )}
        {rows.map(([label, value]) => (
          <div className="info-row" key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>
    );
  };

  const FACE_MATCH_META: Record<FaceMatch["ket_qua"], { label: string; color: string; icon: string }> = {
    khop: { label: "Cùng một người", color: "#16a34a", icon: "✓" },
    khong_khop: { label: "Khác người", color: "#dc2626", icon: "✗" },
    khong_chac: { label: "Không chắc chắn", color: "#d97706", icon: "?" },
    loi: { label: "Lỗi so khớp", color: "#6b7280", icon: "!" },
  };
  const renderFaceMatch = (fm: FaceMatch) => {
    const meta = FACE_MATCH_META[fm.ket_qua] ?? FACE_MATCH_META.khong_chac;
    return (
      <div className="face-match" style={{ borderLeftColor: meta.color }}>
        <div className="face-match-head">
          <span className="face-match-icon" style={{ background: meta.color }}>{meta.icon}</span>
          <span className="face-match-label" style={{ color: meta.color }}>
            So khớp khuôn mặt: {meta.label}
          </span>
          {fm.ket_qua !== "loi" && (
            <span className="face-match-conf">độ tin cậy {fm.do_tin_cay}%</span>
          )}
        </div>
        {fm.nhan_xet && <p className="face-match-note">{fm.nhan_xet}</p>}
      </div>
    );
  };

  return (
    <div className="scanner-page">

      {/* ── Header chế độ quét ─────────────────────────────────────────────── */}
      <div className="scanner-head">
        <span className={`scanner-mode-chip ${scanMode}`}>
          <span className="scanner-mode-dot" />
          {scanMode === "qr" ? "Chế độ QR" : "Chế độ OCR"}
        </span>
        <h2 className="scanner-head-title">
          {scanMode === "qr" ? "Quét mã QR thẻ sinh viên" : "Nhận dạng văn bản (OCR)"}
        </h2>
        <p className="scanner-head-sub">
          {scanMode === "qr"
            ? "Đưa mã QR trên thẻ vào khung — hệ thống tự động phát hiện và đối chiếu."
            : ocrEngine === "gemini"
              ? "Đưa CCCD vào khung rồi chụp — AI bóc tách thông tin."
              : "Đưa CCCD vào khung rồi chụp — pipeline trích xuất thông tin."}
        </p>

        {/* Chọn engine xử lý (chỉ OCR) */}
        {scanMode === "ocr" && (
          <div className="engine-toggle" role="tablist" aria-label="Chọn engine OCR">
            <button
              type="button"
              role="tab"
              aria-selected={ocrEngine === "tesseract"}
              className={`engine-tab${ocrEngine === "tesseract" ? " active" : ""}`}
              onClick={() => setOcrEngine("tesseract")}
              disabled={busy}
            >
              Tesseract
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={ocrEngine === "gemini"}
              className={`engine-tab${ocrEngine === "gemini" ? " active gemini" : ""}`}
              onClick={() => setOcrEngine("gemini")}
              disabled={busy}
            >
              ✦ AI
            </button>
          </div>
        )}
      </div>

      {/* ── Khung camera ───────────────────────────────────────────────────── */}
      <div className="webcam-wrapper">
        {busy && analyzingPreview ? (
          analyzingPreview ? (
            <img src={analyzingPreview} alt="Đang phân tích" className="webcam-video" />
          ) : (
            <div className="webcam-video" />
          )
        ) : (
          <Webcam
            ref={webcamRef}
            audio={false}
            screenshotFormat="image/jpeg"
            screenshotQuality={1}
            videoConstraints={
              deviceId
                ? {
                  deviceId: { exact: deviceId },
                  width: { ideal: 1920 },
                  height: { ideal: 1080 },
                  aspectRatio: { ideal: 16 / 9 },
                  frameRate: { ideal: 30, max: 30 },
                }
                : {
                  facingMode: { ideal: "environment" },
                  width: { ideal: 1920 },
                  height: { ideal: 1080 },
                  aspectRatio: { ideal: 16 / 9 },
                  frameRate: { ideal: 30, max: 30 },
                }
            }
            className="webcam-video"
            onUserMedia={refreshCameras}
            onUserMediaError={() => setError("Không thể mở camera. Hãy cấp quyền truy cập.")}
          />
        )}

        {/* Dropdown chọn camera — góc dưới phải */}
        {cameras.length > 0 && !analyzingPreview && (
          <div className="cam-select-wrap" title="Chọn camera">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
              <circle cx="12" cy="13" r="4" />
            </svg>
            <select
              className="cam-select"
              value={deviceId || ""}
              onChange={(e) => setDeviceId(e.target.value || undefined)}
              aria-label="Chọn camera"
            >
              {cameras.map((cam, i) => (
                <option key={cam.deviceId} value={cam.deviceId}>
                  {cam.label || `Camera ${i + 1}`}
                </option>
              ))}
            </select>
          </div>
        )}
        <div className="card-guide">
          <span className="guide-corner tl" /><span className="guide-corner tr" />
          <span className="guide-corner bl" /><span className="guide-corner br" />
          <span className="guide-label">
            {scanMode === "qr" ? "Đưa QR vào khung" : "Đưa CCCD vào khung"}
          </span>
        </div>
        {busy && analyzingPreview && (
          <div className="scan-overlay">
            <span className="scan-spinner" />
            Đang xử lý...
          </div>
        )}
        {scanMode === "qr" && !qrOverlayUrl && !analyzingPreview && <div className="qr-laser" />}
        {scanMode === "qr" && !busy && !qrOverlayUrl && <div className="auto-badge">AUTO</div>}

        {/* Overlay hiển thị link QR vừa quét được */}
        {scanMode === "qr" && qrOverlayUrl && (
          <div className="qr-cam-overlay">
            <div className="qr-cam-overlay-title">Đã quét được QR</div>
            <a
              href={qrOverlayUrl}
              target="_blank"
              rel="noopener"
              className="qr-cam-overlay-link"
              title={qrOverlayUrl}
            >
              {qrOverlayUrl}
            </a>
            <div className="qr-cam-overlay-actions">
              <a
                href={qrOverlayUrl}
                target="_blank"
                rel="noopener"
                className="qr-cam-btn primary"
              >
                Mở link
              </a>
              <button
                type="button"
                className="qr-cam-btn"
                onClick={() => { setQrOverlayUrl(null); startAutoScan(); }}
              >
                Quét tiếp
              </button>
            </div>
          </div>
        )}
      </div>

      {error && <div className="banner error">{error}</div>}

      {/* ── Điều khiển theo mode  */}
      <div className="scanner-controls">
        {scanMode === "ocr" && (
          <button className="secondary" disabled={busy} onClick={handleCapture}>
            Chụp thủ công
          </button>
        )}
        <input ref={fileInputRef} type="file" accept="image/*" capture="environment" onChange={handleFileUpload} style={{ display: "none" }} />
        <button className="ghost" onClick={() => fileInputRef.current?.click()}>
          Tải ảnh lên
        </button>
      </div>

      {/* ── Nhập MSSV thủ công */}
      {scanMode === "qr" && (
        <div className="manual-lookup">
          <p className="manual-lookup-label">Tra cứu theo MSSV</p>
          <div className="manual-lookup-row">
            <div className="mssv-input-wrapper">
              {/* Lớp hiển thị màu bên dưới */}
              <div className="mssv-input-display" aria-hidden="true">
                {manualMssv ? (
                  <>
                    <span style={{ color: "#dc2626" }}>{manualMssv.slice(0, 4)}</span>
                    <span style={{ color: "#12141f" }}>{manualMssv.slice(4)}</span>
                  </>
                ) : null}
              </div>
              {/* Input trong suốt bên trên để nhận focus/typing */}
              <input
                type="text"
                className="mssv-input mssv-input-ghost"
                placeholder="Nhập mã số sinh viên..."
                value={manualMssv}
                onChange={(e) => setManualMssv(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleManualLookup()}
              />
            </div>
            <button className="primary" disabled={lookupBusy || !manualMssv.trim()} onClick={handleManualLookup}>
              {lookupBusy ? "Đang tìm..." : "Tra cứu"}
            </button>
          </div>
          {lookupError && <p className="lookup-error">{lookupError}</p>}
          {lookupResult && (
            <div className="scan-result-card" style={{ marginTop: 12 }}>
              <div className="scan-result-header">
                <span className="badge qr">TRA CỨU</span>
              </div>
              {renderStudentInfo(lookupResult)}
              {renderMessageActions(lookupResult)}
            </div>
          )}
        </div>
      )}

      {/*Steps xử lý OCR*/}
      {scanMode === "ocr" && visibleSteps.length > 0 && (
        <div className="ocr-steps" ref={stepsRef}>
          <p className="ocr-steps-title">Quá trình xử lý từng bước</p>
          {visibleSteps.map((step, i) => {
            const color = step.visible ? STEP_COLOR[step.status] : STEP_COLOR.pending;
            return (
              <div
                key={i}
                className={`ocr-step-card${step.visible ? " visible" : ""}`}
                style={{ borderLeftColor: color }}
              >
                <div className="ocr-step-header">
                  <span className="step-dot" style={{ background: color }} />
                  <span className="step-name" style={{ color }}>{step.name}</span>
                  {step.visible && (
                    <span className="step-badge" style={{ background: color }}>
                      {step.status === "success" ? "✓" : step.status === "warning" ? "!" : step.status === "fail" ? "✗" : "…"}
                    </span>
                  )}
                </div>
                {step.visible && step.description && (
                  <p className="ocr-step-desc">{step.description}</p>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/*Kết quả quét gần nhất*/}
      {scanMode === "ocr" && lastResult && (
        <div className="scan-result-card" ref={resultRef}>
          <div className="scan-result-header">
            <span className="badge ocr">OCR</span>
            {lastResult.match_result !== null && (
              <span className={`match-badge ${lastResult.match_result === 1 ? "match-ok" : "match-fail"}`}>
                {lastResult.match_result === 1 ? "Khop" : "Khong khop"}
              </span>
            )}
            <span className="scan-result-id">#{lastResult.scan_id.slice(0, 8)}</span>
          </div>
          <div className="scan-result-body">
            {lastResult.warped_image_url && (
              <img
                src={lastResult.warped_image_url}
                alt="Anh da xu ly"
                className="warped-thumb"
              />
            )}
            {lastResult.student_info && renderStudentInfo(lastResult.student_info)}
          </div>
          <div className="raw-section">
            <p className="raw-label">KET QUA PHAN TICH OCR</p>
            <pre className="raw-pre">{lastResult.raw_text || "Khong doc duoc van ban nao."}</pre>
          </div>
          <div className="raw-section">
            <p className="raw-label">Ket qua doi chieu</p>
            <div className="student-info">
              <div className="info-row">
                <span>Trang thai</span>
                <strong>{lastResult.match_result === 1 ? "Khop sinh vien" : "Khong khop sinh vien"}</strong>
              </div>
              <div className="info-row">
                <span>Ho ten OCR</span>
                <strong>{lastResult.extracted_info?.ho_va_ten || lastResult.student_info?.ho_va_ten || "Khong doc duoc"}</strong>
              </div>
              <div className="info-row">
                <span>So CCCD</span>
                <strong>{lastResult.extracted_info?.so_cccd || lastResult.student_info?.so_cccd || "Khong doc duoc"}</strong>
              </div>
              <div className="info-row">
                <span>Ngay sinh</span>
                <strong>{lastResult.extracted_info?.ngay_sinh || lastResult.student_info?.ngay_sinh || "Khong doc duoc"}</strong>
              </div>
              <div className="info-row">
                <span>MSSV doi chieu</span>
                <strong>{lastResult.student_info?.student_id || "Khong co"}</strong>
              </div>
            </div>
          </div>
        </div>
      )}

      {lastResult && !(scanMode === "ocr" && lastResult.scan_type === "ocr") && (
        <div className="scan-result-card" ref={resultRef}>
          <div className="scan-result-header">
            <span className={`badge ${lastResult.scan_type}`}>
              {lastResult.scan_type.toUpperCase()}
            </span>
            {lastResult.match_result !== null && (
              <span className={`match-badge ${lastResult.match_result === 1 ? "match-ok" : "match-fail"}`}>
                {lastResult.match_result === 1 ? "Khớp ✓" : "Không khớp ✗"}
              </span>
            )}
            <span className="scan-result-id">#{lastResult.scan_id.slice(0, 8)}</span>
          </div>
          <div className="scan-result-body">
            {lastResult.warped_image_url && (
              <img
                src={lastResult.warped_image_url}
                alt="Ảnh đã căn chỉnh"
                className="warped-thumb"
              />
            )}
            {lastResult.student_info && renderStudentInfo(lastResult.student_info)}
          </div>
          {(lastResult.scan_type === "qr" || lastResult.match_result === 1) &&
            lastResult.student_info &&
            renderMessageActions(lastResult.student_info)}
          {lastResult.face_match && renderFaceMatch(lastResult.face_match)}
          {lastResult.scan_type === "ocr" && (
            <div className="raw-section">
              <p className="raw-label">Ket qua cuoi cung</p>
              <div className="student-info">
                <div className="info-row">
                  <span>Trang thai</span>
                  <strong>{lastResult.match_result === 1 ? "Khop sinh vien" : "Khong khop sinh vien"}</strong>
                </div>
                <div className="info-row">
                  <span>Ho ten OCR</span>
                  <strong>{lastResult.extracted_info?.ho_va_ten || lastResult.student_info?.ho_va_ten || "Khong doc duoc"}</strong>
                </div>
                <div className="info-row">
                  <span>So CCCD</span>
                  <strong>{lastResult.extracted_info?.so_cccd || lastResult.student_info?.so_cccd || "Khong doc duoc"}</strong>
                </div>
                <div className="info-row">
                  <span>Ngay sinh</span>
                  <strong>{lastResult.extracted_info?.ngay_sinh || lastResult.student_info?.ngay_sinh || "Khong doc duoc"}</strong>
                </div>
                <div className="info-row">
                  <span>MSSV doi chieu</span>
                  <strong>{lastResult.student_info?.student_id || "Khong co"}</strong>
                </div>
              </div>
            </div>
          )}
          {lastResult.qr_data && (
            <div className="raw-section">
              <p className="raw-label">QR Raw Data</p>
              {renderQrData(lastResult.qr_data)}
            </div>
          )}
          {lastResult.scan_type === "ocr" && lastResult.raw_text && (
            <div className="raw-section">
              <p className="raw-label">Kết quả phân tích OCR</p>
              <p className="raw-label" style={{ marginTop: 10 }}>Văn bản OCR thô</p>
              <pre className="raw-pre">{lastResult.raw_text}</pre>
            </div>
          )}
        </div>
      )}

      {/*Lịch sử quét*/}
      {!isLoggedIn && (
        <p className="hint" style={{ marginTop: 24 }}>
          <button className="ghost" style={{ padding: "4px 12px", fontSize: 13, marginRight: 6 }} onClick={onLoginClick}>
            Đăng nhập
          </button>
          để lưu và xem lại lịch sử quét.
        </p>
      )}

      <div className={`history-section${!isLoggedIn ? " hidden" : ""}`}>
        <h3 className="history-section-title">Lịch sử quét</h3>
        {loadingHistory ? (
          <p className="hint">Đang tải...</p>
        ) : records.length === 0 ? (
          <p className="hint">Chưa có bản ghi nào.</p>
        ) : (
          <div className="table-wrapper">
            <table className="history-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Loại</th>
                  <th>Kết quả</th>
                  <th>Thời gian</th>
                </tr>
              </thead>
              <tbody>
                {records.map((r, i) => (
                  <tr key={r.id} className="history-row" onClick={() => openDetail(r.id)}>
                    <td className="row-num">{i + 1}</td>
                    <td><span className={`badge ${r.scan_type}`}>{r.scan_type?.toUpperCase()}</span></td>
                    <td>
                      {r.scan_type === "lookup"
                        ? <span className="match-badge match-ok">Tìm thấy</span>
                        : r.match_result !== null && (
                          <span className={`match-badge ${r.match_result === 1 ? "match-ok" : "match-fail"}`}>
                            {r.match_result === 1 ? "Khớp" : "Không khớp"}
                          </span>
                        )
                      }
                    </td>
                    <td className="row-time">{new Date(r.created_at).toLocaleString("vi-VN")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/*Modal chi tiết*/}
      {(selected || loadingDetail) && (
        <div className="modal-overlay" onClick={() => setSelected(null)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <button className="modal-close" onClick={() => setSelected(null)}>✕</button>
            {loadingDetail ? (
              <p className="hint">Đang tải chi tiết...</p>
            ) : selected ? (
              <>
                <div className="modal-header">
                  <h3>Chi tiết bản ghi</h3>
                  <div className="modal-meta">
                    <span className={`badge ${selected.scan_type}`}>{selected.scan_type?.toUpperCase()}</span>
                    {selected.match_result !== null && (
                      <span className={`match-badge ${selected.match_result === 1 ? "match-ok" : "match-fail"}`}>
                        {selected.match_result === 1 ? "Khớp ✓" : "Không khớp ✗"}
                      </span>
                    )}
                    <span className="row-time">{new Date(selected.created_at).toLocaleString("vi-VN")}</span>
                  </div>
                </div>
                {selected.image_url && !showDetailImage && (
                  <button className="ghost" type="button" onClick={() => setShowDetailImage(true)}>
                    Xem anh da quet
                  </button>
                )}
                {selected.image_url && showDetailImage && (
                  <img src={getImageUrl(selected.image_url) ?? undefined} alt="Anh da quet" className="modal-image" loading="lazy" />
                )}
                {selected.student_info
                  ? renderStudentInfo(selected.student_info)
                  : <p className="hint">Không trích xuất được thông tin sinh viên.</p>
                }
                {selected.qr_data && (
                  <div className="raw-section">
                    <p className="raw-label">QR Raw Data</p>
                    {renderQrData(selected.qr_data)}
                  </div>
                )}
                {selected.scan_type === "ocr" && selected.raw_text && (
                  <div className="raw-section">
                    <p className="raw-label">Kết quả phân tích OCR</p>
                    <pre className="raw-pre">{selected.raw_text}</pre>
                  </div>
                )}
              </>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}
