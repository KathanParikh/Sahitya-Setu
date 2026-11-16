import { describe, expect, it } from "vitest";
import { answerBlocks, findSpans, langOf, parsePages, quotedSpans, splitCitations } from "./text";

describe("langOf", () => {
  it("detects Gujarati script", () => {
    expect(langOf("સરસ્વતીચંદ્ર કોણ છે?")).toBe("gu");
    expect(langOf("Who is Saraswatichandra?")).toBe("en");
    expect(langOf("Kumud અને Saraswatichandra")).toBe("gu");
    expect(langOf("")).toBe("en");
  });
});

describe("page citations", () => {
  it("reads Gujarati and Latin digits, ranges and lists", () => {
    expect(parsePages("૪૨")).toEqual([42]);
    expect(parsePages("196-197")).toEqual([196, 197]);
    expect(parsePages("12–14, 20")).toEqual([12, 13, 14, 20]);
  });

  it("splits a Gujarati line around its citation", () => {
    const parts = splitCitations("કુમુદ સુંદરીનો પરિચય (પાનું ૪૨).");
    expect(parts).toEqual([
      { kind: "text", text: "કુમુદ સુંદરીનો પરિચય (" },
      { kind: "cite", text: "પાનું ૪૨", pages: [42] },
      { kind: "text", text: ")." },
    ]);
  });

  it("splits English citations, including plural ranges", () => {
    const parts = splitCitations("He leaves home (page 12) and returns (pages 30–31).");
    expect(parts.filter((p) => p.kind === "cite").map((p) => p.kind === "cite" && p.pages)).toEqual([
      [12],
      [30, 31],
    ]);
  });

  it("reads single-digit pages, as real answers cite them", () => {
    expect(splitCitations("ત્રણ ઊંચા કબાટ (પાનું 3)")).toEqual([
      { kind: "text", text: "ત્રણ ઊંચા કબાટ (" },
      { kind: "cite", text: "પાનું 3", pages: [3] },
      { kind: "text", text: ")" },
    ]);
    const parts = splitCitations("on Diwali day (page 4).");
    expect(parts[1]).toEqual({ kind: "cite", text: "page 4", pages: [4] });
    expect(splitCitations("(પાનું ૭)")[1]).toEqual({ kind: "cite", text: "પાનું ૭", pages: [7] });
  });

  it("leaves a line without citations as one text part", () => {
    expect(splitCitations("No pages here.")).toEqual([{ kind: "text", text: "No pages here." }]);
  });
});

describe("answerBlocks", () => {
  it("separates list items from paragraphs and drops bold markers", () => {
    expect(answerBlocks("Intro **line**.\n- first (page 1)\n2. second\n\n૩) ત્રીજું")).toEqual([
      { kind: "paragraph", text: "Intro line." },
      { kind: "item", text: "first (page 1)" },
      { kind: "item", text: "second" },
      { kind: "item", text: "ત્રીજું" },
    ]);
  });

  it("treats short bold-only lines and markdown headings as headings", () => {
    expect(answerBlocks("**પ્રથમ પેરા**  \nભીનાં પુસ્તકોની કથા.\n\n## Themes\n**Note:** bold start")).toEqual([
      { kind: "heading", text: "પ્રથમ પેરા" },
      { kind: "paragraph", text: "ભીનાં પુસ્તકોની કથા." },
      { kind: "heading", text: "Themes" },
      { kind: "paragraph", text: "Note: bold start" },
    ]);
  });
});

describe("quotedSpans", () => {
  it("finds curly, straight and single quotes", () => {
    expect(quotedSpans("તે કહે છે “મારું નામ કુમુદ” અને ‘સરસ્વતી’ (પાનું ૩)")).toEqual([
      "મારું નામ કુમુદ",
      "સરસ્વતી",
    ]);
    expect(quotedSpans('He said "go home now".')).toEqual(["go home now"]);
  });
});

describe("findSpans", () => {
  it("matches across different whitespace and maps back to the original text", () => {
    const text = "પહેલું વાક્ય.\nમારું   નામ\nકુમુદ છે. છેલ્લું.";
    const [span] = findSpans(text, ["મારું નામ કુમુદ"]);
    expect(text.slice(span!.start, span!.end)).toBe("મારું   નામ\nકુમુદ");
  });

  it("merges overlapping matches and ignores very short needles", () => {
    const text = "abcdefghij";
    expect(findSpans(text, ["cdef", "efgh", "ab"])).toEqual([{ start: 2, end: 8 }]);
  });

  it("returns nothing when the quote is not in the passage", () => {
    expect(findSpans("some passage text", ["missing words"])).toEqual([]);
  });
});
