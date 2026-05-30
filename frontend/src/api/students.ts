import { api } from "./client";
import type { LookupResult } from "./types";

export async function lookupStudent(studentId: string): Promise<LookupResult> {
  const res = await api.get<LookupResult>(`/students/lookup`, {
    params: { student_id: studentId },
  });
  return res.data;
}
