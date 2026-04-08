export const metadata = {
  title: "Privacy Policy — IntelliAds.ai",
  description:
    "Learn how IntelliAds collects, uses, and protects your data. Covers account info, OAuth integrations, and your privacy rights.",
  robots: "index, follow",
};

export default function PrivacyPage() {
  return (
    <div className="min-h-screen bg-white py-16 px-4">
      <div className="max-w-3xl mx-auto prose prose-slate">
        <h1>Privacy Policy</h1>
        <p className="text-sm text-gray-500">Last updated: April 5, 2026</p>

        <h2>1. Introduction</h2>
        <p>
          IntelliAds.ai (&quot;we&quot;, &quot;our&quot;, &quot;us&quot;) operates the IntelliAds.ai platform
          (the &quot;Service&quot;). This Privacy Policy explains how we collect, use, and protect
          your information when you use our Service.
        </p>

        <h2>2. Information We Collect</h2>
        <ul>
          <li><strong>Account Information:</strong> Name, email address, and business details you provide during registration.</li>
          <li><strong>Third-Party Integrations:</strong> When you connect Google Ads, Google Business Profile, or Meta Ads accounts, we receive OAuth tokens and account data necessary to manage your advertising campaigns.</li>
          <li><strong>Usage Data:</strong> Pages visited, features used, and interactions with the platform.</li>
        </ul>

        <h2>3. How We Use Your Information</h2>
        <ul>
          <li>To provide, maintain, and improve the Service.</li>
          <li>To manage your advertising campaigns across Google Ads, Meta Ads, and other platforms.</li>
          <li>To sync and display your business data (reviews, location info, ad performance).</li>
          <li>To communicate with you about your account or the Service.</li>
        </ul>

        <h2>4. Data Security</h2>
        <p>
          All OAuth tokens and sensitive credentials are encrypted at rest using industry-standard
          encryption (Fernet/AES-128-CBC). We use HTTPS for all data in transit.
        </p>

        <h2>5. Third-Party Services</h2>
        <p>
          We integrate with Google (Google Ads, Google Business Profile), Meta (Facebook/Instagram Ads),
          and other services. Your use of these integrations is also subject to their respective privacy policies.
        </p>

        <h2>6. Data Retention &amp; Deletion</h2>
        <p>
          You can disconnect any integration at any time from the Settings page, which removes stored
          tokens. You may request full account deletion by contacting us at the email below.
        </p>

        <h2>7. Your Rights</h2>
        <p>
          You have the right to access, update, or delete your personal data. You can manage
          connected integrations from your account settings or contact us for assistance.
        </p>

        <h2>8. Contact</h2>
        <p>
          For privacy-related questions, contact us at:{" "}
          <a href="mailto:contact@thekeybot.com">contact@thekeybot.com</a>
        </p>
      </div>
    </div>
  );
}
