export default {
  parserPreset: {
    parserOpts: {
      headerCorrespondence: ["type", "scope", "subject"],
      headerPattern: /^([^():\s]+)(?:\(([^)\r\n]+)\))?!?: (\S(?:.*\S)?)$/,
    },
  },
  rules: {
    "header-trim": [2, "always"],
    "subject-empty": [2, "never"],
    "type-empty": [2, "never"],
  },
};
