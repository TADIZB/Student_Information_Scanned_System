import { api } from "./client";
import type { ScanResult } from "./types";

export async function processScan(
  blob: Blob,
  scanMode: "qr" | "ocr" = "qr",
): Promise<ScanResult> {
  const formData = new FormData();
  formData.append("file", blob, (blob as File).name || "capture.jpg");
  formData.append("scan_mode", scanMode);
  const res = await api.post<ScanResult>("/process-scan", formData);
  return res.data;
}
