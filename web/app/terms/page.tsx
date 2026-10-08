/**
 * Terms of use.
 *
 * A plain-language statement of the terms on which the site is offered, written to
 * match what the site really does: it publishes predictions as information, sells
 * nothing, takes no accounts and links to no bookmakers. Like the privacy policy it
 * is a draft for a qualified person to read before launch. It deliberately names no
 * country, court or company, because none has been decided: the operator's name
 * appears when the site is configured with one (see `lib/site.ts`), and the
 * governing-law clause says only that the laws where the operator is based apply.
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
import { OPERATOR_NAME, SITE_NAME } from "@/lib/site";

export const metadata = pageMetadata({
  title: "Terms of Use",
  description: `The terms for using ${SITE_NAME}: predictions are information, not advice or a promise of winnings, and you must be 18 or over to bet.`,
  path: "/terms",
});

const LAST_UPDATED = "8 October 2026";

export default function TermsPage() {
  return (
    <div className="mx-auto w-full max-w-[1200px] px-4 py-12 sm:px-6 lg:px-10">
      <JsonLd
        data={breadcrumbLd([
          { name: "Home", path: "/" },
          { name: "Terms of use", path: "/terms" },
        ])}
      />

      <PageHeader
        title="Terms of use"
        intro={`These are the terms on which ${SITE_NAME} is offered. By using the site you agree to them. Last updated ${LAST_UPDATED}.`}
      />

      <div className="mt-10 space-y-10">
        <Section id="what" title="What this site is">
          <p>
            {SITE_NAME} publishes statistical predictions for football,
            basketball and tennis matches, and the record of how those
            predictions turned out.{" "}
            {OPERATOR_NAME ? (
              <>
                It is operated by <Strong>{OPERATOR_NAME}</Strong>.
              </>
            ) : null}{" "}
            It is free to read and needs no account.
          </p>
        </Section>

        <Section id="information" title="Information, not advice">
          <List>
            <li>
              Everything here is <Strong>information only</Strong>. It is not
              betting, financial or any other kind of advice, and it is not an
              offer or an invitation to bet.
            </li>
            <li>
              A prediction is a probability. One rated at 70% is expected to be
              wrong three times in ten. Nothing here is a guarantee, a
              &ldquo;sure win&rdquo; or a promise of any result, and past
              results do not promise future ones.
            </li>
            <li>
              The site does not take bets, does not link to bookmakers and is
              not paid by them. Prices shown are for context.
            </li>
          </List>
        </Section>

        <Section id="age" title="Age and responsible gambling">
          <p>
            You must be <Strong>18 or over</Strong> to use this site, or older
            if the law where you live sets a higher age for gambling. If you
            choose to bet, never stake money you cannot afford to lose. See our{" "}
            <Link href="/about#responsible-gambling" className={linkClass}>
              responsible gambling
            </Link>{" "}
            section for where to find help.
          </p>
        </Section>

        <Section id="accuracy" title="Accuracy and availability">
          <p>
            The predictions and results are produced automatically from data
            supplied by third parties, and that data can be late, incomplete or
            wrong. We try to correct mistakes and list the ones that changed
            published figures, but we do not promise that anything on the site
            is accurate, complete or up to date, or that the site will always be
            available. It is provided <Strong>as it is</Strong>, without
            warranty of any kind.
          </p>
        </Section>

        <Section id="liability" title="Our responsibility to you">
          <p>
            To the fullest extent the law allows, we are not liable for any loss
            or damage, including any loss from a bet or decision made using
            information on this site. Nothing in these terms limits a
            responsibility that cannot lawfully be limited.
          </p>
        </Section>

        <Section id="use" title="Using the site fairly">
          <List>
            <li>
              Read it, share links to it and quote it with attribution. The
              graded history can be downloaded from the track record page for
              your own use.
            </li>
            <li>
              Do not try to overload, disrupt or break into the site, and do not
              use automated means to copy it in bulk or at a rate that harms
              other visitors.
            </li>
            <li>
              Do not present the site&rsquo;s predictions as guaranteed, or as
              coming from someone else.
            </li>
          </List>
        </Section>

        <Section id="ownership" title="Content and data">
          <p>
            The predictions, ratings and the graded record are our own work. The
            underlying match data comes from third-party sources named on the{" "}
            <Link href="/about" className={linkClass}>
              About page
            </Link>
            , and remains theirs. Team, player and league names are used only to
            say which match is meant.
          </p>
        </Section>

        <Section id="privacy" title="Your information">
          <p>
            How we handle what little information the site receives is set out
            in the{" "}
            <Link href="/privacy" className={linkClass}>
              privacy policy
            </Link>
            .
          </p>
        </Section>

        <Section id="changes" title="Changes and governing law">
          <p>
            We may change these terms, and the date at the top shows when they
            last changed. Using the site after a change means you accept it.
            These terms are governed by the laws that apply where the operator
            is based.
          </p>
          <p>
            Questions about these terms can be sent through the{" "}
            <Link href="/contact" className={linkClass}>
              contact page
            </Link>
            .
          </p>
        </Section>
      </div>
    </div>
  );
}
