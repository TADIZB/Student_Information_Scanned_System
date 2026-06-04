import { api } from "./client";
import type {
  AuthUser,
  RegisterLocalInput,
  RequestOtpResponse,
  ResetPasswordInput,
} from "./types";

export async function requestLocalOtp(
  username: string,
  email: string
): Promise<RequestOtpResponse> {
  const res = await api.post("/register/local/request-otp", { username, email });
  return res.data;
}
export async function registerLocal(input: RegisterLocalInput): Promise<AuthUser> {
  const res = await api.post("/register/local/verify-otp", input);
  return res.data;
}
export async function requestPasswordResetOtp(
  username: string
): Promise<RequestOtpResponse> {
  const res = await api.post("/password/forgot/request-otp", { username });
  return res.data;
}
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

/** Đăng nhập bằng tài khoản trường (Microsoft/HUST SSO) — xác thực qua sso.hust.edu.vn. */
export async function loginMicrosoft(
  email: string,
  password: string
): Promise<AuthUser> {
  const res = await api.post("/login/microsoft", { email, password });
  return res.data;
}

export async function logout(): Promise<void> {
  await api.post("/logout");
}

export async function getMe(): Promise<AuthUser> {
  const res = await api.get("/me");
  return res.data;
}
