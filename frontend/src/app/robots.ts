import { MetadataRoute } from 'next'

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: '*',
        allow: '/',
        disallow: ['/api/', '/dashboard/', '/settings/', '/onboarding/', '/ads/', '/audit/', '/experiments/', '/optimizations/', '/strategist/', '/calls/', '/gbp/', '/lsa/', '/creative/', '/intel/', '/operator/', '/assets/', '/reports/', '/v2/', '/tenant/', '/tenant-select/', '/get-customers/', '/growth/'],
      },
      {
        userAgent: 'GPTBot',
        allow: ['/', '/marketing', '/pricing', '/lp/'],
      },
      {
        userAgent: 'Google-Extended',
        allow: ['/', '/marketing', '/pricing', '/lp/'],
      },
      {
        userAgent: 'ClaudeBot',
        allow: ['/', '/marketing', '/pricing', '/lp/'],
      },
      {
        userAgent: 'Applebot-Extended',
        allow: ['/', '/marketing', '/pricing', '/lp/'],
      },
    ],
    sitemap: 'https://getintelliads.com/sitemap.xml',
  }
}
