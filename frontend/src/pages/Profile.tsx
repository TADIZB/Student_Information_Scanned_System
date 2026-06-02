import React, { ChangeEvent, FormEvent, useEffect, useRef, useState } from "react";
import {
  deleteAvatar,
  getAvatarUrl,
  getProfile,
  ProfileResponse,
  updateProfile,
  uploadAvatar,
} from "../api";

interface Props {
  onBack?: () => void;
}

const formatBirthForInput = (b: string | null | undefined): string => {
  if (!b) return "";
  // chấp nhận yyyy-mm-dd hoặc dd/mm/yyyy
  if (/^\d{4}-\d{2}-\d{2}$/.test(b)) return b;
  const m = b.match(/^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})$/);
  if (!m) return "";
  return `${m[3]}-${m[2].padStart(2, "0")}-${m[1].padStart(2, "0")}`;
};

const formatDateDisplay = (s: string | null): string => {
  if (!s) return "—";
  if (/^\d{4}-\d{2}-\d{2}/.test(s)) {
    const d = new Date(s);
    if (isNaN(d.getTime())) return s;
    return d.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" });
  }
  return s;
};

export default function Profile({ onBack }: Props) {
  const [data, setData] = useState<ProfileResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [toast, setToast] = useState<{ kind: "success" | "error"; msg: string } | null>(null);

  // Edit form
  const [editMode, setEditMode] = useState(false);
  const [fullName, setFullName] = useState("");
  const [birthDate, setBirthDate] = useState("");
  const [saving, setSaving] = useState(false);

  // Avatar
  const [avatarBust, setAvatarBust] = useState<number>(Date.now());
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const d = await getProfile();
      setData(d);
      setFullName(d.user.full_name || "");
      setBirthDate(formatBirthForInput(d.user.birth_date));
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Không tải được hồ sơ.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 3000);
    return () => clearTimeout(t);
  }, [toast]);

  const handleSave = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const updated = await updateProfile({
        full_name: fullName.trim(),
        birth_date: birthDate || "",
      });
      setData((d) => (d ? { ...d, user: { ...d.user, ...updated } } : d));
      setEditMode(false);
      setToast({ kind: "success", msg: "Đã lưu thay đổi." });
    } catch (err: any) {
      setToast({ kind: "error", msg: err?.response?.data?.detail || "Lưu thất bại." });
    } finally {
      setSaving(false);
    }
  };

  const handleAvatarPick = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      await uploadAvatar(file);
      setAvatarBust(Date.now());
      setData((d) => (d ? { ...d, user: { ...d.user, has_avatar: true } } : d));
      setToast({ kind: "success", msg: "Đã cập nhật ảnh đại diện." });
    } catch (err: any) {
      setToast({ kind: "error", msg: err?.response?.data?.detail || "Tải ảnh thất bại." });
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  };

  const handleAvatarDelete = async () => {
    if (!confirm("Xoá ảnh đại diện hiện tại?")) return;
    try {
      await deleteAvatar();
      setData((d) => (d ? { ...d, user: { ...d.user, has_avatar: false } } : d));
      setToast({ kind: "success", msg: "Đã xoá ảnh đại diện." });
    } catch (err: any) {
      setToast({ kind: "error", msg: err?.response?.data?.detail || "Xoá thất bại." });
    }
  };

  if (loading) {
    return (
      <div className="full-center" style={{ minHeight: 360 }}>
        <span className="brand-mark" style={{ width: 48, height: 48 }} />
      </div>
    );
  }
  if (error || !data) {
    return (
      <div className="profile-page">
        <div className="banner error">{error || "Không có dữ liệu."}</div>
      </div>
    );
  }

  const { user, stats } = data;
  const displayName = user.full_name || user.email || user.username || "Người dùng";
  const accountType = user.email ? "Tài khoản trường" : "Tài khoản thường";
  const avatarSrc = user.has_avatar ? getAvatarUrl(user.id, avatarBust) : null;

  return (
    <div className="profile-page">
      {onBack && (
        <button className="ghost profile-back" onClick={onBack}>
          ← Quay lại
        </button>
      )}

      {/* Header card */}
      <div className="profile-header">
        <div className="profile-cover" />
        <div className="profile-avatar-wrap">
          {avatarSrc ? (
            <img src={avatarSrc} alt="Ảnh đại diện" className="profile-avatar" />
          ) : (
            <div className="profile-avatar profile-avatar-placeholder">
              {displayName.slice(0, 1).toUpperCase()}
            </div>
          )}
          <input
            ref={fileRef}
            type="file"
            accept="image/jpeg,image/png,image/webp,image/gif"
            onChange={handleAvatarPick}
            style={{ display: "none" }}
          />
          <div className="profile-avatar-actions">
            <button
              type="button"
              className="ghost"
              onClick={() => fileRef.current?.click()}
              disabled={uploading}
            >
              {uploading ? "Đang tải..." : avatarSrc ? "Đổi ảnh" : "Tải ảnh"}
            </button>
            {avatarSrc && (
              <button type="button" className="ghost" onClick={handleAvatarDelete}>
                Xoá ảnh
              </button>
            )}
          </div>
        </div>

        <div className="profile-header-info">
          <h2>{displayName}</h2>
          <div className="profile-chip">{accountType}</div>
          <div className="profile-meta-list">
            {user.email && <div className="profile-meta">{user.email}</div>}
            {user.username && <div className="profile-meta">@{user.username}</div>}
            <div className="profile-meta">
              Tham gia: {user.created_at ? new Date(user.created_at).toLocaleDateString("vi-VN") : "—"}
            </div>
          </div>
        </div>
      </div>

      {/* Stats */}
      <div className="profile-stats">
        <StatCard label="Tổng số quét" value={stats.total_scans} tint="#dc2626" icon="total" />
        <StatCard label="QR" value={stats.qr_scans} tint="#ef4444" icon="qr" />
        <StatCard label="OCR" value={stats.ocr_scans} tint="#b91c1c" icon="ocr" />
        <StatCard label="Tra cứu" value={stats.lookup_scans} tint="#f97316" icon="lookup" />
        <StatCard label="Khớp SV" value={stats.matched} tint="#059669" icon="matched" />
      </div>

      {/* Info section */}
      <div className="profile-section">
        <div className="profile-section-header">
          <h3>Thông tin cá nhân</h3>
          {!editMode && (
            <button className="ghost" onClick={() => setEditMode(true)}>Sửa</button>
          )}
        </div>

        {!editMode ? (
          <div className="profile-info-grid">
            <InfoRow label="Họ và tên" value={user.full_name} />
            <InfoRow label="Ngày sinh" value={formatDateDisplay(user.birth_date)} />
            <InfoRow label="Email" value={user.email} muted />
            <InfoRow label="Tên đăng nhập" value={user.username} muted />
          </div>
        ) : (
          <form onSubmit={handleSave} className="profile-edit-form">
            <div className="field">
              <label htmlFor="p-fullname">Họ và tên</label>
              <input
                id="p-fullname"
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Nguyễn Văn A"
              />
            </div>
            <div className="field">
              <label htmlFor="p-birth">Ngày sinh</label>
              <input
                id="p-birth"
                type="date"
                value={birthDate}
                onChange={(e) => setBirthDate(e.target.value)}
              />
            </div>
            <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
              <button type="submit" className="primary" disabled={saving}>
                {saving ? "Đang lưu..." : "Lưu thay đổi"}
              </button>
              <button
                type="button"
                className="ghost"
                onClick={() => {
                  setEditMode(false);
                  setFullName(user.full_name || "");
                  setBirthDate(formatBirthForInput(user.birth_date));
                }}
              >
                Huỷ
              </button>
            </div>
          </form>
        )}
      </div>

      {toast && (
        <div className={`toast ${toast.kind}`} role="status" onClick={() => setToast(null)}>
          {toast.msg}
        </div>
      )}
    </div>
  );
}

const STAT_ICONS: Record<string, React.ReactNode> = {
  total: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="18" height="18" rx="2" /><path d="M3 9h18M9 21V9" />
    </svg>
  ),
  qr: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><path d="M14 14h3v3M21 14v7M17 21h-3" />
    </svg>
  ),
  ocr: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 7V5a1 1 0 0 1 1-1h2M20 7V5a1 1 0 0 0-1-1h-2M4 17v2a1 1 0 0 0 1 1h2M20 17v2a1 1 0 0 1-1 1h-2M8 12h8" />
    </svg>
  ),
  lookup: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" />
    </svg>
  ),
  matched: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20 6 9 17l-5-5" />
    </svg>
  ),
};

function StatCard({ label, value, tint, icon }: { label: string; value: number; tint: string; icon: string }) {
  return (
    <div className="stat-card" style={{ ["--tint" as string]: tint }}>
      <div className="stat-icon">{STAT_ICONS[icon]}</div>
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}

function InfoRow({ label, value, muted }: { label: string; value: string | null; muted?: boolean }) {
  return (
    <div className="profile-info-row">
      <span className="profile-info-label">{label}</span>
      <span className={`profile-info-value${muted ? " muted" : ""}`}>{value || "—"}</span>
    </div>
  );
}
