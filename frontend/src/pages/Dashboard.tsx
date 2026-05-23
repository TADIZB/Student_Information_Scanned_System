import React, { useEffect, useState } from "react";
import { API_BASE, getExportCardUrl, getScanDetail, getScanHistory, ScanDetail, ScanRecord } from "../api";

export default function Dashboard() {
  const [records, setRecords] = useState<ScanRecord[]>([]);
  const [selected, setSelected] = useState<ScanDetail | null>(null);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [error, setError] = useState("");

  // Tải danh sách khi mount
  useEffect(() => {
    getScanHistory()
      .then(setRecords)
      .catch(() => setError("Không thể tải lịch sử quét."))
      .finally(() => setLoadingList(false));
  }, []);

  const openDetail = async (id: string) => {
    setLoadingDetail(true);
    setError("");
    try {
      const detail = await getScanDetail(id);
      setSelected(detail);
    } catch {
      setError("Không thể tải chi tiết bản ghi.");
    } finally {
      setLoadingDetail(false);
    }
  };

  const closeModal = () => setSelected(null);

  // Lấy tên file ảnh từ image_path để dựng URL
  const getImageUrl = (imagePath: string | null) => {
    if (!imagePath) return null;
    const filename = imagePath.split("/").pop();
    return `${API_BASE}/files/warped/${filename}`;
  };

  return (
    <div className="dashboard-page">
      <h2>Lịch sử quét</h2>

      {error && <div className="banner error">{error}</div>}

      {loadingList ? (
        <p className="hint">Đang tải...</p>
      ) : records.length === 0 ? (
        <p className="hint">Chưa có bản ghi nào. Hãy quét một thẻ sinh viên.</p>
      ) : (
        <div className="table-wrapper">
          <table className="history-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Loại</th>
                <th>Thời gian</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {records.map((r, i) => (
                <tr
                  key={r.id}
                  className="history-row"
                  onClick={() => openDetail(r.id)}
                >
                  <td className="row-num">{i + 1}</td>
                  <td>
                    <span className={`badge ${r.scan_type}`}>
                      {r.scan_type?.toUpperCase()}
                    </span>
                  </td>
                  <td className="row-time">
                    {new Date(r.created_at).toLocaleString("vi-VN")}
                  </td>
                  <td>
                    <button className="ghost small">Chi tiết →</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Modal chi tiết ─────────────────────────────────────────────────── */}
      {(selected || loadingDetail) && (
        <div className="modal-overlay" onClick={closeModal}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <button className="modal-close" onClick={closeModal} aria-label="Đóng">
              ✕
            </button>

            {loadingDetail ? (
              <p className="hint">Đang tải chi tiết...</p>
            ) : selected ? (
              <>
                <div className="modal-header">
                  <h3>Chi tiết bản ghi</h3>
                  <div className="modal-meta">
                    <span className={`badge ${selected.scan_type}`}>
                      {selected.scan_type?.toUpperCase()}
                    </span>
                    <span className="row-time">
                      {new Date(selected.created_at).toLocaleString("vi-VN")}
                    </span>
                  </div>
                </div>

                {/* Ảnh đã căn chỉnh */}
                {selected.image_path && (
                  <img
                    src={getImageUrl(selected.image_path) ?? undefined}
                    alt="Ảnh đã quét"
                    className="modal-image"
                  />
                )}

                {/* Thông tin sinh viên bóc tách */}
                {selected.student_info ? (
                  <div className="info-grid">
                    <div className="info-row">
                      <span>MSSV</span>
                      <strong>{selected.student_info.student_id || "—"}</strong>
                    </div>
                    <div className="info-row">
                      <span>Họ tên</span>
                      <strong>{selected.student_info.full_name || "—"}</strong>
                    </div>
                    <div className="info-row">
                      <span>Ngày sinh</span>
                      <strong>{selected.student_info.birth_date || "—"}</strong>
                    </div>
                    <div className="info-row">
                      <span>Ngành</span>
                      <strong>{selected.student_info.major || "—"}</strong>
                    </div>
                  </div>
                ) : (
                  <p className="hint">Không trích xuất được thông tin sinh viên.</p>
                )}

                {/* Dữ liệu QR thô (nếu có) */}
                {selected.qr_data && (
                  <div className="raw-section">
                    <p className="raw-label">QR Raw Data:</p>
                    {(() => {
                      const m = selected.qr_data.match(/https?:\/\/[^\s"'<>]+/i);
                      if (!m) return <pre className="raw-pre">{selected.qr_data}</pre>;
                      const before = selected.qr_data.slice(0, m.index!);
                      const after = selected.qr_data.slice(m.index! + m[0].length);
                      return (
                        <pre className="raw-pre">
                          {before}
                          <a href={m[0]} target="_blank" rel="noopener" className="qr-link">{m[0]}</a>
                          {after}
                        </pre>
                      );
                    })()}
                  </div>
                )}

                {/* Nút xuất thẻ PDF */}
                <a
                  href={getExportCardUrl(selected.id)}
                  download={`the_sv_${selected.id.slice(0, 8)}.pdf`}
                  className="btn-export primary"
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
