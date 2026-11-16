import { forwardRef, useId, useState, type InputHTMLAttributes } from "react";
import { t } from "../i18n";

interface TextFieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "id"> {
  label: string;
  /** Shown under the field when there is no error. */
  hint?: string;
  error?: string | null;
}

/** A labelled input with an optional hint and an inline error. */
export const TextField = forwardRef<HTMLInputElement, TextFieldProps>(function TextField(
  { label, hint, error, className, ...input },
  ref,
) {
  const id = useId();
  const messageId = `${id}-message`;
  const message = error || hint;
  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>
        {label}
      </label>
      <div className="field__control">
        <input
          ref={ref}
          id={id}
          className={["field__input", className].filter(Boolean).join(" ")}
          aria-invalid={error ? true : undefined}
          aria-describedby={message ? messageId : undefined}
          {...input}
        />
      </div>
      {message && (
        <p id={messageId} className={error ? "field__error" : "field__hint"}>
          {message}
        </p>
      )}
    </div>
  );
});

/** A password input with a Show / Hide toggle. */
export const PasswordField = forwardRef<HTMLInputElement, Omit<TextFieldProps, "type">>(
  function PasswordField({ label, hint, error, disabled, ...input }, ref) {
    const id = useId();
    const messageId = `${id}-message`;
    const message = error || hint;
    const [visible, setVisible] = useState(false);
    return (
      <div className="field">
        <label className="field__label" htmlFor={id}>
          {label}
        </label>
        <div className="field__control">
          <input
            ref={ref}
            id={id}
            type={visible ? "text" : "password"}
            className="field__input field__input--with-action"
            aria-invalid={error ? true : undefined}
            aria-describedby={message ? messageId : undefined}
            disabled={disabled}
            spellCheck={false}
            autoCapitalize="none"
            {...input}
          />
          <button
            type="button"
            className="text-button field__action"
            onClick={() => setVisible((v) => !v)}
            aria-label={visible ? t("form.hidePasswordLabel") : t("form.showPasswordLabel")}
            aria-pressed={visible}
            disabled={disabled}
          >
            {visible ? t("form.hidePassword") : t("form.showPassword")}
          </button>
        </div>
        {message && (
          <p id={messageId} className={error ? "field__error" : "field__hint"}>
            {message}
          </p>
        )}
      </div>
    );
  },
);
