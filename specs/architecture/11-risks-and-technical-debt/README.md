# Risks and Technical Debt

The specification can detect drift but cannot prove undocumented human intent.
External host APIs may be unavailable or change within the declared compatibility
range. Live integrations remain bounded by hostless contracts and may require
manual evidence. A malformed or inaccessible local state file is reported as
incomplete rather than repaired implicitly.
