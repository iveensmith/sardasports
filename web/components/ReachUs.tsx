/**
 * "Reach us": the footer's block of direct contact routes, each one a row with
 * its own mark: WhatsApp, Telegram, email, and the social circles beneath.
 *
 * Every route is read from `SOCIAL_CONTACTS` / `CONTACT_EMAIL` in `lib/site.ts`.
 * A route that has not been supplied yet shows "Coming soon" as plain text and
 * its circle is inert: there is no link to follow, so nothing can point at a
 * number, handle or address that was never given. The moment a value is set it
 * becomes a real link, with no change here.
 *
 * Links open in a new tab with `noopener noreferrer`, so a messaging app's page
 * cannot reach back into this one.
 */

import { CONTACT_EMAIL, SOCIAL_CONTACTS } from "@/lib/site";

const LINK =
  "font-medium text-[var(--color-gold-bright)] underline decoration-[var(--color-gold)]/60 decoration-2 underline-offset-4 transition-colors hover:text-[var(--color-text)] hover:decoration-[var(--color-text)]";

function WhatsAppIcon() {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden fill="none">
      <path
        d="M12 3a9 9 0 0 0-7.8 13.5L3 21l4.6-1.2A9 9 0 1 0 12 3z"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinejoin="round"
      />
      <path
        d="M9.2 8.4c-.4.4-.6 1-.4 1.7.6 2 2.3 3.8 4.4 4.5.7.2 1.3 0 1.7-.5l.5-.7-1.9-1-.7.7c-.9-.3-2-1.3-2.4-2.2l.7-.7-1-1.9z"
        fill="currentColor"
      />
    </svg>
  );
}

function TelegramIcon({ size = 20 }: { size?: number }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      aria-hidden
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinejoin="round"
      strokeLinecap="round"
    >
      <path d="M21 4 3 11l5.5 2L18 7l-7.5 7.5V19l3-3 4 3z" />
    </svg>
  );
}

function MailIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="20"
      height="20"
      aria-hidden
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinejoin="round"
      strokeLinecap="round"
    >
      <rect x="3" y="5" width="18" height="14" rx="2.5" />
      <path d="m4 7.5 8 6 8-6" />
    </svg>
  );
}

function XIcon({ size = 16 }: { size?: number }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      aria-hidden
      fill="currentColor"
    >
      <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
    </svg>
  );
}

function Row({
  icon,
  label,
  children,
}: {
  icon: React.ReactNode;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[14.5px]">
      <span className="text-[var(--color-gold-bright)]">{icon}</span>
      <span className="text-[var(--color-text-dim)]">{label}</span>
      {children}
    </li>
  );
}

function ComingSoon() {
  return (
    <span className="text-[var(--color-text-faint)] italic">Coming soon</span>
  );
}

function Circle({
  href,
  label,
  children,
}: {
  href: string | null;
  label: string;
  children: React.ReactNode;
}) {
  const base =
    "flex h-11 w-11 items-center justify-center rounded-full border transition-[border-color,color,transform] duration-200";
  if (!href) {
    // Not supplied yet: shown so the place is held, but inert and said so.
    return (
      <span
        role="img"
        aria-label={`${label}, coming soon`}
        title={`${label}: coming soon`}
        className={`${base} border-dashed border-[var(--color-line-strong)] text-[var(--color-text-faint)]`}
      >
        {children}
      </span>
    );
  }
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={label}
      title={label}
      className={`${base} border-[var(--color-line-strong)] text-[var(--color-text-dim)] hover:border-[var(--color-gold)] hover:text-[var(--color-gold-bright)] active:scale-[0.96]`}
    >
      {children}
    </a>
  );
}

export function ReachUs() {
  const { whatsapp, telegram, x } = SOCIAL_CONTACTS;
  const whatsappHref = whatsapp
    ? `https://wa.me/${whatsapp.replace(/\D/g, "")}`
    : null;
  const telegramHref = telegram
    ? `https://t.me/${telegram.replace(/^@/, "")}`
    : null;
  const xHref = x ? `https://x.com/${x.replace(/^@/, "")}` : null;

  return (
    <section aria-labelledby="reach-us">
      <h2
        id="reach-us"
        className="border-l-[3px] border-[var(--color-gold)] pl-3 text-[17px] font-bold tracking-[-0.01em]"
      >
        Reach us
      </h2>

      <ul className="mt-5 space-y-3.5">
        <Row icon={<WhatsAppIcon />} label="WhatsApp only:">
          {whatsappHref ? (
            <a
              href={whatsappHref}
              target="_blank"
              rel="noopener noreferrer"
              className={LINK}
            >
              Click here to chat
            </a>
          ) : (
            <ComingSoon />
          )}
        </Row>

        <Row icon={<TelegramIcon />} label="Telegram:">
          {telegramHref ? (
            <a
              href={telegramHref}
              target="_blank"
              rel="noopener noreferrer"
              className={LINK}
            >
              Message us on Telegram
            </a>
          ) : (
            <ComingSoon />
          )}
        </Row>

        <Row icon={<MailIcon />} label="Email:">
          {CONTACT_EMAIL ? (
            <a href={`mailto:${CONTACT_EMAIL}`} className={LINK}>
              {CONTACT_EMAIL}
            </a>
          ) : (
            <ComingSoon />
          )}
        </Row>
      </ul>

      <div className="mt-6 flex items-center gap-3">
        <Circle href={xHref} label="SARDASPORTS on X">
          <XIcon />
        </Circle>
        <Circle href={telegramHref} label="SARDASPORTS on Telegram">
          <TelegramIcon size={18} />
        </Circle>
      </div>
    </section>
  );
}
