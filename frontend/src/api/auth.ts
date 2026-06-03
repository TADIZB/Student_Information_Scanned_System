import { api } from "./client";
import type {
  AuthUser,
  RegisterLocalInput,
  RequestOtpResponse,
  ResetPasswordInput,
} from "./types";

// Đăng ký - Bước 1: kiểm tra username + email rồi gửi OTP về email.
export async function requestLocalOtp(
  username: string,
  email: string
): Promise<RequestOtpResponse> {
  const res = await api.post("/register/local/request-otp", { username, email });
  return res.data;
}

// Đăng ký thường - Bước 2: xác minh mã + tạo tài khoản (BE tự set cookie).
export async function registerLocal(input: RegisterLocalInput): Promise<AuthUser> {
  const res = await api.post("/register/local/verify-otp", input);
  return res.data;
}

// Quên mật khẩu - Bước 1: nhập tên đăng nhập → gửi OTP về email đã đăng ký.
export async function requestPasswordResetOtp(
  username: string
): Promise<RequestOtpResponse> {
  const res = await api.post("/password/forgot/request-otp", { username });
  return res.data;
}

// Quên mật khẩu - Bước 2: xác minh mã + đặt lại mật khẩu.
export async function resetPassword(
  input: ResetPasswordInput
): Promise<{ message: string }> {
  const res = await api.post("/password/reset", input);
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
