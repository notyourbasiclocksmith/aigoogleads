export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="marketing-page" style={{ scrollBehavior: "smooth" }}>
      {children}
    </div>
  );
}
