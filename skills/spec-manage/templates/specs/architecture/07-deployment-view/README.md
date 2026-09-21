# 07 Deployment View

## Purpose

Map target-state software units to runtime environments and infrastructure boundaries.

## Included

- Deployment units, runtime nodes and environments, network exposure, communication paths, storage placement, scaling and failure domains.
- Runtime trust boundaries and where secrets are stored, mounted, or injected, with direct links to relevant `REQ-*` entries.

## Excluded

- Provider setup instructions, release sequencing, environment runbooks, identity and authorization policy, or repeated quality thresholds.

## Decomposition Rules

Keep the deployment model in this `README.md`; do not create child files. Describe multiple environments together when their topology is materially the same.

## Expected Structure

Describe runtime nodes, deployed artifacts, network ingress and egress, stores, trust and failure boundaries, secret placement, and material CI/CD runtime boundaries. Use a Deployment diagram only when useful.

## Content Template

Replace this guidance with the target runtime topology, artifact-to-node mapping, network exposure, data and secret placement, trust and failure boundaries, and direct requirement links.
