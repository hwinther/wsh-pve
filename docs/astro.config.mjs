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
            { label: "SPARC lab recordings", slug: "guides/sparc-recordings" },
            { label: "Living museum", slug: "guides/living-museum" },
            { label: "Lab install targets", slug: "guides/lab-install" },
            { label: "3DFX / Mesa passthrough", slug: "guides/3dfx" },
            { label: "Guest operating systems", slug: "guides/operating-systems" },
            { label: "DOS", slug: "guides/dos" },
            { label: "ReactOS", slug: "guides/reactos" },
            { label: "Dial-up modem", slug: "guides/dialup" },
            { label: "Retro net", slug: "guides/retronet" },
            { label: "wisp (tiny test system)", slug: "guides/wisp" },
            { label: "Browser SPARC", slug: "guides/browser-sparc" },
            { label: "The emulation ladder", slug: "guides/emulation-ladder" },
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
