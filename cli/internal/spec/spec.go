package spec

import (
	_ "embed"
	"encoding/json"
	"fmt"
	"strings"
)

//go:embed openapi.json
var raw []byte

type operation struct {
	Summary     string `json:"summary"`
	Description string `json:"description"`
}

type schema struct {
	Paths      map[string]map[string]operation `json:"paths"`
	Components struct {
		Schemas map[string]struct {
			Properties map[string]struct {
				Example     json.RawMessage `json:"example"`
				Description string          `json:"description"`
			} `json:"properties"`
		} `json:"schemas"`
	} `json:"components"`
}

var parsed schema

func init() {
	if err := json.Unmarshal(raw, &parsed); err != nil {
		panic(fmt.Sprintf("failed to parse embedded OpenAPI spec: %v", err))
	}
}

// Example returns the example value for a schema field, or "" if not found.
func Example(schemaName, fieldName string) string {
	s, ok := parsed.Components.Schemas[schemaName]
	if !ok {
		return ""
	}
	prop, ok := s.Properties[fieldName]
	if !ok {
		return ""
	}
	var val interface{}
	if err := json.Unmarshal(prop.Example, &val); err != nil {
		return ""
	}
	return fmt.Sprintf("%v", val)
}

// FlagDesc returns a flag description with the example from the OpenAPI spec appended.
func FlagDesc(description, schemaName, fieldName string) string {
	ex := Example(schemaName, fieldName)
	if ex == "" {
		return description
	}
	return fmt.Sprintf("%s (e.g. %s)", description, ex)
}

// Summary returns the summary for an API endpoint, or fallback if not found.
func Summary(path, method, fallback string) string {
	methods, ok := parsed.Paths[path]
	if !ok {
		return fallback
	}
	op, ok := methods[strings.ToLower(method)]
	if !ok {
		return fallback
	}
	if op.Summary == "" {
		return fallback
	}
	return op.Summary
}

// Description returns the description for an API endpoint, or fallback if not found.
func Description(path, method, fallback string) string {
	methods, ok := parsed.Paths[path]
	if !ok {
		return fallback
	}
	op, ok := methods[strings.ToLower(method)]
	if !ok {
		return fallback
	}
	if op.Description == "" {
		return fallback
	}
	return op.Description
}
