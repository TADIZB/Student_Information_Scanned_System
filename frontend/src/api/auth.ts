import { api } from "./client";
import type { AuthUser, RegisterHustInput, RegisterLocalInput } from "./types";

export async function registerHust(input: RegisterHustInput): Promise<AuthUser> {
  const res = await api.post("/register/hust", input);
  return res.data;
}

export async function registerLocal(input: RegisterLocalInput): Promise<AuthUser> {
  const res = await api.post("/register/local", input);
  return res.data;
}

export async function login(identifier: string, password: string): Promise<AuthUser> {
  const res = await api.post("/login", { identifier, password });
  return res.data;
}

export async function logout(): Promise<void> {
  await api.post("/logout");
}

export async function getMe(): Promise<AuthUser> {
  const res = await api.get("/me");
  return res.data;
}
