/**
 * Privacy policy.
 *
 * Written from an audit of what this site really does, so that every sentence is a
 * description, not an aspiration:
 *
 * - no accounts, no cookies, no advertising, no analytics (checked in the source);
 * - the only thing kept in a visitor's browser is the light/dark choice, in
 *   localStorage, which never leaves the browser;
 * - the only third-party request a visitor's browser makes is for country flag
 *   images (flagcdn.com); fonts are bundled at build time;
 * - the Contact form stores exactly the topic, name (optional), email and message,
 *   and nothing else, with no IP address or browser string.
 *
 * If any of that changes (analytics is the likely one), this page must be updated
 * first. It is a plain-language description of current practice and should be read
 * over by a qualified person before launch; it does not claim compliance with any
 * particular law because that is not something the code can establish.
 */

import Link from "next/link";
import {
  List,
  PageHeader,
  Section,
  Strong,
  linkClass,
} from "@/components/prose/Prose";
import { JsonLd } from "@/components/seo/JsonLd";
import { breadcrumbLd, pageMetadata } from "@/lib/seo";
import { CONTACT_EMAIL, OPERATOR_NAME } from "@/lib/site";

export const metadata = pageMetadata({
  title: "Privacy Policy",
  description:
    "What UniquePredict collects, what it does not, and what is stored in your browser: no accounts, no cookies, no advertising and no analytics.",
  path: "/privacy",
});

const LAST_UPDATED = "8 October 2026";

const CONTENTS = [
  ["summary", "The short version"],
  ["who", "Who is responsible"],
  ["collect", "What we collect"],
  ["browser", "What is stored in your browser"],
  ["third-parties", "Other services involved"],
  ["use", "How we use information"],
  ["keep", "How long we keep it"],
  ["rights", "Your choices and rights"],
  ["security", "Security"],
  ["age", "Age"],
  ["changes", "Changes to this policy"],
] as const;

export default function PrivacyPage() {
  return (
    <div className="mx-auto w-full max-w-[1200px] px-4 py-12 sm:px-6 lg:px-10">
      <JsonLd
        data={breadcrumbLd([
          { name: "Home", path: "/" },
          { name: "Privacy policy", path: "/privacy" },
        ])}
      />

      <PageHeader
        title="Privacy policy"
        intro={`This page explains what happens to your information when you use UniquePredict. Last updated ${LAST_UPDATED}.`}
      />

      <nav
        aria-label="On this page"
        className="mt-8 max-w-[72ch] rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-5"
      >
        <p className="text-[13px] font-semibold text-[var(--color-text)]">
          On this page
        </p>
        <ol className="mt-3 grid gap-x-8 gap-y-1.5 text-[14px] sm:grid-cols-2">
          {CONTENTS.map(([id, label]) => (
            <li key={id}>
              <a href={`#${id}`} className={linkClass}>
                {label}
              </a>
            </li>
          ))}
        </ol>
      </nav>

      <div className="mt-10 space-y-10">
        <Section id="summary" title="The short version">
          <List>
            <li>
              There are no accounts. You do not have to give us anything to use
              the site.
            </li>
            <li>
              The site sets <Strong>no cookies</Strong>, shows{" "}
              <Strong>no advertising</Strong> and runs{" "}
              <Strong>no analytics or tracking</Strong>.
            </li>
            <li>
              If you write to us through the contact form, we keep what you
              typed so we can read and answer it, and nothing else about you.
            </li>
            <li>We do not sell your information or share it for marketing.</li>
          </List>
        </Section>

        <Section id="who" title="Who is responsible">
          <p>
            {OPERATOR_NAME ? (
              <>
                UniquePredict is operated by <Strong>{OPERATOR_NAME}</Strong>,
                who is responsible for the information described on this
                page.{" "}
              </>
            ) : (
              <>
                The operator of UniquePredict is responsible for the information
                described on this page.{" "}
              </>
            )}
            To reach them, use the{" "}
            <Link href="/contact" className={linkClass}>
              contact page
            </Link>
            {CONTACT_EMAIL ? (
              <>
                {" "}
                or write to{" "}
                <a href={`mailto:${CONTACT_EMAIL}`} className={linkClass}>
                  {CONTACT_EMAIL}
                </a>
              </>
            ) : null}
            .
          </p>
        </Section>

        <Section id="collect" title="What we collect">
          <p>
            <Strong>Messages you send us.</Strong> The contact form asks for a
            topic, your email address, your message and, if you choose, your
            name. We store exactly those and nothing else. In particular we do
            not store your IP address or details of your browser with the
            message. To limit spam, the site counts recent messages in memory
            using a code derived from your connection with a one-way hash that
            changes every day. The code is held only in memory, is never written
            to the database or used for anything else, and is discarded an hour
            after your last message.
          </p>
          <p>
            <Strong>Technical logs.</Strong> Like any website, the servers that
            deliver this site keep standard technical logs (such as the time,
            the page requested, your IP address and your browser type) for
            security and to keep the site running. These are kept by the hosting
            provider under its own settings. We do not use them to identify or
            follow individual visitors.
          </p>
          <p>
            <Strong>What we do not collect.</Strong> We do not ask you to
            register, we do not collect payment details (the site sells
            nothing), and we do not build profiles of visitors.
          </p>
        </Section>

        <Section id="browser" title="What is stored in your browser">
          <p>
            The site remembers whether you chose the light or dark theme. That
            choice is kept in your browser&rsquo;s local storage under the name{" "}
            <code className="rounded bg-[var(--color-surface-raised)] px-1.5 py-0.5 text-[13px]">
              theme
            </code>
            , stays on your device and is never sent to us. Clearing your
            browser&rsquo;s site data removes it. The site sets no cookies.
          </p>
        </Section>

        <Section id="third-parties" title="Other services involved">
          <p>
            Country flags on the site are loaded directly by your browser from
            an image service, <Strong>flagcdn.com</Strong>. When your browser
            fetches a flag, that service can see your IP address and browser
            details, as with any image loaded from another site. It is the only
            third-party service your browser contacts while you read the site.
            The site&rsquo;s fonts are bundled with it and are not loaded from a
            third party.
          </p>
          <p>
            Some pages link to other websites, such as our data sources and
            gambling-support organisations. Those sites have their own privacy
            policies, and we are not responsible for them.
          </p>
        </Section>

        <Section id="use" title="How we use information">
          <p>
            We use what you send us only to read and answer your message, and to
            fix a problem you have reported, such as a wrong result. We use
            technical logs only to keep the site secure and working. We do not
            use any of it for advertising, we do not make decisions about you
            from it, and we do not sell it or share it with third parties for
            their own purposes.
          </p>
        </Section>

        <Section id="keep" title="How long we keep it">
          <p>
            A message is kept for as long as it is needed to deal with it and is
            deleted when it is no longer needed, or sooner if you ask. Server
            logs are kept for the period set by the hosting provider.
          </p>
        </Section>

        <Section id="rights" title="Your choices and rights">
          <p>
            You can ask us what we hold about you, ask us to correct it, or ask
            us to delete it. The simplest way is to use the{" "}
            <Link href="/contact" className={linkClass}>
              contact form
            </Link>{" "}
            and choose the topic &ldquo;A privacy request&rdquo;, giving the
            email address you wrote from so we can find your message.
          </p>
          <p>
            Depending on where you live, you may have further rights under local
            law, including the right to complain to your data protection
            authority. Nothing here limits those rights.
          </p>
        </Section>

        <Section id="security" title="Security">
          <p>
            Messages are stored in the site&rsquo;s database, which is not
            publicly accessible. No system is perfectly secure, so we keep what
            we store to the minimum described above.
          </p>
        </Section>

        <Section id="age" title="Age">
          <p>
            The site is intended for people aged 18 and over and is not aimed at
            children. We do not knowingly collect information from anyone under
            18; if you believe a child has written to us, tell us and we will
            delete the message.
          </p>
        </Section>

        <Section id="changes" title="Changes to this policy">
          <p>
            If we change what the site does with information (for example by
            adding analytics), this page will be updated first and the date at
            the top will change. The current version is always the one on this
            page.
          </p>
        </Section>
      </div>
    </div>
  );
}
