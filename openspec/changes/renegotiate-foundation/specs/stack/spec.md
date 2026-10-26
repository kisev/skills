# Spec Delta

## Purpose

Technology boundaries of the project's components: which stack each class of
software uses, so new components have an unambiguous default.

## ADDED Requirements

### Requirement: Runtimes and applications are Python

Runtime logic and standalone applications SHALL be implemented in Python
with declared dependencies (uv-installable), including the `agentomatic`
rewrite and the `taskmatic` and `memomatic` ports.

#### Scenario: New runtime tool

- **WHEN** a new runtime tool or application is created
- **THEN** it is a Python application with declared dependencies

### Requirement: Scripts inside skill archives are stdlib-only

Scripts shipped inside portable skill archives MUST be compatible with
Python 3.12+ and use only the standard library, so installed archives never
require package installation.

#### Scenario: Archive script runs anywhere

- **WHEN** a script inside an installed skill archive runs
- **THEN** it executes using only the Python standard library
