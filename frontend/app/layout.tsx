import type { Metadata } from "next";
import "./globals.css";
import Nav from "@/components/Nav";
import Footer from "@/components/Footer";

export const metadata: Metadata = {
  title: "RedBeacon",
  description: "小红书自动运营平台",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh" suppressHydrationWarning>
      <body className="min-h-screen antialiased" style={{ display: "flex", flexDirection: "column" }}>
        <Nav />
        <main className="max-w-6xl mx-auto px-6 py-8 w-full" style={{ flex: 1 }}>{children}</main>
        <Footer />
      </body>
    </html>
  );
}
