// Builds static/tailwind.css (2 Nov 2026: replaces the Tailwind play CDN, which needed 'unsafe-eval' in the CSP).
// After adding Tailwind classes to a template or a JS file, rebuild:
//   npx tailwindcss@3.4.17 -c tailwind.config.js -i static/tailwind.src.css -o static/tailwind.css --minify
// Commit the result: the app itself needs no Node.js.
module.exports = {
  content: ['./templates/**/*.html', './static/*.js', '!./static/avatars.js'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Plus Jakarta Sans"', '-apple-system', 'BlinkMacSystemFont', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      },
      colors: {
        brand: { yellow: '#FBBF24', orange: '#F97316', blue: '#2563EB', teal: '#0D9488', emerald: '#059669', slate: '#0F172A' },
      },
    },
  },
  plugins: [],
};
