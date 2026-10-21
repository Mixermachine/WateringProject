import { defineConfig } from "vite";

// The card is shipped as one self-contained ES module that Home Assistant loads
// straight from `/watering_project/watering-project-card.js`. Lit is bundled on
// purpose: a second module request would have to be cache-busted as well.
export default defineConfig({
  build: {
    outDir: "../custom_components/watering_project/www",
    emptyOutDir: true,
    target: "es2022",
    minify: true,
    sourcemap: false,
    lib: {
      entry: "src/watering-project-card.ts",
      formats: ["es"],
      fileName: () => "watering-project-card.js",
    },
    rollupOptions: {
      output: {
        inlineDynamicImports: true,
      },
    },
  },
  test: {
    environment: "jsdom",
    environmentOptions: { jsdom: { url: "http://localhost:3000" } },
    setupFiles: ["test/setup.ts"],
    include: ["test/**/*.test.ts"],
    restoreMocks: true,
  },
});
