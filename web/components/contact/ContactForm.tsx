"use client";

/**
 * The Contact form.
 *
 * Labels sit above their fields and are real labels, errors sit below the field
 * they belong to and are tied to it for screen readers, and nothing is placed
 * in a field as a stand-in for its label. Every problem is reported at once so a
 * person is not sent round the form one error at a time.
 *
 * `website` is a trap: a field a person never sees and never tabs to, so anything
 * in it means a program filled the form in. The server drops such a message while
 * answering exactly as it does for a real one, so the bot learns nothing.
 */

import Link from "next/link";
import { useId, useState, type FormEvent } from "react";

export interface Topic {
  value: string;
  label: string;
}

type Status = "idle" | "sending" | "sent";

const MESSAGE_MAX = 5000;

const field =
  "mt-2 block w-full rounded-[var(--radius-md)] border border-[var(--color-line-strong)] bg-[var(--color-surface)] px-3.5 py-2.5 text-[15px] text-[var(--color-text)] placeholder:text-[var(--color-text-faint)]";

export function ContactForm({ topics }: { topics: Topic[] }) {
  const uid = useId();
  const [status, setStatus] = useState<Status>("idle");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [length, setLength] = useState(0);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (status === "sending") return;
    const form = event.currentTarget;
    const data = new FormData(form);

    setStatus("sending");
    setErrors({});
    setFailure(null);

    try {
      const response = await fetch("/api/contact", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          // An unchosen select submits nothing at all, so default each to "".
          topic: data.get("topic") ?? "",
          name: data.get("name") ?? "",
          email: data.get("email") ?? "",
          message: data.get("message") ?? "",
          website: data.get("website") ?? "",
        }),
      });
      const body = (await response.json().catch(() => ({}))) as {
        ok?: boolean;
        errors?: Record<string, string>;
        error?: string;
      };

      if (response.ok) {
        form.reset();
        setLength(0);
        setStatus("sent");
        return;
      }
      if (body.errors) setErrors(body.errors);
      else
        setFailure(
          body.error ??
            "The message could not be sent. Please try again in a few minutes.",
        );
    } catch {
      setFailure(
        "The message could not be sent. Check your connection and try again.",
      );
    }
    setStatus("idle");
  }

  if (status === "sent") {
    return (
      <div
        role="status"
        className="rounded-[var(--radius-lg)] border border-[var(--color-line-strong)] bg-[var(--color-surface)] p-6"
      >
        <p className="text-[17px] font-semibold">Message sent</p>
        <p className="mt-2 max-w-[56ch] text-[14.5px] leading-relaxed text-[var(--color-text-dim)]">
          Thank you. Your message has been saved for the site&rsquo;s operator
          to read. There is no automatic reply, so if you asked for something to
          be corrected or removed, it will be dealt with when the message is
          read.
        </p>
        <button
          type="button"
          onClick={() => setStatus("idle")}
          className="mt-5 text-[14px] text-[var(--color-gold-bright)] underline-offset-4 hover:underline"
        >
          Send another message
        </button>
      </div>
    );
  }

  const describedBy = (name: string) =>
    errors[name] ? `${uid}-${name}-error` : undefined;

  return (
    <form onSubmit={onSubmit} noValidate className="relative space-y-6">
      {failure && (
        <p
          role="alert"
          className="rounded-[var(--radius-md)] border border-[var(--color-lost)] px-4 py-3 text-[14px] text-[var(--color-lost)]"
        >
          {failure}
        </p>
      )}

      <div>
        <label htmlFor={`${uid}-topic`} className="text-[14px] font-medium">
          What is it about?
        </label>
        <select
          id={`${uid}-topic`}
          name="topic"
          defaultValue=""
          required
          aria-invalid={Boolean(errors.topic)}
          aria-describedby={describedBy("topic")}
          className={field}
        >
          <option value="" disabled>
            Choose a topic
          </option>
          {topics.map((topic) => (
            <option key={topic.value} value={topic.value}>
              {topic.label}
            </option>
          ))}
        </select>
        {errors.topic && (
          <p
            id={`${uid}-topic-error`}
            className="mt-1.5 text-[13px] text-[var(--color-lost)]"
          >
            {errors.topic}
          </p>
        )}
      </div>

      <div className="grid gap-6 sm:grid-cols-2">
        <div>
          <label htmlFor={`${uid}-name`} className="text-[14px] font-medium">
            Your name{" "}
            <span className="font-normal text-[var(--color-text-faint)]">
              (optional)
            </span>
          </label>
          <input
            id={`${uid}-name`}
            name="name"
            type="text"
            autoComplete="name"
            maxLength={120}
            aria-invalid={Boolean(errors.name)}
            aria-describedby={describedBy("name")}
            className={field}
          />
          {errors.name && (
            <p
              id={`${uid}-name-error`}
              className="mt-1.5 text-[13px] text-[var(--color-lost)]"
            >
              {errors.name}
            </p>
          )}
        </div>

        <div>
          <label htmlFor={`${uid}-email`} className="text-[14px] font-medium">
            Email address
          </label>
          <input
            id={`${uid}-email`}
            name="email"
            type="email"
            autoComplete="email"
            required
            maxLength={254}
            aria-invalid={Boolean(errors.email)}
            aria-describedby={describedBy("email")}
            className={field}
          />
          {errors.email && (
            <p
              id={`${uid}-email-error`}
              className="mt-1.5 text-[13px] text-[var(--color-lost)]"
            >
              {errors.email}
            </p>
          )}
        </div>
      </div>

      <div>
        <label htmlFor={`${uid}-message`} className="text-[14px] font-medium">
          Your message
        </label>
        <textarea
          id={`${uid}-message`}
          name="message"
          rows={7}
          required
          maxLength={MESSAGE_MAX}
          onChange={(event) => setLength(event.target.value.length)}
          aria-invalid={Boolean(errors.message)}
          aria-describedby={
            [describedBy("message"), `${uid}-message-help`]
              .filter(Boolean)
              .join(" ") || undefined
          }
          className={`${field} resize-y leading-relaxed`}
        />
        <div className="mt-1.5 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          {errors.message ? (
            <p
              id={`${uid}-message-error`}
              className="text-[13px] text-[var(--color-lost)]"
            >
              {errors.message}
            </p>
          ) : (
            <span />
          )}
          <p
            id={`${uid}-message-help`}
            className="text-[12.5px] text-[var(--color-text-faint)] tabular-nums"
          >
            {length.toLocaleString()} / {MESSAGE_MAX.toLocaleString()}
          </p>
        </div>
      </div>

      {/* The trap. Out of sight and out of the tab order; a person never meets it. */}
      <div
        aria-hidden="true"
        className="absolute -left-[9999px] h-0 w-0 overflow-hidden"
      >
        <label>
          Leave this empty
          <input type="text" name="website" tabIndex={-1} autoComplete="off" />
        </label>
      </div>

      <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
        <button
          type="submit"
          disabled={status === "sending"}
          className="nt-cta nt-cta--primary disabled:opacity-60"
        >
          {status === "sending" ? "Sending…" : "Send message"}
        </button>
        <p className="max-w-[48ch] text-[12.5px] leading-relaxed text-[var(--color-text-faint)]">
          We store your message and email address only to read and answer it.
          See the{" "}
          <Link
            href="/privacy"
            className="text-[var(--color-gold-bright)] underline-offset-4 hover:underline"
          >
            privacy policy
          </Link>
          .
        </p>
      </div>
    </form>
  );
}
