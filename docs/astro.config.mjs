// @ts-check
import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";

// https://astro.build/config
export default defineConfig({
  site: "https://debian.wshosting.no",
  integrations: [
    starlight({
      title: "WSH PVE",
      social: [
        {
          icon: "github",
          label: "GitHub",
          href: "https://github.com/hwinther/wsh-pve",
        },
      ],
      sidebar: [
        {
          label: "Guides",
          items: [
            // Each item here is one entry in the navigation menu.
            { label: "Setup Guide", slug: "guides/setup" },
            { label: "SPARC Guests", slug: "guides/sparc" },
            { label: "Guest operating systems", slug: "guides/operating-systems" },
          ],
        },
        {
          label: "Reference",
          items: [{ autogenerate: { directory: "reference" } }],
        },
      ],
    }),
  ],
});
