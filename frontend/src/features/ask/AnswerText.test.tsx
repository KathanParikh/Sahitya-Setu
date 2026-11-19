import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { AnswerText } from "./AnswerText";

const ENGLISH = "- He was born in Karachi — “કરસનદાસ માણેકનો જન્મ કરાંચીમાં થયો હતો.” (page 16)";

describe("AnswerText", () => {
  it("shows the book's Gujarati under an English point", () => {
    const html = renderToStaticMarkup(<AnswerText answer={ENGLISH} language="english" onCite={() => {}} />);
    expect(html).toContain('<div class="answer" lang="en">');
    expect(html).toContain("He was born in Karachi");
    expect(html).toContain('<span class="answer__source" lang="gu">');
    expect(html).toContain("From the book");
    expect(html).toContain('<q class="answer__quote">કરસનદાસ માણેકનો જન્મ કરાંચીમાં થયો હતો.</q>');
    // The citation stays a button inside the source block.
    expect(html).toMatch(/answer__source.*<button[^>]*class="cite"[^>]*>page 16<\/button>/s);
    // The separator dash and the typed quote marks are gone; <q> draws its own.
    expect(html).not.toContain("—");
    expect(html).not.toContain("“");
  });

  it("leaves a Gujarati answer as it was", () => {
    const html = renderToStaticMarkup(
      <AnswerText answer="- “નટોની ક્રિયા કે કાર્ય એટલે નટોનો આંગિક અભિનય” (પાનું 201)" language="gujarati" />,
    );
    expect(html).toContain('lang="gu"');
    expect(html).not.toContain("answer__source");
    expect(html).toContain("“નટોની ક્રિયા");
  });

  it("falls back to guessing the language for answers saved without one", () => {
    const html = renderToStaticMarkup(<AnswerText answer="Fifteen notes went missing (page 91)" />);
    expect(html).toContain('lang="en"');
    expect(html).not.toContain("answer__source");
  });
});
