import MarketingPage from "./marketing/page";
import AuthRedirect from "./auth-redirect";

/**
 * Root page — renders the full marketing landing page for SEO,
 * while a client component silently redirects authenticated users
 * to /dashboard. Crawlers and new visitors see the complete page.
 */
export { metadata } from "./marketing/page";

export default function Home() {
  return (
    <>
      <AuthRedirect />
      <MarketingPage />
    </>
  );
}
