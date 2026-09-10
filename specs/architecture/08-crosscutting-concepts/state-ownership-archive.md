# State, Ownership, and Archive

Every durable state has one owner: portable skill state, package state, user
configuration, runtime state, and archive are distinct. Managed files are
identified by exact semantic ownership and digest. Retired assets are preserved
in a content-addressed archive; unrelated history and user-owned content remain
byte-for-byte unchanged.
