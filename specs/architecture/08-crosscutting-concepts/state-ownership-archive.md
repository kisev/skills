# State, Ownership, and Archive

Every durable state has one owner: portable skill state, package state, user
configuration, runtime state, and archive are distinct. Managed files are
identified by exact semantic ownership and digest. Portable cleanup ownership is
identified by an exact source marker and matching frontmatter/directory name.
Retired assets are preserved in a content-addressed archive; unrelated history
and user-owned content remain byte-for-byte unchanged. External cleanup changes
are journaled with exact before/after file images and restored on execution or
postcondition failure; an unexpected concurrent image on a planned path fails
recovery closed. Files created concurrently outside the preview inventory are not
covered by byte-for-byte rollback.
Global archives have one global owner, while each project archive is isolated by
the digest of its resolved project directory so one project's recovery cannot
remove another project's objects.
