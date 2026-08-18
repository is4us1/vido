import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // הדאטה נטענת מקובץ JSON בזמן build/בקשה — אין צורך בשרת דאטהבייס.
  experimental: { typedRoutes: true },
};

export default nextConfig;
