import { Activity, BookOpen, CalendarDays, ClipboardCheck, FlaskConical, HeartPulse, Pill, Stethoscope, Syringe, TriangleAlert, Users } from "lucide-vue-next";

// Field ekstraksi -> label, ikon, warna (desain "Info Klinis")
export const FIELD = {
  keluhan_utama: { label: "Keluhan Utama", icon: Activity, tone: "danger" },
  keluhan_lain: { label: "Keluhan Lain", icon: TriangleAlert, tone: "warning" },
  riwayat: { label: "Riwayat Penyakit", icon: BookOpen, tone: "success" },
  alergi: { label: "Alergi", icon: Pill, tone: "info" },
  tanda_vital: { label: "Tanda Vital", icon: HeartPulse, tone: "purple" },
  pemeriksaan_fisik: { label: "Pemeriksaan", icon: Stethoscope, tone: "purple" },
  penunjang: { label: "Penunjang", icon: FlaskConical, tone: "info" },
  diagnosis: { label: "Diagnosis", icon: ClipboardCheck, tone: "purple" },
  obat: { label: "Terapi", icon: Pill, tone: "info" },
  tindakan: { label: "Tindakan", icon: Syringe, tone: "teal" },
  edukasi: { label: "Edukasi", icon: Users, tone: "teal" },
  rencana: { label: "Rencana", icon: CalendarDays, tone: "navy" },
};
