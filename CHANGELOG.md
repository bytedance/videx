# Changelog

All notable changes to this project will be documented in this file.

Including `Added`, `Changed`, `Fixed`, `Deprecated`, `Removed`, `Security`.

## [Unreleased]

### Added
- refactor videx-server codes, more decoupling with SQLBrain.
- Add a single-stack script to fetch metadata, mirror schema into VIDEX-MySQL, and import metadata into Videx-Server.

### Fixed
- fix ndv calculation bugs when ndv information is missing.

### Use
- Add an example metadata file based on TPC-H (scale-factor=1) for onboarding.
- provide a simple videx model implementation: `VidexModelExample` for onboarding.

## [0.1.0] - 2025-02-12
### Added
- VIDEX-MySQL plugin
- VIDEX-Server basic code

