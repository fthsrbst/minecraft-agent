// @ts-check
import eslint from "@eslint/js";
import { defineConfig } from "eslint/config";
import tseslint from "typescript-eslint";

export default defineConfig(
  // skills/*.js are skill bodies (top-level await and return), run by the skill executor, not modules.
  { ignores: ["dist/", "node_modules/", "skills/"] },
  eslint.configs.recommended,
  tseslint.configs.strictTypeChecked,
  tseslint.configs.stylisticTypeChecked,
  {
    languageOptions: {
      parserOptions: {
        projectService: { allowDefaultProject: ["eslint.config.js"] },
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      // A floating promise in a bot loop is a silent stuck bot; make it an error everywhere.
      "@typescript-eslint/no-floating-promises": "error",
    },
  },
);
