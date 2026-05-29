import { Inter, Crimson_Pro, JetBrains_Mono } from "next/font/google"

import "./globals.css"
import { ThemeProvider } from "@/components/theme-provider"
import { cn } from "@/lib/utils"
import { NavLinks } from "@/components/NavLinks"

const inter = Inter({ subsets: ["latin"], variable: "--font-sans" })
const crimsonPro = Crimson_Pro({ subsets: ["latin"], variable: "--font-display" })
const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
})

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={cn(
        "antialiased",
        inter.variable,
        crimsonPro.variable,
        jetbrainsMono.variable,
        "font-sans"
      )}
    >
      <body>
        <ThemeProvider>
          <nav className="sticky top-0 z-50 bg-background/80 backdrop-blur-lg">
            <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-6">
              {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
              <a href="/" className="flex items-center gap-0.5">
                <span className="font-display text-xl font-semibold tracking-tight">
                  Pixel
                </span>
                <span className="font-display text-xl font-semibold tracking-tight text-primary">
                  RAG
                </span>
              </a>
              <NavLinks />
            </div>
            {/* Gradient fade bottom border */}
            <div className="h-px bg-gradient-to-r from-transparent via-border/60 to-transparent" />
          </nav>
          <main>{children}</main>
        </ThemeProvider>
      </body>
    </html>
  )
}
