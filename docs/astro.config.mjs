// @ts-check
import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";

// https://astro.build/config
export default defineConfig({
  integrations: [
    starlight({
      title: "WSH PVE",
      social: {
        github: "https://github.com/hwinther/wsh-pve",
      },
      sidebar: [
        {
          label: "Guides",
          items: [
            // Each item here is one entry in the navigation menu.
            { label: "Setup Guide", slug: "guides/setup" },
          ],
        },
        {
          label: "Reference",
          autogenerate: { directory: "reference" },
        },
      ],
    }),
  ],
});
