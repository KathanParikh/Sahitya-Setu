import { describe, expect, it } from "vitest";
import { answerAsText } from "./copy";

const citations = [
  { page_start: 12, page_end: 12, chapter_title: "કાળુ અને રાજુ" },
  { page_start: 88, page_end: 89, chapter_title: "" },
];

describe("answerAsText", () => {
  it("keeps paragraphs, inline page references and adds the sources", () => {
    const answer = "કાળુ અને રાજુ સાથે ઊછર્યાં (પાનું ૧૨).\n\nપછી લગ્ન જુદાં થયાં (પાનાં ૮૮-૮૯).";
    expect(answerAsText(answer, citations, "માનવીની ભવાઈ")).toBe(
      [
        "કાળુ અને રાજુ સાથે ઊછર્યાં (પાનું ૧૨).",
        "",
        "પછી લગ્ન જુદાં થયાં (પાનાં ૮૮-૮૯).",
        "",
        "Sources: માનવીની ભવાઈ",
        "p. 12, કાળુ અને રાજુ",
        "pp. 88–89",
      ].join("\n"),
    );
  });

  it("keeps list items together and drops markdown markers", () => {
    const answer = "**Main characters**\n- Kalu (page 3)\n- Raju (page 5)\nBoth grow up together.";
    expect(answerAsText(answer, [], "Book")).toBe(
      ["Main characters", "", "• Kalu (page 3)", "• Raju (page 5)", "", "Both grow up together."].join("\n"),
    );
  });
});
