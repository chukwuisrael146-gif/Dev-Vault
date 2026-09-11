import { useEffect, useRef, useState } from 'react';
import type { ReactNode, FormEvent } from 'react';
import { ArrowUpRight, Check, Copy, Plus, X } from 'lucide-react';
import { ErrorMessage } from './Feedback';

export function Brand() {
  return (
    <span className="brand">
      <svg viewBox="0 0 40 40" aria-hidden="true">
        <path d="M10 8h10l12 12-12 12H10l12-12z" fill="currentColor" />
        <path d="M8 15v10l5-5z" fill="currentColor" />
      </svg>
      devvault<span className="brand-dot">.</span>
    </span>
  );
}
export function Status({ value }: { value: string }) {
  const positive = ['active', 'success'].includes(value.toLowerCase());
  const negative = ['revoked', 'rate limited'].includes(value.toLowerCase());
  return (
    <span className={`status ${positive ? 'positive' : negative ? 'warning' : ''}`}>
      <span aria-hidden="true" />
      {value}
    </span>
  );
}
export function PageHeading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <p className="muted">{description}</p>
      </div>
      {action}
    </div>
  );
}
export function CreateButton({ children, onClick }: { children: ReactNode; onClick: () => void }) {
  return (
    <button className="button primary" onClick={onClick}>
      <Plus size={16} />
      {children}
    </button>
  );
}
export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <span className="empty-mark">↳</span>
      <h2>{title}</h2>
      <p>{children}</p>
      {action}
    </div>
  );
}
export function CopyButton({ value, label = 'Copy' }: { value: string; label?: string }) {
  const [message, setMessage] = useState('');
  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setMessage('Copied');
    } catch {
      setMessage('Select and copy the text manually');
    }
  }
  return (
    <span className="copy-control">
      <button type="button" className="button quiet" onClick={copy}>
        {message === 'Copied' ? <Check size={15} /> : <Copy size={15} />}
        {label}
      </button>
      <span role="status" className="small muted">
        {message}
      </span>
    </span>
  );
}
export type Field = {
  name: string;
  label: string;
  placeholder?: string;
  type?: string;
  options?: (string | { value: string; label: string })[];
  optional?: boolean;
  value?: string;
  hint?: string;
  min?: number;
  max?: number;
};
export function FormDialog({
  title,
  description,
  fields,
  submitLabel = 'Create',
  onClose,
  onSubmit,
}: {
  title: string;
  description: string;
  fields: Field[];
  submitLabel?: string;
  onClose: () => void;
  onSubmit: (values: Record<string, string>, key: string) => void | Promise<void>;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const operation = useRef({ fingerprint: '', key: crypto.randomUUID() });
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const element = dialog.current;
    element?.showModal();
    return () => {
      element?.close();
      previous?.focus();
    };
  }, []);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const data = new FormData(event.currentTarget);
    const values = Object.fromEntries(
      fields.map((field) => [field.name, data.getAll(field.name).join(',')]),
    );
    const fingerprint = JSON.stringify(values);
    if (operation.current.fingerprint !== fingerprint)
      operation.current = { fingerprint, key: crypto.randomUUID() };
    setBusy(true);
    setError(null);
    try {
      await onSubmit(values, operation.current.key);
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  }
  return (
    <dialog
      ref={dialog}
      onCancel={(event) => {
        if (busy) event.preventDefault();
        else onClose();
      }}
      className="dialog"
      aria-labelledby="dialog-title"
    >
      <div className="dialog-header">
        <span className="eyebrow">WORKSPACE / CONFIRM DETAILS</span>
        <button className="icon-button" aria-label="Close dialog" onClick={onClose} disabled={busy}>
          <X size={19} />
        </button>
      </div>
      <h2 id="dialog-title">{title}</h2>
      <p className="muted">{description}</p>
      <form onSubmit={submit}>
        <fieldset disabled={busy} className="form-fields">
          {fields.map((field) => (
            <div className="field" key={field.name}>
              <label htmlFor={`dialog-${field.name}`}>{field.label}</label>
              {field.options ? (
                <select
                  id={`dialog-${field.name}`}
                  name={field.name}
                  defaultValue={
                    field.type === 'multiselect' ? field.value?.split(',') || [] : field.value
                  }
                  required={!field.optional}
                  multiple={field.type === 'multiselect'}
                  aria-describedby={field.hint ? `hint-${field.name}` : undefined}
                >
                  {field.options.map((option) =>
                    typeof option === 'string' ? (
                      <option key={option}>{option}</option>
                    ) : (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ),
                  )}
                </select>
              ) : (
                <input
                  id={`dialog-${field.name}`}
                  aria-describedby={field.hint ? `hint-${field.name}` : undefined}
                  name={field.name}
                  type={field.type ?? 'text'}
                  defaultValue={field.value}
                  placeholder={field.placeholder}
                  required={!field.optional}
                  min={field.min}
                  max={field.max}
                  maxLength={field.type === 'number' ? undefined : 256}
                />
              )}
              {field.hint && (
                <span id={`hint-${field.name}`} className="small muted">
                  {field.hint}
                </span>
              )}
            </div>
          ))}
        </fieldset>
        <ErrorMessage error={error} />
        <p className="preview-note">Changes are saved to your DevVault backend.</p>
        <div className="dialog-actions">
          <button type="button" className="button" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button className="button primary" type="submit" disabled={busy}>
            {busy ? 'Saving…' : submitLabel}
            <ArrowUpRight size={16} />
          </button>
        </div>
      </form>
    </dialog>
  );
}
