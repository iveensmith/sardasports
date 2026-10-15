/**
 * Privacy policy.
 *
 * Written from an audit of what this site really does, so that every sentence is a
 * description, not an aspiration:
 *
 * - accounts are optional. A member's record is the e-mail address, an optional name,
 *   a salted scrypt hash of the password, the date they confirmed they are 18 or over
 *   and the version of the Terms they accepted, and their premium status. Card details
 *   are never seen: payment happens on the payment provider's own page;
 * - one cookie, `sd_session`, only after signing in: an opaque random value, HttpOnly,
 *   SameSite=Lax, 30 days. No advertising, no analytics;
 * - the light/dark choice is in localStorage and never leaves the browser;
 * - the third-party requests a visitor's browser makes are for country flag images
 *   (flagcdn.com) and club crests (media.api-sports.io); fonts are bundled at build time;
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
    "What SARDASPORTS collects, what it does not, and what is stored in your browser: accounts are optional, one sign-in cookie, no advertising and no analytics.",
  path: "/privacy",
});

const LAST_UPDATED = "14 October 2026";

const CONTENTS = [
  ["summary", "The short version"],
  ["who", "Who is responsible"],
  ["collect", "What we collect"],
  ["accounts", "If you create an account"],
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
        intro={`This page explains what happens to your information when you use SARDASPORTS. Last updated ${LAST_UPDATED}.`}
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
              You do not have to give us anything to read the site. An account
              is optional, and you can delete yours yourself at any time.
            </li>
            <li>
              The site sets <Strong>one cookie, and only if you sign in</Strong>,
              to remember that you are signed in. It shows{" "}
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
                SARDASPORTS is operated by <Strong>{OPERATOR_NAME}</Strong>, who
                is responsible for the information described on this page.{" "}
              </>
            ) : (
              <>
                The operator of SARDASPORTS is responsible for the information
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
            <Strong>What we do not collect.</Strong> We never see or store your
            card number or bank details: if you buy premium, you pay on the
            payment provider&rsquo;s own page. We do not build profiles of
            visitors, and we do not use tracking or advertising technology.
          </p>
        </Section>

        <Section id="accounts" title="If you create an account">
          <p>An account is optional. If you create one we keep:</p>
          <List>
            <li>
              your <Strong>e-mail address</Strong> and, if you give one, a name;
            </li>
            <li>
              your <Strong>password</Strong>, but only as a salted one-way hash.
              We cannot read it, and neither can anyone who obtains the
              database;
            </li>
            <li>
              the date you confirmed you are <Strong>18 or over</Strong> and the
              version of the Terms you accepted;
            </li>
            <li>
              whether you have <Strong>premium</Strong> and until when, and a
              record that a payment was received (the amount, the date and the
              provider&rsquo;s reference, never card details);
            </li>
            <li>
              when you last signed in, and a short description of each browser
              you are signed in on, so you can recognise it.
            </li>
          </List>
          <p>
            <Strong>E-mail.</Strong> We send the messages an account needs
            (confirming your address, resetting a password, receipts and notices
            about your account). We send news about the site only if you tick
            the box for it, and you can untick it in your account.
            We keep a copy of messages we send so that a failed delivery can be
            retried. They are sent through a mail service, which handles them
            for us.
          </p>
          <p>
            <Strong>Editorial content.</Strong> If you are an administrator,
            what you publish (posts and picks) and a log of your changes are
            kept.
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
            browser&rsquo;s site data removes it.
          </p>
          <p>
            If you <Strong>sign in</Strong>, the site sets one cookie,{" "}
            <code className="rounded bg-[var(--color-surface-raised)] px-1.5 py-0.5 text-[13px]">
              sd_session
            </code>
            . It holds a random value that identifies your sign-in, cannot be
            read by scripts on the page, is sent only to this site, and lasts up
            to 30 days or until you sign out. It is strictly necessary for
            being signed in and is not used for anything else. If you never
            sign in, the site sets no cookie.
          </p>
        </Section>

        <Section id="third-parties" title="Other services involved">
          <p>
            Country flags are loaded directly by your browser from an image
            service, <Strong>flagcdn.com</Strong>, and club crests from the
            data provider&rsquo;s image server,{" "}
            <Strong>media.api-sports.io</Strong>. When your browser fetches one
            of these images, that service can see your IP address and browser
            details, as with any image loaded from another site. They are the
            only third-party services your browser contacts while you read the
            site. The site&rsquo;s fonts are bundled with it and are not loaded
            from a third party.
          </p>
          <p>
            If you buy premium, the payment is taken by a payment provider
            (Stripe or Paystack) on its own page, under its own privacy policy.
            They tell us that a payment succeeded; they do not give us your card
            details. Account e-mails are delivered through a mail service.
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
            account details only to run your account: signing you in,
            confirming your address, applying premium and sending you the
            messages described above. We use technical logs only to keep the
            site secure and working. We do not
            use any of it for advertising, we do not make decisions about you
            from it, and we do not sell it or share it with third parties for
            their own purposes.
          </p>
        </Section>

        <Section id="keep" title="How long we keep it">
          <p>
            A message is kept for as long as it is needed to deal with it and is
            deleted when it is no longer needed, or sooner if you ask. Your
            account is kept until you delete it. When you do, your account, your
            sign-ins and your premium access are deleted straight away; a record
            that a payment was received is kept for as long as accounting rules
            require, with no personal details attached to it beyond what the
            provider holds. Server logs are kept for the period set by the
            hosting provider.
          </p>
        </Section>

        <Section id="rights" title="Your choices and rights">
          <p>
            You can <Strong>delete your account yourself</Strong> from the
            account page, change your e-mail preferences there, and sign out of
            every browser. You can also ask us what we hold about you, ask us to
            correct it, or ask us to delete it. The simplest way is to use the{" "}
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
            Messages and accounts are stored in the site&rsquo;s database, which
            is not publicly accessible. Passwords are stored only as salted
            hashes, sign-in tokens only as hashes, and the site is served over
            HTTPS. No system is perfectly secure, so we keep what we store to the
            minimum described above.
          </p>
        </Section>

        <Section id="age" title="Age">
          <p>
            The site is intended for people aged 18 and over and is not aimed at
            children. Creating an account requires you to confirm that you are
            18 or over. We do not knowingly collect information from anyone
            under 18; if you believe a child has an account or has written to
            us, tell us and we will delete it.
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
