import { render } from "@testing-library/react";

import { MarkdownView } from "./Markdown";

// TCMS-138 (NFR-SEC-06): Markdown from users never runs script or carries script URLs.
const PAYLOADS = [
  "<script>window.__xss = 1</script>",
  '<img src="x" onerror="window.__xss = 1">',
  '<svg onload="window.__xss = 1"></svg>',
  '<iframe src="javascript:window.__xss = 1"></iframe>',
  "[click](javascript:window.__xss=1)",
  "[click](JaVaScRiPt:window.__xss=1)",
  "[click](vbscript:msgbox(1))",
  "[click](data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==)",
  "![x](javascript:window.__xss=1)",
  '<a href="javascript:window.__xss=1">raw link</a>',
  "<div style=\"background:url('javascript:window.__xss=1')\">styled</div>",
];

describe("MarkdownView (TCMS-138)", () => {
  it.each(PAYLOADS)("neutralises %s", (payload) => {
    const { container } = render(<MarkdownView text={`Before\n\n${payload}\n\nAfter`} />);
    expect(container.querySelector("script, iframe, svg, object, embed, style")).toBeNull();
    for (const el of container.querySelectorAll("*")) {
      for (const attr of el.attributes) {
        expect(attr.name, `${el.tagName} ${attr.name}`).not.toMatch(/^on/i);
        expect(attr.value, `${el.tagName} ${attr.name}`).not.toMatch(/^\s*(javascript|vbscript|data):/i);
      }
      expect(el.getAttribute("style")).toBeNull();
    }
    expect((window as unknown as { __xss?: number }).__xss).toBeUndefined();
    expect(container).toHaveTextContent("Before");
    expect(container).toHaveTextContent("After");
  });

  it("keeps ordinary links, opening them in a new tab without referrer", () => {
    const { container } = render(
      <MarkdownView text="See [the ticket](https://jira.example.com/browse/PAY-1)" />,
    );
    const a = container.querySelector("a");
    expect(a).toHaveAttribute("href", "https://jira.example.com/browse/PAY-1");
    expect(a).toHaveAttribute("target", "_blank");
    expect(a).toHaveAttribute("rel", "noreferrer noopener");
  });
});
