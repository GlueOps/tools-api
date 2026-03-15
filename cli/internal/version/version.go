package version

// Set via ldflags at build time.
var (
	Version        = "dev"
	CommitSHA      = "unknown"
	ShortSHA       = "unknown"
	BuildTimestamp = "unknown"
	GitRef         = "unknown"
)
