import { reactive } from "vue";

// Status UI lintas halaman (bukan data klinis): sesi yang sedang dikerjakan untuk tautan "Sesi Aktif" dan pasien berikutnya.
export const app = reactive({ activeSessionId: null, navOpen: false });
