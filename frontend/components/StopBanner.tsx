import SafetyActionCard from "./SafetyActionCard";
import type { Notice } from "../lib/types";

export default function StopBanner({ notice }: { notice: Notice | null }) {
  return notice?.safety_blocked ? <SafetyActionCard notice={notice} /> : null;
}
