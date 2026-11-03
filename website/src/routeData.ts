import { defineRouteMiddleware } from '@astrojs/starlight/route-data';

// Homepage tab: "LiteInjector Documentation". Other pages: "<Page> - LiteInjector".
export const onRequest = defineRouteMiddleware((context) => {
	const { id, entry, head } = context.locals.starlightRoute;
	const isHome = id === '' || id === 'index' || entry.id.startsWith('index');
	const title = isHome ? 'LiteInjector Documentation' : `${entry.data.title} - LiteInjector`;
	const tag = head.find((t) => t.tag === 'title');
	if (tag) tag.content = title;
});
