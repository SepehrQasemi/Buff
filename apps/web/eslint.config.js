import js from "@eslint/js";
import globals from "globals";
import nextConfig from "eslint-config-next";

const config = [
  {
    ignores: [".next/**", "node_modules/**", "out/**"],
  },
  js.configs.recommended,
  ...nextConfig,
  {
    files: ["**/*.{js,jsx}"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
    rules: {
      "react/prop-types": "off",
      "react/react-in-jsx-scope": "off",
      "react-hooks/set-state-in-effect": "off",
    },
  },
  {
    files: ["scripts/**/*.mjs", "scripts/**/*.js", "**/*.mjs"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: {
        ...globals.node,
        ...globals.browser,
      },
    },
    rules: {
      "no-control-regex": "off",
    },
  },
];

export default config;
