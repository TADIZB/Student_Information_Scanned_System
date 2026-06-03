import axios from "axios";

export const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

export const api = axios.create({
  baseURL: API_BASE,
  withCredentials: true,
});
