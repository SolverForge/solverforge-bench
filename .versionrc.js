// Release configuration for commit-and-tag-version.
//
// pyproject.toml is the only version surface in this repository, so the tool
// owns it: the version line is read and written through an anchored updater
// rather than a plain-text swap, which would replace the whole file.
module.exports = {
  packageFiles: [
    {
      filename: "pyproject.toml",
      updater: {
        readVersion: (contents) => contents.match(/^version = "([^"]+)"/m)[1],
        writeVersion: (contents, version) =>
          contents.replace(/^version = "[^"]+"/m, `version = "${version}"`),
      },
    },
  ],
  bumpFiles: [
    {
      filename: "pyproject.toml",
      updater: {
        readVersion: (contents) => contents.match(/^version = "([^"]+)"/m)[1],
        writeVersion: (contents, version) =>
          contents.replace(/^version = "[^"]+"/m, `version = "${version}"`),
      },
    },
  ],
  tagPrefix: "v",
  releaseCommitMessageFormat: "chore(release): {{currentTag}}",
  commitUrlFormat:
    "https://github.com/SolverForge/solverforge-bench/commit/{{hash}}",
  compareUrlFormat:
    "https://github.com/SolverForge/solverforge-bench/compare/{{previousTag}}...{{currentTag}}",
  issueUrlFormat:
    "https://github.com/SolverForge/solverforge-bench/issues/{{id}}",
};
