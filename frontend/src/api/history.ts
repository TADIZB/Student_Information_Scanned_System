import { api } from "./client";
import type { ScanDetail, ScanRecord } from "./types";

export async function getScanHistory(): Promise<ScanRecord[]> {
  const res = await api.get<ScanRecord[]>("/scan-history");
  return res.data;
}

export async function getScanDetail(scanId: string): Promise<ScanDetail> {
  const res = await api.get<ScanDetail>(`/scan-history/${scanId}`);
  return res.data;
}
