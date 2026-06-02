export { API_BASE, api } from "./client";
export * from "./types";
export { requestHustOtp, verifyHustOtp, registerLocal, login, logout, getMe } from "./auth";
export { processScan } from "./scan";
export { lookupStudent } from "./students";
export { getScanHistory, getScanDetail } from "./history";
export { getProfile, updateProfile, uploadAvatar, deleteAvatar, getAvatarUrl } from "./profile";
