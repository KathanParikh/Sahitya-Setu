import { useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Button } from "../../components/Button";
import { langOf } from "../../lib/text";
import { t } from "../../i18n";

const MAX_LENGTH = 1000;

interface QuestionFormProps {
  disabled: boolean;
  onAsk: (question: string) => void;
}

/** One question at a time. Enter asks; Shift+Enter adds a line. */
export function QuestionForm({ disabled, onAsk }: QuestionFormProps) {
  const [question, setQuestion] = useState("");
  // Shown after trying to ask with nothing typed; cleared by typing.
  const [empty, setEmpty] = useState(false);
  const ref = useRef<HTMLTextAreaElement>(null);
  const trimmed = question.trim();

  function submit(event?: FormEvent) {
    event?.preventDefault();
    if (disabled) return;
    if (!trimmed) {
      setEmpty(true);
      ref.current?.focus();
      return;
    }
    onAsk(trimmed);
    setQuestion("");
    ref.current?.focus();
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    // Do not submit while an IME (e.g. Gujarati phonetic input) is composing.
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <form className="ask-form" onSubmit={submit}>
      <label className="visually-hidden" htmlFor="question">
        {t("ask.label")}
      </label>
      <textarea
        ref={ref}
        id="question"
        className="ask-form__input"
        rows={1}
        maxLength={MAX_LENGTH}
        placeholder={t("ask.placeholder")}
        lang={langOf(question)}
        value={question}
        onChange={(e) => {
          setQuestion(e.target.value);
          if (empty) setEmpty(false);
        }}
        aria-invalid={empty || undefined}
        onKeyDown={onKeyDown}
        aria-describedby="question-hint"
      />
      <div className="ask-form__bar">
        <p
          id="question-hint"
          className={`ask-form__hint${disabled ? " ask-form__hint--waiting" : ""}${empty ? " ask-form__hint--error" : ""}`}
          aria-live="polite"
        >
          {disabled ? t("ask.waitHint") : empty ? t("ask.emptyQuestion") : t("ask.hint")}
        </p>
        {question.length > MAX_LENGTH - 200 && (
          <span className="ask-form__count" aria-live="polite">
            {t("ask.charactersLeft", { count: MAX_LENGTH - question.length })}
          </span>
        )}
        <Button type="submit" variant="primary" className="ask-form__submit" disabled={disabled}>
          {disabled ? (
            <span className="spinner" aria-hidden="true" />
          ) : (
            <svg width="16" height="16" viewBox="0 0 20 20" fill="none" aria-hidden="true">
              <path d="M10 16V4.5M5 9.5l5-5 5 5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          )}
          {t("ask.submit")}
        </Button>
      </div>
    </form>
  );
}
