import axios from "axios";

// Dùng cùng origin với frontend (Vite proxy tự chuyển tiếp sang backend)
export const API_BASE = "";

// Axios instance với withCredentials: true để trình duyệt tự gửi Cookie
const api = axios.create({
  baseURL: API_BASE,
  withCredentials: true,
});

// ─── Types ────────────────────────────────────────────────────────────────────

export interface LineData {
  text: string;
  bbox: [number, number, number, number];
  conf?: number;
}

export interface BlockData {
  type: string;
  bbox: [number, number, number, number];
  lines: LineData[];
  confidence?: number;
}

export interface StudentInfo {
  full_name: string | null;
  birth_date: string | null;
  school: string | null;
  student_id: string | null;
  email: string | null;
  avatar_url: string | null;
}

export interface ScanStep {
  name: string;
  status: "success" | "fail" | "warning" | "pending";
}

export interface ScanResult {
  scan_id: string;
  scan_type: "qr" | "ocr";
  match_result: 0 | 1 | null;
  qr_data: string | null;
  student_info: StudentInfo;
  warped_image_url: string;
  steps: ScanStep[];
  blocks: BlockData[];
}

export interface ScanRecord {
  id: string;
  scan_type: string;
  match_result: 0 | 1 | null;
  image_url: string | null;
  created_at: string;
}

export interface ScanDetail extends ScanRecord {
  raw_text: string | null;
  qr_data: string | null;
  student_info: StudentInfo | null;
}

// ─── Auth ─────────────────────────────────────────────────────────────────────

export async function register(username: string, password: string): Promise<void> {
  await api.post("/register", { username, password });
}

export async function login(username: string, password: string): Promise<{ username: string }> {
  const res = await api.post("/login", { username, password });
  return res.data;
}

export async function logout(): Promise<void> {
  await api.post("/logout");
}

export async function getMe(): Promise<{ id: string; username: string }> {
  const res = await api.get("/me");
  return res.data;
}

// ─── Quét thẻ ─────────────────────────────────────────────────────────────────

export async function processScan(
  blob: Blob,
  scanMode: "qr" | "ocr" = "qr",
  avatarBlob?: Blob | null,
): Promise<ScanResult> {
  const formData = new FormData();
  formData.append("file", blob, (blob as File).name || "capture.jpg");
  formData.append("scan_mode", scanMode);
  if (avatarBlob) {
    formData.append("avatar", avatarBlob, (avatarBlob as File).name || "avatar.jpg");
  }
  const res = await api.post<ScanResult>("/process-scan", formData);
  return res.data;
}

// ─── Lịch sử ──────────────────────────────────────────────────────────────────

export async function getScanHistory(): Promise<ScanRecord[]> {
  const res = await api.get<ScanRecord[]>("/scan-history");
  return res.data;
}

export async function getScanDetail(scanId: string): Promise<ScanDetail> {
  const res = await api.get<ScanDetail>(`/scan-history/${scanId}`);
  return res.data;
}

export function getExportCardUrl(scanId: string): string {
  return `${API_BASE}/export-card/${scanId}`;
}

export interface LookupResult extends StudentInfo {
  scan_id: string | null;
}

export async function lookupStudent(studentId: string): Promise<LookupResult> {
  const res = await api.get<LookupResult>(`/students/lookup`, {
    params: { student_id: studentId },
  });
  return res.data;
}

// ─── Legacy (giữ tương thích với code cũ) ─────────────────────────────────────

export interface AnalyzeResponse {
  warped_image_id: string;
  warped_preview_url: string;
  blocks: BlockData[];
}

export interface ExportResponse {
  export_pdf_url: string;
}

export interface ExportPayload {
  warped_image_id: string;
  blocks: BlockData[];
}

export async function analyzeImage(blob: Blob): Promise<AnalyzeResponse> {
  const formData = new FormData();
  formData.append("file", blob, (blob as File).name || "capture.jpg");
  const res = await api.post<AnalyzeResponse>("/analyze", formData);
  return res.data;
}

export async function exportPdf(payload: ExportPayload): Promise<ExportResponse> {
  const res = await api.post<ExportResponse>("/export", payload);
  return res.data;
}
