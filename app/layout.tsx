import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Carte des habitats — Risque incendie",
  description:
    "Visualisez les habitats colorés en bleu, orange ou rouge selon leur proximité avec les zones à risque incendie.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="fr">
      <body>{children}</body>
    </html>
  );
}
