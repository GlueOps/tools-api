package version

// These variables are set at build time via -ldflags.
var (
	Version        = "UNKNOWN"
	CommitSHA      = "UNKNOWN"
	ShortSHA       = "UNKNOWN"
	BuildTimestamp = "UNKNOWN"
	GitRef         = "UNKNOWN"
)
