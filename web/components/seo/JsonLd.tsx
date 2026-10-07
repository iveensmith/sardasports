/**
 * Emits one or more JSON-LD blocks.
 *
 * `<` is escaped so a string inside the data can never close the script tag early.
 * The data is built server-side from content the page also shows; nothing here
 * comes from a visitor.
 */

export function JsonLd({ data }: { data: object | object[] }) {
  const nodes = Array.isArray(data) ? data : [data];
  return (
    <>
      {nodes.map((node, index) => (
        <script
          key={index}
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: JSON.stringify(node).replace(/</g, "\\u003c"),
          }}
        />
      ))}
    </>
  );
}
