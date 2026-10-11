import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import RetrievalAssessmentPanel from "../../components/RetrievalAssessmentPanel";
import type { RetrievalAssessment } from "../../lib/types";

afterEach(cleanup);
const row = { assessment_id: "row", source_ref: "A203", citation_id: "release:A203", pinned: true,
  route: "REQUIRED", status: "SKIPPED_POLICY", processing_mode: "RULE", actual_model: null,
  relevance_level: null, confidence: null, reason_code: "INPUT_NOT_APPROVED", usage_state: "NOT_CALLED",
  latency_ms: 0, rubric_version: "rubric-v1", ranking_policy_version: "ranking-v1" };
const base: RetrievalAssessment = { diagnosis_run_id: "run", retrieval_round: 1, status: "SKIPPED_POLICY", assessments: [row] };

test("policy skip is visibly not a model score or zero relevance", () => {
  render(<RetrievalAssessmentPanel assessment={base} />);
  expect(screen.getByText(/资料受限，未发送 · 检索轮次 1/)).toBeInTheDocument();
  expect(screen.getByText(/未调用 Jev/)).toBeInTheDocument();
  expect(screen.getByText(/相关性：未判断/)).toBeInTheDocument();
  expect(screen.queryByText(/0 \/ 3/)).not.toBeInTheDocument();
});

test("cache shows the actual original fixture model without claiming external call", () => {
  render(<RetrievalAssessmentPanel assessment={{ ...base, retrieval_round: 3, status: "CACHED",
    assessments: [{ ...row, status: "CACHED", processing_mode: "FIXTURE", actual_model: "fixture-jev-v1" }] }} />);
  expect(screen.getByText(/复用已授权缓存 · 检索轮次 3/)).toBeInTheDocument();
  expect(screen.getByText(/FIXTURE · fixture-jev-v1/)).toBeInTheDocument();
  expect(screen.queryByText(/未调用 Jev/)).not.toBeInTheDocument();
});

test("folding retains the source and does not imply confirmed root cause", () => {
  render(<RetrievalAssessmentPanel assessment={{ ...base, status: "FIXTURE",
    assessments: [{ ...row, source_ref: "simulated-reference", route: "FOLDED", status: "FIXTURE",
      processing_mode: "FIXTURE", actual_model: "scripted-fixture", relevance_level: 0 }] }} />);
  expect(screen.getByText("simulated-reference")).toBeInTheDocument();
  expect(screen.getByText(/折叠保留/)).toBeInTheDocument();
  expect(screen.getByText(/相关性等级不是根因概率/)).toBeInTheDocument();
});
