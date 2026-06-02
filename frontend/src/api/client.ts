import axios from "axios";

// Lấy API_BASE từ biến môi trường Vite. Để rỗng ("") thì FE và BE dùng cùng origin
// (Vite proxy ở dev hoặc reverse proxy ở production).
export const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

export const api = axios.create({
  baseURL: API_BASE,
  withCredentials: true,
});
