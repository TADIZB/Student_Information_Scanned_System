import { api } from "./client";
import type {
  AuthUser,
  RegisterLocalInput,
  RequestOtpResponse,
  VerifyHustOtpInput,
} from "./types";

// Bước 1: xin mã OTP gửi về email trường.
export async function requestHustOtp(email: string): Promise<RequestOtpResponse> {
  const res = await api.post("/register/hust/request-otp", { email });
  return res.data;
}

// Bước 2: xác minh mã + tạo tài khoản (BE tự set cookie đăng nhập).
export async function verifyHustOtp(input: VerifyHustOtpInput): Promise<AuthUser> {
  const res = await api.post("/register/hust/verify-otp", input);
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
