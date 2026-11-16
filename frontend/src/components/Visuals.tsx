import type { CSSProperties } from "react";

/**
 * Sahitya Setu's visual elements. All are decorative (aria-hidden) and drawn
 * only from the theme's tokens, so they follow any palette change.
 *
 *   ReadingJourney  the product in one sequence: a Gujarati book page in
 *                   chapters; a reader's question; the passage that answers
 *                   it, lit; the answer written from it; and a summary.
 *                   Played once on the sign-in page; shown still elsewhere.
 *   WordsToMeaning  words of Gujarati literature, a few of them marked, joined
 *                   by a fine path that ends in સમજ, "understanding".
 *   LetterField     the Gujarati consonants, set in the book serif, as a faint
 *                   typographic texture.
 *
 * They share one vocabulary: the book serif for Gujarati, the reader's
 * highlighter marks, chapter numerals, and a fine teal path.
 */

/** The consonants of the Gujarati varnamala, in order. */
const VARNAMALA = "ક ખ ગ ઘ ઙ ચ છ જ ઝ ઞ ટ ઠ ડ ઢ ણ ત થ દ ધ ન પ ફ બ ભ મ ય ર લ વ શ ષ સ હ ળ ક્ષ જ્ઞ";

export function LetterField({ className = "" }: { className?: string }) {
  return (
    <div className={`letter-field ${className}`} aria-hidden="true" lang="gu">
      {VARNAMALA}
    </div>
  );
}

/** Seconds into the sequence at which an element arrives. */
const at = (seconds: number): CSSProperties => ({ animationDelay: `${seconds}s` });

/**
 * The page's text: three passages of three lines each, [y, width, words?].
 * A few lines carry the book's own words; the rest stay as lines of text.
 */
const PASSAGES: [number, number, string?][][] = [
  [[70, 148, "કાળુ ને રાજુ નાનપણથી"], [86, 136, "સાથે જ રમતાં."], [102, 118]],
  [[140, 150, "ગામને પાદરે વડલાની છાયામાં"], [156, 128], [172, 140, "બેય કલાકો વાતો કરતાં."]],
  [[210, 146], [226, 132, "પણ વડીલોની વાત આગળ"], [242, 96]],
];
const NUMERALS = ["૧", "૨", "૩"];
/** The summary, one line per chapter; the last stays a line of text. */
const SUMMARY = ["કાળુ અને રાજુનું બાળપણ", "છપ્પનિયો દુકાળ અને કસોટી", ""];

/**
 * Book (in chapters) → question → the passage that answers it → the answer →
 * a summary. Each element arrives once and stays; the finished picture is
 * the resting state. `still` shows that picture without motion (as does
 * prefers-reduced-motion).
 */
export function ReadingJourney({ still = false, className = "" }: { still?: boolean; className?: string }) {
  return (
    <svg
      className={`journey${still ? " journey--still" : ""} ${className}`}
      viewBox="0 0 460 320"
      aria-hidden="true"
      focusable="false"
    >
      {/* 1. The book: a page of Gujarati text */}
      <g className="rj-rise" style={at(0.1)}>
        <rect className="rj-page" x="2" y="14" width="200" height="290" rx="4" />
        <text className="rj-chapter" x="22" y="44" lang="gu">
          પ્રકરણ ૧
        </text>
        <text className="rj-folio" x="184" y="44" textAnchor="end" lang="gu">
          ૧૨
        </text>
      </g>
      {/* The book's passages, marked and numbered as chapters (drawn first, so the text sits on top) */}
      {PASSAGES.map((passage, p) => (
        <g key={p} className="rj-fade" style={at(0.85 + p * 0.12)}>
          <rect
            className="rj-band"
            x="14"
            y={passage[0]![0] - 10}
            width="176"
            height={passage[2]![0] - passage[0]![0] + 26}
            rx="6"
          />
          <text className="rj-num" x="26" y={passage[1]![0] + 7} textAnchor="middle" lang="gu">
            {NUMERALS[p]}
          </text>
        </g>
      ))}
      {PASSAGES.flatMap((passage, p) =>
        passage.map(([y, w, words], l) =>
          words ? (
            <text
              key={`${p}-${l}`}
              className="rj-wipe rj-ptext"
              style={at(0.3 + (p * 3 + l) * 0.05)}
              x="40"
              y={y + 7}
              lang="gu"
            >
              {words}
            </text>
          ) : (
            <rect
              key={`${p}-${l}`}
              className="rj-grow rj-text"
              style={at(0.3 + (p * 3 + l) * 0.05)}
              x="40"
              y={y}
              width={w}
              height="6"
              rx="3"
            />
          ),
        ),
      )}

      {/* 2. The reader's question arrives first */}
      <rect className="rj-slide rj-bubble" style={at(1.5)} x="248" y="14" width="210" height="44" rx="14" />
      <text className="rj-wipe rj-question" style={at(1.75)} x="266" y="41" lang="gu">
        કાળુ અને રાજુ કોણ છે?
      </text>

      {/* 3. The passage that answers it is found in the book... */}
      <rect className="rj-fade rj-focus" style={at(2.6)} x="14" y="130" width="176" height="58" rx="6" />
      <path className="rj-path" style={at(2.9)} d="M190 156 C 214 156, 214 100, 236 92" pathLength={1} />

      {/* 4. ...and the answer is written from it */}
      <rect className="rj-rise rj-card" style={at(3.1)} x="236" y="72" width="222" height="122" rx="12" />
      <text className="rj-fade rj-label" style={at(3.3)} x="254" y="98" lang="gu">
        ઉત્તર
      </text>
      <text className="rj-wipe rj-answer" style={at(3.4)} x="254" y="120" lang="gu">
        કાળુ અને રાજુ બાળપણથી સાથે
      </text>
      <text className="rj-wipe rj-answer" style={at(3.65)} x="254" y="138" lang="gu">
        ઊછરેલાં મિત્રો છે. ગામને પાદરે
      </text>
      <text className="rj-wipe rj-answer" style={at(3.9)} x="254" y="156" lang="gu">
        વડલા નીચે બેય રમતાં
      </text>
      {/* the page reference: present, but a detail, inline as in a real answer */}
      <g className="rj-fade" style={at(4.3)}>
        <rect className="rj-cite" x="354" y="144" width="54" height="16" rx="4" />
        <text className="rj-cite-text" x="381" y="155.5" textAnchor="middle" lang="gu">
          પાનું ૧૨
        </text>
      </g>
      <rect className="rj-grow rj-line" style={at(4.15)} x="254" y="172" width="122" height="6" rx="3" />

      <path className="rj-path" style={at(4.8)} d="M190 226 C 214 226, 214 262, 236 262" pathLength={1} />
      {/* 5. Understanding: a summary, chapter by chapter */}
      <g className="rj-rise" style={at(5.0)}>
        <rect className="rj-summary" x="236" y="210" width="222" height="96" rx="12" />
        <text className="rj-summary-title" x="254" y="236" lang="gu">
          સાર
        </text>
      </g>
      {SUMMARY.map((line, i) => (
        <g key={i} className="rj-fade" style={at(5.3 + i * 0.15)}>
          <text className="rj-summary-num" x="258" y={258 + i * 17} textAnchor="middle" lang="gu">
            {NUMERALS[i]}
          </text>
          {line ? (
            <text className="rj-stext" x="270" y={258 + i * 17} lang="gu">
              {line}
            </text>
          ) : (
            <rect className="rj-sline" x="270" y={252 + i * 17} width="132" height="6" rx="3" />
          )}
        </g>
      ))}
    </svg>
  );
}

/** Words of Gujarati literature, a few marked, joined by a path that ends in understanding. */
const WORDS: { text: string; x: number; y: number; size: number; tone?: "mark" | "end" }[] = [
  { text: "સાહિત્ય", x: 4, y: 30, size: 24 },
  { text: "નવલકથા", x: 122, y: 26, size: 16 },
  { text: "કવિતા", x: 214, y: 30, size: 16 },
  { text: "વાર્તા", x: 292, y: 24, size: 15 },
  { text: "પ્રકરણ", x: 28, y: 78, size: 18, tone: "mark" },
  { text: "પાત્ર", x: 132, y: 74, size: 15 },
  { text: "પ્રશ્ન", x: 206, y: 80, size: 17, tone: "mark" },
  { text: "અર્થ", x: 96, y: 126, size: 20 },
  { text: "સમજ", x: 208, y: 128, size: 38, tone: "end" },
];

export function WordsToMeaning({ className = "" }: { className?: string }) {
  return (
    <svg className={`words ${className}`} viewBox="0 0 360 140" aria-hidden="true" focusable="false">
      <path
        className="words__path"
        d="M92 22 C 108 30, 112 12, 120 18 S 196 34, 210 24 S 270 12, 286 18 M330 34 C 300 56, 150 46, 112 64 M112 64 C 150 80, 176 66, 200 72 M268 86 C 240 104, 160 100, 142 112 M142 112 C 160 124, 182 120, 194 118"
        pathLength={1}
      />
      {WORDS.map((w, i) => (
        <g key={w.text} className="words__word" style={at(0.15 + i * 0.09)}>
          {w.tone === "mark" && (
            <rect className="words__mark" x={w.x - 4} y={w.y - w.size * 0.55} width={w.size * 3.2} height={w.size * 0.75} rx="3" />
          )}
          <text
            className={`words__text${w.tone ? ` words__text--${w.tone}` : ""}`}
            x={w.x}
            y={w.y}
            fontSize={w.size}
            lang="gu"
          >
            {w.text}
          </text>
        </g>
      ))}
      <circle className="words__end" cx="196" cy="118" r="3.5" />
    </svg>
  );
}
