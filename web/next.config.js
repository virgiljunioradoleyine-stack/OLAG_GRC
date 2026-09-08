/** @type {import('next').NextConfig} */
module.exports = {
  reactStrictMode: true,
  // The /api/stations route validates a request against the published
  // candidate sites and the current station list. Those live in public/, which
  // is not traced into a serverless bundle by default, so the route would find
  // nothing to validate against and refuse every request.
  outputFileTracingIncludes: {
    "/api/stations": ["./public/data/candidates.geojson",
                      "./public/data/stations.json"],
  },
};
