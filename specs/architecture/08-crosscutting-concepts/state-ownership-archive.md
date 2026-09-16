# State, Ownership, and Archive

Every durable state has one owner: portable skill state, package state, user
configuration, runtime state, and archive are distinct. Managed files are
identified by exact semantic ownership and digest. The `skills` CLI owns portable
skill trees and locks; package reconciliation neither inspects nor mutates them.
Retired package assets are preserved in a content-addressed archive; unrelated
history and user-owned content remain byte-for-byte unchanged.
Global archives have one global owner, while each project archive is isolated by
the digest of its resolved project directory so one project's recovery cannot
remove another project's objects.
