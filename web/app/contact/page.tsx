/**
 * Contact.
 *
 * A form that works without any configuration, because it stores the message in
 * the database for the operator to read (see scripts/list_contact_messages.py), so
 * no email address has to be invented for the page to be useful. A public address
 * is shown only if one is configured (NEXT_PUBLIC_CONTACT_EMAIL).
 *
 * The page is honest about what it cannot promise: there is no automatic reply and
 * no response time, because neither is something the code can guarantee.
 */

import Link from "next/link";
import { ContactForm } from "@/components/contact/ContactForm";
import { Strong, linkClass } from "@/components/prose/Prose";
import { JsonLd } from "@/components/seo/JsonLd";
import { getContactTopics } from "@/lib/api";
import { breadcrumbLd, pageMetadata } from "@/lib/seo";
import { CONTACT_EMAIL, absoluteUrl } from "@/lib/site";

export const revalidate = 3600;

export const metadata = pageMetadata({
  title: "Contact Us",
  description:
    "Report a wrong pick or result, ask about our data, or get in touch about press and partnerships. Send a message through the form.",
  path: "/contact",
});

export default async function ContactPage() {
  const topics = await getContactTopics();

  return (
    <div className="mx-auto w-full max-w-[1200px] px-4 py-12 sm:px-6 lg:px-10">
      <JsonLd
        data={[
          {
            "@context": "https://schema.org",
            "@type": "ContactPage",
            name: "Contact UniquePredict",
            url: absoluteUrl("/contact"),
          },
          breadcrumbLd([
            { name: "Home", path: "/" },
            { name: "Contact", path: "/contact" },
          ]),
        ]}
      />

      <header className="max-w-[72ch]">
        <h1 className="text-[clamp(1.9rem,4.5vw,2.75rem)] leading-tight font-bold tracking-[-0.02em]">
          Contact us
        </h1>
        <p className="mt-4 text-[16px] leading-relaxed text-[var(--color-text-dim)]">
          Spotted a pick or a result that looks wrong, have a question about the
          data, or want to write about the site? Send a message and it will be
          read by the person who runs it.
        </p>
      </header>

      <div className="mt-10 grid gap-12 lg:grid-cols-[minmax(0,1fr)_340px]">
        <ContactForm topics={topics} />

        <aside className="space-y-8 text-[14.5px] leading-relaxed text-[var(--color-text-dim)]">
          <div>
            <h2 className="text-[16px] font-semibold text-[var(--color-text)]">
              Reporting a mistake
            </h2>
            <p className="mt-2">
              Name the match, say which number or result looks wrong, and say
              what you think it should be. A link to the match page is ideal.
              Errors in the record are corrected, and corrections are listed on
              the{" "}
              <Link href="/about#corrections" className={linkClass}>
                About page
              </Link>
              .
            </p>
          </div>

          <div>
            <h2 className="text-[16px] font-semibold text-[var(--color-text)]">
              What to expect
            </h2>
            <p className="mt-2">
              Messages are read by the site&rsquo;s operator. There is no
              automatic reply and no guaranteed response time, so include an
              email address you check.
            </p>
          </div>

          <div>
            <h2 className="text-[16px] font-semibold text-[var(--color-text)]">
              What we cannot help with
            </h2>
            <p className="mt-2">
              We cannot recommend a bet, give personal betting advice, or help
              with an account at a bookmaker. For how the predictions are made,
              see{" "}
              <Link href="/how-it-works" className={linkClass}>
                how it works
              </Link>
              ; for how they have performed, see the{" "}
              <Link href="/progress" className={linkClass}>
                track record
              </Link>
              .
            </p>
          </div>

          {CONTACT_EMAIL && (
            <div>
              <h2 className="text-[16px] font-semibold text-[var(--color-text)]">
                By email
              </h2>
              <p className="mt-2">
                <a href={`mailto:${CONTACT_EMAIL}`} className={linkClass}>
                  {CONTACT_EMAIL}
                </a>
              </p>
            </div>
          )}

          <p className="text-[13px] text-[var(--color-text-faint)]">
            <Strong>Privacy requests</Strong> (to see, correct or delete what we
            hold about you) can be sent through this form with the topic set
            accordingly.
          </p>
        </aside>
      </div>
    </div>
  );
}
