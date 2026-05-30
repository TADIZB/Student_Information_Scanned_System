import { api, API_BASE } from "./client";
import type { ProfileResponse, ProfileUser, UpdateProfileInput } from "./types";

export async function getProfile(): Promise<ProfileResponse> {
  const res = await api.get<ProfileResponse>("/me/profile");
  return res.data;
}

export async function updateProfile(input: UpdateProfileInput): Promise<ProfileUser> {
  const res = await api.patch<ProfileUser>("/me", input);
  return res.data;
}

export async function uploadAvatar(file: File): Promise<{ avatar_url: string }> {
  const form = new FormData();
  form.append("file", file);
  const res = await api.post<{ avatar_url: string }>("/me/avatar", form);
  return res.data;
}

export async function deleteAvatar(): Promise<void> {
  await api.delete("/me/avatar");
}

export function getAvatarUrl(userId: string, cacheBust?: string | number): string {
  const v = cacheBust ?? userId;
  return `${API_BASE}/me/avatar?v=${encodeURIComponent(String(v))}`;
}
