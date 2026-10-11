import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import EvidenceReviewPanel from "../../components/EvidenceReviewPanel";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
describe("explicit evidence decisions", () => {
  it("never defaults to acceptance and sends only the selected item", async () => {
    const rows = ["alarm_code", "actual_temperature_c"].map((key, i) => ({
      evidence_id: `sample-${i}`, version: 1, key, state: "CANDIDATE", source: "OCR",
      media_id: "media-fixture", value: { value: key === "alarm_code" ? "A203" : 128, limitation: null },
      locators: {}, provenance: { mode: "FIXTURE" }, reviewable: true,
    }));
    const fetcher = vi.fn().mockImplementation(async (input: string, options?: RequestInit) =>
      ({ ok: true, json: async () => options?.method === "POST" ? { versions: [] } :
        { evidence: rows, processing_pending: false } }));
    vi.stubGlobal("fetch", fetcher);
    render(<EvidenceReviewPanel incidentId="sample" csrf="test-csrf" onDiagnose={vi.fn()} busy={false} />);
    await waitFor(() => expect(screen.getByLabelText("复核 报警码")).toHaveValue(""));
    expect(screen.getByRole("button", { name: "保存本轮证据复核 →" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "使用当前已确认事实开始诊断 →" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("复核 报警码"), { target: { value: "CONFIRMED" } });
    fireEvent.change(screen.getByLabelText("本轮复核说明"), { target: { value: "已对照原图核实报警码。" } });
    fireEvent.click(screen.getByRole("button", { name: "保存本轮证据复核 →" }));
    await waitFor(() => expect(fetcher.mock.calls.some(call => call[1]?.method === "POST")).toBe(true));
    const post = fetcher.mock.calls.find(call => call[1]?.method === "POST")!;
    const payload = JSON.parse(post[1].body);
    expect(payload.decisions).toHaveLength(1);
    expect(payload.decisions[0].evidence_id).toBe("sample-0");
    expect(payload.decisions[0].decision).toBe("CONFIRMED");
    expect(screen.getByLabelText("复核 实际温度")).toHaveValue("");
  });
  it("failed evidence access cannot unlock diagnosis", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false }));
    render(<EvidenceReviewPanel incidentId="unavailable" csrf="test-csrf" onDiagnose={vi.fn()} busy={false} />);
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("EVIDENCE_UNAVAILABLE"));
    expect(screen.getByRole("button", { name: "使用当前已确认事实开始诊断 →" })).toBeDisabled();
  });
});
