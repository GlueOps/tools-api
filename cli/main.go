package main

import (
	"os"

	"github.com/GlueOps/tools-api/cli/cmd"
)

func main() {
	if err := cmd.Execute(); err != nil {
		os.Exit(1)
	}
}
