import { notFound } from "next/navigation";
import { Metadata } from "next";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface PageProps {
  params: Promise<{ slug: string }>;
}

async function fetchLandingPageHtml(slug: string): Promise<string | null> {
  try {
    const res = await fetch(`${API_URL}/lp/${slug}`, {
      cache: "no-store",
    });

    if (!res.ok) return null;

    return await res.text();
  } catch {
    return null;
  }
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params;

  // Attempt to extract a title from the HTML <title> tag
  const html = await fetchLandingPageHtml(slug);
  let title = slug.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

  if (html) {
    const match = html.match(/<title>(.*?)<\/title>/i);
    if (match?.[1]) {
      title = match[1];
    }
  }

  return {
    title,
    robots: { index: true, follow: true },
  };
}

export default async function LandingPage({ params }: PageProps) {
  const { slug } = await params;
  const html = await fetchLandingPageHtml(slug);

  if (!html) {
    notFound();
  }

  return (
    <div
      style={{ minHeight: "100vh" }}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
