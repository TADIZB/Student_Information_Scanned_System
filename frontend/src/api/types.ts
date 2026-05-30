// Tập trung tất cả interface dùng chung cho FE — tách riêng để các module gọn hơn.

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
  description?: string | null;
  image_url?: string | null;   // data URL minh hoạ kết quả của bước
}

export interface ExtractedInfo {
  full_name: string | null;
  birth_date: string | null;
  school: string | null;
  student_id: string | null;
  email: string | null;
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
  raw_text: string | null;
  extracted_info: ExtractedInfo | null;
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

export interface AuthUser {
  id: string;
  username: string | null;
  email: string | null;
  full_name: string | null;
  birth_date: string | null;
}

export interface RegisterHustInput {
  email: string;
  password: string;
  full_name?: string;
  birth_date?: string;
}

export interface RegisterLocalInput {
  username: string;
  password: string;
  full_name?: string;
  birth_date?: string;
}

// ─── Lookup ───────────────────────────────────────────────────────────────────

export interface LookupResult extends StudentInfo {
  scan_id: string | null;
}
