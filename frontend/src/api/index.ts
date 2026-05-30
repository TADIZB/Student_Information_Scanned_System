// Re-export tất cả module API + types để các import cũ `from "./api"` vẫn hoạt động.
export { API_BASE, api } from "./client";
export * from "./types";
export { registerHust, registerLocal, login, logout, getMe } from "./auth";
export { processScan } from "./scan";
export { lookupStudent } from "./students";
export { getScanHistory, getScanDetail, getExportCardUrl } from "./history";
