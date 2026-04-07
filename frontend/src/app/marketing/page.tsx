import type { Metadata } from "next";
import MarketingContent from "./marketing-content";

export const metadata: Metadata = {
  metadataBase: new URL("https://getintelliads.com"),
  title: "IntelliAds — Professional Ad Campaigns in Under 5 Minutes",
  description:
    "Create professionally designed Google & Meta ad campaigns in minutes, not hours. AI-powered keyword research, ad copy, image generation, and landing pages — all in one platform.",
  keywords:
    "AI ad campaigns, Google Ads automation, Meta Ads automation, AI campaign builder, PPC automation, AI ad copy, landing page generator, keyword research AI, ad image generator, IntelliAds",
  authors: [{ name: "IntelliAds" }],
  creator: "IntelliAds",
  publisher: "IntelliAds",
  robots: "index, follow",
  openGraph: {
    type: "website",
    locale: "en_US",
    url: "https://getintelliads.com",
    siteName: "IntelliAds",
    title: "IntelliAds — Professional Ad Campaigns in Under 5 Minutes",
    description:
      "Create professionally designed ad campaigns in minutes. AI handles keyword research, ad copy, images, and landing pages.",
    images: [
      {
        url: "/og-image.png",
        width: 1200,
        height: 630,
        alt: "IntelliAds Platform",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "IntelliAds — Professional Ad Campaigns in Under 5 Minutes",
    description:
      "Create professionally designed ad campaigns in minutes. AI handles keyword research, ad copy, images, and landing pages.",
    images: ["/og-image.png"],
  },
  alternates: {
    canonical: "https://getintelliads.com",
  },
};

export default function MarketingPage() {
  return <MarketingContent />;
}
