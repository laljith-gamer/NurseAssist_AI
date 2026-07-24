import type { Metadata } from 'next'
import { IBM_Plex_Sans, Space_Grotesk } from 'next/font/google'
import './globals.css'

const bodyFont = IBM_Plex_Sans({
  subsets: ['latin'],
  variable: '--font-body',
  weight: ['400', '500', '600'],
})

const headingFont = Space_Grotesk({
  subsets: ['latin'],
  variable: '--font-heading',
  weight: ['500', '600', '700'],
})

export const metadata: Metadata = {
  title: 'Digital Clinical Nurse Assistant',
  description: 'AI-powered clinical nursing assistant for patient care',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className={`${bodyFont.variable} ${headingFont.variable}`}>
        <div className="ambient ambient-one" aria-hidden="true" />
        <div className="ambient ambient-two" aria-hidden="true" />
        <div className="min-h-screen flex flex-col relative z-10">
          {children}
        </div>
      </body>
    </html>
  )
}
