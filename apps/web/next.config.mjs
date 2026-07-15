/** @type {import('next').NextConfig} */
const nextConfig = {
  typedRoutes: true,
  outputFileTracingRoot: new URL(".", import.meta.url).pathname,
};

export default nextConfig;
