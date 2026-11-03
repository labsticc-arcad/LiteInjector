// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

// SITE_URL and SITE_BASE set the deployment location (e.g. https://<owner>.github.io and /LiteInjector).
// Both are empty by default so that the site works locally with `npm run dev` / `npm run preview`.
export default defineConfig({
	site: process.env.SITE_URL || undefined,
	base: process.env.SITE_BASE || undefined,
	integrations: [
		starlight({
			title: 'LiteInjector',
			routeMiddleware: './src/routeData.ts',
			description: 'Open source fault injection emulator for LiteX Systems on Chip.',
			favicon: '/favicon-32x32.png',
			customCss: ['./src/styles/custom.css'],
			social: [{ icon: 'github', label: 'GitHub', href: 'https://github.com/labsticc-arcad/LiteInjector' }],
			editLink: { baseUrl: 'https://github.com/labsticc-arcad/LiteInjector/edit/main/website/' },
			lastUpdated: true,
			sidebar: [
				{
					label: 'Start here',
					items: [
						{ label: 'Introduction', slug: 'start/introduction' },
						{ label: 'Installation', slug: 'start/installation' },
						{ label: 'Your first injection', slug: 'start/first-injection' },
					],
				},
				{
					label: 'Concepts',
					items: [
						{ label: 'Architecture', slug: 'concepts/architecture' },
						{ label: 'Trigger system', slug: 'concepts/trigger' },
						{ label: 'Fault injector', slug: 'concepts/injector' },
						{ label: 'Software controller', slug: 'concepts/software' },
						{ label: 'Debugging with LiteScope', slug: 'concepts/litescope' },
					],
				},
				{
					label: 'Tutorials',
					items: [
						{ label: 'Bypass a BIOS password', slug: 'tutorials/bios-password' },
						{ label: 'Bypass PMP from the instruction bus', slug: 'tutorials/pmp-software' },
						{ label: 'Fault the PMP hardware', slug: 'tutorials/pmp-hardware' },
						{ label: 'VerifyPIN on Linux', slug: 'tutorials/linux-verifypin' },
						{ label: 'Run an injection campaign', slug: 'tutorials/campaign' },
					],
				},
				{
					label: 'Reference',
					items: [
						{ label: 'Command line', slug: 'reference/cli' },
						{ label: 'Campaign files', slug: 'reference/campaign-file' },
						{ label: 'Python API', slug: 'reference/python-api' },
						{ label: 'Gateware', slug: 'reference/gateware' },
					],
				},
				{ label: 'Cite LiteInjector', slug: 'cite' },
			],
		}),
	],
});
