import React, { ChangeEvent, useCallback, useEffect, useRef, useState } from "react";
import Webcam from "react-webcam";
import {
  API_BASE,
  getExportCardUrl,
  getScanDetail,
  getScanHistory,
  lookupStudent,
  LookupResult,
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
  onLoginClick?: () => void;
}

// Hiển thị MSSV: 4 số đầu (năm) màu đỏ, phần còn lại màu đen
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

// Màu hiển thị theo trạng thái từng bước OCR
const STEP_COLOR: Record<string, string> = {
  pending: "#9ca3af",   // xám
  success: "#22c55e",   // xanh lá
  warning: "#f59e0b",   // vàng (warp không tìm được biên nhưng vẫn tiếp tục)
  fail: "#ef4444",   // đỏ
};

export default function Scanner({ onScanSuccess, scanMode, isLoggedIn, onLoginClick }: Props) {
  const webcamRef = useRef<Webcam>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const intervalRef = useRef<number | null>(null);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [lastResult, setLastResult] = useState<ScanResult | null>(null);

  // ── MSSV nhập tay (chỉ QR) ────────────────────────────────────────────────
  const [manualMssv, setManualMssv] = useState("");
  const [lookupResult, setLookupResult] = useState<LookupResult | null>(null);
  const [lookupError, setLookupError] = useState("");
  const [lookupBusy, setLookupBusy] = useState(false);

  // ── Steps animation (chỉ OCR) ─────────────────────────────────────────────
  const [visibleSteps, setVisibleSteps] = useState<(ScanStep & { visible: boolean })[]>([]);

  // ── Lịch sử ───────────────────────────────────────────────────────────────
  const [records, setRecords] = useState<ScanRecord[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [selected, setSelected] = useState<ScanDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  const loadHistory = useCallback(() => {
    if (!isLoggedIn) return;
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
  }, [scanMode]);

  const openDetail = async (id: string) => {
    setLoadingDetail(true);
    try { setSelected(await getScanDetail(id)); }
    catch { /* ignore */ }
    finally { setLoadingDetail(false); }
  };

  const getImageUrl = (imageUrl: string | null) => {
    if (!imageUrl) return null;
    if (imageUrl.startsWith("data:")) return imageUrl;
    return `${API_BASE}${imageUrl}`;
  };

  // ── Animate OCR steps ─────────────────────────────────────────────────────
  const animateSteps = (steps: ScanStep[]) => {
    // Khởi tạo tất cả là pending
    const init = steps.map((s) => ({ ...s, status: "pending" as const, visible: false }));
    setVisibleSteps(init);
    steps.forEach((step, i) => {
      setTimeout(() => {
        setVisibleSteps((prev) =>
          prev.map((s, idx) =>
            idx === i ? { ...step, visible: true } : s
          )
        );
      }, (i + 1) * 500);
    });
  };

  // ── Xử lý blob (dùng chung cho cả QR lẫn OCR) ───────────────────────────
  const handleBlob = useCallback(
    async (blob: Blob, force = false) => {
      if (!force && busy) return;
      setBusy(true);
      setError("");
      setVisibleSteps([]);
      try {
        const result = await processScan(blob, scanMode);

        // QR auto-scan: frame không có QR → bỏ qua, không cập nhật UI
        if (scanMode === "qr" && !result.qr_data) return;

        setLastResult(result);

        if (scanMode === "ocr" && result.steps?.length) {
          animateSteps(result.steps);
        }

        const recognized = scanMode === "qr" ? !!result.qr_data : result.match_result === 1;
        if (recognized) {
          if (scanMode === "qr") stopAutoScan();
          loadHistory();
          onScanSuccess(result);
        }
      } catch (err: any) {
        const detail = err?.response?.data?.detail;
        setError(detail || "Quét thất bại. Vui lòng thử lại hoặc điều chỉnh góc chụp.");
      } finally {
        setBusy(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [busy, scanMode, loadHistory, onScanSuccess],
  );

  // ── Auto-scan (QR luôn bật khi mount) ────────────────────────────────────
  const startAutoScan = useCallback(() => {
    if (intervalRef.current) return;
    intervalRef.current = window.setInterval(() => {
      const imageSrc = webcamRef.current?.getScreenshot();
      if (!imageSrc) return;
      fetch(imageSrc).then((r) => r.blob()).then((blob) => handleBlob(blob));
    }, 600);
  }, [handleBlob]);

  const stopAutoScan = useCallback(() => {
    if (intervalRef.current) { clearInterval(intervalRef.current); intervalRef.current = null; }
  }, []);

  // QR: tự bật auto-scan khi mount
  useEffect(() => {
    if (scanMode === "qr") startAutoScan();
    return () => stopAutoScan();
  }, [scanMode, startAutoScan, stopAutoScan]);

  // ── Upload file ───────────────────────────────────────────────────────────
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

  // ── OCR: chụp thủ công ────────────────────────────────────────────────────
  const handleCapture = useCallback(() => {
    const imageSrc = webcamRef.current?.getScreenshot();
    if (!imageSrc) return;
    fetch(imageSrc).then((r) => r.blob()).then(handleBlob);
  }, [handleBlob]);

  // ── MSSV nhập tay ─────────────────────────────────────────────────────────
  const handleManualLookup = async () => {
    if (!manualMssv.trim()) return;
    setLookupBusy(true);
    setLookupError("");
    setLookupResult(null);
    try {
      const info = await lookupStudent(manualMssv.trim());
      setLookupResult(info);
      if (info.scan_id) loadHistory();   // reload lịch sử nếu đã lưu được
    } catch (err: any) {
      setLookupError(err?.response?.data?.detail || "Không tìm thấy sinh viên.");
    } finally {
      setLookupBusy(false);
    }
  };

  // ── Render thông tin sinh viên ────────────────────────────────────────────
  const renderStudentInfo = (info: StudentInfo) => (
    <div className="student-info">
      {info.avatar_url && (
        <img src={getImageUrl(info.avatar_url) ?? undefined} alt="Ảnh đại diện" className="student-avatar" />
      )}
      {([
        ["Họ tên", info.full_name],
        ["Ngày sinh", info.birth_date],
        ["Trường, Viện", info.school],
        ["Email", info.email],
      ] as [string, string | null][]).map(([label, value]) => (
        <div className="info-row" key={label}>
          <span>{label}</span>
          <strong>{value || "—"}</strong>
        </div>
      ))}
      <div className="info-row" key="MSSV">
        <span>MSSV</span>
        <strong>{renderMssvStyled(info.student_id)}</strong>
      </div>
    </div>
  );

  return (
    <div className="scanner-page">

      {/* ── Khung camera ───────────────────────────────────────────────────── */}
      <div className="webcam-wrapper">
        <Webcam
          ref={webcamRef}
          audio={false}
          screenshotFormat="image/jpeg"
          screenshotQuality={0.92}
          videoConstraints={{ facingMode: "environment" }}
          className="webcam-video"
          onUserMediaError={() => setError("Không thể mở camera. Hãy cấp quyền truy cập.")}
        />
        <div className="card-guide">
          <span className="guide-corner tl" /><span className="guide-corner tr" />
          <span className="guide-corner bl" /><span className="guide-corner br" />
          <span className="guide-label">
            {scanMode === "qr" ? "Xin QR" : "Chụp nè"}
          </span>
        </div>
        {busy && scanMode === "ocr" && (
          <div className="scan-overlay">
            <span className="scan-spinner" />
            Đang xử lý...
          </div>
        )}
        {scanMode === "qr" && <div className="qr-laser" />}
        {scanMode === "qr" && !busy && <div className="auto-badge">AUTO</div>}
      </div>

      {error && <div className="banner error">{error}</div>}

      {/* ── Điều khiển theo mode ───────────────────────────────────────────── */}
      <div className="scanner-controls">
        {scanMode === "ocr" && (
          <button className="secondary" disabled={busy} onClick={handleCapture}>
            Chụp thủ công
          </button>
        )}
        <input ref={fileInputRef} type="file" accept="image/*" onChange={handleFileUpload} style={{ display: "none" }} />
        <button className="ghost" onClick={() => fileInputRef.current?.click()}>
          Tải ảnh lên
        </button>
      </div>

      {/* ── Nhập MSSV thủ công (chỉ QR) ───────────────────────────────────── */}
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
            </div>
          )}
        </div>
      )}

      {/* ── Steps xử lý OCR ────────────────────────────────────────────────── */}
      {scanMode === "ocr" && visibleSteps.length > 0 && (
        <div className="ocr-steps">
          <p className="ocr-steps-title">Quá trình xử lý</p>
          {visibleSteps.map((step, i) => (
            <div key={i} className="ocr-step">
              <span
                className="step-dot"
                style={{ background: step.visible ? STEP_COLOR[step.status] : STEP_COLOR.pending }}
              />
              <span
                className="step-name"
                style={{ color: step.visible ? STEP_COLOR[step.status] : STEP_COLOR.pending }}
              >
                {step.name}
              </span>
              {step.visible && (
                <span className="step-badge" style={{ background: STEP_COLOR[step.status] }}>
                  {step.status === "success" ? "✓" : step.status === "warning" ? "!" : "✗"}
                </span>
              )}
            </div>
          ))}
        </div>
      )}

      {/* ── Kết quả quét gần nhất ──────────────────────────────────────────── */}
      {lastResult && (
        <div className="scan-result-card">
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
          {lastResult.qr_data && (
            <div className="raw-section">
              <p className="raw-label">QR Raw Data</p>
              <pre className="raw-pre">{lastResult.qr_data}</pre>
            </div>
          )}
          <div style={{ marginTop: 14 }}>
            <a
              href={getExportCardUrl(lastResult.scan_id)}
              download={`the_sv_${lastResult.scan_id.slice(0, 8)}.pdf`}
              className="btn-export"
            >
              Xuất thẻ PDF
            </a>
          </div>
        </div>
      )}

      {/* ── Lịch sử quét ───────────────────────────────────────────────────── */}
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
                  <th>Xuất PDF</th>
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
                    <td onClick={(e) => e.stopPropagation()}>
                      <a href={getExportCardUrl(r.id)} download={`the_sv_${r.id.slice(0, 8)}.pdf`} className="btn-export-small">
                        PDF
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── Modal chi tiết ─────────────────────────────────────────────────── */}
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
                {selected.image_url && (
                  <img src={getImageUrl(selected.image_url) ?? undefined} alt="Ảnh đã quét" className="modal-image" />
                )}
                {selected.student_info
                  ? renderStudentInfo(selected.student_info)
                  : <p className="hint">Không trích xuất được thông tin sinh viên.</p>
                }
                {selected.qr_data && (
                  <div className="raw-section">
                    <p className="raw-label">QR Raw Data</p>
                    <pre className="raw-pre">{selected.qr_data}</pre>
                  </div>
                )}
                <a
                  href={getExportCardUrl(selected.id)}
                  download={`the_sv_${selected.id.slice(0, 8)}.pdf`}
                  className="btn-export"
                  onClick={(e) => e.stopPropagation()}
                >
                  Xuất thẻ PDF
                </a>
              </>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}
